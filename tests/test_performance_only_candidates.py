import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from passdistill import evaluator
from passdistill.config import ExperimentConfig
from passdistill.orchestrator import run
from passdistill.types import CommandResult, Kernel, TimingResult


class PerformanceOnlyCandidateTests(unittest.TestCase):
    def evaluate(self, root, *, reference=False, preflight_ok=True, median=2.0):
        config = ExperimentConfig()
        kernel = Kernel("test", root / "source.c", root / "source.h", root)
        with ExitStack() as stack:
            for name in ("opt_pipeline", "compile_ir_to_object", "compile_polybench_object", "link_objects"):
                stack.enter_context(patch.object(evaluator, name, return_value=CommandResult([], 0)))
            stack.enter_context(patch.object(evaluator, "preflight_pipeline", return_value=CommandResult([], 0 if preflight_ok else 1)))
            emit = stack.enter_context(patch.object(evaluator, "emit_frontend_ir", return_value=CommandResult([], 1, stderr="reference dump sentinel")))
            compare = stack.enter_context(patch.object(evaluator, "compare_stderr_md5", side_effect=AssertionError("must not compare candidate output")))
            timing = stack.enter_context(patch.object(evaluator, "run_binary", return_value=(TimingResult(median=median), [])))
            result = evaluator.evaluate_pipeline_candidate(
                config, kernel, root / "input.ll", "default<O3>", root / "candidate", "C1",
                baseline_dump=root / "nonexistent-reference.stderr", baseline_runtime=4.0,
                build_reference_dump=reference,
            )
            return result, emit.call_count, compare.call_count, timing.call_count

    def test_candidate_only_builds_and_times_performance_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, emit, compare, timing = self.evaluate(root)
            self.assertTrue(result.correctness.ok)
            self.assertEqual(result.speedup_vs_baseline, 2.0)
            self.assertEqual((emit, compare, timing), (0, 0, 1))
            self.assertIsNone(result.artifacts.dump_stderr)
            self.assertFalse(list((root / "candidate").glob("*dump*")))

    def test_reference_still_builds_dump(self):
        with tempfile.TemporaryDirectory() as directory:
            result, emit, compare, timing = self.evaluate(Path(directory), reference=True)
            self.assertEqual((emit, compare, timing), (1, 0, 0))
            self.assertEqual(result.error, "reference dump sentinel")

    def test_preflight_failure_does_not_pass_or_measure(self):
        with tempfile.TemporaryDirectory() as directory:
            result, emit, compare, timing = self.evaluate(Path(directory), preflight_ok=False)
            self.assertFalse(result.compile_ok)
            self.assertIsNone(result.correctness)
            self.assertEqual(timing, 0)

    def test_missing_runtime_is_not_a_performance_success(self):
        with tempfile.TemporaryDirectory() as directory:
            result, *_ = self.evaluate(Path(directory), median=None)
            self.assertIsNone(result.timing.median)
            self.assertIsNone(result.speedup_vs_baseline)

    def test_md5_experiment_cannot_resume_under_new_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "old"
            target.mkdir()
            original = json.dumps({"correctness_mode": "stderr_md5", "correctness_reference": "search_baseline"})
            (target / "config.json").write_text(original)
            with self.assertRaisesRegex(ValueError, "choose a new run_id"):
                run(ExperimentConfig(artifacts_root=root, run_id="old", resume=True), kernel="2mm", all_kernels=False)
            self.assertEqual((target / "config.json").read_text(), original)


if __name__ == "__main__":
    unittest.main()
