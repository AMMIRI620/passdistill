from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from passdistill.agents.base import AgentBackend
from passdistill.agents.direction_distiller import distill_direction
from passdistill.agents.source_oracle import propose_teachers
from passdistill.config import ExperimentConfig
from passdistill.evaluator import evaluate_source
from passdistill.patching import apply_teacher_patch
from passdistill.search.recovery_search import run_recovery_episode
from passdistill.types import Kernel
from passdistill.util import ensure_dir, read_json, write_json


def round_teacher_limit(round_index: int) -> int:
    return 2


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


def completed_teachers_in_round(history: list[dict[str, Any]], round_index: int) -> int:
    pattern = re.compile(rf"^T{round_index}_")
    return sum(bool(pattern.match(str(entry.get("direction_id") or ""))) for entry in history)


def resume_artifact_dir(base: Path) -> Path:
    if not base.exists() or not any(base.iterdir()):
        return base
    resume_index = 1
    while base.with_name(f"{base.name}_resume_{resume_index}").exists():
        resume_index += 1
    return base.with_name(f"{base.name}_resume_{resume_index}")


def uniform_round_target(total_budget: int, teacher_count: int, teacher_index: int, round_index: int, max_rounds: int) -> int:
    """Cumulative fixed-budget target for one teacher after a recovery round."""
    if teacher_count <= 0 or max_rounds <= 0:
        return 0
    teacher_quota = total_budget // teacher_count + (1 if teacher_index < total_budget % teacher_count else 0)
    base = teacher_quota // max_rounds
    extra = teacher_quota % max_rounds
    return base * round_index + min(round_index, extra)


def has_recovery_candidates(out_dir: Path, history: list[dict[str, Any]]) -> bool:
    # Invalid/partially written candidates count too: never change their baseline.
    if any(entry.get("recovery", {}).get("candidates_tried", 0) for entry in history):
        return True
    if any((out_dir / "recovery").glob("*/candidates/*")):
        return True
    if any(read_json(path) for path in (out_dir / "recovery").glob("*/history.json")):
        return True
    return any(read_json(path).get("candidates_tried", 0)
               for path in (out_dir / "recovery").glob("*/summary.json"))


