"""cBench-only DMXAPI client; does not change the PolyBench client."""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from passdistill.agents.base import extract_json
from passdistill.util import write_json
from .control import checkpoint, pending_response


class DMXBackend:
    def __init__(self, model):
        self.model = model
        self.timeout = 900
        self.retries = 5

    def complete_json(self, system, user, *, schema_hint, out_dir):
        checkpoint('LLM ' + schema_hint)
        base = os.environ.get('PASSDISTILL_OPENAI_BASE_URL', '').rstrip('/')
        key = os.environ.get('PASSDISTILL_OPENAI_API_KEY')
        if not base or not key:
            raise RuntimeError('DMXAPI environment is missing; launch with manage_cbench_run.py')
        out_dir.mkdir(parents=True, exist_ok=True)
        pending = pending_response(system, user)
        (out_dir / 'system_prompt.txt').write_text(system)
        (out_dir / 'user_prompt.txt').write_text(user)
        if pending is not None:
            source, parsed = pending
            write_json(out_dir / 'response.json', parsed)
            write_json(out_dir / 'parsed_response.json', parsed)
            write_json(out_dir / 'request_status.json', dict(status='replayed_saved_response', source=str(source)))
            return parsed
        payload = {'model': self.model, 'stream': False, 'messages': [
            {'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}
        # Match PolyBench's retry budget, timeout and JSON repair policy, while
        # omitting temperature on every attempt for this model.
        write_json(out_dir / 'request_settings.json', dict(model=self.model, api_host=urlsplit(base).hostname,
                   timeout_sec=self.timeout, schema=schema_hint, temperature_omitted=True, automatic_retries=self.retries))
        started = time.monotonic()
        repair_mode = False
        for attempt in range(self.retries + 1):
            checkpoint('LLM ' + schema_hint)
            content = None
            request = urllib.request.Request(base + '/chat/completions', data=json.dumps(payload).encode(),
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, method='POST')
            write_json(out_dir / 'request_status.json', dict(status='running', attempt=attempt + 1,
                       max_attempts=self.retries + 1, elapsed_sec=time.monotonic()-started))
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read())
                content = data['choices'][0]['message']['content']
                response_name = f'repair_response_{attempt}.txt' if repair_mode else 'raw_response.txt'
                (out_dir / response_name).write_text(content)
                write_json(out_dir / f'api_usage_{attempt}.json', {'model': data.get('model'), 'usage': data.get('usage'),
                                                                  'response_id': data.get('id')})
                parsed = extract_json(content)
                write_json(out_dir / 'response.json', parsed)
                write_json(out_dir / 'parsed_response.json', parsed)
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
                if isinstance(exc, urllib.error.HTTPError):
                    error += '\n' + exc.read(2000).decode(errors='replace')
                (out_dir / f'error_{attempt}.txt').write_text(error)
                write_json(out_dir / 'request_status.json', dict(
                    status='retrying' if attempt < self.retries else 'failed', attempt=attempt + 1,
                    max_attempts=self.retries + 1, elapsed_sec=time.monotonic()-started, error=error))
                if attempt == self.retries:
                    raise RuntimeError(f'LLM JSON completion failed after {attempt + 1} attempts: {error}') from exc
                if content is not None:
                    repair_prompt = ('previous response is not valid JSON; return the same information using exactly '
                                     'the required schema, no markdown, no prose')
                    (out_dir / f'repair_prompt_{attempt + 1}.txt').write_text(repair_prompt)
                    payload = {'model': self.model, 'stream': False, 'messages': [
                        {'role': 'system', 'content': system}, {'role': 'user', 'content': user},
                        {'role': 'assistant', 'content': content}, {'role': 'user', 'content': repair_prompt}]}
                    repair_mode = True
                # No response means no JSON-repair conversation; retry the same payload.
                time.sleep(min(2**attempt, 30))
                continue
            write_json(out_dir / 'request_status.json', dict(status='completed', attempt=attempt + 1,
                       elapsed_sec=time.monotonic()-started))
            checkpoint('LLM response saved: ' + schema_hint)
            return parsed
