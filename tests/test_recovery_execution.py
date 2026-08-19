from pathlib import Path

import passdistill.evaluator as evaluator
import passdistill.search.recovery_search as recovery_search
import passdistill.search.teacher_search as teacher_search
from passdistill.agents.base import MockBackend
from passdistill.agents.catalog import load_static_catalog, relevant_catalog
from passdistill.agents.recovery_planner import plan_recovery_candidates
from passdistill.config import ExperimentConfig
from passdistill.search.recovery_search import global_candidate_id, requested_candidate_count, sanitize_local_candidate_id
from passdistill.search.teacher_search import global_direction_id, sort_valid_directions_for_recovery
from passdistill.types import BuildArtifacts, CorrectnessResult, EvaluationResult, Kernel, TimingResult


BASE = "module(function(loop-distribute,loop-vectorize,instcombine),verify)"


def test_global_candidate_id_includes_direction_and_round():
    assert global_direction_id(1, "D1") == "T1_D1"
    assert global_direction_id(2, "D1") == "T2_D1"
    assert global_candidate_id("T1_D1", 1, "C1") == "T1_D1_R1_C1"
    assert global_candidate_id("T1_D1", 2, "C1") == "T1_D1_R2_C1"
    assert sanitize_local_candidate_id("T1_D2_R2_C1", 9) == "C1"


def test_budget_schedule_prioritizes_fast_teachers_for_first_batches():
    directions = [
        {"direction_id": "D1", "teacher_runtime": 0.78},
        {"direction_id": "D2", "teacher_runtime": 0.53},
        {"direction_id": "D3", "teacher_runtime": 0.25},
    ]
    ordered = sort_valid_directions_for_recovery(directions)
    assert [item["direction_id"] for item in ordered] == ["D3", "D2", "D1"]


def test_requested_candidate_count_never_overshoots_budget():
    total = 0
    for _round in range(20):
        requested = requested_candidate_count(36 - total, 36 - total)
        total += requested
        if requested == 0:
            break
    assert total == 36
    assert requested_candidate_count(2, 9) == 2
    assert requested_candidate_count(9, 1) == 1


def test_feedback_context_and_mock_parent_branching(tmp_path):
    catalog = load_static_catalog(Path.cwd())
    direction = {
        "direction_id": "T1_D1",
        "optimization_intent": "loop locality and vectorization",
        "search_guidance": {"candidate_passes": ["loop-interchange", "licm", "loop-vectorize"]},
    }
    rel = relevant_catalog(catalog, direction=direction, baseline_pipeline=BASE, current_pipeline=BASE)
    previous_history = [
        {
            "candidate_id": "T1_D1_R1_C1",
            "parent_id": "SEARCH_BASELINE",
            "hypothesis": "legal loop interchange",
            "status": "measured",
            "runtime": 0.9,
            "speedup_vs_search_baseline": 1.1,
            "speedup_vs_parent": 1.1,
            "important_remarks": [],
            "edits": [],
            "opt_options": [],
        },
        {
            "candidate_id": "T1_D1_R1_C2",
            "parent_id": "SEARCH_BASELINE",
            "hypothesis": "illegal gvn nesting",
            "status": "preflight_failed",
            "normalized_error": "pass gvn is not allowed in manager loop",
            "edits": [],
            "opt_options": [],
        },
    ]
    candidates = plan_recovery_candidates(
        MockBackend(),
        direction=direction,
        baseline_context={"candidate_id": "SEARCH_BASELINE", "runtime": 1.0, "local_pipeline": {}},
        current_promoted_parent={"candidate_id": "T1_D1_R1_C1", "runtime": 0.9, "speedup_vs_search_baseline": 1.1, "local_pipeline": {}},
        current_measured_best={"candidate_id": "T1_D1_R1_C1", "runtime": 0.9, "speedup_vs_search_baseline": 1.1, "local_pipeline": {}},
        allowed_parents=[
            {"candidate_id": "SEARCH_BASELINE", "runtime": 1.0, "local_pipeline": {}},
            {"candidate_id": "T1_D1_R1_C1", "runtime": 0.9, "local_pipeline": {}},
        ],
        previous_history=previous_history,
        relevant_catalog=rel,
        remaining_budget=3,
        round_index=2,
        max_candidates=3,
        out_dir=tmp_path,
        repo_root=Path.cwd(),
    )
    context = (tmp_path / "feedback_context.json").read_text()
    assert "current_promoted_parent" in context
    assert "T1_D1_R1_C1" in context
    assert "preflight_failed" in context
    assert "relevant_catalog" in context
    assert candidates[0]["parent_id"] == "CURRENT_PROMOTED_BEST"
    assert any(candidate["parent_id"] == "SEARCH_BASELINE" for candidate in candidates)


