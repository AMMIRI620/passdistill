from __future__ import annotations

from pathlib import Path
from typing import Any

from passdistill.patching import extract_function_span
from passdistill.util import write_json

from .base import AgentBackend
from .feedback import grouped_remark_feedback, parse_optimization_remarks, select_relevant_remark_events, source_line_range, structured_remarks
from .prompts import load_prompt


def compact_teacher_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in history:
        recovery = item.get("recovery", {}) if isinstance(item, dict) else {}
        compact.append(
            {
                "teacher": item.get("direction_id"),
                "source_optimization_intent": item.get("summary") or item.get("optimization_idea") or item.get("intent"),
                "compile_ok": item.get("compile_ok"),
                "correctness_ok": item.get("correctness_ok"),
                "teacher_runtime": item.get("runtime"),
                "teacher_speedup_vs_clang": item.get("teacher_speedup_vs_clang"),
                "recovery_best_gain": recovery.get("best_speedup_vs_search"),
                "main_recovery_blocker": recovery.get("main_blocker") or recovery.get("main_recovery_blocker"),
            }
        )
    return compact


def propose_teachers(
    backend: AgentBackend,
    *,
    kernel_name: str,
    target_function: str | None = None,
    original_source: str,
    baseline_remarks: str,
    baseline_runtime: float,
    history: list[dict[str, Any]],
    round_index: int,
    max_candidates: int,
    remaining_teacher_budget: int,
    out_dir: Path,
    repo_root: Path = Path.cwd(),
) -> list[dict[str, Any]]:
    system = load_prompt(repo_root, "source_oracle")
    target_function = target_function or f"kernel_{kernel_name.replace('-', '_')}"
    try:
        kernel_span = extract_function_span(original_source, target_function)
        target_source = kernel_span.text
        kernel_range = source_line_range(original_source, target_source)
    except ValueError:
        target_source = original_source
        kernel_range = None
    events = parse_optimization_remarks(baseline_remarks)
    filtered_events = select_relevant_remark_events(events, target_function=target_function, kernel_range=kernel_range, limit=40)
    write_json(out_dir / "structured_remarks.json", structured_remarks(filtered_events))
    feedback = grouped_remark_feedback(filtered_events)
    history_text = compact_teacher_history(history) if history else "None."
    user = f"""Kernel: {kernel_name}
Target function: {target_function}

Teacher round: {round_index}
Requested new directions this round: {max_candidates}

Experiment:
- LLVM version: 22.1.3
- Optimization level: -O3 -ffast-math
- dataset: LARGE_DATASET
- Baseline runtime: {baseline_runtime} s (clang median)

Previous teacher/recovery feedback:
{history_text}

Relevant compiler feedback for {target_function}:
{feedback}

Target kernel source:
```c
{target_source}
```

Instruction:
Generate exactly {max_candidates} meaningfully different teacher directions.
Return JSON only using the required schema."""
    data = backend.complete_json(system, user, schema_hint="source_oracle.v1", out_dir=out_dir)
    if isinstance(data, list):
        return data[:max_candidates]
    return data.get("directions", data.get("candidates", []))[:max_candidates]
