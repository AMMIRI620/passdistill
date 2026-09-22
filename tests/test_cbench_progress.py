from passdistill.cbench.progress import Progress
from passdistill.util import write_json


def candidate(name, runtime, status='measured'):
    return dict(candidate_id=name, runtime=runtime, status=status, compile_ok=True, correctness_ok=True)


def test_best_is_global_and_invalid_candidates_do_not_rank(tmp_path, capsys):
    progress = Progress(tmp_path, 'demo', 2, 27, 10, 8, 6, 50)
    progress.update('Teacher', dict(direction_id='T1_D1', runtime=5, compile_ok=True, correctness_ok=True))
    progress.update('Recovery', candidate('T1_D1_R1_C1', 8))
    progress.update('Recovery', candidate('T2_D1_R1_C1', 9))
    progress.update('Recovery', candidate('T2_D1_R1_C2', 1, 'incorrect'))
    state = progress.snapshot()
    assert state['best_teacher_vs_search'] == 2
    assert state['best_recovery_vs_search'] == 1.25
    assert state['best_recovery_vs_clang'] == 1
    assert state['best_recovery_id'] == 'T1_D1_R1_C1'
    assert state['recoveries'] == 3
    line = capsys.readouterr().out.splitlines()[-1]
    assert '[2/27 demo] Recovery=3/50' in line
    assert 'current_vs_search=n/a' in line
    assert 'best_recovery_vs_search=1.2500x' in line


def test_resume_restores_best_without_double_counting(tmp_path):
    write_json(tmp_path / 'teacher_history.json', [dict(direction_id='T1_D1', runtime=4, compile_ok=True, correctness_ok=True)])
    entry = candidate('T1_D1_R1_C1', 5)
    write_json(tmp_path / 'recovery/T1_D1/candidates/T1_D1_R1_C1/candidate_summary.json', entry)
    progress = Progress(tmp_path, 'demo', 1, 1, 10, 9, 6, 50)
    assert progress.snapshot()['best_recovery_vs_search'] == 2
    progress.update('Recovery', entry)
    assert progress.snapshot()['recoveries'] == 1
    progress.update('Teacher', dict(direction_id='T2_D1', compile_ok=False, error='patch failed: invalid signature'))
    assert progress.snapshot()['best_teacher_vs_search'] == 2.5


def test_search_baseline_remains_best_when_candidates_are_slower(tmp_path):
    progress = Progress(tmp_path, 'demo', 1, 1, 10, 9, 6, 50)
    progress.update('Recovery', candidate('C1', 12))
    assert progress.snapshot()['best_recovery_vs_search'] == 1
    assert progress.snapshot()['best_recovery_id'] == 'SEARCH_BASELINE'
