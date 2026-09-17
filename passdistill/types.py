from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


def to_jsonable(value: Any) -> Any:
    if isinstance(value, CommandResult):
        return {
            "argv": value.argv,
            "returncode": value.returncode,
            "elapsed_sec": value.elapsed_sec,
            "stdout_path": str(value.stdout_path) if value.stdout_path else None,
            "stderr_path": str(value.stderr_path) if value.stderr_path else None,
            "timed_out": value.timed_out,
        }
    if hasattr(value, "__dataclass_fields__"):
        return {item.name: to_jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    elapsed_sec: float = 0.0
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class Kernel:
    name: str
    source: Path
    header: Path
    rel_dir: Path
    target_function: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimingResult:
    warmups: list[float] = field(default_factory=list)
    measured: list[float] = field(default_factory=list)
    median: float | None = None


@dataclass
class CorrectnessResult:
    ok: bool
    message: str = ""
    mismatches: int = 0
    expected_md5: str | None = None
    actual_md5: str | None = None


@dataclass
class BuildArtifacts:
    binary: Path | None = None
    dump_stdout: Path | None = None
    dump_stderr: Path | None = None
    remarks: Path | None = None
    frontend_ir: Path | None = None
    optimized_ir: Path | None = None
    pipeline: Path | None = None


@dataclass
class EvaluationResult:
    candidate_id: str
    compile_ok: bool
    correctness: CorrectnessResult | None = None
    timing: TimingResult | None = None
    speedup_vs_baseline: float | None = None
    command_log: list[dict[str, Any]] = field(default_factory=list)
    artifacts: BuildArtifacts = field(default_factory=BuildArtifacts)
    error: str = ""
