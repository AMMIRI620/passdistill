from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .agents.base import make_backend
from .baseline import build_baseline
from .config import ExperimentConfig
from .polybench import discover_kernels, find_kernel
from .search.teacher_search import run_teacher_search
from .util import ensure_dir, read_json, write_json


def make_run_dir(config: ExperimentConfig) -> Path:
    run_id = config.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    return ensure_dir(config.artifacts_root / run_id)


def selected_kernels(config: ExperimentConfig, kernel: str | None, all_kernels: bool):
    if all_kernels:
        return discover_kernels(config.polybench_root)
    if not kernel:
        raise ValueError("choose --kernel NAME or --all")
    return [find_kernel(config.polybench_root, kernel)]


def _get(obj, *keys):
    for key in keys:
        obj = obj[key] if isinstance(obj, dict) else getattr(obj, key)
    return obj


def _runtime(summary: dict, key: str) -> float | None:
    try:
        return _get(summary[key], "timing", "median")
    except (KeyError, TypeError, AttributeError):
        return None


def run(config: ExperimentConfig, *, kernel: str | None, all_kernels: bool) -> Path:
    run_dir = make_run_dir(config)
    write_json(run_dir / "config.json", config.as_json())
    backend = None
    final: dict = {"kernels": {}}
    for item in selected_kernels(config, kernel, all_kernels):
        kernel_dir = ensure_dir(run_dir / "kernels" / item.name)
        baseline_file = kernel_dir / "baseline" / "baseline_summary.json"
        if config.resume and baseline_file.exists():
            baseline_summary = read_json(baseline_file)
        else:
            baseline_summary = build_baseline(config, item, kernel_dir / "baseline")
        if config.baseline_only:
            search_summary = {"baseline_only": True}
        elif config.dry_run:
            search_summary = {"dry_run": True}
        else:
            if backend is None:
                backend = make_backend(config.llm_backend, config.model)
            search_summary = run_teacher_search(
                config,
                backend,
                item,
                baseline_summary=baseline_summary,
                out_dir=kernel_dir / "search",
            )
        clang_baseline_runtime = _runtime(baseline_summary, "baseline")
        search_baseline_runtime = _runtime(baseline_summary, "search_baseline")
        best_teacher = search_summary.get("best_teacher") if isinstance(search_summary, dict) else None
        best_recovery = search_summary.get("best_recovery") if isinstance(search_summary, dict) else None
        best_teacher_runtime = best_teacher.get("runtime") if best_teacher else None
        best_pass_runtime = best_recovery.get("best_runtime") if best_recovery else None
        teacher_speedup_vs_clang = (
            clang_baseline_runtime / best_teacher_runtime
            if clang_baseline_runtime and best_teacher_runtime
            else None
        )
        pass_speedup_vs_search = (
            search_baseline_runtime / best_pass_runtime
            if search_baseline_runtime and best_pass_runtime
            else None
        )
        pass_speedup_vs_clang = (
            clang_baseline_runtime / best_pass_runtime
            if clang_baseline_runtime and best_pass_runtime
            else None
        )
        teacher_gain = (
            (clang_baseline_runtime - best_teacher_runtime) / clang_baseline_runtime
            if clang_baseline_runtime and best_teacher_runtime
            else None
        )
        pass_gain = (
            (search_baseline_runtime - best_pass_runtime) / search_baseline_runtime
            if search_baseline_runtime and best_pass_runtime
            else None
        )
        recovery_ratio = pass_gain / teacher_gain if teacher_gain and teacher_gain > 0 and pass_gain is not None else None
        final["kernels"][item.name] = {
            "clang_baseline_runtime": clang_baseline_runtime,
            "search_baseline_runtime": search_baseline_runtime,
            "best_teacher_runtime": best_teacher_runtime,
            "best_pass_runtime": best_pass_runtime,
            "teacher_speedup_vs_clang": teacher_speedup_vs_clang,
            "pass_speedup_vs_search": pass_speedup_vs_search,
            "pass_speedup_vs_clang": pass_speedup_vs_clang,
            "teacher_gain": teacher_gain,
            "pass_gain": pass_gain,
            "recovery_ratio": recovery_ratio,
            "teacher_candidates_tried": search_summary.get("teacher_candidates_tried", 0) if isinstance(search_summary, dict) else 0,
            "pass_candidates_tried": search_summary.get("pass_candidates_tried", 0) if isinstance(search_summary, dict) else 0,
            "best_teacher_direction": best_teacher.get("direction_id") if best_teacher else None,
            "best_pass_pipeline": best_recovery.get("best_pipeline") if best_recovery else None,
            "final_correctness": True,
        }
    write_json(run_dir / "summary.json", final)
    return run_dir
