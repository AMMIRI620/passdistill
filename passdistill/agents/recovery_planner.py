from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .base import AgentBackend
from .prompts import load_prompt


def compact_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in history:
        compact.append(
            {
                "candidate_id": item.get("candidate_id"),
                "parent_id": item.get("parent_id"),
                "hypothesis": item.get("hypothesis"),
                "status": item.get("status"),
                "runtime": item.get("runtime"),
                "speedup_vs_search_baseline": item.get("speedup_vs_search_baseline"),
                "speedup_vs_parent": item.get("speedup_vs_parent"),
                "speedup_vs_current_best": item.get("speedup_vs_current_best"),
                "normalized_error": item.get("normalized_error"),
                "important_remarks": item.get("important_remarks", []),
                "edits": item.get("edits", []),
                "opt_options": item.get("opt_options", []),
                "pipeline_fragment": item.get("pipeline_fragment"),
            }
        )
    return compact


def local_candidate_id(raw: Any, fallback_index: int) -> str:
    text = str(raw or "").strip()
    match = re.search(r"(?:^|_)C(\d+)$", text)
    if match:
        return f"C{match.group(1)}"
    if re.fullmatch(r"C\d+", text):
        return text
    return f"C{fallback_index}"


def plan_recovery_candidates(
    backend: AgentBackend,
    *,
    direction: dict[str, Any],
    baseline_context: dict[str, Any],
    current_promoted_parent: dict[str, Any],
    current_measured_best: dict[str, Any],
    allowed_parents: list[dict[str, Any]],
    previous_history: list[dict[str, Any]],
    relevant_catalog: dict[str, Any],
    remaining_budget: int,
    round_index: int,
    max_candidates: int,
    out_dir: Path,
    repo_root: Path = Path.cwd(),
) -> list[dict[str, Any]]:
    system = load_prompt(repo_root, "recovery_planner")
    history_text: Any = compact_history(previous_history) if previous_history else "none"
    mode = "initial" if not previous_history else "feedback"
    user = f"""round: {round_index}
mode: {mode}
requested_candidates_count: {max_candidates}
remaining_budget: {remaining_budget}

direction:
{direction}

baseline_reference:
{baseline_context}

current_promoted_parent:
{current_promoted_parent}

current_measured_best:
{current_measured_best}

allowed_parents:
{allowed_parents}

previous_history:
{history_text}

relevant_catalog:
{relevant_catalog}

Return JSON using the schema from the system prompt. Every candidate must use one parent_id from allowed_parents. Do not output full LLVM pipelines."""
    (out_dir / "feedback_context.json").parent.mkdir(parents=True, exist_ok=True)
    from passdistill.util import write_json

    write_json(
        out_dir / "feedback_context.json",
        {
            "round": round_index,
            "mode": mode,
            "baseline_reference": baseline_context,
            "current_promoted_parent": current_promoted_parent,
            "current_measured_best": current_measured_best,
            "allowed_parents": allowed_parents,
            "previous_history": history_text,
            "relevant_catalog": relevant_catalog,
            "remaining_budget": remaining_budget,
            "requested_candidates_count": max_candidates,
        },
    )
    data = backend.complete_json(system, user, schema_hint="recovery_planner.v2", out_dir=out_dir)
    candidates = data if isinstance(data, list) else data.get("candidates", [])
    normalized = []
    for index, candidate in enumerate(candidates[:max_candidates], start=1):
        item = dict(candidate)
        item["candidate_id"] = local_candidate_id(item.get("candidate_id"), index)
        normalized.append(item)
    return normalized