def test_mock_parent_refinement_smoke(tmp_path, monkeypatch):
    source = tmp_path / "mock.c"
    source.write_text(
        "#include <stdio.h>\n"
        "static void kernel_mock(int n, double A[n]) {\n"
        "  for (int i = 0; i < n; i++) { A[i] = A[i] + 1.0; }\n"
        "}\n"
    )
    header = tmp_path / "mock.h"
    header.write_text("")
    frontend_ir = tmp_path / "frontend.ll"
    frontend_ir.write_text("; mock\n")
    expanded = tmp_path / "o3.txt"
    expanded.write_text(BASE)
    dump = tmp_path / "baseline.stderr"
    dump.write_text("0.0\n")
    remarks = tmp_path / "o3.opt.yaml"
    remarks.write_text("--- !Passed\nPass: loop-vectorize\n")

    def fake_source_eval(config, kernel, candidate_source, out_dir, candidate_id, *, baseline_dump=None, baseline_runtime=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        teacher_remarks = out_dir / "remarks" / "o3.opt.yaml"
        teacher_remarks.parent.mkdir(parents=True, exist_ok=True)
        teacher_remarks.write_text("--- !Passed\nPass: loop-vectorize\n")
        return EvaluationResult(
            candidate_id=candidate_id,
            compile_ok=True,
            correctness=CorrectnessResult(ok=True),
            timing=TimingResult(measured=[0.8], median=0.8),
            speedup_vs_baseline=1.25,
            artifacts=BuildArtifacts(remarks=teacher_remarks),
        )

    def fake_pipeline_eval(config, kernel, frontend_ir, pipeline, out_dir, candidate_id, *, baseline_dump, baseline_runtime, extra_options=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "pipeline.txt").write_text(pipeline + "\n")
        remarks_path = out_dir / "remarks.txt"
        remarks_path.write_text("--- !Passed\nPass: mock\n")
        runtime = 0.9
        if "_R2_C1" in candidate_id:
            runtime = 0.85
        elif "_R2_C2" in candidate_id:
            runtime = 0.98
        return EvaluationResult(
            candidate_id=candidate_id,
            compile_ok=True,
            correctness=CorrectnessResult(ok=True),
            timing=TimingResult(measured=[runtime], median=runtime),
            speedup_vs_baseline=baseline_runtime / runtime,
            artifacts=BuildArtifacts(remarks=remarks_path, pipeline=out_dir / "pipeline.txt"),
        )

    monkeypatch.setattr(teacher_search, "evaluate_source", fake_source_eval)
    monkeypatch.setattr(recovery_search, "evaluate_pipeline_candidate", fake_pipeline_eval)
    monkeypatch.setattr(evaluator, "evaluate_pipeline_candidate", fake_pipeline_eval)

    config = ExperimentConfig(
        repo_root=Path.cwd(),
        artifacts_root=tmp_path / "runs",
        max_teacher_rounds=1,
        max_teachers=1,
        max_recovery_rounds=2,
        max_pass_candidates=5,
        llm_backend="mock",
    )
    kernel = Kernel(name="mock", source=source, header=header, rel_dir=Path("mock"))
    summary = teacher_search.run_teacher_search(
        config,
        MockBackend(),
        kernel,
        baseline_summary={
            "baseline": {"timing": {"median": 1.0}, "artifacts": {"dump_stderr": str(dump), "remarks": str(remarks)}},
            "search_baseline": {"timing": {"median": 1.0}},
            "frontend_ir": str(frontend_ir),
            "expanded_pipeline": str(expanded),
        },
        out_dir=tmp_path / "search",
    )

    recovery_dir = tmp_path / "search" / "recovery" / "T1_mock_direction"
    oracle_prompt = (tmp_path / "search" / "oracle_round_1" / "user_prompt.txt").read_text()
    history = (recovery_dir / "history.json").read_text()
    r1_pipeline = (recovery_dir / "candidates" / "T1_mock_direction_R1_C1" / "materialized_pipeline.txt").read_text()
    r2_parent = (recovery_dir / "candidates" / "T1_mock_direction_R2_C1" / "parent_id.txt").read_text().strip()
    r2_pipeline = (recovery_dir / "candidates" / "T1_mock_direction_R2_C1" / "materialized_pipeline.txt").read_text()
    r2_branch_parent = (recovery_dir / "candidates" / "T1_mock_direction_R2_C2" / "parent_id.txt").read_text().strip()

    assert summary["pass_candidates_tried"] <= 5
    assert "Target function: kernel_mock" in oracle_prompt
    assert "Target kernel source:" in oracle_prompt
    assert "Instruction:" in oracle_prompt
    assert "T1_mock_direction_R1_C1" in history
    assert "T1_mock_direction_R2_C1" in history
    assert r2_parent == "T1_mock_direction_R1_C1"
    assert r2_branch_parent == "SEARCH_BASELINE"
    assert "loop(loop-interchange)" in r1_pipeline
    assert "loop(loop-interchange)" in r2_pipeline
    assert "loop-vectorize,instcombine" in r2_pipeline
    assert (recovery_dir / "candidates" / "T1_mock_direction_R2_C1" / "structured_remarks.json").exists()


def test_promotion_threshold_distinguishes_measured_best_and_promoted_parent(tmp_path, monkeypatch):
    class TwoRoundBackend:
        def __init__(self):
            self.calls = 0

        def complete_json(self, system, user, *, schema_hint, out_dir):
            self.calls += 1
            out_dir.mkdir(parents=True, exist_ok=True)
            if self.calls == 1:
                data = {
                    "candidates": [
                        {
                            "candidate_id": "C1",
                            "parent_id": "SEARCH_BASELINE",
                            "hypothesis": "small improvement",
                            "edits": [
                                {
                                    "type": "insert_fragment",
                                    "target": {"parent_manager": "function", "anchor": "loop-vectorize#1", "position": "after"},
                                    "fragment": [{"kind": "pass", "name": "instcombine"}],
                                }
                            ],
                            "opt_options": [],
                        }
                    ]
                }
            else:
                data = {
                    "candidates": [
                        {
                            "candidate_id": "C1",
                            "parent_id": "SEARCH_BASELINE",
                            "hypothesis": "large improvement",
                            "edits": [
                                {
                                    "type": "insert_fragment",
                                    "target": {"parent_manager": "function", "anchor": "loop-vectorize#1", "position": "after"},
                                    "fragment": [{"kind": "pass", "name": "gvn"}],
                                }
                            ],
                            "opt_options": [],
                        }
                    ]
                }
            (out_dir / "parsed_response.json").write_text("{}")
            return data

    def fake_pipeline_eval(config, kernel, frontend_ir, pipeline, out_dir, candidate_id, *, baseline_dump, baseline_runtime, extra_options=None):
        runtime = 0.998 if "_R1_" in candidate_id else 0.985
        remarks_path = out_dir / "remarks.txt"
        remarks_path.write_text("")
        return EvaluationResult(
            candidate_id=candidate_id,
            compile_ok=True,
            correctness=CorrectnessResult(ok=True),
            timing=TimingResult(measured=[runtime], median=runtime),
            speedup_vs_baseline=baseline_runtime / runtime,
            artifacts=BuildArtifacts(remarks=remarks_path),
        )

    monkeypatch.setattr(recovery_search, "evaluate_pipeline_candidate", fake_pipeline_eval)
    config = ExperimentConfig(repo_root=Path.cwd(), promotion_min_relative_gain=0.01, max_recovery_rounds=2, max_pass_candidates=2)
    frontend_ir = tmp_path / "frontend.ll"
    frontend_ir.write_text("; mock\n")
    dump = tmp_path / "dump.stderr"
    dump.write_text("0\n")
    kernel = Kernel(name="mock", source=tmp_path / "mock.c", header=tmp_path / "mock.h", rel_dir=Path("mock"))
    result = recovery_search.run_recovery_episode(
        config,
        TwoRoundBackend(),
        kernel,
        direction={"direction_id": "T1_D1", "search_guidance": {"candidate_passes": ["instcombine", "gvn"]}},
        frontend_ir=frontend_ir,
        baseline_pipeline=BASE,
        baseline_dump=dump,
        baseline_runtime=1.0,
        out_dir=tmp_path / "recovery",
        remaining_budget=2,
        max_rounds=2,
    )
    assert result["current_measured_best_id"] == "T1_D1_R2_C1"
    assert result["current_promoted_parent_id"] == "T1_D1_R2_C1"
    round2_context = (tmp_path / "recovery" / "planner_round_2" / "feedback_context.json").read_text()
    assert '"current_promoted_parent"' in round2_context
    assert '"candidate_id": "SEARCH_BASELINE"' in round2_context
    assert '"current_measured_best"' in round2_context
    assert "T1_D1_R1_C1" in round2_context
    first = result["history"][0]
    assert first["candidate_id"] == "T1_D1_R1_C1"
    assert first["runtime"] == 0.998
