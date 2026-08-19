from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Toolchain:
    llvm_bin: Path = Path(
        os.environ.get(
            "LLVM_BIN",
            "/home/liujf/project/llvm22.1.3/llvm-project-llvmorg-22.1.3/build-stage1/bin",
        )
    )

    @property
    def clang(self) -> Path:
        return self.llvm_bin / "clang"

    @property
    def opt(self) -> Path:
        return self.llvm_bin / "opt"

    @property
    def llc(self) -> Path:
        return self.llvm_bin / "llc"


@dataclass
class ExperimentConfig:
    repo_root: Path = Path.cwd()
    polybench_root: Path = Path("third_party/polybench-c-4.2.1-beta")
    artifacts_root: Path = Path("artifacts/runs")
    dataset: str = "LARGE_DATASET"
    opt_level: str = "-O3"
    fast_math: bool = True
    cpu: int = 3
    numa_node: int = 0
    warmups: int = 1
    runs: int = 3
    rtol: float = 1e-4
    atol: float = 1e-6
    max_teacher_rounds: int = 3
    max_teachers: int = 6
    max_recovery_rounds: int = 3
    max_pass_candidates: int = 36
    promotion_min_relative_gain: float = 0.01
    llm_backend: str = "mock"
    model: str | None = None
    dry_run: bool = False
    baseline_only: bool = False
    resume: bool = False
    run_id: str | None = None
    toolchain: Toolchain = field(default_factory=Toolchain)

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        self.polybench_root = (self.repo_root / self.polybench_root).resolve()
        self.artifacts_root = (self.repo_root / self.artifacts_root).resolve()

    @property
    def cflags(self) -> list[str]:
        flags = [self.opt_level, f"-D{self.dataset}", "-DPOLYBENCH_TIME"]
        if self.fast_math:
            flags.append("-ffast-math")
        return flags

    @property
    def dump_cflags(self) -> list[str]:
        return [flag for flag in self.cflags if flag != "-DPOLYBENCH_TIME"] + [
            "-DPOLYBENCH_DUMP_ARRAYS"
        ]

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["repo_root"] = str(self.repo_root)
        data["polybench_root"] = str(self.polybench_root)
        data["artifacts_root"] = str(self.artifacts_root)
        data["toolchain"]["llvm_bin"] = str(self.toolchain.llvm_bin)
        return data
