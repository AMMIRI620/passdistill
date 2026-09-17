#!/usr/bin/env python3
"""Report live candidate progress for an already-running 2mm DMX experiment."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from run_2mm_dmxapi_50 import candidate_summaries, report_new_candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-pid", type=int, required=True)
    parser.add_argument("--run-id", default="2mm-dmxapi-50-fast-math-on")
    args = parser.parse_args()
    seen: set[Path] = set()
    best = 1.0
    print(f"[{args.run_id}] live progress monitor started", flush=True)
    while True:
        best = report_new_candidates(args.run_id, seen, best)
        try:
            os.kill(args.runner_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(2)
    report_new_candidates(args.run_id, seen, best)
    print(f"[{args.run_id}] runner exited; progress monitor stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
