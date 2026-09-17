import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from passdistill.config import ExperimentConfig
from passdistill.correctness import compare_stderr_md5
from passdistill.orchestrator import run


class MD5CorrectnessTests(unittest.TestCase):
    def test_full_stderr_including_whitespace_and_numeric_spelling(self):
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory) / "reference.stderr"
            actual = Path(directory) / "candidate.stderr"
            content = b"begin D\n1.00 2.00 \nend D\n"
            expected.write_bytes(content)
            for candidate, accepted in (
                (content, True),
                (content.replace(b"1.00", b"1.01"), False),
                (content.replace(b"1.00", b"1.0"), False),
                (content.replace(b" \n", b"\n"), False),
                (content.replace(b"\n", b"\r\n"), False),
                (b"", False),
            ):
                actual.write_bytes(candidate)
                result = compare_stderr_md5(expected, actual)
                self.assertEqual(result.ok, accepted)
                self.assertEqual(result.expected_md5, hashlib.md5(content).hexdigest())
                self.assertEqual(result.actual_md5, hashlib.md5(candidate).hexdigest())

    def test_nonzero_tolerance_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not allow tolerances"):
            ExperimentConfig(rtol=1e-4)

    def test_legacy_resume_rejected_without_overwriting_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "legacy"
            run_dir.mkdir()
            config_file = run_dir / "config.json"
            original = json.dumps({"rtol": 1e-4, "atol": 1e-6})
            config_file.write_text(original)
            config = ExperimentConfig(artifacts_root=root, run_id="legacy", resume=True)
            with self.assertRaisesRegex(ValueError, "legacy correctness policy"):
                run(config, kernel="2mm", all_kernels=False)
            self.assertEqual(config_file.read_text(), original)


if __name__ == "__main__":
    unittest.main()
