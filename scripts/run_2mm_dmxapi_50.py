#!/usr/bin/env python3
"""Run the 2mm fast-math experiment with an isolated artifact directory."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".passdistill_dmxapi.env"
CONFIGS = (
    ROOT / "configs" / "2mm_dmxapi_50_fast_math_on.json",
)
MAX_STALLED_ATTEMPTS = 2
MAX_TOTAL_ATTEMPTS = 10
PROGRESS_POLL_SECONDS = 2


def dmx_environment(env_file: Path | None = None, *, model: str | None = None) -> dict[str, str]:
    env_file = env_file or ENV_FILE
    values: dict[str, str] = {}
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"PASSDISTILL_OPENAI_API_KEY", "PASSDISTILL_OPENAI_BASE_URL", "PASSDISTILL_MODEL"}:
            values[key] = value.strip().strip('"').strip("'")
    if model is not None:
        values["PASSDISTILL_MODEL"] = model
    for key in ("PASSDISTILL_OPENAI_API_KEY", "PASSDISTILL_OPENAI_BASE_URL", "PASSDISTILL_MODEL"):
        if not values.get(key):
            raise RuntimeError(f"{env_file.name} is missing {key}")
    environment = os.environ.copy()
    environment.update(values)
    return environment


def kernel_state(run_id: str) -> tuple[int, str | None]:
    summary = ROOT / "artifacts" / "runs" / run_id / "2mm" / "summary.json"
    if not summary.exists():
        return 0, None
    data = json.loads(summary.read_text())
    return int(data.get("pass_candidates_tried", 0)), data.get("recovery_status")


def candidate_summaries(run_id: str) -> list[Path]:
    recovery = ROOT / "artifacts" / "runs" / run_id / "2mm" / "search" / "recovery"
    return sorted(
        recovery.glob("*/candidates/*/candidate_summary.json"),
        key=lambda path: (path.stat().st_mtime_ns, str(path)),
    )


def report_new_candidates(run_id: str, seen: set[Path], best: float) -> float:
    for path in candidate_summaries(run_id):
        if path in seen:
            continue
        try:
            candidate = json.loads(path.read_text())
        except (OSError, ValueError):
            # A candidate may be visible before its JSON write has finished.
            continue
        seen.add(path)
        speedup = candidate.get("speedup_vs_search_baseline")
        if isinstance(speedup, (int, float)) and speedup > best:
            best = float(speedup)
        current = f"{speedup:.4f}x" if isinstance(speedup, (int, float)) else "n/a"
        print(
            f"[{run_id}] candidate={len(seen)}/50 "
            f"teacher={path.parents[2].name} round=R{candidate.get('round', '?')} "
            f"id={candidate.get('candidate_id', path.parent.name)} "
            f"status={candidate.get('status', '?')} "
            f"current_speedup_vs_search={current} best_speedup_vs_search={best:.4f}x",
            flush=True,
        )
    return best


def main() -> int:
    environment = dmx_environment()
    for config_path in CONFIGS:
        config = json.loads(config_path.read_text())
        run_id = config["run_id"]
        attempts = 0
        stalled = 0
        count, status = kernel_state(run_id)
        seen = set(candidate_summaries(run_id))
        best = 1.0
        for path in seen:
            try:
                speedup = json.loads(path.read_text()).get("speedup_vs_search_baseline")
            except (OSError, ValueError):
                continue
            if isinstance(speedup, (int, float)):
                best = max(best, float(speedup))
        print(f"[{run_id}] start candidates={count}/50 status={status}", flush=True)
        print(f"[{run_id}] checkpoint candidates={len(seen)}/50 best_speedup_vs_search={best:.4f}x", flush=True)
        while count < 50 and status != "no_valid_teacher" and attempts < MAX_TOTAL_ATTEMPTS:
            attempts += 1
            print(f"[{run_id}] attempt={attempts} candidates={count}/50", flush=True)
            command = [
                sys.executable,
                str(ROOT / "scripts" / "run_passdistill.py"),
                "--config",
                str(config_path),
                "--kernel",
                "2mm",
                "--resume",
                "--model",
                environment["PASSDISTILL_MODEL"],
            ]
            process = subprocess.Popen(command, cwd=ROOT, env=environment)
            while process.poll() is None:
                best = report_new_candidates(run_id, seen, best)
                time.sleep(PROGRESS_POLL_SECONDS)
            best = report_new_candidates(run_id, seen, best)
            result_code = process.returncode
            new_count, status = kernel_state(run_id)
            stalled = 0 if new_count > count else stalled + 1
            count = new_count
            print(
                f"[{run_id}] exit={result_code} candidates={count}/50 "
                f"status={status} consecutive_no_progress={stalled}",
                flush=True,
            )
            if count >= 50 or status == "no_valid_teacher":
                break
            if stalled >= MAX_STALLED_ATTEMPTS:
                print(f"[{run_id}] stopped_after_no_progress; artifacts retained", flush=True)
                break
            time.sleep(5)
        print(f"[{run_id}] done candidates={count}/50 status={status}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
