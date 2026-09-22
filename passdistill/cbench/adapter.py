"""cBench boundary operations for the unchanged shared search scheduler."""
from __future__ import annotations
import json
from pathlib import Path
import re
import shutil

from passdistill.agents.feedback import grouped_remark_feedback, parse_optimization_remarks
from passdistill.agents.source_oracle import compact_teacher_history
from passdistill.types import BuildArtifacts, CommandResult, CorrectnessResult, EvaluationResult, Kernel
from passdistill.util import read_json, write_json
from . import native
from .context import readonly_context, replacement_function, split_hotspot


class CBenchBackend:
    """Add suite context only to Recovery; Distiller and backend behavior stay intact."""
    def __init__(self, backend, repo_root):
        self.backend = backend
        self.repo_root = repo_root

    def complete_json(self, system, user, *, schema_hint, out_dir):
        if schema_hint.startswith('recovery_planner'):
            system = (self.repo_root / 'prompt/cbench/Recovery Context.md').read_text() + '\n\n' + system
        return self.backend.complete_json(system, user, schema_hint=schema_hint, out_dir=out_dir)


class CBenchAdapter:
    def progress_update(self, stage, entry):
        if getattr(self, 'progress', None):
            self.progress.update(stage, entry)

    def __init__(self, config, program, hotspot):
        self.config, self.program, self.hotspot = config, program, hotspot
        self.source_root = Path(program['source_dir']).resolve()
        self.source = (config.repo_root / hotspot['path']).resolve()
        self.relative_source = self.source.relative_to(self.source_root)
        self.prefix, self.function, self.suffix = split_hotspot(self.source, hotspot)
        self.kernel = Kernel(program['program'], self.source, self.source, self.source_root,
                             target_function=hotspot['function'])

    def source_text(self, path):
        text = path.read_text()
        if not text.startswith(self.prefix) or not text.endswith(self.suffix):
            raise ValueError('Teacher changed source outside the fixed hotspot')
        end = len(text) - len(self.suffix) if self.suffix else len(text)
        return text[len(self.prefix):end]

    def apply_teacher_patch(self, original, patch, output):
        split_hotspot(original, self.hotspot)
        replacement = replacement_function(patch, self.function)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.prefix + replacement + self.suffix)

    def propose_teachers(self, backend, **kwargs):
        system = (self.config.repo_root / 'prompt/cbench/Source Oracle.md').read_text()
        # Input remarks have already been selected by TU + file + function below.
        # Do not inherit PolyBench's main blacklist or file-agnostic line matching.
        events = parse_optimization_remarks(kwargs['baseline_remarks'])[:40]
        context = readonly_context(self.source, self.source_root)
        metadata = dict(program=self.program['program'], file=str(self.relative_source),
                        function=self.hotspot['function'], start_line=self.hotspot['start_line'],
                        end_line=self.hotspot['end_line'], dataset_id='1',
                        native_repeat=self.program['native_repeat'],
                        compile_flags=[u['flags'] for u in self.program['tus']
                                       if u['source'] == str(self.relative_source)],
                        baseline_median_seconds=kwargs['baseline_runtime'])
        user = (f"Teacher round: {kwargs['round_index']}\nRequested directions: {kwargs['max_candidates']}\n"
                + 'Fixed target and build context:\n' + json.dumps(metadata, indent=2)
                + '\n\nEditable function (return its full replacement):\n```c\n' + self.function + '\n```'
                + '\n\nRead-only context (function bodies elided where syntactically identifiable):\n' + context
                + '\n\nRelevant compiler feedback:\n' + str(grouped_remark_feedback(events))
                + '\n\nPrevious Teacher feedback:\n' + json.dumps(compact_teacher_history(kwargs['history']), indent=2))
        write_json(kwargs['out_dir'] / 'context.json', dict(target=metadata, characters=len(user),
                   context_policy='fixed function + TU declarations + local headers; no callee expansion'))
        data = backend.complete_json(system, user, schema_hint='source_oracle.v1', out_dir=kwargs['out_dir'])
        return (data if isinstance(data, list) else data.get('directions', []))[:kwargs['max_candidates']]

    def _hotspot_remarks(self, out):
        selected = []
        for unit in self.program['tus']:
            if unit['source'] != str(self.relative_source):
                continue
            text = (out / 'build' / (unit['id'] + '.opt.yaml')).read_text()
            for block in re.split(r'(?=^---\s+!)', text, flags=re.M):
                events = parse_optimization_remarks(block)
                if not events:
                    continue
                event = events[0]
                same_file = event.file and (Path(event.file).name == self.source.name)
                same_function = event.function == self.hotspot['function']
                inline_location = (event.line is not None and
                                   self.hotspot['start_line'] <= event.line <= self.hotspot['end_line'])
                if (same_file and (same_function or inline_location)) or (not event.file and same_function):
                    selected.append(block)
        path = out / 'remarks/o3.opt.yaml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(selected))
        return path

    def _evaluate(self, out, candidate_id, *, manifest=None, pipeline=None, options=(),
                  source_dir=None, baseline_dump=None, baseline_runtime=None):
        result = EvaluationResult(candidate_id=candidate_id, compile_ok=False)
        try:
            binary = native.build(self.program, self.config.toolchain.llvm_bin, out / 'build',
                                  manifest=manifest, pipeline=pipeline, opt_options=options,
                                  source_dir=source_dir)
            result.compile_ok = True
            result.artifacts = BuildArtifacts(binary=binary, remarks=self._hotspot_remarks(out))
            reference = read_json(baseline_dump) if baseline_dump else None
            measured = native.measure(self.program, binary, out / 'measurement',
                         cpu=self.config.cpu, numa_node=self.config.numa_node, reference=reference,
                         timeout=self.config.command_timeout_sec)
            result.timing = measured['timing']
            result.correctness = CorrectnessResult(ok=measured['correctness_ok'],
                     message='Exact functional output hashes checked in pre-run and all three timed runs')
            result.command_log = [{'phase': 'run', 'result': CommandResult(
                argv=r['argv'], returncode=r['returncode'], elapsed_sec=r['elapsed_sec'],
                timed_out=r['timed_out'])} for r in measured['runs']]
            oracle = out / 'reference.json'
            write_json(oracle, measured['reference_md5'])
            result.artifacts.dump_stderr = oracle  # Common scheduler transports an opaque reference path.
            if result.timing.median and baseline_runtime:
                result.speedup_vs_baseline = baseline_runtime / result.timing.median
            if not result.timing.median:
                result.error = 'Invalid execution, incomplete timing, or functional output mismatch'
        except Exception as exc:
            result.error = str(exc)
        write_json(out / 'evaluation.json', result)
        runtime = result.timing.median if result.timing else None
        def speedup(attribute):
            base = getattr(self, attribute, None)
            return f'{base / runtime:.4f}x' if base and runtime else 'n/a'
        if not getattr(self, 'progress', None):
            print(f"[{self.program['program']}] {candidate_id}: "
                  f"median={runtime} current_vs_search={speedup('search_baseline_runtime')} "
                  f"current_vs_clang={speedup('clang_baseline_runtime')} error={result.error or 'none'}", flush=True)
        return result

    def evaluate_source(self, config, kernel, source, out, candidate_id, *, baseline_dump=None, baseline_runtime=None):
        # Each Teacher starts from the original project, never from another Teacher.
        self.source_text(source)
        project = out / 'project'
        shutil.copytree(self.source_root, project)
        shutil.copy2(source, project / self.relative_source)
        return self._evaluate(out, candidate_id, source_dir=project,
                              baseline_dump=baseline_dump, baseline_runtime=baseline_runtime)

    def evaluate_pipeline_candidate(self, config, kernel, frontend_ir, pipeline, out, candidate_id,
                                    *, baseline_dump, baseline_runtime, extra_options=None):
        return self._evaluate(out, candidate_id, manifest=frontend_ir, pipeline=pipeline,
                    options=extra_options or (), baseline_dump=baseline_dump, baseline_runtime=baseline_runtime)
