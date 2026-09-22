#!/usr/bin/env python3
"""Start, cooperatively pause, resume and inspect a cBench DMXAPI experiment."""
import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_2mm_dmxapi_50 import dmx_environment
from passdistill.cbench.control import configure, state
from passdistill.cbench.runner import main as run
from passdistill.util import read_json, write_json

CURRENT = ROOT / 'artifacts/cbench-dmxapi-current.json'


def process_identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, IndexError):
        return None


def alive(saved):
    return bool(saved.get('pid') and process_identity(saved['pid']) == saved.get('start_ticks'))


def launch(out, saved):
    # Check the environment before launching; save only its path and API hostname.
    env = dmx_environment(Path(saved['env_file']), model=saved['model'])
    saved['api_host'] = urlsplit(env['PASSDISTILL_OPENAI_BASE_URL']).hostname
    with (out / 'runner.log').open('a') as log:
        proc = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()),
                    '_worker', '--output', str(out)], cwd=ROOT, env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    saved.update(pid=proc.pid, start_ticks=process_identity(proc.pid))
    write_json(out / 'controller.json', saved)
    print(f"Started PID={proc.pid}, host={saved['api_host']}, model={saved['model']}")
    print(f'Output: {out}\nLog: {out / "runner.log"}')


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'pause', 'resume', 'switch-api', 'status', '_worker'])
    parser.add_argument('--output', type=Path, help='defaults to the last launched cBench DMXAPI run')
    parser.add_argument('--program', nargs='+', default=['automotive_bitcount'])
    parser.add_argument('--all-ready', action='store_true')
    parser.add_argument('--exclude', nargs='+', default=[], help='exclude programs from this new run')
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/cbench_dmxapi.json')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.passdistill_dmxapi.env')
    args = parser.parse_args(argv)
    if args.action == 'start':
        out = (args.output or ROOT / 'artifacts/runs' / ('cbench-dmxapi-' + datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve()
        # Do not silently run two managed experiments on the same pinned CPU.
        if CURRENT.exists():
            previous = Path(read_json(CURRENT)['output']) / 'controller.json'
            if previous.exists() and alive(read_json(previous)):
                raise RuntimeError('A managed cBench run is still alive (possibly paused); use resume/status')
        settings = read_json(args.config)
        if settings['llm_backend'] != 'dmxapi':
            raise ValueError('controller requires a DMXAPI configuration')
        env = dmx_environment(args.env_file.resolve(), model=settings['model'])
        programs = args.program
        if args.all_ready:
            programs = [p['program'] for p in read_json(ROOT / settings['hotspots'])['programs'] if p['status'] == 'ready']
        programs = [name for name in programs if name not in args.exclude]
        available = {p['program'] for p in read_json(ROOT / settings['hotspots'])['programs'] if p['status'] == 'ready'}
        if not programs or not set(programs) <= available or len(set(programs)) != len(programs):
            raise ValueError('choose distinct ready programs from the hotspot manifest')
        out.mkdir(parents=True, exist_ok=False)
        write_json(out / 'config.json', settings)
        saved = {'programs': programs, 'env_file': str(args.env_file.resolve()), 'model': settings['model'],
                 'api_host': urlsplit(env['PASSDISTILL_OPENAI_BASE_URL']).hostname}
        write_json(out / 'controller.json', saved)
        write_json(CURRENT, {'output': str(out)})
    else:
        out = (args.output or Path(read_json(CURRENT)['output'])).resolve()

    if args.action == 'status':
        saved = read_json(out / 'controller.json')
        activity = out / 'control/activity.json'
        print(json.dumps({'output': str(out), 'alive': alive(saved),
                          'pause_requested': (out / 'control/pause.request').exists(),
                          'activity': read_json(activity) if activity.exists() else {},
                          'programs': saved['programs'], 'pid': saved.get('pid'),
                          'api_host': saved['api_host'], 'model': saved['model'],
                          'log': str(out / 'runner.log')}, indent=2))
        return 0

    if args.action == '_worker':
        # A process-lifetime lock also prevents simultaneous resume workers.
        with (out / 'worker.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            saved = read_json(out / 'controller.json')
            configure(out / 'control')
            try:
                return run(['--config', str(out / 'config.json'), '--program', *saved['programs'],
                            '--output', str(out), '--resume', '--control-dir', str(out / 'control')])
            except BaseException as exc:
                state('failed', error=str(exc))
                raise

    with (out / 'controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        saved = read_json(out / 'controller.json')
        pause = out / 'control/pause.request'
        if args.action == 'start':
            launch(out, saved)
        elif args.action == 'pause':
            if not alive(saved):
                raise RuntimeError('Experiment is not running')
            pause.parent.mkdir(parents=True, exist_ok=True)
            pause.touch()
            print('Pause requested. Current API/build/full measurement finishes before pausing; use status to confirm paused.')
        elif args.action == 'resume':
            pause.unlink(missing_ok=True)
            if alive(saved):
                print('Resume requested; existing worker continues without repeating the in-flight operation.')
            else:
                launch(out, saved)
        elif args.action == 'switch-api':
            new_env = args.env_file.resolve()
            environment = dmx_environment(new_env, model=saved['model'])
            if alive(saved):
                pause.parent.mkdir(parents=True, exist_ok=True)
                pause.touch()
                print('Waiting for the current operation to finish before switching API.', flush=True)
                deadline = time.monotonic() + 960
                while alive(saved):
                    activity_path = out / 'control/activity.json'
                    activity = read_json(activity_path) if activity_path.exists() else {}
                    if activity.get('status') == 'paused':
                        # A completed response may be saved just before being returned
                        # to the scheduler. Replay it once after restart, without billing again.
                        if activity.get('phase', '').startswith('LLM response saved:'):
                            responses = [p for p in out.glob('*/search/**/request_status.json')
                                         if read_json(p).get('status') == 'completed'
                                         and (p.parent / 'response.json').exists()]
                            if responses:
                                latest = max(responses, key=lambda p: p.stat().st_mtime_ns)
                                write_json(out / 'control/api_handoff.json',
                                           {'response_directory': str(latest.parent), 'consumed': False})
                        if alive(saved):
                            os.kill(saved['pid'], signal.SIGTERM)
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('No safe pause reached; API was not switched. Inspect status.')
                    time.sleep(0.5)
                deadline = time.monotonic() + 15
                while alive(saved) and time.monotonic() < deadline:
                    time.sleep(0.1)
                if alive(saved):
                    raise RuntimeError('Old worker did not exit; refusing a concurrent launch')
            saved['env_file'] = str(new_env)
            saved['api_host'] = urlsplit(environment['PASSDISTILL_OPENAI_BASE_URL']).hostname
            write_json(out / 'controller.json', saved)
            with (out / 'api_transitions.jsonl').open('a') as history:
                history.write(json.dumps({'time': time.time(), 'env_file': str(new_env),
                                          'api_host': saved['api_host'], 'model': saved['model']}) + '\n')
            pause.unlink(missing_ok=True)
            launch(out, saved)
    return 0


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] in {'_worker', 'status'}:
        return _main(arguments)
    CURRENT.parent.mkdir(parents=True, exist_ok=True)
    with (CURRENT.parent / 'cbench-dmxapi-controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _main(arguments)


if __name__ == '__main__':
    raise SystemExit(main())
