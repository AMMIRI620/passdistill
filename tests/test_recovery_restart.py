import json
from pathlib import Path
from unittest.mock import patch

import tempfile
import unittest

from passdistill.baseline import remeasure_search_baseline
from passdistill.config import ExperimentConfig
from passdistill.search import teacher_search
from passdistill.types import BuildArtifacts, EvaluationResult, Kernel, TimingResult
from passdistill.util import write_json


def baseline_fixture(tmp_path, dataclasses=False):
    binary = tmp_path / "search_o3_time"
    binary.write_bytes(b"unchanged executable")
    pipeline = tmp_path / "pipeline.txt"
    pipeline.write_text("function(instcombine)")
    evaluation = EvaluationResult(
        "search_o3", compile_ok=True, timing=TimingResult([10.0], [10.0] * 3, 10.0),
        artifacts=BuildArtifacts(binary=binary, dump_stderr=tmp_path / "reference"),
    )
    from passdistill.types import to_jsonable
    return {
        "kernel": "mock",
        "baseline": {"timing": {"median": 12.0}, "artifacts": {"remarks": None}},
        "search_baseline": evaluation if dataclasses else to_jsonable(evaluation),
        "frontend_ir": str(tmp_path / "input.ll"), "expanded_pipeline": str(pipeline),
    }


def check_remeasure_updates_persisted_baseline_and_preserves_original(tmp_path, dataclasses):
    baseline = baseline_fixture(tmp_path, dataclasses)
    config = ExperimentConfig()
    with patch("passdistill.baseline.run_binary", return_value=(TimingResult([8.0], [8.0, 9.0, 10.0], 9.0), [])) as run:
        assert remeasure_search_baseline(config, baseline, tmp_path / "baseline") == 9.0
        run.assert_called_once_with(config, tmp_path / "search_o3_time", log_dir=tmp_path / "baseline/search_baseline/remeasure_1/runs")
        remeasure_search_baseline(config, baseline, tmp_path / "baseline")
    saved = json.loads((tmp_path / "baseline/baseline_summary.json").read_text())
    assert saved == baseline
    assert saved["initial_search_baseline"]["timing"]["median"] == 10.0
    assert saved["search_baseline"]["timing"]["median"] == 9.0
    assert saved["search_baseline"]["speedup_vs_baseline"] == 12 / 9
    assert (tmp_path / "baseline/search_baseline/remeasure_1/measurement.json").exists()
    assert (tmp_path / "baseline/search_baseline/remeasure_2/measurement.json").exists()
    assert (tmp_path / "search_o3_time").read_bytes() == b"unchanged executable"


def check_failed_remeasure_does_not_replace_reference(tmp_path):
    baseline = baseline_fixture(tmp_path)
    out = tmp_path / "baseline"
    write_json(out / "baseline_summary.json", baseline)
    previous = (out / "baseline_summary.json").read_text()
    with patch("passdistill.baseline.run_binary", return_value=(TimingResult([8.0], [8.0], 8.0), [])):
        with unittest.TestCase().assertRaisesRegex(RuntimeError, "remeasurement failed"):
            remeasure_search_baseline(ExperimentConfig(), baseline, out)
    assert baseline["search_baseline"]["timing"]["median"] == 10.0
    assert (out / "baseline_summary.json").read_text() == previous


def check_zero_candidate_guard_includes_invalid_and_partial_candidates(tmp_path, kind):
    history = []
    if kind == "candidate_dir":
        (tmp_path / "recovery/T1/candidates/invalid_partial").mkdir(parents=True)
    elif kind == "history":
        write_json(tmp_path / "recovery/T1/history.json", [{"status": "invalid_candidate"}])
    elif kind == "summary":
        write_json(tmp_path / "recovery/T1/summary.json", {"candidates_tried": 1})
    elif kind == "teacher_history":
        history = [{"recovery": {"candidates_tried": 1}}]
    assert teacher_search.has_recovery_candidates(tmp_path, history) == (kind != "none")


