#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from passdistill.config import ExperimentConfig, Toolchain
from passdistill.orchestrator import run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PassDistill PolyBench autotuning.")
    parser.add_argument("--config", "--experiment-config", dest="experiment_config", type=Path)
    target = parser.add_mutually_exclusive_group(required=False)
    target.add_argument("--kernel", help="PolyBench kernel name, for example 2mm")
    target.add_argument("--kernels", help="Comma-separated PolyBench kernel names")
    target.add_argument("--all", action="store_true", default=None, help="Run all PolyBench kernels")
    parser.add_argument("--max-teacher-rounds", type=int)
    parser.add_argument("--max-teachers", type=int)
    parser.add_argument("--max-recovery-rounds", type=int)
    parser.add_argument("--max-pass-candidates", type=int)
    parser.add_argument("--promotion-min-relative-gain", type=float)
    parser.add_argument("--runs", type=int)
    parser.add_argument("--warmups", type=int)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--numa-node", type=int)
    parser.add_argument("--rtol", type=float, help="Must be 0; full-stderr MD5 checking has no numeric tolerance")
    parser.add_argument("--atol", type=float, help="Must be 0; full-stderr MD5 checking has no numeric tolerance")
    parser.add_argument("--llm-backend", choices=["mock", "openai", "openai-compatible", "http"])
    parser.add_argument("--model")
    parser.add_argument("--dry-run", action="store_true", default=None)
    parser.add_argument(
        "--baseline-only",
        action="store_true", default=None,
        help="Build and measure clang/search baselines, then stop before any agent calls.",
    )
    parser.add_argument("--resume", action="store_true", default=None)
    parser.add_argument("--run-id")
    parser.add_argument("--llvm-bin", type=Path)
    parser.add_argument("--artifacts-root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_config = json.loads(args.experiment_config.read_text()) if args.experiment_config else {}
    config_values = ExperimentConfig.load_json(args.experiment_config, repo_root=ROOT) if args.experiment_config else {"repo_root": ROOT}
    llvm_bin = args.llvm_bin or config_values.pop("llvm_bin", None)
    cli_fields = (
        "artifacts_root", "warmups", "runs", "cpu", "numa_node", "rtol", "atol",
        "max_teacher_rounds", "max_teachers", "max_recovery_rounds", "max_pass_candidates",
        "promotion_min_relative_gain", "llm_backend", "model", "dry_run", "baseline_only",
        "resume", "run_id",
    )
    for name in cli_fields:
        value = getattr(args, name)
        if value is not None:
            config_values[name] = value
    config_values["toolchain"] = Toolchain(llvm_bin=llvm_bin) if llvm_bin else Toolchain()
    config = ExperimentConfig(**config_values)
    configured_kernels = raw_config.get("kernels", [])
    if args.kernels:
        kernel_names = [name.strip() for name in args.kernels.split(",") if name.strip()]
    elif args.kernel or args.all:
        # Explicit CLI selectors take precedence over a configured default list.
        kernel_names = []
    else:
        kernel_names = configured_kernels
    if not (args.kernel or args.all or kernel_names):
        raise SystemExit("choose --kernel NAME, --kernels A,B, --all, or configure kernels in --config")
    run_dir = run(config, kernel=args.kernel, all_kernels=bool(args.all), kernels=kernel_names)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
