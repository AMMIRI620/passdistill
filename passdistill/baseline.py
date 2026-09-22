from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from .compiler import emit_frontend_ir, emit_optimized_ir, expanded_o3_pipeline
from .correctness import stderr_md5
from .config import ExperimentConfig
from .evaluator import evaluate_pipeline_candidate, evaluate_source, run_binary
from .types import EvaluationResult, Kernel, to_jsonable
from .util import ensure_dir, save_command_result, write_json


def remeasure_search_baseline(config: ExperimentConfig, summary: dict, out_dir: Path) -> float:
    """Refresh timing only, immediately before a zero-candidate recovery search.

    Preserve the executable, correctness reference, original measurements, and
    every remeasurement attempt. The caller must not use this mid-search.
    """
    updated = to_jsonable(summary)
    search_eval = updated["search_baseline"]
    binary = Path(search_eval["artifacts"]["binary"])
    if not binary.is_file():
        raise RuntimeError(f"Missing search baseline executable: {binary}")
    attempt = 1
    while (out_dir / "search_baseline" / f"remeasure_{attempt}").exists():
        attempt += 1
    measurement_dir = ensure_dir(out_dir / "search_baseline" / f"remeasure_{attempt}")
    timing, logs = run_binary(config, binary, log_dir=measurement_dir / "runs")
    record = {
        "reason": "before_zero_candidate_recovery",
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "previous_timing": search_eval["timing"],
        "timing": timing,
        "binary": binary,
        "command_log": logs,
    }
    write_json(measurement_dir / "measurement.json", record)
    if timing.median is None or timing.median <= 0 or len(timing.measured) != config.runs or len(timing.warmups) != config.warmups:
        raise RuntimeError(f"Search baseline remeasurement failed: {measurement_dir}")
    updated.setdefault("initial_search_baseline", to_jsonable(summary["search_baseline"]))
    search_eval["timing"] = to_jsonable(timing)
    search_eval["command_log"] = search_eval.get("command_log", []) + to_jsonable(logs)
    clang_runtime = updated["baseline"]["timing"]["median"]
    search_eval["speedup_vs_baseline"] = clang_runtime / timing.median
    updated["search_baseline_remeasurement"] = str(measurement_dir / "measurement.json")
    temporary = out_dir / "baseline_summary.tmp.json"
    write_json(temporary, updated)
    temporary.replace(out_dir / "baseline_summary.json")
    summary.clear()
    summary.update(updated)
    print(f"[{summary['kernel']}] search baseline remeasured before candidate 1: "
          f"{timing.median:.6f}s ({config.warmups} warmups, {config.runs} runs)", flush=True)
    return timing.median


def build_baseline(
    config: ExperimentConfig,
    kernel: Kernel,
    out_dir: Path,
) -> dict:
    ensure_dir(out_dir)
    source_copy = out_dir / "kernel_source.c"
    header_copy = out_dir / kernel.header.name
    source_copy.write_text(kernel.source.read_text())
    header_copy.write_text(kernel.header.read_text())

    source_eval = evaluate_source(config, kernel, kernel.source, out_dir / "clang_o3", "baseline")
    if source_eval.timing is None or source_eval.timing.median is None:
        raise RuntimeError(f"baseline failed for {kernel.name}: {source_eval.error}")

    frontend_ir = out_dir / "ir" / f"{kernel.name}_frontend_o3.ll"
    frontend_result = emit_frontend_ir(config, kernel, kernel.source, frontend_ir)
    save_command_result(out_dir / "ir" / "frontend_ir.json", frontend_result)
    if not frontend_result.ok:
        raise RuntimeError(frontend_result.stderr)

    clang_ir = out_dir / "ir" / f"{kernel.name}_clang_o3.ll"
    clang_ir_result = emit_optimized_ir(config, kernel, kernel.source, clang_ir)
    save_command_result(out_dir / "ir" / "clang_o3_ir.json", clang_ir_result)

    pipeline_result = expanded_o3_pipeline(config)
    save_command_result(out_dir / "ir" / "expanded_pipeline_command.json", pipeline_result)
    if not pipeline_result.ok:
        raise RuntimeError(pipeline_result.stderr)
    pipeline = pipeline_result.stdout.strip()
    pipeline_path = out_dir / "ir" / "o3_expanded_pipeline.txt"
    pipeline_path.write_text(pipeline + "\n")

    search_eval = evaluate_pipeline_candidate(
        config,
        kernel,
        frontend_ir,
        pipeline,
        out_dir / "search_baseline",
        "search_o3",
        # The O3 pipeline establishes the reference; it is not gated by Clang's output.
        baseline_dump=None,
        baseline_runtime=source_eval.timing.median,
        build_reference_dump=True,
    )
    if search_eval.timing is None or search_eval.timing.median is None or not search_eval.artifacts.dump_stderr:
        raise RuntimeError(f"O3 pipeline reference failed for {kernel.name}: {search_eval.error}")
    summary = {
        "correctness_mode": config.correctness_mode,
        "correctness_reference": config.correctness_reference,
        "correctness_reference_md5": stderr_md5(search_eval.artifacts.dump_stderr),
        "kernel": kernel.name,
        "baseline": source_eval,
        "frontend_ir": frontend_ir,
        "clang_o3_ir": clang_ir,
        "expanded_pipeline": pipeline_path,
        "search_baseline": search_eval,
    }
    write_json(out_dir / "baseline_summary.json", summary)
    return summary
