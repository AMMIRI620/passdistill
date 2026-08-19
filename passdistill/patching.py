from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .util import ensure_dir


@dataclass(frozen=True)
class FunctionSpan:
    start: int
    end: int
    text: str


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].strip().lower() in {"```", "```c"}:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _match_balanced(text: str, open_index: int, opener: str, closer: str) -> int:
    depth = 0
    in_line_comment = False
    in_block_comment = False
    in_string: str | None = None
    escape = False
    index = open_index
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            index += 1
            continue
        if in_block_comment:
            if char == "*" and nxt == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == in_string:
                in_string = None
            index += 1
            continue

        if char == "/" and nxt == "/":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and nxt == "*":
            in_block_comment = True
            index += 2
            continue
        if char in {'"', "'"}:
            in_string = char
            index += 1
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError(f"unmatched {opener!r} starting at offset {open_index}")


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def extract_function_span(text: str, function_name: str) -> FunctionSpan:
    name_index = text.find(function_name)
    if name_index < 0:
        raise ValueError(f"function {function_name} not found")
    start = text.rfind("\n", 0, name_index)
    start = 0 if start < 0 else start + 1

    open_paren = text.find("(", name_index + len(function_name))
    if open_paren < 0:
        raise ValueError(f"function {function_name} has no parameter list")
    close_paren = _match_balanced(text, open_paren, "(", ")")

    body_index = _skip_space(text, close_paren + 1)
    while body_index < len(text) and text[body_index : body_index + 2] in {"__", "[["}:
        next_brace = text.find("{", body_index)
        if next_brace < 0:
            break
        body_index = _skip_space(text, next_brace)
        break
    if body_index >= len(text) or text[body_index] != "{":
        body_index = text.find("{", close_paren + 1)
    if body_index < 0:
        raise ValueError(f"function {function_name} has no body")
    end_brace = _match_balanced(text, body_index, "{", "}")
    end = end_brace + 1
    return FunctionSpan(start=start, end=end, text=text[start:end])


def _kernel_name_from_source(text: str) -> str:
    marker = "kernel_"
    index = text.find(marker)
    if index < 0:
        raise ValueError("no kernel_* function found")
    end = index
    while end < len(text) and (text[end].isalnum() or text[end] in "_-"):
        end += 1
    return text[index:end]


def apply_teacher_patch(original: Path, patch_text: str, output: Path) -> None:
    ensure_dir(output.parent)
    original_text = original.read_text()
    output.write_text(original_text)
    text = strip_code_fence(patch_text)
    if not text:
        raise ValueError("empty teacher source_patch")
    if text.startswith("--- ") or text.startswith("diff "):
        proc = subprocess.run(
            ["patch", str(output)],
            input=text,
            text=True,
            cwd=str(output.parent),
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr or proc.stdout)
        return
    if "kernel_" in text and "#include" in text:
        target_name = _kernel_name_from_source(original_text)
        extract_function_span(text, target_name)
        output.write_text(text)
        return
    if "kernel_" in text:
        target_name = _kernel_name_from_source(original_text)
        original_span = extract_function_span(original_text, target_name)
        replacement_span = extract_function_span(text, target_name)
        new_source = original_text[: original_span.start] + replacement_span.text + original_text[original_span.end :]
        extract_function_span(new_source, target_name)
        output.write_text(new_source)
        return
    raise ValueError("source_patch must be a unified diff, full source, or full kernel function")