def run_teacher_search(
    config: ExperimentConfig,
    backend: AgentBackend,
    kernel: Kernel,
    *,
    baseline_summary: dict[str, Any],
    out_dir: Path,
    adapter: Any = None,
) -> dict[str, Any]:
    ensure_dir(out_dir)
    baseline_eval = baseline_summary["baseline"]
    search_baseline_eval = baseline_summary["search_baseline"]
    clang_baseline_runtime = _get(baseline_eval, "timing", "median")
    search_baseline_runtime = _get(search_baseline_eval, "timing", "median")
    baseline_dump = _path(_get(search_baseline_eval, "artifacts", "dump_stderr"))
    frontend_ir = _path(baseline_summary["frontend_ir"])
    pipeline = _path(baseline_summary["expanded_pipeline"]).read_text().strip()
    remarks_path = _get(baseline_eval, "artifacts", "remarks")
    remarks_path = _path(remarks_path) if remarks_path else None
    baseline_remarks = remarks_path.read_text(errors="replace") if remarks_path and remarks_path.exists() else ""
    source_text = adapter.source_text if adapter else lambda path: path.read_text()
    propose = adapter.propose_teachers if adapter else propose_teachers
    patch_source = adapter.apply_teacher_patch if adapter else apply_teacher_patch
    evaluate = adapter.evaluate_source if adapter else evaluate_source
    original_source = source_text(kernel.source)
    history: list[dict[str, Any]] = []
    valid_directions: list[dict[str, Any]] = []
    recovery_summaries: list[dict[str, Any]] = []
    teacher_count = 0
    pass_budget_used = 0

    if config.resume and (out_dir / "teacher_history.json").exists():
        history = read_json(out_dir / "teacher_history.json")
        teacher_count = len(history)
        for entry in history:
            direction_id = entry.get("direction_id")
            teacher_dir = out_dir / "teachers" / str(direction_id)
            intent_path = teacher_dir / "intent.json"
            if not (entry.get("compile_ok") and entry.get("runtime")):
                continue
            if entry["runtime"] >= clang_baseline_runtime and not config.uniform_fixed_recovery_budget:
                continue
            if not intent_path.exists():
                # Evaluation is checkpointed before distillation. Resume that
                # unfinished stage instead of silently dropping the teacher.
                proposal = read_json(teacher_dir / "proposal.json")
                teacher_source = teacher_dir / "source.c"
                teacher_remarks_path = teacher_dir / "eval" / "remarks" / "o3.opt.yaml"
                teacher_remarks = teacher_remarks_path.read_text(errors="replace") if teacher_remarks_path.exists() else ""
                print(f"[{kernel.name}] resuming missing intent for {direction_id}", flush=True)
                direction = distill_direction(
                    backend, direction_id=direction_id,
                    original_source=original_source, teacher_source=source_text(teacher_source),
                    original_remarks=baseline_remarks, teacher_remarks=teacher_remarks,
                    baseline_runtime=clang_baseline_runtime, teacher_runtime=entry["runtime"],
                    out_dir=resume_artifact_dir(teacher_dir / "distill"), repo_root=config.repo_root,
                )
                direction["direction_id"] = direction_id
                direction["local_direction_id"] = proposal.get("local_direction_id", proposal.get("direction_id"))
                write_json(intent_path, direction)
            direction = read_json(intent_path)
            recovery_dir = out_dir / "recovery" / str(direction_id)
            recovery_path = recovery_dir / "summary.json"
            recovery = read_json(recovery_path) if recovery_path.exists() else None
            recovery_history_path = recovery_dir / "history.json"
            recovery_history = read_json(recovery_history_path) if recovery_history_path.exists() else []
            candidate_dirs = list((recovery_dir / "candidates").glob("*")) if (recovery_dir / "candidates").exists() else []
            candidate_rounds = [int(match.group(1)) for path in candidate_dirs if (match := re.search(r"_R(\d+)_", path.name))]
            rounds_done = max([*(int(item.get("round", 0)) for item in recovery_history), *candidate_rounds], default=0)
            candidates_used = max(len(recovery_history), len(candidate_dirs))
            if recovery:
                recovery_summaries.append(recovery)
                pass_budget_used += candidates_used
                entry["recovery"] = {
                    "candidates_tried": candidates_used,
                    "best_speedup_vs_search": recovery.get("best_speedup_vs_search"),
                }
            valid_directions.append(
                {
                    "direction_id": direction_id,
                    "direction": direction,
                    "teacher_runtime": entry["runtime"],
                    "entry": entry,
                    "rounds_done": rounds_done,
                }
            )

    for round_index in range(1, config.max_teacher_rounds + 1):
        if teacher_count >= config.max_teachers:
            break
        completed_in_round = completed_teachers_in_round(history, round_index)
        remaining_in_round = max(0, round_teacher_limit(round_index) - completed_in_round)
        if remaining_in_round == 0:
            continue
        proposals = propose(
            backend,
            kernel_name=kernel.name,
            target_function=kernel.target_function,
            original_source=original_source,
            baseline_remarks=baseline_remarks,
            baseline_runtime=clang_baseline_runtime,
            history=history,
            round_index=round_index,
            max_candidates=min(remaining_in_round, config.max_teachers - teacher_count),
            remaining_teacher_budget=config.max_teachers - teacher_count,
            out_dir=resume_artifact_dir(out_dir / f"oracle_round_{round_index}"),
            repo_root=config.repo_root,
            opt_level=config.opt_level,
            fast_math=config.fast_math,
            dataset=config.dataset,
        )
        if not proposals:
            break
        for proposal in proposals:
            teacher_count += 1
            local_direction_id = proposal.get("direction_id") or f"D{teacher_count}"
            direction_id = global_direction_id(round_index, local_direction_id)
            used_direction_ids = {str(entry.get("direction_id")) for entry in history}
            if direction_id in used_direction_ids:
                base_direction_id = direction_id
                resume_index = 1
                while direction_id in used_direction_ids:
                    direction_id = f"{base_direction_id}_resume_{resume_index}"
                    resume_index += 1
            proposal = dict(proposal)
            proposal["local_direction_id"] = local_direction_id
            proposal["direction_id"] = direction_id
            teacher_dir = out_dir / "teachers" / direction_id
            ensure_dir(teacher_dir)
            write_json(teacher_dir / "proposal.json", proposal)
            teacher_source = teacher_dir / "source.c"
            try:
                patch_source(kernel.source, proposal.get("source_patch", ""), teacher_source)
            except Exception as exc:
                entry = {"direction_id": direction_id, "compile_ok": False, "error": f"patch failed: {exc}"}
                history.append(entry)
                write_json(teacher_dir / "runtime.json", entry)
                write_json(out_dir / "teacher_history.json", history)
                if adapter is not None:
                    adapter.progress_update('Teacher', entry)
                continue
            eval_result = evaluate(
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
                "correctness_checked": eval_result.correctness is not None,
                "runtime": eval_result.timing.median if eval_result.timing else None,
                "teacher_speedup_vs_clang": eval_result.speedup_vs_baseline,
                "error": eval_result.error,
            }
            history.append(entry)
            write_json(teacher_dir / "runtime.json", entry)
            write_json(out_dir / "teacher_history.json", history)
            if adapter is not None:
                adapter.progress_update('Teacher', entry)
            if not (eval_result.compile_ok and eval_result.timing and eval_result.timing.median):
                continue
            if eval_result.timing.median >= clang_baseline_runtime and not config.uniform_fixed_recovery_budget:
                continue
            teacher_remarks_path = eval_result.artifacts.remarks
            teacher_remarks = teacher_remarks_path.read_text(errors="replace") if teacher_remarks_path and teacher_remarks_path.exists() else ""
            direction = distill_direction(
                backend,
                direction_id=direction_id,
                original_source=original_source,
                teacher_source=source_text(teacher_source),
                original_remarks=baseline_remarks,
                teacher_remarks=teacher_remarks,
                baseline_runtime=clang_baseline_runtime,
                teacher_runtime=eval_result.timing.median,
                out_dir=teacher_dir / "distill",
                repo_root=config.repo_root,
            )
            direction["direction_id"] = direction_id
            direction["local_direction_id"] = local_direction_id
            write_json(teacher_dir / "intent.json", direction)
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
    # Keep the saved baseline fixed across teacher generation and recovery/resume.
    if config.uniform_fixed_recovery_budget:
        for teacher_index, item in enumerate(valid_directions):
            final_quota = uniform_round_target(
                config.max_pass_candidates,
                len(valid_directions),
                teacher_index,
                config.max_recovery_rounds,
                config.max_recovery_rounds,
            )
            teacher_used = item["entry"].get("recovery", {}).get("candidates_tried", 0)
            if item["rounds_done"] >= config.max_recovery_rounds and teacher_used < final_quota:
                item["rounds_done"] = config.max_recovery_rounds - 1
    while valid_directions and pass_budget_used < config.max_pass_candidates:
        progressed = False
        for teacher_index, item in enumerate(valid_directions):
            if pass_budget_used >= config.max_pass_candidates:
                break
            if item["rounds_done"] >= config.max_recovery_rounds:
                continue
            remaining = max(0, config.max_pass_candidates - pass_budget_used)
            if config.uniform_fixed_recovery_budget:
                cumulative_target = uniform_round_target(
                    config.max_pass_candidates,
                    len(valid_directions),
                    teacher_index,
                    item["rounds_done"] + 1,
                    config.max_recovery_rounds,
                )
                teacher_used = item["entry"].get("recovery", {}).get("candidates_tried", 0)
                batch_budget = min(max(0, cumulative_target - teacher_used), remaining)
            else:
                batch_budget = min(3, remaining)
            if batch_budget <= 0:
                break
            recovery_kwargs = {"adapter": adapter} if adapter else {}
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
                **recovery_kwargs,
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
    latest_recovery = {item.get("direction_id"): item for item in recovery_summaries}
    final_recoveries = list(latest_recovery.values())
    best_recovery = max(final_recoveries, key=lambda r: r.get("best_speedup") or 0, default=None)
    failure_counts: dict[str, int] = {}
    for recovery in final_recoveries:
        for failure_class, count in recovery.get("failure_counts", {}).items():
            failure_counts[failure_class] = failure_counts.get(failure_class, 0) + int(count)
    recovery_depth = []
    for recovery in final_recoveries:
        running_best = search_baseline_runtime
        trajectory = [{"candidate_count": 0, "candidate_id": "SEARCH_BASELINE", "round": 0, "best_runtime": running_best}]
        for candidate_count, candidate in enumerate(recovery.get("history", []), start=1):
            runtime = candidate.get("runtime")
            if runtime is not None and runtime < running_best:
                running_best = runtime
                trajectory.append(
                    {
                        "candidate_count": candidate_count,
                        "candidate_id": candidate.get("candidate_id"),
                        "round": candidate.get("round"),
                        "best_runtime": running_best,
                    }
                )
        recovery_depth.append({"direction_id": recovery.get("direction_id"), "trajectory": trajectory})
    summary = {
        "clang_baseline_runtime": clang_baseline_runtime,
        "search_baseline_runtime": search_baseline_runtime,
        "teacher_candidates_tried": teacher_count,
        "teacher_correct_count": sum(h.get("correctness_checked", False) and h.get("correctness_ok") is True for h in history),
        "teacher_incorrect_count": sum(h.get("correctness_checked", False) and h.get("correctness_ok") is False for h in history),
        "teacher_unchecked_count": sum(not h.get("correctness_checked", False) for h in history),
        "valid_teacher_count": len(valid_directions),
        "pass_candidates_tried": pass_budget_used,
        "total_recovery_budget": config.max_pass_candidates,
        "recovery_budget_allocation": "uniform_fixed" if config.uniform_fixed_recovery_budget else "round_robin_3",
        "best_teacher": best_teacher,
        "best_recovery": best_recovery,
        "evaluated_candidates": sum(int(item.get("valid_pipeline_candidates", 0)) for item in final_recoveries),
        "measured_candidates": sum(int(item.get("measured_candidates", 0)) for item in final_recoveries),
        "failure_counts": failure_counts,
        "recovery_depth": recovery_depth,
        "recovery_summaries": final_recoveries,
        "history": history,
    }
    write_json(out_dir / "summary.json", summary)
    return summary
