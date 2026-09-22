from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

from .agents.base import make_backend
from .agents.catalog import catalog_sha256
from .baseline import build_baseline
from .config import ExperimentConfig
from .polybench import discover_kernels, find_kernel
from .search.teacher_search import run_teacher_search
from .util import ensure_dir, read_json, write_json


def make_run_dir(config: ExperimentConfig) -> Path:
    run_id = config.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    return ensure_dir(config.artifacts_root / run_id)


def selected_kernels(config: ExperimentConfig, kernel: str | None, all_kernels: bool, kernels: list[str] | None = None):
    if all_kernels:
        return discover_kernels(config.polybench_root, config.kernel_metadata)
    if kernels:
        return [find_kernel(config.polybench_root, name, config.kernel_metadata) for name in kernels]
    if not kernel:
        raise ValueError("choose --kernel NAME or --all")
    return [find_kernel(config.polybench_root, kernel, config.kernel_metadata)]


def _get(obj, *keys):
    for key in keys:
        obj = obj[key] if isinstance(obj, dict) else getattr(obj, key)
    return obj


def _runtime(summary: dict, key: str) -> float | None:
    try:
        return _get(summary[key], "timing", "median")
    except (KeyError, TypeError, AttributeError):
        return None


def _best_timing_metrics(
    search_summary: dict,
) -> dict:
    best_recovery = search_summary.get("best_recovery") or {}
    best_id = best_recovery.get("current_measured_best_id")
    best_entry = next(
        (item for item in best_recovery.get("history", []) if item.get("candidate_id") == best_id),
        None,
    )
    return {
        "best_recovery_round": (
            0 if best_id == "SEARCH_BASELINE"
            else best_entry.get("round") if best_entry
            else best_recovery.get("best_candidate_round")
        ),
    }


