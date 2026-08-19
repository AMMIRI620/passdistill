from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPT_FILES = {
    "source_oracle": "Source Oracle Prompt.md",
    "direction_distiller": "Direction Distiller Prompt.md",
    "recovery_planner": "Recovery Planner Prompt.md",
}


@lru_cache(maxsize=None)
def load_prompt(repo_root: Path, agent_name: str) -> str:
    try:
        filename = PROMPT_FILES[agent_name]
    except KeyError as exc:
        raise KeyError(f"unknown prompt template: {agent_name}") from exc
    path = repo_root / "prompt" / filename
    if not path.exists():
        raise FileNotFoundError(f"missing prompt template for {agent_name}: {path}")
    return path.read_text()

