import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from passdistill.agents.base import OpenAICompatBackend, make_backend
from passdistill.search.teacher_search import completed_teachers_in_round, resume_artifact_dir


class FakeResponse:
    def __init__(self, content: str):
        self.payload = json.dumps({"choices": [{"message": {"content": content}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


class OpenAICompatBackendTests(unittest.TestCase):
    @staticmethod
    def responses_response(text, status="completed"):
        response = FakeResponse("")
        response.payload = json.dumps({
            "id": "resp_test", "model": "gpt-5.6-sol", "status": status,
            "output": [{"type": "reasoning", "summary": []},
                       {"type": "message", "content": [
                           {"type": "output_text", "text": text[:3]},
                           {"type": "output_text", "text": text[3:]}]}],
            "usage": {"input_tokens": 2000, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}}
        }).encode()
        return response

    def test_responses_explicit_success_and_json_repair(self):
        requests = []
        def fake_urlopen(request, timeout):
            self.assertTrue(request.full_url.endswith('/responses'))
            self.assertEqual(timeout, 900)
            requests.append(json.loads(request.data))
            return self.responses_response('not json' if len(requests) == 1 else '{"ok":true}')
        with tempfile.TemporaryDirectory() as directory, patch(
            'passdistill.agents.base.urllib.request.urlopen', side_effect=fake_urlopen
        ), patch('passdistill.agents.base.time.sleep'), patch.dict('os.environ', {'PASSDISTILL_PROMPT_CACHE_MODE': 'implicit'}):
            backend = OpenAICompatBackend(model='gpt-5.6-sol', api_key='key', retries=1,
                                          api_mode='responses', prompt_cache_mode='explicit')
            root = Path(directory)
            self.assertEqual(backend.complete_json('sys', 'usr', schema_hint='test', out_dir=root), {'ok': True})
            self.assertEqual(requests[0]['input'], [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'usr'}])
            self.assertEqual(len(requests[1]['input']), 4)
            self.assertEqual(requests[1]['input'][2], {'role': 'assistant', 'content': 'not json'})
            self.assertEqual([r['temperature'] for r in requests], [0.2, 0.0])
            for request in requests:
                self.assertEqual(request['prompt_cache_options'], {'mode': 'explicit'})
                self.assertNotIn('prompt_cache_breakpoint', json.dumps(request))
                self.assertNotIn('messages', request)
                self.assertNotIn('previous_response_id', request)
                self.assertFalse(request['store'])
                self.assertFalse(request['stream'])
            usage = json.loads((root / 'api_usage_1.json').read_text())
            self.assertEqual(usage['api_mode'], 'responses')
            self.assertEqual(usage['usage']['input_tokens_details']['cache_write_tokens'], 0)
            self.assertTrue((root / 'response_envelope_1.json').exists())

    def test_responses_transport_retry_same_input_no_fallback(self):
        requests = []
        def fake_urlopen(request, timeout):
            self.assertTrue(request.full_url.endswith('/responses'))
            requests.append(json.loads(request.data))
            if len(requests) == 1:
                raise ConnectionResetError('dropped')
            return self.responses_response('{"ok":true}')
        with tempfile.TemporaryDirectory() as directory, patch(
            'passdistill.agents.base.urllib.request.urlopen', side_effect=fake_urlopen
        ), patch('passdistill.agents.base.time.sleep'):
            backend = OpenAICompatBackend(model='test', api_key='key', retries=1,
                                          api_mode='responses', prompt_cache_mode='explicit')
            backend.complete_json('sys', 'usr', schema_hint='test', out_dir=Path(directory))
            self.assertEqual(requests[0], requests[1])

    def test_responses_incomplete_not_accepted_even_with_valid_json(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            'passdistill.agents.base.urllib.request.urlopen', return_value=self.responses_response('{"ok":true}', 'incomplete')
        ):
            backend = OpenAICompatBackend(model='test', api_key='key', retries=0, api_mode='responses')
            with self.assertRaisesRegex(RuntimeError, 'not completed'):
                backend.complete_json('sys', 'usr', schema_hint='test', out_dir=Path(directory))
            self.assertFalse((Path(directory) / 'response.json').exists())
            self.assertTrue((Path(directory) / 'response_envelope_0.json').exists())

    def test_configured_responses_backend(self):
        backend = make_backend('openai', 'gpt-5.6-sol', api_mode='responses', prompt_cache_mode='explicit')
        self.assertEqual(backend.api_mode, 'responses')
        self.assertEqual(backend.prompt_cache_mode, 'explicit')

    def test_explicit_no_breakpoints_survives_json_repair(self):
        requests = []
        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data))
            return FakeResponse('not json' if len(requests) == 1 else '{"ok": true}')
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            'os.environ', {'PASSDISTILL_PROMPT_CACHE_MODE': 'explicit'}
        ), patch('passdistill.agents.base.urllib.request.urlopen', side_effect=fake_urlopen), patch('passdistill.agents.base.time.sleep'):
            root = Path(directory)
            OpenAICompatBackend(model='test', api_key='key', retries=1).complete_json('system', 'user', schema_hint='test', out_dir=root)
            self.assertEqual(len(requests), 2)
            for request in requests:
                self.assertEqual(request['prompt_cache_options'], {'mode': 'explicit'})
                self.assertNotIn('prompt_cache_breakpoint', json.dumps(request))
            self.assertTrue((root / 'api_usage_1.json').exists())

    def test_transport_retry_reuses_original_payload(self):
        requests = []
        timeouts = []

        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data))
            timeouts.append(timeout)
            if len(requests) == 1:
                raise ConnectionResetError("connection dropped")
            return FakeResponse('{"ok": true}')

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "passdistill.agents.base.urllib.request.urlopen", side_effect=fake_urlopen
        ), patch("passdistill.agents.base.time.sleep"):
            out_dir = Path(temp_dir)
            backend = OpenAICompatBackend(model="test", api_key="key", retries=1)
            result = backend.complete_json("system", "user", schema_hint="test", out_dir=out_dir)

            self.assertEqual(result, {"ok": True})
            self.assertEqual(requests[0], requests[1])
            self.assertEqual(timeouts, [900, 900])
            self.assertTrue((out_dir / "raw_response.txt").exists())
            self.assertFalse((out_dir / "repair_prompt_1.txt").exists())

    def test_json_failure_adds_repair_conversation(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data))
            if len(requests) == 1:
                return FakeResponse("not json")
            return FakeResponse('{"ok": true}')

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "passdistill.agents.base.urllib.request.urlopen", side_effect=fake_urlopen
        ), patch("passdistill.agents.base.time.sleep"):
            out_dir = Path(temp_dir)
            backend = OpenAICompatBackend(model="test", api_key="key", retries=1)
            result = backend.complete_json("system", "user", schema_hint="test", out_dir=out_dir)

            self.assertEqual(result, {"ok": True})
            self.assertEqual(len(requests[1]["messages"]), 4)
            self.assertEqual(requests[1]["messages"][2]["content"], "not json")
            self.assertTrue((out_dir / "repair_prompt_1.txt").exists())
            self.assertTrue((out_dir / "repair_response_1.txt").exists())

    def test_teacher_resume_rounds_and_artifact_directories(self):
        history = [
            {"direction_id": "T1_D1"},
            {"direction_id": "T1_D2"},
            {"direction_id": "T1_D3"},
            {"direction_id": "T2_D1"},
        ]
        self.assertEqual(completed_teachers_in_round(history, 1), 3)
        self.assertEqual(completed_teachers_in_round(history, 2), 1)
        self.assertEqual(completed_teachers_in_round(history, 3), 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            original = Path(temp_dir) / "oracle_round_2"
            original.mkdir()
            (original / "error_0.txt").write_text("transport failure")
            self.assertEqual(resume_artifact_dir(original), Path(temp_dir) / "oracle_round_2_resume_1")
            (Path(temp_dir) / "oracle_round_2_resume_1").mkdir()
            self.assertEqual(resume_artifact_dir(original), Path(temp_dir) / "oracle_round_2_resume_2")


if __name__ == "__main__":
    unittest.main()
