from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from passdistill.reporting import filter_remarks


HIGH_VALUE_PASSES = {
    "loop-vectorize",
    "slp-vectorizer",
    "loop-interchange",
    "loop-distribute",
    "loop-unroll",
    "loop-unroll-and-jam",
    "licm",
    "gvn",
    "loop-delete",
    "loop-simplify",
    "lcssa",
    "indvars",
    "dse",
    "mldst-motion",
    "loop-load-elim",
}

LOW_VALUE_PASSES = {"inline", "function-attrs", "argpromotion"}
NON_TARGET_FUNCTIONS = {
    "main",
    "init_array",
    "print_array",
    "rtclock",
    "xmalloc",
    "polybench_flush_cache",
    "polybench_prepare_instruments",
    "polybench_timer_start",
    "polybench_timer_stop",
    "polybench_timer_print",
    "polybench_alloc_data",
    "polybench_free_data",
}


@dataclass
class RemarkEvent:
    kind: str
    pass_name: str = ""
    name: str = ""
    function: str = ""
    file: str = ""
    line: int | None = None
    column: int | None = None
    message: str = ""

    def category(self) -> str:
        if self.pass_name in {"loop-vectorize", "slp-vectorizer"}:
            return "loop-vectorization"
        if self.pass_name in {"loop-interchange", "loop-distribute", "loop-unroll", "loop-unroll-and-jam", "loop-simplify", "lcssa", "indvars"}:
            return "loop-transformations"
        if self.pass_name in {"licm", "gvn", "dse", "mldst-motion", "loop-load-elim"}:
            return "memory-locality"
        return "other"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "pass": self.pass_name,
            "name": self.name,
            "function": self.function,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "message": self.message or self.name,
            "category": self.category(),
        }

    def location(self) -> str:
        if not self.file:
            return "<unknown>"
        if self.line is None:
            return self.file
        if self.column is None:
            return f"{self.file}:{self.line}"
        return f"{self.file}:{self.line}:{self.column}"

    def format(self) -> str:
        function = self.function or "<unknown>"
        return f"[{self.kind}][{self.pass_name}] function: {function} location: {self.location()} message: {self.message or self.name}"


def _clean_value(value: str) -> str:
    value = value.strip().rstrip(",")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def _extract_debug_loc(block: str) -> tuple[str, int | None, int | None]:
    match = re.search(r"DebugLoc:\s*\{\s*File:\s*([^,\n]+),\s*\n?\s*Line:\s*([^,\n}]+),\s*Column:\s*([^,\n}]+)", block)
    if not match:
        return "", None, None
    file_name = _clean_value(match.group(1))
    try:
        line = int(_clean_value(match.group(2)))
    except ValueError:
        line = None
    try:
        column = int(_clean_value(match.group(3)))
    except ValueError:
        column = None
    return file_name, line, column


