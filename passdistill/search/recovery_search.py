from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from passdistill.agents.base import AgentBackend
from passdistill.agents.catalog import build_pass_catalog, relevant_catalog
from passdistill.agents.feedback import parse_optimization_remarks, select_relevant_remark_events, structured_remarks, summarize_remarks_text
from passdistill.agents.recovery_planner import plan_recovery_candidates
from passdistill.config import ExperimentConfig
from passdistill.evaluator import evaluate_pipeline_candidate
from passdistill.pipeline import PipelineEditor, local_region
from passdistill.types import Kernel
from passdistill.util import ensure_dir, read_json, write_json


def global_candidate_id(direction_id: str, round_index: int, local_id: str) -> str:
    safe_direction = str(direction_id or "direction").replace("/", "_")
    safe_local = str(local_id or "candidate").replace("/", "_")
    return f"{safe_direction}_R{round_index}_{safe_local}"


def sanitize_local_candidate_id(raw: Any, fallback_index: int) -> str:
    text = str(raw or "").strip()
    match = re.search(r"(?:^|_)C(\d+)$", text)
    if match:
        return f"C{match.group(1)}"
    if re.fullmatch(r"C\d+", text):
        return text
    return f"C{fallback_index}"


def normalize_error(error: str, limit: int = 600) -> str:
    text = " ".join((error or "").split())
    return text[:limit]


def requested_candidate_count(remaining_kernel_budget: int, remaining_episode_budget: int, per_round_limit: int = 3) -> int:
    return max(0, min(per_round_limit, remaining_kernel_budget, remaining_episode_budget))


def _speedup(base: float | None, runtime: float | None) -> float | None:
    return base / runtime if base and runtime else None


def _parent_summary(parent_id: str, runtime: float, pipeline: str, baseline_runtime: float) -> dict[str, Any]:
    return {
        "candidate_id": parent_id,
        "runtime": runtime,
        "speedup_vs_search_baseline": _speedup(baseline_runtime, runtime),
        "local_pipeline": local_region(pipeline),
    }


def _allowed_parents(parents: dict[str, dict[str, Any]], promoted_id: str, measured_best_id: str, baseline_runtime: float) -> list[dict[str, Any]]:
    allowed: list[dict[str, Any]] = []
    if promoted_id in parents:
        promoted = _parent_summary(promoted_id, parents[promoted_id]["runtime"], parents[promoted_id]["pipeline"], baseline_runtime)
        promoted["candidate_id"] = "CURRENT_PROMOTED_BEST"
        promoted["resolves_to"] = promoted_id
        allowed.append(promoted)
    for parent_id in ["SEARCH_BASELINE", promoted_id, measured_best_id, *parents.keys()]:
        if parent_id not in parents or any(item["candidate_id"] == parent_id for item in allowed):
            continue
        parent = parents[parent_id]
        allowed.append(_parent_summary(parent_id, parent["runtime"], parent["pipeline"], baseline_runtime))
        if len(allowed) >= 6:
            break
    return allowed


def _resolve_parent_id(raw_parent_id: str | None, promoted_id: str, parents: dict[str, dict[str, Any]]) -> str:
    if raw_parent_id in parents:
        return str(raw_parent_id)
    if raw_parent_id == "CURRENT_PROMOTED_BEST":
        return promoted_id
    return "SEARCH_BASELINE"


def _candidate_fragment(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "parent_id": candidate.get("parent_id"),
        "edits": candidate.get("edits", []),
        "opt_options": candidate.get("opt_options", []),
        "legacy_operations": candidate.get("operations", []),
    }


