from __future__ import annotations

import statistics
from pathlib import Path

from .compiler import (
    compile_c,
    compile_ir_to_object,
    compile_polybench_object,
    emit_frontend_ir,
    link_objects,
    opt_pipeline,
    pinned_prefix,
    preflight_pipeline,
)
from .config import ExperimentConfig
from .correctness import compare_files
from .types import BuildArtifacts, EvaluationResult, Kernel, TimingResult
from .util import ensure_dir, run_command, save_command_result


def run_binary(
    config: ExperimentConfig,
    binary: Path,
    *,
    warmups: int | None = None,
    runs: int | None = None,
    log_dir: Path | None = None,
) -> tuple[TimingResult, list[dict]]:
    warmup_count = config.warmups if warmups is None else warmups
    measured_count = config.runs if runs is None else runs
    timings = TimingResult()
    command_log: list[dict] = []
    argv = [*pinned_prefix(config), str(binary)]
    for index in range(warmup_count + measured_count):
        result = run_command(argv, config.repo_root)
        if log_dir is not None:
            save_command_result(log_dir / f"run_{index}.json", result)
        command_log.append({"phase": "run", "index": index, "result": result})
        if not result.ok:
            continue
        try:
            value = float(result.stdout.strip().split()[-1])
        except (IndexError, ValueError):
            continue
        if index < warmup_count:
            timings.warmups.append(value)
        else:
            timings.measured.append(value)
    if timings.measured:
        timings.median = statistics.median(timings.measured)
    return timings, command_log


def dump_output(config: ExperimentConfig, kernel: Kernel, source: Path, out_dir: Path, stem: str) -> tuple[Path, Path, list[dict], bool, str]:
    binary = out_dir / f"{stem}_dump"
    compile_result = compile_c(config, kernel, source, binary, dump_arrays=True)
    logs = [{"phase": "compile_dump", "result": compile_result}]
    save_command_result(out_dir / f"{stem}_compile_dump.json", compile_result)
    if not compile_result.ok:
        return out_dir / f"{stem}.stdout", out_dir / f"{stem}.stderr", logs, False, compile_result.stderr
    run_result = run_command([str(binary)], config.repo_root)
    stdout = out_dir / f"{stem}.stdout"
    stderr = out_dir / f"{stem}.stderr"
    stdout.write_text(run_result.stdout)
    stderr.write_text(run_result.stderr)
    run_result.stdout_path = stdout
    run_result.stderr_path = stderr
    save_command_result(out_dir / f"{stem}_run_dump.json", run_result)
    logs.append({"phase": "run_dump", "result": run_result})
    return stdout, stderr, logs, run_result.ok, run_result.stderr


def evaluate_source(
    config: ExperimentConfig,
    kernel: Kernel,
    source: Path,
    out_dir: Path,
    candidate_id: str,
    *,
    baseline_dump: Path | None = None,
    baseline_runtime: float | None = None,
) -> EvaluationResult:
    ensure_dir(out_dir)
    binary = out_dir / f"{candidate_id}_time"
    remarks_record = out_dir / "remarks" / "o3.opt.yaml"
    compile_result = compile_c(config, kernel, source, binary, remarks=remarks_record)
    save_command_result(out_dir / "compile_time.json", compile_result)
    result = EvaluationResult(
        candidate_id=candidate_id,
        compile_ok=compile_result.ok,
        command_log=[{"phase": "compile_time", "result": compile_result}],
        artifacts=BuildArtifacts(binary=binary if compile_result.ok else None, remarks=remarks_record),
    )
    if not compile_result.ok:
        result.error = compile_result.stderr
        return result

    stdout, stderr, dump_logs, dump_ok, dump_error = dump_output(config, kernel, source, out_dir, candidate_id)
    result.command_log.extend(dump_logs)
    result.artifacts.dump_stdout = stdout
    result.artifacts.dump_stderr = stderr
    if not dump_ok:
        result.error = dump_error
        return result

    if baseline_dump is not None:
        result.correctness = compare_files(baseline_dump, stderr, rtol=config.rtol, atol=config.atol)
        if not result.correctness.ok:
            return result

    timing, run_logs = run_binary(config, binary, log_dir=out_dir / "runs")
    result.timing = timing
    result.command_log.extend(run_logs)
    if baseline_runtime and timing.median:
        result.speedup_vs_baseline = baseline_runtime / timing.median
    return result


