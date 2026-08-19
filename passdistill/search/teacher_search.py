from __future__ import annotations

from pathlib import Path
from typing import Any

from passdistill.agents.base import AgentBackend
from passdistill.agents.direction_distiller import distill_direction
from passdistill.agents.source_oracle import propose_teachers
from passdistill.config import ExperimentConfig
from passdistill.evaluator import evaluate_source
from passdistill.patching import apply_teacher_patch
from passdistill.search.recovery_search import run_recovery_episode
from passdistill.types import Kernel
from passdistill.util import ensure_dir, write_json


def round_teacher_limit(round_index: int) -> int:
    return {1: 3, 2: 2, 3: 1}.get(round_index, 1)


def _path(value) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _get(obj, *keys):
    for key in keys:
        obj = obj[key] if isinstance(obj, dict) else getattr(obj, key)
    return obj


def sort_valid_directions_for_recovery(valid_directions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(valid_directions, key=lambda item: item["teacher_runtime"])


def global_direction_id(teacher_round: int, local_direction_id: str) -> str:
    safe_local = str(local_direction_id or "D").replace("/", "_")
    return f"T{teacher_round}_{safe_local}"


def run_teacher_search(
    config: ExperimentConfig,
    backend: AgentBackend,
    kernel: Kernel,
    *,
    baseline_summary: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    ensure_dir(out_dir)
    baseline_eval = baseline_summary["baseline"]
    search_baseline_eval = baseline_summary["search_baseline"]
    clang_baseline_runtime = _get(baseline_eval, "timing", "median")
    search_baseline_runtime = _get(search_baseline_eval, "timing", "median")
    baseline_dump = _path(_get(baseline_eval, "artifacts", "dump_stderr"))
    frontend_ir = _path(baseline_summary["frontend_ir"])
    pipeline = _path(baseline_summary["expanded_pipeline"]).read_text().strip()
    remarks_path = _get(baseline_eval, "artifacts", "remarks")
    remarks_path = _path(remarks_path) if remarks_path else None
    baseline_remarks = remarks_path.read_text(errors="replace") if remarks_path and remarks_path.exists() else ""
    original_source = kernel.source.read_text()
    history: list[dict[str, Any]] = []
    valid_directions: list[dict[str, Any]] = []
    recovery_summaries: list[dict[str, Any]] = []
    teacher_count = 0
    pass_budget_used = 0

    for round_index in range(1, config.max_teacher_rounds + 1):
        if teacher_count >= config.max_teachers:
            break
        proposals = propose_teachers(
            backend,
            kernel_name=kernel.name,
            original_source=original_source,
            baseline_remarks=baseline_remarks,
            baseline_runtime=clang_baseline_runtime,
            history=history,
            round_index=round_index,
            max_candidates=min(round_teacher_limit(round_index), config.max_teachers - teacher_count),
            remaining_teacher_budget=config.max_teachers - teacher_count,
            out_dir=out_dir / f"oracle_round_{round_index}",
            repo_root=config.repo_root,
        )
        if not proposals:
            break
        for proposal in proposals:
            teacher_count += 1
            local_direction_id = proposal.get("direction_id") or f"D{teacher_count}"
            direction_id = global_direction_id(round_index, local_direction_id)
            proposal = dict(proposal)
            proposal["local_direction_id"] = local_direction_id
            proposal["direction_id"] = direction_id
            teacher_dir = out_dir / "teachers" / direction_id
            ensure_dir(teacher_dir)
            write_json(teacher_dir / "proposal.json", proposal)
            teacher_source = teacher_dir / kernel.source.name
            try:
                apply_teacher_patch(kernel.source, proposal.get("source_patch", ""), teacher_source)
            except Exception as exc:
                entry = {"direction_id": direction_id, "compile_ok": False, "error": f"patch failed: {exc}"}
                history.append(entry)
                write_json(out_dir / "teacher_history.json", history)
                continue
            eval_result = evaluate_source(
                config,
                kernel,
                teacher_source,
                teacher_dir / "eval",
                direction_id,
                baseline_dump=baseline_dump,
                baseline_runtime=clang_baseline_runtime,
            )
            entry = {
                "direction_id": direction_id,
                "compile_ok": eval_result.compile_ok,
                "correctness_ok": bool(eval_result.correctness and eval_result.correctness.ok),
                "runtime": eval_result.timing.median if eval_result.timing else None,
                "teacher_speedup_vs_clang": eval_result.speedup_vs_baseline,
                "error": eval_result.error,
            }
            history.append(entry)
            write_json(out_dir / "teacher_history.json", history)
            if not (eval_result.correctness and eval_result.correctness.ok and eval_result.timing and eval_result.timing.median):
                continue
            if eval_result.timing.median >= clang_baseline_runtime:
                continue
            teacher_remarks_path = eval_result.artifacts.remarks
            teacher_remarks = teacher_remarks_path.read_text(errors="replace") if teacher_remarks_path and teacher_remarks_path.exists() else ""
            direction = distill_direction(
                backend,
                direction_id=direction_id,
                original_source=original_source,
                teacher_source=teacher_source.read_text(),
                original_remarks=baseline_remarks,
                teacher_remarks=teacher_remarks,
                baseline_runtime=clang_baseline_runtime,
                teacher_runtime=eval_result.timing.median,
                out_dir=teacher_dir / "distill",
                repo_root=config.repo_root,
            )
            direction["direction_id"] = direction_id
            direction["local_direction_id"] = local_direction_id
            valid_directions.append(
                {
                    "direction_id": direction_id,
                    "direction": direction,
                    "teacher_runtime": eval_result.timing.median,
                    "entry": entry,
                    "rounds_done": 0,
                }
            )
            write_json(out_dir / "teacher_history.json", history)

    valid_directions = sort_valid_directions_for_recovery(valid_directions)
    while valid_directions and pass_budget_used < config.max_pass_candidates:
        progressed = False
        for item in valid_directions:
            if pass_budget_used >= config.max_pass_candidates:
                break
            if item["rounds_done"] >= config.max_recovery_rounds:
                continue
            remaining = max(0, config.max_pass_candidates - pass_budget_used)
            batch_budget = min(3, remaining)
            if batch_budget <= 0:
                break
            recovery = run_recovery_episode(
                config,
                backend,
                kernel,
                direction=item["direction"],
                frontend_ir=frontend_ir,
                baseline_pipeline=pipeline,
                baseline_dump=baseline_dump,
                baseline_runtime=search_baseline_runtime,
                out_dir=out_dir / "recovery" / item["direction_id"],
                remaining_budget=batch_budget,
                start_round=item["rounds_done"] + 1,
                max_rounds=1,
            )
            item["rounds_done"] += 1
            used = recovery.get("new_candidates_tried", recovery.get("candidates_tried", 0))
            pass_budget_used += used
            recovery_summaries.append(recovery)
            item["entry"]["recovery"] = {
                "candidates_tried": item["entry"].get("recovery", {}).get("candidates_tried", 0) + used,
                "best_speedup_vs_search": recovery.get("best_speedup_vs_search"),
            }
            write_json(out_dir / "teacher_history.json", history)
            progressed = progressed or used > 0
        if not progressed:
            break

    best_teacher = min((h for h in history if h.get("runtime")), key=lambda h: h["runtime"], default=None)
    best_recovery = max(recovery_summaries, key=lambda r: r.get("best_speedup") or 0, default=None)
    summary = {
        "clang_baseline_runtime": clang_baseline_runtime,
        "search_baseline_runtime": search_baseline_runtime,
        "teacher_candidates_tried": teacher_count,
        "pass_candidates_tried": pass_budget_used,
        "best_teacher": best_teacher,
        "best_recovery": best_recovery,
        "history": history,
    }
    write_json(out_dir / "summary.json", summary)
    return summary
