#!/usr/bin/env python3
"""Serial PolyBench experiments with bounded resume and artifact-based progress."""
import fcntl
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from run_2mm_dmxapi_50 import ROOT, dmx_environment

CONFIG = ROOT / "configs/polybench30_dmxapi_50_md5.json"


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def log(message):
    print(f"{datetime.now().astimezone().isoformat(timespec='seconds')} {message}", flush=True)


def scan(kernel_dir):
    paths = kernel_dir.glob("search/recovery/*/candidates/*/candidate_summary.json")
    return [(p, read_json(p, {})) for p in sorted(paths, key=lambda p: (p.stat().st_mtime_ns, str(p)))]


def main():
    config = json.loads(CONFIG.read_text())
    run_dir = ROOT / "artifacts/runs" / config["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    lock = (run_dir / "runner.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    environment = dmx_environment()
    if environment["PASSDISTILL_MODEL"] != config["model"]:
        raise RuntimeError("DMX model and experiment config differ; align them before starting")
    budget = config["max_pass_candidates"]
    states = read_json(run_dir / "runner_status.json", {})

    def save_state(kernel, **fields):
        states[kernel] = {**fields, "updated_at_utc": datetime.now(timezone.utc).isoformat()}
        path = run_dir / "runner_status.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(states, indent=2) + "\n")
        temporary.replace(path)

    for kernel in config["kernels"]:
        directory = run_dir / kernel
        records = scan(directory)
        seen = {p for p, data in records if data}
        best = max([1.0] + [d.get("speedup_vs_search_baseline") or 0 for _, d in records])
        stalled = 0
        outcome = "attempt_limit"
        summary = read_json(directory / "summary.json", {})
        if summary.get("recovery_status") in ("complete", "no_valid_teacher"):
            log(f"[{kernel}] already_terminal={summary['recovery_status']}")
            save_state(kernel, status=summary["recovery_status"], candidates=len(seen))
            continue
        for attempt in range(1, 11):
            before = (len(seen), len(read_json(directory / "search/teacher_history.json", [])))
            save_state(kernel, status="running", attempt=attempt, candidates=len(seen))
            log(f"[{kernel}] attempt={attempt} candidates={len(seen)}/{budget}")
            command = [sys.executable, str(ROOT / "scripts/run_passdistill.py"),
                       "--config", str(CONFIG), "--kernel", kernel, "--resume"]
            process = subprocess.Popen(command, cwd=ROOT, env=environment)
            while True:
                code = process.poll()
                for path, data in scan(directory):
                    if path in seen or not data:
                        continue
                    seen.add(path)
                    speedup = data.get("speedup_vs_search_baseline")
                    best = max(best, speedup or 0)
                    current = f"{speedup:.4f}x" if speedup is not None else "n/a"
                    log(f"[{kernel}] candidate={len(seen)}/{budget} "
                        f"id={data.get('candidate_id')} round=R{data.get('round')} "
                        f"status={data.get('status')} current_vs_search={current} best_vs_search={best:.4f}x")
                if code is not None:
                    break
                time.sleep(2)
            summary = read_json(directory / "summary.json", {})
            outcome = summary.get("recovery_status", "incomplete")
            after = (len(seen), len(read_json(directory / "search/teacher_history.json", [])))
            stalled = stalled + 1 if after == before else 0
            log(f"[{kernel}] exit={code} candidates={len(seen)}/{budget} status={outcome} stalled={stalled}")
            if outcome in ("complete", "no_valid_teacher"):
                break
            if stalled >= 2:
                outcome = "stopped_no_progress"
                break
            if attempt == 10:
                outcome = "attempt_limit"
                break
            time.sleep(5)
        save_state(kernel, status=outcome, candidates=len(seen), best_speedup_vs_search=best)
        log(f"[{kernel}] finished status={outcome}; proceeding to next kernel")
    log("All kernels attempted; inspect summary.json and runner_status.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
