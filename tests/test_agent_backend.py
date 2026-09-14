import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from passdistill.agents.base import OpenAICompatBackend
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
            self.assertEqual(timeouts, [300, 300])
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