def evaluate_pipeline_candidate(
    config: ExperimentConfig,
    kernel: Kernel,
    frontend_ir: Path,
    pipeline: str,
    out_dir: Path,
    candidate_id: str,
    *,
    baseline_dump: Path,
    baseline_runtime: float,
    extra_options: list[str] | None = None,
) -> EvaluationResult:
    ensure_dir(out_dir)
    preflight = preflight_pipeline(config, frontend_ir, pipeline, extra_options=extra_options)
    save_command_result(out_dir / "preflight.json", preflight)
    result = EvaluationResult(candidate_id=candidate_id, compile_ok=False, command_log=[{"phase": "preflight", "result": preflight}])
    (out_dir / "pipeline.txt").write_text(pipeline + "\n")
    if not preflight.ok:
        result.error = preflight.stderr
        return result

    candidate_ir = out_dir / f"{candidate_id}.ll"
    remarks = out_dir / "remarks.txt"
    opt_result = opt_pipeline(config, frontend_ir, candidate_ir, pipeline, remarks=remarks, extra_options=extra_options)
    save_command_result(out_dir / "opt.json", opt_result)
    result.command_log.append({"phase": "opt", "result": opt_result})
    if not opt_result.ok:
        result.error = opt_result.stderr
        return result

    candidate_object = out_dir / f"{candidate_id}.o"
    llc_result = compile_ir_to_object(config, candidate_ir, candidate_object)
    save_command_result(out_dir / "llc.json", llc_result)
    result.command_log.append({"phase": "llc", "result": llc_result})
    if not llc_result.ok:
        result.error = llc_result.stderr
        return result

    polybench_object = out_dir / "polybench.o"
    polybench_result = compile_polybench_object(config, kernel, polybench_object)
    save_command_result(out_dir / "polybench_compile.json", polybench_result)
    result.command_log.append({"phase": "polybench_compile", "result": polybench_result})
    if not polybench_result.ok:
        result.error = polybench_result.stderr
        return result

    binary = out_dir / f"{candidate_id}_time"
    link_result = link_objects(config, [candidate_object, polybench_object], binary)
    save_command_result(out_dir / "link.json", link_result)
    result.command_log.append({"phase": "link", "result": link_result})
    result.artifacts = BuildArtifacts(binary=binary, optimized_ir=candidate_ir, remarks=remarks, pipeline=out_dir / "pipeline.txt")
    result.compile_ok = link_result.ok
    if not link_result.ok:
        result.error = link_result.stderr
        return result

    dump_frontend = out_dir / f"{candidate_id}_dump_frontend.ll"
    dump_ir = out_dir / f"{candidate_id}_dump.ll"
    dump_binary = out_dir / f"{candidate_id}_dump"
    dump_frontend_result = emit_frontend_ir(config, kernel, kernel.source, dump_frontend, dump_arrays=True)
    save_command_result(out_dir / "dump_frontend_ir.json", dump_frontend_result)
    result.command_log.append({"phase": "dump_frontend_ir", "result": dump_frontend_result})
    if not dump_frontend_result.ok:
        result.error = dump_frontend_result.stderr
        return result
    dump_opt_result = opt_pipeline(config, dump_frontend, dump_ir, pipeline, extra_options=extra_options)
    save_command_result(out_dir / "dump_opt.json", dump_opt_result)
    result.command_log.append({"phase": "dump_opt", "result": dump_opt_result})
    if not dump_opt_result.ok:
        result.error = dump_opt_result.stderr
        return result

    dump_object = out_dir / f"{candidate_id}_dump.o"
    dump_llc_result = compile_ir_to_object(config, dump_ir, dump_object)
    save_command_result(out_dir / "dump_llc.json", dump_llc_result)
    result.command_log.append({"phase": "dump_llc", "result": dump_llc_result})
    if not dump_llc_result.ok:
        result.error = dump_llc_result.stderr
        return result

    dump_polybench_object = out_dir / "polybench_dump.o"
    dump_polybench_result = compile_polybench_object(config, kernel, dump_polybench_object)
    save_command_result(out_dir / "dump_polybench_compile.json", dump_polybench_result)
    result.command_log.append({"phase": "dump_polybench_compile", "result": dump_polybench_result})
    if not dump_polybench_result.ok:
        result.error = dump_polybench_result.stderr
        return result

    dump_link_result = link_objects(config, [dump_object, dump_polybench_object], dump_binary)
    save_command_result(out_dir / "dump_link.json", dump_link_result)
    result.command_log.append({"phase": "dump_link", "result": dump_link_result})
    if not dump_link_result.ok:
        result.error = dump_link_result.stderr
        return result
    dump_run_result = run_command([str(dump_binary)], config.repo_root)
    dump_stdout = out_dir / f"{candidate_id}_dump.stdout"
    dump_stderr = out_dir / f"{candidate_id}_dump.stderr"
    dump_stdout.write_text(dump_run_result.stdout)
    dump_stderr.write_text(dump_run_result.stderr)
    dump_run_result.stdout_path = dump_stdout
    dump_run_result.stderr_path = dump_stderr
    save_command_result(out_dir / "dump_run.json", dump_run_result)
    result.command_log.append({"phase": "dump_run", "result": dump_run_result})
    result.artifacts.dump_stdout = dump_stdout
    result.artifacts.dump_stderr = dump_stderr
    if not dump_run_result.ok:
        result.error = dump_run_result.stderr
        return result
    result.correctness = compare_files(baseline_dump, dump_stderr, rtol=config.rtol, atol=config.atol)
    if not result.correctness.ok:
        return result

    timing, run_logs = run_binary(config, binary, log_dir=out_dir / "runs")
    result.timing = timing
    result.command_log.extend(run_logs)
    if timing.median:
        result.speedup_vs_baseline = baseline_runtime / timing.median
    return result
