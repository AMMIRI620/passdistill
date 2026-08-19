from __future__ import annotations

from pathlib import Path

from .base import AgentBackend
from .feedback import format_lines, summarize_remarks_text
from .prompts import load_prompt


def distill_direction(
    backend: AgentBackend,
    *,
    direction_id: str,
    original_source: str,
    teacher_source: str,
    original_remarks: str,
    teacher_remarks: str,
    baseline_runtime: float,
    teacher_runtime: float,
    out_dir: Path,
    repo_root: Path = Path.cwd(),
    ir_observations: list[str] | None = None,
) -> dict:
    system = load_prompt(repo_root, "direction_distiller")
    baseline_feedback = summarize_remarks_text(original_remarks, limit=60)
    teacher_feedback = summarize_remarks_text(teacher_remarks, limit=60)
    observations = "\n".join(f"- {line}" for line in (ir_observations or [])) or "none"
    user = f"""direction_id: {direction_id}
clang baseline runtime: {baseline_runtime}
teacher runtime: {teacher_runtime}

filtered baseline LLVM optimization remarks:
{format_lines(baseline_feedback)}

filtered teacher LLVM optimization remarks:
{format_lines(teacher_feedback)}

selected IR observations:
{observations}

original kernel source:
```c
{original_source}
```

teacher kernel source:
```c
{teacher_source}
```

Return JSON using the schema from the system prompt."""
    return backend.complete_json(system, user, schema_hint="direction_distiller.v1", out_dir=out_dir)
