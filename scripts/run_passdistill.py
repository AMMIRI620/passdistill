#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from passdistill.config import ExperimentConfig, Toolchain
from passdistill.orchestrator import run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PassDistill PolyBench autotuning.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--kernel", help="PolyBench kernel name, for example 2mm")
    target.add_argument("--all", action="store_true", help="Run all PolyBench kernels")
    parser.add_argument("--max-teacher-rounds", type=int, default=3)
    parser.add_argument("--max-teachers", type=int, default=6)
    parser.add_argument("--max-recovery-rounds", type=int, default=3)
    parser.add_argument("--max-pass-candidates", type=int, default=36)
    parser.add_argument("--promotion-min-relative-gain", type=float, default=0.01)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--cpu", type=int, default=3)
    parser.add_argument("--numa-node", type=int, default=0)
    parser.add_argument("--rtol", type=float, default=1e-4)
    parser.add_argument("--atol", type=float, default=1e-6)
    parser.add_argument("--llm-backend", default="mock", choices=["mock", "openai", "openai-compatible", "http"])
    parser.add_argument("--model")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Build and measure clang/search baselines, then stop before any agent calls.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--llvm-bin", type=Path)
    parser.add_argument("--artifacts-root", type=Path, default=Path("artifacts/runs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = ExperimentConfig(
        repo_root=ROOT,
        artifacts_root=args.artifacts_root,
        warmups=args.warmups,
        runs=args.runs,
        cpu=args.cpu,
        numa_node=args.numa_node,
        rtol=args.rtol,
        atol=args.atol,
        max_teacher_rounds=args.max_teacher_rounds,
        max_teachers=args.max_teachers,
        max_recovery_rounds=args.max_recovery_rounds,
        max_pass_candidates=args.max_pass_candidates,
        promotion_min_relative_gain=args.promotion_min_relative_gain,
        llm_backend=args.llm_backend,
        model=args.model,
        dry_run=args.dry_run,
        baseline_only=args.baseline_only,
        resume=args.resume,
        run_id=args.run_id,
        toolchain=Toolchain(llvm_bin=args.llvm_bin) if args.llvm_bin else Toolchain(),
    )
    run_dir = run(config, kernel=args.kernel, all_kernels=args.all)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