def run_recovery_episode(
    config: ExperimentConfig,
    backend: AgentBackend,
    kernel: Kernel,
    *,
    direction: dict[str, Any],
    frontend_ir: Path,
    baseline_pipeline: str,
    baseline_dump: Path,
    baseline_runtime: float,
    out_dir: Path,
    remaining_budget: int,
    start_round: int = 1,
    max_rounds: int | None = None,
) -> dict[str, Any]:
    ensure_dir(out_dir)
    history: list[dict[str, Any]] = read_json(out_dir / "history.json") if (out_dir / "history.json").exists() else []
    previous_summary = read_json(out_dir / "summary.json") if (out_dir / "summary.json").exists() else {}
    previous_candidates = int(previous_summary.get("candidates_tried", 0))
    candidates_tried = previous_candidates
    stats = {
        "proposed_candidates": int(previous_summary.get("proposed_candidates", 0)),
        "valid_pipeline_candidates": int(previous_summary.get("valid_pipeline_candidates", 0)),
        "compiled_candidates": int(previous_summary.get("compiled_candidates", 0)),
        "correctness_pass_candidates": int(previous_summary.get("correctness_pass_candidates", 0)),
        "measured_candidates": int(previous_summary.get("measured_candidates", 0)),
    }

    catalog = build_pass_catalog(config, out_dir / "catalog", baseline_pipeline)
    direction_id = str(direction.get("direction_id") or out_dir.name)
    parents: dict[str, dict[str, Any]] = {
        "SEARCH_BASELINE": {
            "pipeline": baseline_pipeline,
            "runtime": baseline_runtime,
            "speedup_vs_search_baseline": 1.0,
        }
    }
    for item in history:
        if item.get("status") == "measured" and item.get("pipeline") and item.get("runtime"):
            parents[item["candidate_id"]] = {
                "pipeline": item["pipeline"],
                "runtime": item["runtime"],
                "speedup_vs_search_baseline": item.get("speedup_vs_search_baseline"),
            }

    best_id = previous_summary.get("current_measured_best_id", "SEARCH_BASELINE")
    promoted_id = previous_summary.get("current_promoted_parent_id", best_id)
    best_runtime = float(previous_summary.get("best_runtime", baseline_runtime))
    best_pipeline = previous_summary.get("best_pipeline", baseline_pipeline)
    promotion_min_relative_gain = float(getattr(config, "promotion_min_relative_gain", 0.01))
    if best_id not in parents:
        best_id = "SEARCH_BASELINE"
    if promoted_id not in parents:
        promoted_id = best_id

    round_limit = config.max_recovery_rounds if max_rounds is None else start_round + max_rounds - 1
    for round_index in range(start_round, min(config.max_recovery_rounds, round_limit) + 1):
        local_used = candidates_tried - previous_candidates
        requested = requested_candidate_count(remaining_budget - local_used, remaining_budget - local_used)
        if requested <= 0:
            break
        current_parent = parents[promoted_id]
        baseline_context = {
            "candidate_id": "SEARCH_BASELINE",
            "runtime": baseline_runtime,
            "local_pipeline": local_region(baseline_pipeline),
        }
        current_promoted_parent = _parent_summary(promoted_id, current_parent["runtime"], current_parent["pipeline"], baseline_runtime)
        current_measured_best = _parent_summary(best_id, parents[best_id]["runtime"], parents[best_id]["pipeline"], baseline_runtime)
        allowed = _allowed_parents(parents, promoted_id, best_id, baseline_runtime)
        rel_catalog = relevant_catalog(
            catalog,
            direction=direction,
            baseline_pipeline=baseline_pipeline,
            current_pipeline=current_parent["pipeline"],
        )
        planned = plan_recovery_candidates(
            backend,
            direction=direction,
            baseline_context=baseline_context,
            current_promoted_parent=current_promoted_parent,
            current_measured_best=current_measured_best,
            allowed_parents=allowed,
            previous_history=history,
            relevant_catalog=rel_catalog,
            remaining_budget=remaining_budget - local_used,
            round_index=round_index,
            max_candidates=requested,
            out_dir=out_dir / f"planner_round_{round_index}",
            repo_root=config.repo_root,
        )
        if not planned:
            break
        for local_index, candidate in enumerate(planned, start=1):
            local_used = candidates_tried - previous_candidates
            if local_used >= remaining_budget:
                break
            local_candidate_id = sanitize_local_candidate_id(candidate.get("candidate_id"), local_index)
            candidate_id = global_candidate_id(direction_id, round_index, local_candidate_id)
            parent_id = _resolve_parent_id(candidate.get("parent_id"), promoted_id, parents)
            parent = parents[parent_id]
            candidate_dir = ensure_dir(out_dir / "candidates" / candidate_id)
            write_json(candidate_dir / "planner_fragment.json", candidate)
            (candidate_dir / "parent_id.txt").write_text(parent_id + "\n")
            write_json(candidate_dir / "parent_metadata.json", _parent_summary(parent_id, parent["runtime"], parent["pipeline"], baseline_runtime))
            (candidate_dir / "parent_pipeline.txt").write_text(parent["pipeline"] + "\n")

            editor = PipelineEditor(parent["pipeline"], catalog=rel_catalog)
            edit_result = editor.apply_candidate(candidate)
            (candidate_dir / "materialized_pipeline.txt").write_text(edit_result.pipeline + "\n")
            candidates_tried += 1
            stats["proposed_candidates"] += 1

            eval_result = None
            status = "invalid_candidate"
            remarks_text = ""
            error = "; ".join(edit_result.invalid_errors)
            if edit_result.valid:
                stats["valid_pipeline_candidates"] += 1
                eval_result = evaluate_pipeline_candidate(
                    config,
                    kernel,
                    frontend_ir,
                    edit_result.pipeline,
                    candidate_dir,
                    candidate_id,
                    baseline_dump=baseline_dump,
                    baseline_runtime=baseline_runtime,
                    extra_options=edit_result.opt_options,
                )
                if not eval_result.compile_ok and eval_result.command_log and eval_result.command_log[0].get("phase") == "preflight":
                    status = "preflight_failed"
                elif not eval_result.compile_ok:
                    status = "compile_failed"
                elif eval_result.correctness and not eval_result.correctness.ok:
                    status = "correctness_failed"
                elif eval_result.timing and eval_result.timing.median:
                    status = "measured"
                else:
                    status = "unknown_failed"
                if eval_result.compile_ok:
                    stats["compiled_candidates"] += 1
                if eval_result.correctness and eval_result.correctness.ok:
                    stats["correctness_pass_candidates"] += 1
                if eval_result.timing and eval_result.timing.median:
                    stats["measured_candidates"] += 1
                if eval_result.artifacts.remarks and eval_result.artifacts.remarks.exists():
                    remarks_text = eval_result.artifacts.remarks.read_text(errors="replace")
                    target_function = f"kernel_{kernel.name.replace('-', '_')}"
                    remark_events = select_relevant_remark_events(parse_optimization_remarks(remarks_text), target_function=target_function, limit=30)
                    write_json(candidate_dir / "structured_remarks.json", structured_remarks(remark_events))
                error = eval_result.error
            else:
                write_json(
                    candidate_dir / "invalid_candidate.json",
                    {
                        "candidate_id": candidate_id,
                        "parent_id": parent_id,
                        "status": status,
                        "errors": edit_result.invalid_errors,
                        "warnings": edit_result.warnings,
                    },
                )

            runtime = eval_result.timing.median if eval_result and eval_result.timing else None
            speedup_vs_search = eval_result.speedup_vs_baseline if eval_result else None
            speedup_vs_parent = _speedup(parent["runtime"], runtime)
            speedup_vs_current_best = _speedup(best_runtime, runtime)
            feedback = {
                "candidate_id": candidate_id,
                "local_candidate_id": local_candidate_id,
                "round": round_index,
                "parent_id": parent_id,
                "status": status,
                "hypothesis": candidate.get("hypothesis", ""),
                "edits": candidate.get("edits", []),
                "opt_options": edit_result.opt_options,
                "pipeline_warnings": edit_result.warnings,
                "compile_ok": bool(eval_result and eval_result.compile_ok),
                "correctness_ok": bool(eval_result and eval_result.correctness and eval_result.correctness.ok),
                "runtime": runtime,
                "speedup_vs_search_baseline": speedup_vs_search,
                "speedup_vs_parent": speedup_vs_parent,
                "speedup_vs_current_best": speedup_vs_current_best,
                "normalized_error": normalize_error(error),
                "important_remarks": summarize_remarks_text(remarks_text, target_function=f"kernel_{kernel.name.replace('-', '_')}", limit=30),
                "error": error,
                "pipeline_fragment": _candidate_fragment(candidate),
                "pipeline": edit_result.pipeline,
            }
            write_json(candidate_dir / "candidate_summary.json", feedback)
            history.append(feedback)
            write_json(out_dir / "history.json", history)

            if status == "measured":
                parents[candidate_id] = {
                    "pipeline": edit_result.pipeline,
                    "runtime": runtime,
                    "speedup_vs_search_baseline": speedup_vs_search,
                }
                if runtime is not None and runtime < best_runtime:
                    best_runtime = runtime
                    best_pipeline = edit_result.pipeline
                    best_id = candidate_id
                if runtime is not None:
                    promoted_runtime = parents[promoted_id]["runtime"]
                    gain_vs_promoted = (promoted_runtime - runtime) / promoted_runtime if promoted_runtime else 0.0
                    if gain_vs_promoted >= promotion_min_relative_gain:
                        promoted_id = candidate_id

    new_candidates = candidates_tried - previous_candidates
    summary = {
        "direction_id": direction.get("direction_id"),
        "search_baseline_runtime": baseline_runtime,
        "candidates_tried": candidates_tried,
        "new_candidates_tried": new_candidates,
        **stats,
        "current_promoted_parent_id": promoted_id,
        "current_measured_best_id": best_id,
        "promotion_min_relative_gain": promotion_min_relative_gain,
        "best_runtime": best_runtime,
        "best_speedup": baseline_runtime / best_runtime if best_runtime else None,
        "best_speedup_vs_search": baseline_runtime / best_runtime if best_runtime else None,
        "best_pipeline": best_pipeline,
        "history": history,
    }
    write_json(out_dir / "summary.json", summary)
    return summary
