#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "high_budget_polybench.json"
RUN_DIR = ROOT / "artifacts" / "runs" / "high-budget-polybench"
MAX_RESUME_ATTEMPTS = 100
KERNELS = [
    "floyd-warshall",
    "lu",
    "gramschmidt",
    "durbin",
    "deriche",
]


def kernel_state(kernel: str) -> tuple[int, str | None]:
    path = RUN_DIR / kernel / "summary.json"
    if not path.exists():
        return 0, None
    try:
        summary = json.loads(path.read_text())
        return int(summary.get("pass_candidates_tried", 0)), summary.get("recovery_status")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return 0, None


def main() -> int:
    for kernel in KERNELS:
        attempts = 0
        count, status = kernel_state(kernel)
        while count < 200 and status != "no_valid_teacher":
            attempts += 1
            print(f"[{kernel}] attempt={attempts} candidates={count}/200 status={status}", flush=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_passdistill.py"),
                    "--config",
                    str(CONFIG),
                    "--kernel",
                    kernel,
                    "--resume",
                ],
                cwd=ROOT,
                check=False,
            )
            count, status = kernel_state(kernel)
            print(f"[{kernel}] exit={result.returncode} candidates={count}/200 status={status}", flush=True)
            if count >= 200 or status == "no_valid_teacher":
                break
            if attempts >= MAX_RESUME_ATTEMPTS:
                print(
                    f"[{kernel}] warning=resume_limit_reached candidates={count}/200; "
                    "preserving incomplete artifacts and continuing",
                    flush=True,
                )
                break
            time.sleep(5)
        if status == "no_valid_teacher":
            print(f"[{kernel}] terminal=no_valid_teacher; preserving artifacts and continuing", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
