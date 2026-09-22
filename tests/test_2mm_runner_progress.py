import contextlib
import importlib.util
import io
import json
from pathlib import Path


def test_candidate_progress_reports_round_and_best(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_2mm_dmxapi_50.py"
    spec = importlib.util.spec_from_file_location("run_2mm_dmxapi_50", script)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.ROOT = tmp_path
    candidate_dir = (
        tmp_path / "artifacts" / "runs" / "test-run" / "2mm" / "search" /
        "recovery" / "T1_D1" / "candidates" / "T1_D1_R2_C1"
    )
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "candidate_summary.json").write_text(json.dumps({
        "candidate_id": "T1_D1_R2_C1",
        "round": 2,
        "status": "measured",
        "speedup_vs_search_baseline": 1.12,
    }))
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        best = runner.report_new_candidates("test-run", set(), 1.0)
    assert best == 1.12
    assert "candidate=1/50" in output.getvalue()
    assert "round=R2" in output.getvalue()
    assert "current_speedup_vs_search=1.1200x" in output.getvalue()
    assert "best_speedup_vs_search=1.1200x" in output.getvalue()


def test_select_env_and_override_model_without_editing_file(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_2mm_dmxapi_50.py"
    spec = importlib.util.spec_from_file_location("run_2mm_env_test", script)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    env_file = tmp_path / ".passdistill.env"
    original = ('PASSDISTILL_OPENAI_API_KEY=test-only-key\n'
                'PASSDISTILL_OPENAI_BASE_URL=https://xcode.best/v1\n'
                'PASSDISTILL_MODEL=gpt-5.5\n')
    env_file.write_text(original)
    monkeypatch.setenv("PASSDISTILL_OPENAI_API_KEY", "old-provider-key")
    monkeypatch.setenv("PASSDISTILL_OPENAI_BASE_URL", "https://old.invalid/v1")
    environment = runner.dmx_environment(env_file, model="gpt-5.6-sol")
    assert environment["PASSDISTILL_MODEL"] == "gpt-5.6-sol"
    assert environment["PASSDISTILL_OPENAI_API_KEY"] == "test-only-key"
    assert environment["PASSDISTILL_OPENAI_BASE_URL"] == "https://xcode.best/v1"
    assert env_file.read_text() == original
    assert runner.dmx_environment(env_file)["PASSDISTILL_MODEL"] == "gpt-5.5"
