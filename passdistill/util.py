from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .types import CommandResult, to_jsonable


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(to_jsonable(data), indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def run_command(
    argv: list[str],
    cwd: Path,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    start = time.perf_counter()
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(
        argv=argv,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        elapsed_sec=time.perf_counter() - start,
    )


def save_command_result(path: Path, result: CommandResult) -> None:
    ensure_dir(path.parent)
    stdout_path = result.stdout_path or path.with_suffix(".stdout")
    stderr_path = result.stderr_path or path.with_suffix(".stderr")
    stdout_path.write_text(result.stdout)
    stderr_path.write_text(result.stderr)
    result.stdout_path = stdout_path
    result.stderr_path = stderr_path
    write_json(path, result)