def check_resume_missing_intent_without_regeneration_or_remeasurement_of_teacher(tmp_path, distill_fails):
    baseline = baseline_fixture(tmp_path)
    source = tmp_path / "source.c"
    source.write_text("void kernel_mock() {}")
    kernel = Kernel("mock", source, tmp_path / "source.h", tmp_path)
    out = tmp_path / "search"
    teacher = out / "teachers/T1_D1"
    history = [{"direction_id": "T1_D1", "compile_ok": True, "runtime": 2.0,
                "correctness_checked": True, "correctness_ok": False}]
    write_json(out / "teacher_history.json", history)
    write_json(teacher / "proposal.json", {"local_direction_id": "D1"})
    (teacher / "source.c").write_text(source.read_text())
    (teacher / "distill").mkdir()
    (teacher / "distill/error_0.txt").write_text("previous network failure")
    remarks = teacher / "eval/remarks/o3.opt.yaml"
    remarks.parent.mkdir(parents=True)
    remarks.write_text("original teacher remarks")
    config = ExperimentConfig(resume=True, max_teachers=1, max_pass_candidates=1,
                              max_recovery_rounds=1, uniform_fixed_recovery_budget=True)
    events = []
    def distill(*args, **kwargs):
        events.append("distill")
        assert kwargs["teacher_remarks"] == "original teacher remarks"
        assert kwargs["out_dir"] == teacher / "distill_resume_1"
        if distill_fails:
            raise RuntimeError("API still down")
        return {"optimization_intent": "test"}
    def refresh(*args):
        events.append("remeasure")
        return 9.0
    def recover(*args, **kwargs):
        events.append("recovery")
        assert kwargs["baseline_runtime"] == 10.0
        return {"direction_id": "T1_D1", "new_candidates_tried": 1,
                "candidates_tried": 1, "history": []}
    with patch.object(teacher_search, "propose_teachers") as propose, patch.object(
        teacher_search, "evaluate_source"
    ) as evaluate, patch.object(teacher_search, "distill_direction", side_effect=distill), patch(
        "passdistill.baseline.remeasure_search_baseline", side_effect=refresh
    ), patch.object(teacher_search, "run_recovery_episode", side_effect=recover):
        if distill_fails:
            with unittest.TestCase().assertRaisesRegex(RuntimeError, "API still down"):
                teacher_search.run_teacher_search(config, object(), kernel, baseline_summary=baseline, out_dir=out)
            assert events == ["distill"]
            assert not (teacher / "intent.json").exists()
        else:
            result = teacher_search.run_teacher_search(config, object(), kernel, baseline_summary=baseline, out_dir=out)
            assert events == ["distill", "recovery"]
            assert result["valid_teacher_count"] == 1
            assert result["teacher_incorrect_count"] == 1
            assert result["teacher_candidates_tried"] == 1
        propose.assert_not_called()
        evaluate.assert_not_called()
    assert (teacher / "distill/error_0.txt").read_text() == "previous network failure"


class RecoveryRestartTests(unittest.TestCase):
    def test_remeasurement(self):
        for dataclasses in (False, True):
            with self.subTest(dataclasses=dataclasses), tempfile.TemporaryDirectory() as directory:
                check_remeasure_updates_persisted_baseline_and_preserves_original(Path(directory), dataclasses)

    def test_failed_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            check_failed_remeasure_does_not_replace_reference(Path(directory))

    def test_zero_candidate_guard(self):
        for kind in ("candidate_dir", "history", "summary", "teacher_history", "none"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                check_zero_candidate_guard_includes_invalid_and_partial_candidates(Path(directory), kind)

    def test_intent_resume(self):
        for fails in (False, True):
            with self.subTest(fails=fails), tempfile.TemporaryDirectory() as directory:
                check_resume_missing_intent_without_regeneration_or_remeasurement_of_teacher(Path(directory), fails)
