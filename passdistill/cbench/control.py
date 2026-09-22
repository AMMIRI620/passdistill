"""Cooperative pause points: never suspend a timed execution or an HTTP request."""
import json
from pathlib import Path
import time

_directory: Path | None = None


def configure(directory):
    global _directory
    _directory = Path(directory) if directory else None


def state(status, **details):
    if _directory is None:
        return
    _directory.mkdir(parents=True, exist_ok=True)
    path = _directory / 'activity.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'status': status, 'updated_at': time.time(), **details}, indent=2) + '\n')
    temporary.replace(path)


def checkpoint(phase):
    if _directory is None:
        return
    pause = _directory / 'pause.request'
    if pause.exists():
        print(f'[control] paused before {phase}; current operation completed', flush=True)
        state('paused', phase=phase)
        while pause.exists():
            time.sleep(0.5)
        print(f'[control] resumed: {phase}', flush=True)
    state('running', phase=phase)


def pending_response(system, user):
    """Reuse only the exact completed request saved during an API handoff."""
    if _directory is None:
        return None
    handoff = _directory / 'api_handoff.json'
    if not handoff.exists():
        return None
    record = json.loads(handoff.read_text())
    if record.get('consumed'):
        return None
    source = Path(record['response_directory'])
    if ((source / 'system_prompt.txt').read_text() != system or
            (source / 'user_prompt.txt').read_text() != user):
        return None
    result = json.loads((source / 'response.json').read_text())
    record.update(consumed=True, consumed_at=time.time())
    handoff.write_text(json.dumps(record, indent=2) + '\n')
    return source, result
