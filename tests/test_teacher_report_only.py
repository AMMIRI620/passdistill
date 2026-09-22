import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from passdistill import evaluator
from passdistill.config import ExperimentConfig
from passdistill.search import teacher_search
from passdistill.types import CommandResult, CorrectnessResult, EvaluationResult, Kernel, TimingResult


class TeacherReportOnlyTests(unittest.TestCase):
    def test_mismatch_is_still_timed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected, actual = root / "reference", root / "actual"
            expected.write_text("1.00")
            actual.write_text("2.00")
            kernel = Kernel("mock", root / "source.c", root / "source.h", root)
            with patch.object(evaluator, "compile_c", return_value=CommandResult([], 0)), patch.object(
                evaluator, "dump_output", return_value=(root / "stdout", actual, [], True, "")
            ), patch.object(evaluator, "run_binary", return_value=(TimingResult(median=2.0), [])) as timing:
                result = evaluator.evaluate_source(ExperimentConfig(), kernel, kernel.source, root / "eval", "T1", baseline_dump=expected, baseline_runtime=4.0)
            self.assertFalse(result.correctness.ok)
            self.assertEqual(result.timing.median, 2.0)
            timing.assert_called_once()

    def test_two_per_round_and_incorrect_teachers_recover_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.c"
            source.write_text("void kernel_mock() {}")
            pipeline = root / "pipeline.txt"
            pipeline.write_text("function(instcombine)")
            kernel = Kernel("mock", source, root / "source.h", root)
            baseline = {
                "baseline": {"timing": {"median": 1.0}, "artifacts": {"remarks": None}},
                "search_baseline": {"timing": {"median": 1.0}, "artifacts": {"dump_stderr": str(root / "reference")}},
                "frontend_ir": str(root / "input.ll"), "expanded_pipeline": str(pipeline),
            }
            config = ExperimentConfig(max_pass_candidates=6, max_recovery_rounds=1, uniform_fixed_recovery_budget=True)
            requests = []
            def propose(*args, **kwargs):
                requests.append((kwargs["max_candidates"], len(kwargs["history"])))
                return [{"direction_id": "D1"}, {"direction_id": "D2"}]
            def evaluate(*args, **kwargs):
                return EvaluationResult(candidate_id=args[4], compile_ok=True, correctness=CorrectnessResult(ok=False), timing=TimingResult(median=2.0))
            def recover(*args, **kwargs):
                return {"direction_id": kwargs["direction"]["direction_id"], "new_candidates_tried": 1, "candidates_tried": 1, "history": []}
            with patch.object(teacher_search, "propose_teachers", side_effect=propose), patch.object(
                teacher_search, "apply_teacher_patch", side_effect=lambda src, patch_text, dest: dest.write_text(src.read_text())
            ), patch.object(teacher_search, "evaluate_source", side_effect=evaluate), patch.object(
                teacher_search, "distill_direction", return_value={}
            ), patch.object(teacher_search, "run_recovery_episode", side_effect=recover) as recovery, patch(
                "passdistill.baseline.remeasure_search_baseline", return_value=1.0
            ) as remeasure:
                summary = teacher_search.run_teacher_search(config, object(), kernel, baseline_summary=baseline, out_dir=root / "search")
                self.assertEqual(requests, [(2, 0), (2, 2), (2, 4)])
                self.assertEqual(summary["teacher_correct_count"], 0)
                self.assertEqual(summary["teacher_incorrect_count"], 6)
                self.assertEqual(summary["teacher_unchecked_count"], 0)
                self.assertEqual(summary["valid_teacher_count"], 6)
                self.assertEqual(recovery.call_count, 6)
                config.resume = True
                resumed = teacher_search.run_teacher_search(config, object(), kernel, baseline_summary=baseline, out_dir=root / "search")
                self.assertEqual(resumed["valid_teacher_count"], 6)
                self.assertEqual(len(requests), 3)
                remeasure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