def run(
    config: ExperimentConfig,
    *,
    kernel: str | None,
    all_kernels: bool,
    kernels: list[str] | None = None,
) -> Path:
    run_dir = make_run_dir(config)
    config_path = run_dir / "config.json"
    if config.resume and config_path.exists():
        previous = read_json(config_path)
        if any(previous.get(key) != getattr(config, key) for key in ("correctness_mode", "correctness_reference", "candidate_evaluation_mode", "teacher_correctness_policy")):
            raise ValueError("Cannot resume artifacts with a different or legacy correctness policy; choose a new run_id")
    catalog_hash = catalog_sha256(config.repo_root)
    if config.resume and config_path.exists() and previous.get("catalog_sha256") != catalog_hash:
        raise ValueError("Cannot resume with a different or unrecorded catalog hash; choose a new run_id")
    write_json(run_dir / "config.json", {**config.as_json(), "catalog_sha256": catalog_hash})
    (run_dir / "catalog_snapshot.json").write_bytes((config.repo_root / "configs/llvm22.1.3_pass_catalog.json").read_bytes())
    backend = None
    summary_path = run_dir / "summary.json"
    final: dict = read_json(summary_path) if config.resume and summary_path.exists() else {"kernels": {}}
    final["active_experiment_model"] = config.model
    final["catalog_sha256"] = catalog_hash
    for item in selected_kernels(config, kernel, all_kernels, kernels):
        kernel_started = time.perf_counter()
        kernel_dir = ensure_dir(run_dir / item.name if config.flat_kernel_artifacts else run_dir / "kernels" / item.name)
        timing_path = kernel_dir / "experiment_timing.json"
        if config.resume and timing_path.exists():
            experiment_timing = read_json(timing_path)
        else:
            experiment_timing = {"kernel_started_at_utc": datetime.now(timezone.utc).isoformat()}
            write_json(timing_path, experiment_timing)
        baseline_file = kernel_dir / "baseline" / "baseline_summary.json"
        if config.resume and baseline_file.exists():
            baseline_summary = read_json(baseline_file)
            if baseline_summary.get("correctness_mode") != config.correctness_mode or baseline_summary.get("correctness_reference") != config.correctness_reference:
                raise ValueError("Legacy baseline correctness reference; choose a new run_id")
        else:
            baseline_summary = build_baseline(config, item, kernel_dir / "baseline")
        if config.baseline_only:
            search_summary = {"baseline_only": True}
        elif config.dry_run:
            search_summary = {"dry_run": True}
        else:
            if backend is None:
                backend = make_backend(config.llm_backend, config.model, api_mode=config.llm_api, prompt_cache_mode=config.prompt_cache_mode)
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
        failure_counts = {name: 0 for name in (
            "pipeline_invalid",
            "llvm_preflight_failed",
            "compile_failed",
            "runtime_failed",
            "incorrect",
            "timeout",
        )}
        failure_counts.update(search_summary.get("failure_counts", {}) if isinstance(search_summary, dict) else {})
        timing_metrics = _best_timing_metrics(search_summary if isinstance(search_summary, dict) else {})
        try:
            kernel_total_time_seconds = max(
                0.0,
                (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(experiment_timing["kernel_started_at_utc"])
                ).total_seconds(),
            )
        except (KeyError, TypeError, ValueError):
            kernel_total_time_seconds = time.perf_counter() - kernel_started
        valid_teacher_count = search_summary.get("valid_teacher_count", 0) if isinstance(search_summary, dict) else 0
        pass_candidates_tried = search_summary.get("pass_candidates_tried", 0) if isinstance(search_summary, dict) else 0
        if not (config.baseline_only or config.dry_run) and valid_teacher_count == 0:
            recovery_status = "no_valid_teacher"
        elif pass_candidates_tried >= config.max_pass_candidates:
            recovery_status = "complete"
        else:
            recovery_status = "incomplete"
        kernel_summary = {
            "catalog_sha256": catalog_hash,
            "teacher_correctness_policy": config.teacher_correctness_policy,
            "teacher_correct_count": search_summary.get("teacher_correct_count", 0),
            "teacher_incorrect_count": search_summary.get("teacher_incorrect_count", 0),
            "teacher_unchecked_count": search_summary.get("teacher_unchecked_count", 0),
            "best_teacher_correctness_ok": best_teacher.get("correctness_ok") if best_teacher else None,
            "candidate_evaluation_mode": config.candidate_evaluation_mode,
            "correctness_mode": config.correctness_mode,
            "correctness_reference": config.correctness_reference,
            "correctness_reference_md5": baseline_summary.get("correctness_reference_md5"),
            "kernel": item.name,
            "agent_model": config.model,
            "baseline_runtime": clang_baseline_runtime,
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
            "teacher_speedup": teacher_speedup_vs_clang,
            "pass_speedup": pass_speedup_vs_search,
            "transfer_ratio": recovery_ratio,
            "teacher_count": search_summary.get("teacher_candidates_tried", 0) if isinstance(search_summary, dict) else 0,
            "teacher_candidates_tried": search_summary.get("teacher_candidates_tried", 0) if isinstance(search_summary, dict) else 0,
            "valid_teacher_count": valid_teacher_count,
            "recovery_status": recovery_status,
            "total_recovery_budget": config.max_pass_candidates,
            "pass_candidates_tried": pass_candidates_tried,
            "evaluated_candidates": search_summary.get("evaluated_candidates", 0) if isinstance(search_summary, dict) else 0,
            "measured_candidates": search_summary.get("measured_candidates", 0) if isinstance(search_summary, dict) else 0,
            "best_teacher_direction": best_teacher.get("direction_id") if best_teacher else None,
            "best_pass_candidate": best_recovery.get("current_measured_best_id") if best_recovery else None,
            "best_recovery_round": timing_metrics["best_recovery_round"],
            "kernel_total_time_seconds": kernel_total_time_seconds,
            "best_pass_pipeline": best_recovery.get("best_pipeline") if best_recovery else None,
            "failure_counts": failure_counts,
            "recovery_depth": search_summary.get("recovery_depth", []) if isinstance(search_summary, dict) else [],
            "final_correctness": True,
        }
        final["kernels"][item.name] = kernel_summary
        write_json(kernel_dir / "summary.json", kernel_summary)
        write_json(summary_path, final)
    write_json(summary_path, final)
    return run_dir
