"""Separate cBench entry point; PolyBench configuration/entry points stay unchanged."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path

from passdistill.agents.base import MockBackend, make_backend
from passdistill.compiler import expanded_o3_pipeline
from passdistill.config import ExperimentConfig, Toolchain
from passdistill.search.teacher_search import run_teacher_search
from passdistill.util import read_json, write_json
from .adapter import CBenchAdapter, CBenchBackend
from . import native
from .control import configure, checkpoint, state
from .dmxapi import DMXBackend
from .progress import Progress


class SmokeBackend(MockBackend):
    """Offline proposals; every build, correctness check and timing is real."""
    def complete_json(self, system, user, *, schema_hint, out_dir):
        result = super().complete_json(system, user, schema_hint=schema_hint, out_dir=out_dir)
        if schema_hint.startswith('source_oracle'):
            # A byte-local source change exercises replacement without alleging optimization.
            result['directions'][0]['source_patch'] = result['directions'][0]['source_patch'].replace(
                '{', '{ /* offline smoke: preserve semantics */', 1)
        if schema_hint.startswith('recovery_planner'):
            result = {'candidates': [{'candidate_id': 'C1', 'parent_id': 'SEARCH_BASELINE',
                      'hypothesis': 'offline control: rebuild original IR with the baseline pipeline',
                      'edits': [], 'opt_options': []}]}
        write_json(out_dir / 'response.json', result)
        write_json(out_dir / 'parsed_response.json', result)
        write_json(out_dir / 'raw_response.txt', result)
        return result


def load_program(root, name, locations_path, builds_path):
    locations = read_json(locations_path)['programs']
    hotspot = next((p for p in locations if p['program'] == name), None)
    if not hotspot or hotspot['status'] != 'ready':
        raise ValueError(f'{name}: no ready sampled hotspot')
    program = next(p for p in read_json(builds_path)['programs'] if p['program'] == name)
    program['source_dir'] = str((root / program['source_dir']).resolve())
    src = Path(program['source_dir'])
    lines = (src / '_ccc_info_datasets').read_text().splitlines()
    protocols = [(lines[i+2], int(lines[i+3])) for i, line in enumerate(lines)
                 if line == '=====' and lines[i+1] == '1']
    if protocols != [(program['command'], program['native_repeat'])]:
        raise ValueError('dataset 1 command/repeat disagrees with native definition')
    for path in program['inputs']:
        if not (src / path).is_file():
            raise ValueError(f'missing dataset input: {path}')
    return program, hotspot


def identity(config, program, hotspot, settings):
    return dict(schema='cbench.search.v1', program=program, hotspot=hotspot,
                settings=settings,
                policy=dict(dataset_id='1', runs=3, statistic='median', cpu=3, numa_node=0,
                            correctness='pre-run and every timed run; strict', native_repeat=program['native_repeat']))


def check_identity(path, current, resume):
    if path.exists():
        if not resume:
            raise ValueError('run already exists; choose a new output directory or explicit --resume')
        previous = read_json(path)
        # Old runs may retain audit hashes. They are no longer validation gates.
        for key in ('source_sha256', 'catalog_sha256', 'prompts', 'implementation', 'toolchain'):
            previous.pop(key, None)
        for key in ('program', 'hotspot'):
            if isinstance(previous.get(key), dict):
                previous[key] = {k: v for k, v in previous[key].items() if not k.endswith('_sha256')}
        if isinstance(previous.get('program', {}).get('inputs'), dict):
            previous['program']['inputs'] = list(previous['program']['inputs'])
        if previous != current:
            raise ValueError('resume identity mismatch: program configuration, hotspot location or measurement/search settings changed')
    elif resume and path.parent.exists() and any(path.parent.iterdir()):
        raise ValueError('cannot resume a directory without a matching identity')
    else:
        write_json(path, current)


def baseline(adapter, out):
    config = adapter.config
    manifest = native.frontend(adapter.program, config.toolchain.llvm_bin, out / 'frontend')
    expanded = expanded_o3_pipeline(config)
    if not expanded.ok:
        raise RuntimeError(expanded.stderr)
    pipeline_path = out / 'pipeline.txt'
    pipeline_path.write_text(expanded.stdout.strip() + '\n')
    search = adapter._evaluate(out / 'search', 'SEARCH_BASELINE', manifest=manifest,
                                pipeline=expanded.stdout.strip())
    if not search.timing or search.timing.median is None:
        raise RuntimeError('search baseline blocked: ' + search.error)
    clang = adapter._evaluate(out / 'clang', 'CLANG_BASELINE', baseline_dump=search.artifacts.dump_stderr,
                               baseline_runtime=search.timing.median)
    if not clang.timing or clang.timing.median is None:
        raise RuntimeError('clang baseline blocked: ' + clang.error)
    summary = dict(baseline=clang, search_baseline=search, frontend_ir=manifest,
                   expanded_pipeline=pipeline_path)
    write_json(out / 'baseline_summary.json', summary)
    return summary


def main(argv=None):
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=root / 'configs/cbench.json')
    parser.add_argument('--program', nargs='+', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--smoke', action='store_true', help='one offline Teacher and one Recovery; real execution')
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--control-dir', type=Path)
    args = parser.parse_args(argv)
    configure(args.control_dir)
    settings = read_json(args.config)
    if (settings['cpu'], settings['numa_node'], settings['runs'], settings['dataset_id'], settings['statistic']) != (3, 0, 3, '1', 'median'):
        raise ValueError('this cBench protocol requires CPU 3, NUMA 0, dataset 1, three-run median')
    output = (args.output or root / 'artifacts/runs' / ('cbench-' + datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve()
    config = ExperimentConfig(repo_root=root, artifacts_root=output, dataset='1', fast_math=False,
             cpu=3, numa_node=0, runs=3, warmups=0, resume=args.resume,
             max_teacher_rounds=1 if args.smoke else settings['max_teacher_rounds'],
             max_teachers=1 if args.smoke else settings['max_teachers'],
             max_recovery_rounds=1 if args.smoke else settings['max_recovery_rounds'],
             max_pass_candidates=1 if args.smoke else settings['max_pass_candidates'],
             uniform_fixed_recovery_budget=settings['uniform_fixed_recovery_budget'],
             command_timeout_sec=settings['command_timeout_sec'],
             toolchain=Toolchain(Path(settings['llvm_bin'])))
    selected_backend = (SmokeBackend() if args.smoke else DMXBackend(settings['model'])
                        if settings['llm_backend'] == 'dmxapi' else
                        make_backend(settings['llm_backend'], settings.get('model')))
    backend = CBenchBackend(selected_backend, root)
    summary_path = output / 'summary.json'
    final = read_json(summary_path) if args.resume and summary_path.exists() else {}
    for index, name in enumerate(args.program, 1):
        checkpoint('program ' + name)
        print(f'[{name}] starting: dataset 1, native repeats, CPU 3 / NUMA 0, median of 3', flush=True)
        program, hotspot = load_program(root, name, root / settings['hotspots'], root / settings['builds'])
        adapter = CBenchAdapter(config, program, hotspot)
        out = output / name
        current = identity(config, program, hotspot, {**settings, 'smoke': args.smoke,
                           'baseline_only': args.baseline_only})
        check_identity(out / 'identity.json', current, args.resume)
        summary_file = out / 'baseline/baseline_summary.json'
        try:
            summary = read_json(summary_file) if args.resume and summary_file.exists() else baseline(adapter, out / 'baseline')
            def median(result):
                return result['timing']['median'] if isinstance(result, dict) else result.timing.median
            adapter.search_baseline_runtime = median(summary['search_baseline'])
            adapter.clang_baseline_runtime = median(summary['baseline'])
            adapter.progress = Progress(out / 'search', name, index, len(args.program),
                adapter.search_baseline_runtime, adapter.clang_baseline_runtime,
                config.max_teachers, config.max_pass_candidates)
            adapter.progress.emit(status='baseline_ready')
            if args.baseline_only:
                final[name] = {'status': 'baseline_ready', 'baseline': summary}
            else:
                search = run_teacher_search(config, backend, adapter.kernel, baseline_summary=summary,
                                            out_dir=out / 'search', adapter=adapter)
                final[name] = {'status': 'completed', 'search': search}
                adapter.progress.emit(status='completed')
                if args.smoke and (search['valid_teacher_count'] != 1 or search['measured_candidates'] != 1):
                    raise RuntimeError('smoke did not complete a valid Teacher and measured Recovery')
        except Exception as exc:
            final[name] = {'status': 'blocked', 'error': str(exc)}
            print(f'[{name}] blocked: {exc}', flush=True)
        write_json(summary_path, final)
    print(f'Results: {output / "summary.json"}', flush=True)
    state('completed' if all(p['status'] != 'blocked' for p in final.values()) else 'failed')
    return 1 if any(p['status'] == 'blocked' for p in final.values()) else 0
