#!/usr/bin/env python3
"""Start/stop/resume one PolyBench experiment, optionally switching API env files."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from run_2mm_dmxapi_50 import ROOT, dmx_environment

DEFAULT_CONFIG = ROOT / "configs/polybench30_gpt56sol_50_baseline_refresh_v3.json"
RUNNER = ROOT / "scripts/run_polybench30_dmxapi_50.py"
WORKER = ROOT / "scripts/run_passdistill.py"


def processes():
    """Read identities, never credentials/environment; exclude dead zombies."""
    result = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(") ", 1)[1].split()
            if fields[0] == "Z":
                continue
            result[int(path.name)] = {
                "pgid": int(fields[2]), "start_ticks": fields[19],
                "argv": (path / "cmdline").read_bytes().decode(errors="replace").rstrip("\0").split("\0"),
                "cwd": (path / "cwd").resolve(),
            }
        except (OSError, ValueError, IndexError):
            continue
    return result


def matches(proc, script, config):
    if proc["cwd"] != ROOT:
        return False
    argv = proc["argv"]
    if not any((proc["cwd"] / arg).resolve() == script for arg in argv[:3]):
        return False
    try:
        return (proc["cwd"] / argv[argv.index("--config") + 1]).resolve() == config
    except (ValueError, IndexError):
        return False


def experiment_groups(snapshot, config, saved):
    groups = set()
    for pid, proc in snapshot.items():
        if not (matches(proc, RUNNER, config) or matches(proc, WORKER, config)):
            continue
        pgid = proc["pgid"]
        leader = snapshot.get(pgid)
        if pgid == os.getpgrp():
            raise RuntimeError("Experiment shares this terminal's process group; stop it manually first")
        if leader and matches(leader, RUNNER, config):
            groups.add(pgid)
        elif saved.get("pid") == pgid and (not leader or leader["start_ticks"] == saved.get("start_ticks")):
            groups.add(pgid)
        else:
            raise RuntimeError(f"Cannot safely identify experiment process group {pgid}; refusing to signal it")
    # Include orphan descendants of a runner launched by this controller.
    pgid = saved.get("pid")
    leader = snapshot.get(pgid)
    if pgid and pgid != os.getpgrp() and (not leader or leader["start_ticks"] == saved.get("start_ticks")):
        if any(p["pgid"] == pgid for p in snapshot.values()):
            groups.add(pgid)
    return groups


def stop_groups(groups):
    for group in groups:
        try:
            os.killpg(group, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for attempt in range(60):
        remaining = groups & {p["pgid"] for p in processes().values()}
        if not remaining:
            return
        if attempt == 40:
            for group in remaining:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        time.sleep(0.25)
    raise RuntimeError(f"Processes still present in {sorted(remaining)}; refusing to start another runner")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "restart", "stop", "status"])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".passdistill_dmxapi.env")
    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text())
    run_id = config["run_id"]
    if Path(run_id).name != run_id or run_id in {".", ".."}:
        raise ValueError("Expected a single run_id directory name")
    run_dir = ROOT / "artifacts/runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "controller.json"
    with (run_dir / "controller.lock").open("a") as control_lock:
        fcntl.flock(control_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        saved = json.loads(state_path.read_text()) if state_path.exists() else {}
        groups = experiment_groups(processes(), config_path, saved)
        if args.action == "status":
            print(json.dumps({"run_id": run_id, "running_process_groups": sorted(groups),
                              "last_launch": saved, "log": str(run_dir / "runner.log")}, indent=2))
            return 0
        if args.action == "start" and groups:
            raise RuntimeError("Experiment already running; use restart to switch API")
        if args.action in {"start", "restart"}:
            # Validate before stopping; no secrets enter logs or controller state.
            env_file = args.env_file.resolve()
            environment = dmx_environment(env_file, model=config["model"])
            host = urlsplit(environment["PASSDISTILL_OPENAI_BASE_URL"]).hostname
        if args.action in {"stop", "restart"}:
            stop_groups(groups)
            print(f"Stopped experiment process groups: {sorted(groups)}", flush=True)
        if args.action == "stop":
            return 0
        # Also reject an unrecognized runner holding the existing experiment lock.
        with (run_dir / "runner.lock").open("a") as runner_lock:
            fcntl.flock(runner_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        command = [sys.executable, "-u", str(RUNNER), "--config", str(config_path),
                   "--env-file", str(env_file), "--model", config["model"]]
        with (run_dir / "runner.log").open("a") as log:
            proc = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        identity = processes().get(proc.pid)
        if not identity:
            raise RuntimeError("Runner exited at startup; inspect runner.log")
        state = {"pid": proc.pid, "start_ticks": identity["start_ticks"],
                 "started_at_utc": datetime.now(timezone.utc).isoformat(),
                 "config": str(config_path), "env_file": str(env_file), "api_host": host,
                 "model": config["model"], "action": args.action}
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(state_path)
        with (run_dir / "api_transitions.jsonl").open("a") as transitions:
            transitions.write(json.dumps(state) + "\n")
        time.sleep(1)
        if proc.poll() is not None:
            raise RuntimeError(f"Runner exited ({proc.returncode}); inspect runner.log")
        print(f"Running PID={proc.pid} host={host} model={config['model']} (resume)")
        print(f"Log: {run_dir / 'runner.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
