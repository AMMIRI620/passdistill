from __future__ import annotations

from pathlib import Path
import json

from .types import Kernel


def discover_kernels(polybench_root: Path, metadata_path: Path | None = None) -> list[Kernel]:
    if metadata_path and metadata_path.exists():
        data = json.loads(metadata_path.read_text())
        entries = data.get("kernels", [])
        kernels = []
        for entry in entries:
            rel_source = Path(entry["source_file"])
            source = polybench_root / rel_source
            kernels.append(
                Kernel(
                    name=entry["kernel_name"],
                    source=source,
                    header=source.with_suffix(".h"),
                    rel_dir=rel_source.parent,
                    target_function=entry["target_function"],
                    metadata=entry,
                )
            )
        return kernels
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
        kernels.append(
            Kernel(
                name=name,
                source=source,
                header=header,
                rel_dir=rel_source.parent,
                target_function=f"kernel_{name.replace('-', '_')}",
            )
        )
    return kernels


def find_kernel(polybench_root: Path, name: str, metadata_path: Path | None = None) -> Kernel:
    for kernel in discover_kernels(polybench_root, metadata_path):
        if kernel.name == name:
            return kernel
    raise KeyError(f"unknown PolyBench kernel: {name}")


def utility_sources(polybench_root: Path) -> list[Path]:
    return [polybench_root / "utilities" / "polybench.c"]


def include_dirs(polybench_root: Path, kernel: Kernel) -> list[Path]:
    return [polybench_root / "utilities", kernel.source.parent]
