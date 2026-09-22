import json
from pathlib import Path
import threading
import time
from unittest.mock import patch

import pytest

from passdistill.cbench import control
from passdistill.cbench.dmxapi import DMXBackend


def test_dmx_payload_omits_temperature_and_keeps_900_seconds(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('PASSDISTILL_OPENAI_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('PASSDISTILL_OPENAI_API_KEY', 'test-key')
    def open_request(request, timeout):
        payload = json.loads(request.data)
        assert 'temperature' not in payload
        assert payload['model'] == 'gpt-5.6-sol'
        assert timeout == 900
        from io import BytesIO
        return BytesIO(json.dumps({'choices': [{'message': {'content': '{"directions":[]}'}}],
                                  'usage': {'prompt_tokens': 12}}).encode())
    with patch('urllib.request.urlopen', side_effect=open_request) as request:
        assert DMXBackend('gpt-5.6-sol').complete_json('system', 'user', schema_hint='source_oracle.v1', out_dir=tmp_path) == {'directions': []}
    assert request.call_count == 1
    assert capsys.readouterr().out == ''
    assert 'test-key' not in ''.join(p.read_text() for p in tmp_path.iterdir())


def test_dmx_retries_transport_five_times_before_failing(tmp_path, monkeypatch):
    monkeypatch.setenv('PASSDISTILL_OPENAI_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('PASSDISTILL_OPENAI_API_KEY', 'test-key')
    with patch('urllib.request.urlopen', side_effect=TimeoutError('network timeout')) as request, patch('passdistill.cbench.dmxapi.time.sleep') as sleep:
        with pytest.raises(RuntimeError, match='network timeout'):
            DMXBackend('gpt-5.6-sol').complete_json('s', 'u', schema_hint='source_oracle.v1', out_dir=tmp_path)
    assert request.call_count == 6
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2, 4, 8, 16]
    assert all(call.kwargs['timeout'] == 900 for call in request.call_args_list)
    assert json.loads((tmp_path / 'request_status.json').read_text())['status'] == 'failed'
    assert len(list(tmp_path.glob('error_*.txt'))) == 6


@pytest.mark.parametrize('schema', ['source_oracle.v1', 'direction_distiller.v1', 'recovery_planner.v2'])
def test_transport_retry_succeeds_without_json_repair(tmp_path, monkeypatch, capsys, schema):
    from io import BytesIO
    from http.client import RemoteDisconnected
    monkeypatch.setenv('PASSDISTILL_OPENAI_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('PASSDISTILL_OPENAI_API_KEY', 'test-key')
    response = BytesIO(json.dumps({'choices': [{'message': {'content': '{"ok":true}'}}]}).encode())
    with patch('urllib.request.urlopen', side_effect=[RemoteDisconnected('closed'), response]) as request, patch('passdistill.cbench.dmxapi.time.sleep'):
        assert DMXBackend('gpt-5.6-sol').complete_json('s', 'u', schema_hint=schema, out_dir=tmp_path) == {'ok': True}
    assert request.call_count == 2
    payloads = [json.loads(call.args[0].data) for call in request.call_args_list]
    assert payloads[0] == payloads[1]
    assert len(payloads[1]['messages']) == 2
    assert 'temperature' not in payloads[1]
    assert json.loads((tmp_path / 'request_status.json').read_text())['status'] == 'completed'
    assert capsys.readouterr().out == ''


def test_invalid_json_uses_repair_and_transport_failure_keeps_repair_payload(tmp_path, monkeypatch):
    from io import BytesIO
    monkeypatch.setenv('PASSDISTILL_OPENAI_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('PASSDISTILL_OPENAI_API_KEY', 'test-key')
    def response(text):
        return BytesIO(json.dumps({'choices': [{'message': {'content': text}}]}).encode())
    with patch('urllib.request.urlopen', side_effect=[response('invalid json'), TimeoutError('closed'), response('{"ok":true}')]) as request, patch('passdistill.cbench.dmxapi.time.sleep'):
        assert DMXBackend('gpt-5.6-sol').complete_json('s', 'u', schema_hint='source_oracle.v1', out_dir=tmp_path) == {'ok': True}
    payloads = [json.loads(call.args[0].data) for call in request.call_args_list]
    assert payloads[1] == payloads[2]
    assert payloads[1]['messages'][2] == {'role': 'assistant', 'content': 'invalid json'}
    assert len(payloads[1]['messages']) == 4
    assert all('temperature' not in payload for payload in payloads)
    assert (tmp_path / 'repair_response_2.txt').exists()


def test_cooperative_pause_continues_same_operation_once(tmp_path):
    pause = tmp_path / 'pause.request'
    pause.touch()
    completed = []
    control.configure(tmp_path)
    worker = threading.Thread(target=lambda: (control.checkpoint('next candidate'), completed.append(True)))
    try:
        worker.start()
        deadline = time.monotonic() + 3
        while not (tmp_path / 'activity.json').exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert json.loads((tmp_path / 'activity.json').read_text())['status'] == 'paused'
        assert completed == []
        pause.unlink()
        worker.join(3)
        assert not worker.is_alive()
        assert completed == [True]
        assert json.loads((tmp_path / 'activity.json').read_text())['status'] == 'running'
    finally:
        pause.unlink(missing_ok=True)
        worker.join(3)
        control.configure(None)


def test_api_switch_replays_exact_saved_response_without_another_request(tmp_path, monkeypatch):
    monkeypatch.setenv('PASSDISTILL_OPENAI_BASE_URL', 'https://new-api.invalid/v1')
    monkeypatch.setenv('PASSDISTILL_OPENAI_API_KEY', 'new-test-key')
    previous = tmp_path / 'previous'
    previous.mkdir()
    (previous / 'system_prompt.txt').write_text('system')
    (previous / 'user_prompt.txt').write_text('user')
    (previous / 'response.json').write_text('{"candidates": []}')
    controls = tmp_path / 'control'
    controls.mkdir()
    (controls / 'api_handoff.json').write_text(json.dumps({'response_directory': str(previous), 'consumed': False}))
    control.configure(controls)
    try:
        # A different request must never consume the pending response.
        assert control.pending_response('system', 'different user') is None
        with patch('urllib.request.urlopen') as request:
            result = DMXBackend('gpt-5.6-sol').complete_json('system', 'user',
                     schema_hint='recovery_planner.v2', out_dir=tmp_path / 'resumed')
        assert result == {'candidates': []}
        request.assert_not_called()
        assert control.pending_response('system', 'user') is None
        status = json.loads((tmp_path / 'resumed/request_status.json').read_text())
        assert status['status'] == 'replayed_saved_response'
    finally:
        control.configure(None)
