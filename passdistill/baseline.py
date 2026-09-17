from __future__ import annotations

from pathlib import Path

from .compiler import emit_frontend_ir, emit_optimized_ir, expanded_o3_pipeline
from .correctness import stderr_md5
from .config import ExperimentConfig
from .evaluator import evaluate_pipeline_candidate, evaluate_source
from .types import EvaluationResult, Kernel
from .util import ensure_dir, save_command_result, write_json


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
