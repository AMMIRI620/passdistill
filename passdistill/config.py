from __future__ import annotations

import json
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
    kernel_metadata: Path = Path("configs/polybench_kernels.json")
    artifacts_root: Path = Path("artifacts/runs")
    dataset: str = "LARGE_DATASET"
    opt_level: str = "-O3"
    fast_math: bool = True
    cpu: int = 3
    numa_node: int = 0
    warmups: int = 1
    runs: int = 3
    rtol: float = 0.0
    atol: float = 0.0
    correctness_mode: str = "stderr_md5"
    correctness_reference: str = "search_baseline"
    max_teacher_rounds: int = 3
    max_teachers: int = 6
    max_recovery_rounds: int = 3
    max_pass_candidates: int = 36
    uniform_fixed_recovery_budget: bool = False
    promotion_min_relative_gain: float = 0.01
    llm_backend: str = "mock"
    model: str | None = None
    dry_run: bool = False
    baseline_only: bool = False
    resume: bool = False
    run_id: str | None = None
    flat_kernel_artifacts: bool = False
    command_timeout_sec: int = 300
    toolchain: Toolchain = field(default_factory=Toolchain)

    def __post_init__(self) -> None:
        if self.correctness_mode != "stderr_md5" or self.correctness_reference != "search_baseline":
            raise ValueError("correctness requires stderr_md5 against search_baseline")
        if self.rtol != 0 or self.atol != 0:
            raise ValueError("stderr_md5 correctness does not allow tolerances; use rtol=0 and atol=0")
        self.repo_root = self.repo_root.resolve()
        self.polybench_root = (self.repo_root / self.polybench_root).resolve()
        self.kernel_metadata = (self.repo_root / self.kernel_metadata).resolve()
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

    @classmethod
    def load_json(cls, path: Path, *, repo_root: Path) -> dict[str, Any]:
        """Load user-facing experiment defaults without constructing the config yet."""
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"experiment config must be a JSON object: {path}")
        allowed = set(cls.__dataclass_fields__) - {"repo_root", "toolchain"}
        unknown = sorted(set(data) - allowed - {"llvm_bin", "kernels"})
        if unknown:
            raise ValueError(f"unknown experiment config keys: {', '.join(unknown)}")
        result = {key: value for key, value in data.items() if key in allowed}
        for key in ("polybench_root", "kernel_metadata", "artifacts_root"):
            if key in result:
                result[key] = Path(result[key])
        if "llvm_bin" in data:
            result["llvm_bin"] = Path(data["llvm_bin"])
        result["repo_root"] = repo_root
        return result
