from __future__ import annotations

from pathlib import Path

from .types import Kernel


def discover_kernels(polybench_root: Path) -> list[Kernel]:
    benchmark_list = polybench_root / "utilities" / "benchmark_list"
    kernels: list[Kernel] = []
    for raw in benchmark_list.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rel_source = Path(line.removeprefix("./"))
        source = polybench_root / rel_source
        name = source.stem
        header = source.with_suffix(".h")
        kernels.append(Kernel(name=name, source=source, header=header, rel_dir=rel_source.parent))
    return kernels


def find_kernel(polybench_root: Path, name: str) -> Kernel:
    for kernel in discover_kernels(polybench_root):
        if kernel.name == name:
            return kernel
    raise KeyError(f"unknown PolyBench kernel: {name}")


def utility_sources(polybench_root: Path) -> list[Path]:
    return [polybench_root / "utilities" / "polybench.c"]


def include_dirs(polybench_root: Path, kernel: Kernel) -> list[Path]:
    return [polybench_root / "utilities", kernel.source.parent]