def _extract_scalar(block: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    return _clean_value(match.group(1)) if match else ""


def _extract_args_message(block: str) -> str:
    args_match = re.search(r"^Args:\s*$([\s\S]*?)(?:^\.\.\.|\Z)", block, flags=re.MULTILINE)
    if not args_match:
        return ""
    parts: list[str] = []
    for raw in args_match.group(1).splitlines():
        match = re.match(r"\s*-\s+([A-Za-z0-9_]+):\s*(.+?)\s*$", raw)
        if not match:
            match = re.match(r"\s+([A-Za-z0-9_]+):\s*(.+?)\s*$", raw)
        if not match:
            continue
        key, value = match.group(1), _clean_value(match.group(2))
        if key == "DebugLoc":
            continue
        parts.append(value)
    return "".join(parts).strip()


def parse_optimization_remarks(text: str) -> list[RemarkEvent]:
    events: list[RemarkEvent] = []
    for raw in re.split(r"(?=^---\s+!)", text, flags=re.MULTILINE):
        block = raw.strip()
        if not block.startswith("--- !"):
            continue
        first = block.splitlines()[0]
        kind = first.removeprefix("--- !").strip()
        file_name, line, column = _extract_debug_loc(block)
        events.append(
            RemarkEvent(
                kind=kind,
                pass_name=_extract_scalar(block, "Pass"),
                name=_extract_scalar(block, "Name"),
                function=_extract_scalar(block, "Function"),
                file=file_name,
                line=line,
                column=column,
                message=_extract_args_message(block),
            )
        )
    return events


def source_line_range(source: str, function_text: str) -> tuple[int, int] | None:
    start = source.find(function_text)
    if start < 0:
        return None
    start_line = source[:start].count("\n") + 1
    end_line = start_line + function_text.count("\n")
    return start_line, end_line


def _kernel_relevance(event: RemarkEvent, target_function: str | None, kernel_range: tuple[int, int] | None) -> int:
    if target_function and event.function == target_function:
        return 0
    if kernel_range and event.line is not None and kernel_range[0] <= event.line <= kernel_range[1]:
        return 1
    if event.function in {"init_array", "print_array", "main"}:
        return 5
    if event.pass_name in HIGH_VALUE_PASSES:
        return 2
    if event.pass_name in LOW_VALUE_PASSES:
        return 4
    return 3


def select_relevant_remark_events(
    events: list[RemarkEvent],
    *,
    target_function: str | None = None,
    kernel_range: tuple[int, int] | None = None,
    limit: int = 40,
) -> list[RemarkEvent]:
    target_mode = bool(target_function or kernel_range)
    candidates = events
    if target_mode:
        candidates = [
            event
            for event in events
            if event.function not in NON_TARGET_FUNCTIONS and not event.function.startswith("polybench_")
        ]
    ranked = sorted(
        candidates,
        key=lambda event: (
            _kernel_relevance(event, target_function, kernel_range),
            0 if event.pass_name in HIGH_VALUE_PASSES else 1,
            event.pass_name,
            event.line or 10**9,
        ),
    )
    selected = [event for event in ranked if _kernel_relevance(event, target_function, kernel_range) < 5]
    return selected[:limit]


def grouped_remark_feedback(events: list[RemarkEvent]) -> str:
    groups = [
        ("Loop vectorization", {"loop-vectorize", "slp-vectorizer"}),
        ("Loop transformations", {"loop-interchange", "loop-distribute", "loop-unroll", "loop-unroll-and-jam", "loop-simplify", "lcssa", "indvars"}),
        ("Memory / locality", {"licm", "gvn", "dse", "mldst-motion", "loop-load-elim"}),
        ("Other relevant", set()),
    ]
    remaining = list(events)
    lines: list[str] = []
    for title, passes in groups:
        if passes:
            group = [event for event in remaining if event.pass_name in passes]
        else:
            group = remaining
        if not group:
            continue
        lines.append(f"{title}:")
        for event in group:
            lines.append(f"- {event.format()}")
        remaining = [event for event in remaining if event not in group]
    return "\n".join(lines) if lines else "None."


def structured_remarks(events: list[RemarkEvent]) -> list[dict]:
    return [event.to_dict() for event in events]


def summarize_remarks_text(
    text: str,
    *,
    limit: int = 60,
    target_function: str | None = None,
    kernel_range: tuple[int, int] | None = None,
) -> list[str]:
    events = parse_optimization_remarks(text)
    if not events:
        return filter_remarks(text, limit=limit)
    return [event.format() for event in select_relevant_remark_events(events, target_function=target_function, kernel_range=kernel_range, limit=limit)]


def summarize_remarks_file(path: Path | None, *, limit: int = 60) -> list[str]:
    if path is None or not path.exists():
        return []
    return summarize_remarks_text(path.read_text(errors="replace"), limit=limit)


def format_lines(lines: Iterable[str]) -> str:
    values = list(lines)
    return "\n".join(f"- {line}" for line in values) if values else "none"
