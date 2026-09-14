from __future__ import annotations

import shutil
from pathlib import Path

from .config import ExperimentConfig
from .polybench import include_dirs, utility_sources
from .types import CommandResult, Kernel
from .util import ensure_dir, run_command


def _include_flags(config: ExperimentConfig, kernel: Kernel) -> list[str]:
    flags: list[str] = []
    for path in include_dirs(config.polybench_root, kernel):
        flags.extend(["-I", str(path)])
    return flags


def _compile_flags(config: ExperimentConfig, kernel: Kernel, *, dump_arrays: bool = False) -> list[str]:
    configured = kernel.metadata.get("compilation_flags") if kernel.metadata else None
    if not configured:
        return config.dump_cflags if dump_arrays else config.cflags
    flags = [str(flag) for flag in configured if flag not in {"-DPOLYBENCH_TIME", "-DPOLYBENCH_DUMP_ARRAYS"}]
    flags.append("-DPOLYBENCH_DUMP_ARRAYS" if dump_arrays else "-DPOLYBENCH_TIME")
    return flags


def compile_c(
    config: ExperimentConfig,
    kernel: Kernel,
    source: Path,
    output: Path,
    *,
    dump_arrays: bool = False,
    remarks: Path | None = None,
) -> CommandResult:
    ensure_dir(output.parent)
    flags = _compile_flags(config, kernel, dump_arrays=dump_arrays)
    argv = [
        str(config.toolchain.clang),
        *flags,
        *_include_flags(config, kernel),
        str(source),
        *(str(path) for path in utility_sources(config.polybench_root)),
        "-lm",
        "-o",
        str(output),
    ]
    if remarks is not None:
        ensure_dir(remarks.parent)
        argv.extend(["-fsave-optimization-record", f"-foptimization-record-file={remarks}"])
    return run_command(argv, config.repo_root, timeout=config.command_timeout_sec)


def emit_frontend_ir(
    config: ExperimentConfig,
    kernel: Kernel,
    source: Path,
    output: Path,
    *,
    dump_arrays: bool = False,
) -> CommandResult:
    ensure_dir(output.parent)
    flags = _compile_flags(config, kernel, dump_arrays=dump_arrays)
    argv = [
        str(config.toolchain.clang),
        *flags,
        *_include_flags(config, kernel),
        "-Xclang",
        "-disable-llvm-passes",
        "-S",
        "-emit-llvm",
        str(source),
        "-o",
        str(output),
    ]
    return run_command(argv, config.repo_root, timeout=config.command_timeout_sec)


def emit_optimized_ir(
    config: ExperimentConfig,
    kernel: Kernel,
    source: Path,
    output: Path,
) -> CommandResult:
    ensure_dir(output.parent)
    argv = [
        str(config.toolchain.clang),
        *_compile_flags(config, kernel),
        *_include_flags(config, kernel),
        "-S",
        "-emit-llvm",
        str(source),
        "-o",
        str(output),
    ]
    return run_command(argv, config.repo_root, timeout=config.command_timeout_sec)


def expanded_o3_pipeline(config: ExperimentConfig) -> CommandResult:
    empty_ir = ensure_dir(config.artifacts_root / "_inputs") / "empty_module.ll"
    if not empty_ir.exists():
        empty_ir.write_text('source_filename = "empty_module.c"\n')
    argv = [
        str(config.toolchain.opt),
        "-passes=default<O3>",
        "-print-pipeline-passes",
        "-disable-output",
        str(empty_ir),
    ]
    return run_command(argv, config.repo_root, timeout=30)


def opt_pipeline(
    config: ExperimentConfig,
    input_ir: Path,
    output_ir: Path,
    pipeline: str,
    *,
    remarks: Path | None = None,
    extra_options: list[str] | None = None,
) -> CommandResult:
    ensure_dir(output_ir.parent)
    argv = [
        str(config.toolchain.opt),
        f"-passes={pipeline}",
        str(input_ir),
        "-S",
        "-o",
        str(output_ir),
    ]
    if remarks is not None:
        ensure_dir(remarks.parent)
        argv.extend(["-pass-remarks=.*", "-pass-remarks-missed=.*", "-pass-remarks-analysis=.*"])
    if extra_options:
        argv[1:1] = extra_options
    result = run_command(argv, config.repo_root, timeout=config.command_timeout_sec)
    if remarks is not None:
        remarks.write_text(result.stderr)
    return result


def preflight_pipeline(
    config: ExperimentConfig,
    input_ir: Path,
    pipeline: str,
    *,
    extra_options: list[str] | None = None,
) -> CommandResult:
    argv = [str(config.toolchain.opt), f"-passes={pipeline}", str(input_ir), "-disable-output"]
    if extra_options:
        argv[1:1] = extra_options
    return run_command(argv, config.repo_root, timeout=config.command_timeout_sec)


def compile_ir_to_object(
    config: ExperimentConfig,
    input_ir: Path,
    output: Path,
) -> CommandResult:
    ensure_dir(output.parent)
    argv = [
        str(config.toolchain.llc),
        "-O=3",
        "-filetype=obj",
        "-relocation-model=pic",
        str(input_ir),
        "-o",
        str(output),
    ]
    return run_command(argv, config.repo_root, timeout=config.command_timeout_sec)


def compile_polybench_object(
    config: ExperimentConfig,
    kernel: Kernel,
    output: Path,
) -> CommandResult:
    ensure_dir(output.parent)
    argv = [
        str(config.toolchain.clang),
        *_compile_flags(config, kernel),
        *_include_flags(config, kernel),
        "-c",
        str(config.polybench_root / "utilities" / "polybench.c"),
        "-o",
        str(output),
    ]
    return run_command(argv, config.repo_root, timeout=config.command_timeout_sec)


def link_objects(
    config: ExperimentConfig,
    objects: list[Path],
    output: Path,
) -> CommandResult:
    ensure_dir(output.parent)
    flags = ["-ffast-math"] if config.fast_math else []
    argv = [
        str(config.toolchain.clang),
        *flags,
        *(str(path) for path in objects),
        "-lm",
        "-o",
        str(output),
    ]
    return run_command(argv, config.repo_root, timeout=config.command_timeout_sec)


def pinned_prefix(config: ExperimentConfig) -> list[str]:
    prefix: list[str] = []
    if shutil.which("setarch"):
        prefix.extend(["setarch", "x86_64", "-R"])
    if shutil.which("numactl"):
        prefix.extend(["numactl", f"--physcpubind={config.cpu}", f"--membind={config.numa_node}"])
    return prefix
