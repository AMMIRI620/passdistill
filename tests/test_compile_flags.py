from pathlib import Path

from passdistill.compiler import _compile_flags
from passdistill.config import ExperimentConfig
from passdistill.types import Kernel


def test_polybench_metadata_respects_fast_math_switch(tmp_path):
    kernel = Kernel(
        name="2mm",
        source=tmp_path / "2mm.c",
        header=tmp_path / "2mm.h",
        rel_dir=Path("linear-algebra/kernels/2mm"),
        target_function="kernel_2mm",
        metadata={"compilation_flags": ["-O3", "-ffast-math", "-DLARGE_DATASET"]},
    )
    for enabled in (True, False):
        config = ExperimentConfig(repo_root=tmp_path, fast_math=enabled)
        for dump_arrays in (True, False):
            flags = _compile_flags(config, kernel, dump_arrays=dump_arrays)
            assert ("-ffast-math" in flags) is enabled
            assert ("-DPOLYBENCH_DUMP_ARRAYS" in flags) is dump_arrays
            assert ("-DPOLYBENCH_TIME" in flags) is not dump_arrays
