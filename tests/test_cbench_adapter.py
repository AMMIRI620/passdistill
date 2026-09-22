import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from passdistill.cbench import native
from passdistill.cbench.adapter import CBenchAdapter, CBenchBackend
from passdistill.cbench.context import readonly_context, replacement_function, split_hotspot
from passdistill.cbench.runner import check_identity, load_program
from passdistill.config import ExperimentConfig
from passdistill.util import write_json


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def example(tmp_path):
    source = tmp_path / 'native/demo/src'
    source.mkdir(parents=True)
    (source / 'main.c').write_text('int helper(void);\nint main(void) { return helper(); }\n')
    hot = source / 'helper.c'
    hot.write_text('/* function helper elsewhere is irrelevant */\nstatic int helper(void)\n{\n return 0;\n}\n/* trailing context */\n')
    data = source / '../../inputs/in.dat'
    data.parent.mkdir(parents=True)
    data.write_text('original input')
    (source / 'result').write_text('stale output')
    program = dict(program='demo', source_dir=str(source), native_repeat=80, dataset_id='1',
                   command='../../inputs/in.dat > result', environment={'LC_ALL': 'C'},
                   inputs=['../../inputs/in.dat'], outputs=['result'],
                   tus=[dict(id='tu_000', source='main.c', flags=['-O3']),
                        dict(id='tu_001', source='helper.c', flags=['-O3'])], link_flags=[])
    hotspot = dict(program='demo', status='ready', path=str(hot), function='helper',
                   start_line=2, end_line=5)
    return program, hotspot


def test_minimal_inventory_is_static_and_sources_match():
    locations = json.loads((ROOT / 'configs/cbench_hotspots.json').read_text())
    assert len(locations['programs']) == 32
    assert sum(p['status'] == 'ready' for p in locations['programs']) == 28
    for p in locations['programs']:
        if p['status'] == 'ready':
            program, hotspot = load_program(ROOT, p['program'], ROOT / 'configs/cbench_hotspots.json', ROOT / 'configs/cbench_builds.json')
            _, function, _ = split_hotspot(ROOT / hotspot['path'], hotspot)
            assert p['function'] in function
            assert program['native_repeat'] > 0


def test_three_samples_use_median_without_partial_results():
    assert native.median_timing([1, 1, 10], True).median == 1
    for samples, valid in [([1, 1], True), ([1, 1, 10], False), ([1, float('nan'), 10], True)]:
        assert native.median_timing(samples, valid).median is None


def test_stage_resets_outputs_inputs_and_keeps_native_repeat(example, tmp_path):
    program, _ = example
    binary = tmp_path / 'binary'
    binary.write_text('binary')
    first = native.stage(program, binary, tmp_path / 'first')
    assert (first / '_finfo_dataset').read_text() == '80\n'
    assert not (first / 'result').exists()
    (first / '../../inputs/in.dat').write_text('mutated input')
    (first / 'result').write_text('old candidate')
    second = native.stage(program, binary, tmp_path / 'second')
    assert (second / '../../inputs/in.dat').read_text() == 'original input'
    assert not (second / 'result').exists()


@pytest.mark.parametrize('failure', ['wrong_output', 'timeout', 'exit_error'])
def test_bad_timed_sample_invalidates_candidate_without_retry(monkeypatch, tmp_path, failure):
    calls = []
    def execute(*args):
        calls.append(args)
        i = len(calls)
        return dict(valid=not (i == 3 and failure != 'wrong_output'),
                    output_md5={'out': 'bad' if i == 3 and failure == 'wrong_output' else 'good'},
                    elapsed_sec=1)
    monkeypatch.setattr(native, 'execute', execute)
    result = native.measure({'program': 'demo', 'native_repeat': 80}, tmp_path / 'binary', tmp_path / 'measure')
    assert result['timing'].median is None
    assert result['timing'].measured == [1]
    assert not result['correctness_ok']
    assert len(calls) == 3  # pre-run plus two timed attempts, no retry


def test_prerun_is_not_a_timing_sample(monkeypatch, tmp_path):
    times = iter([999, 1, 1, 10])
    monkeypatch.setattr(native, 'execute', lambda *args: dict(valid=True, output_md5={'out': 'ok'}, elapsed_sec=next(times)))
    result = native.measure({'program': 'demo', 'native_repeat': 80}, tmp_path / 'binary', tmp_path / 'measure')
    assert result['timing'].measured == [1, 1, 10]
    assert result['timing'].median == 1


def test_execution_pins_cpu_and_numa(example, tmp_path, monkeypatch):
    program, _ = example
    binary = tmp_path / 'binary'
    binary.touch()
    def command(argv, cwd, log, timeout, env):
        assert argv[:3] == ['numactl', '--physcpubind=3', '--membind=0']
        assert (cwd / '_finfo_dataset').read_text() == '80\n'
        (cwd / 'result').write_text('ok')
        return dict(returncode=0, timed_out=False, elapsed_sec=1)
    monkeypatch.setattr(native, 'command', command)
    assert native.execute(program, binary, tmp_path / 'run')['valid']


def test_teacher_replaces_only_audited_span_and_uses_independent_project(example, tmp_path, monkeypatch):
    program, hotspot = example
    adapter = CBenchAdapter(ExperimentConfig(), program, hotspot)
    original = adapter.source.read_bytes()
    candidate = tmp_path / 'teacher.c'
    replacement = adapter.function.replace('return 0', 'return 1')
    adapter.apply_teacher_patch(adapter.source, replacement, candidate)
    assert candidate.read_text() == adapter.prefix + replacement + adapter.suffix
    def evaluate(out, candidate_id, **kwargs):
        project = kwargs['source_dir']
        assert (project / 'helper.c').read_text() == candidate.read_text()
        assert (project / 'main.c').read_bytes() == (adapter.source_root / 'main.c').read_bytes()
        (project / 'main.c').write_text('Teacher-only mutation')
        return 'evaluated'
    monkeypatch.setattr(adapter, '_evaluate', evaluate)
    assert adapter.evaluate_source(adapter.config, adapter.kernel, candidate, tmp_path / 'eval', 'T1') == 'evaluated'
    assert adapter.source.read_bytes() == original
    assert 'Teacher-only' not in (adapter.source_root / 'main.c').read_text()
    with pytest.raises(ValueError):
        replacement_function(replacement + 'int extra(void) { return 0; }', adapter.function)
    adapter.source.write_text(original.decode().replace('return 0', 'return 2'))
    _, changed, _ = split_hotspot(adapter.source, hotspot)
    assert 'return 2' in changed


def test_context_does_not_expand_data_tables_or_other_function_bodies(tmp_path):
    source = tmp_path / 'file.c'
    source.write_text('#include "types.h"\nint table[1000] = {\n#include "data.inc"\n};\nint other(void) { return 98765; }\n')
    (tmp_path / 'types.h').write_text('typedef unsigned int WORD;\n')
    (tmp_path / 'data.inc').write_text('very large constant data')
    view = readonly_context(source, tmp_path)
    assert 'WORD' in view
    assert 'very large constant data' not in view
    assert '98765' not in view
    assert 'table[1000]' in view


def test_recovery_uses_same_configuration_for_every_original_tu(example, tmp_path, monkeypatch):
    program, _ = example
    units = []
    for u in program['tus']:
        ir = tmp_path / (u['id'] + '.ll')
        ir.write_text('original IR ' + u['source'])
        units.append({**u, 'ir': str(ir)})
    manifest = tmp_path / 'frontend.json'
    write_json(manifest, units)
    calls = []
    def checked(argv, cwd, log, timeout=300):
        calls.append(argv)
        stderr = log.with_suffix('.stderr')
        stderr.write_text('')
        for arg in argv:
            if arg.startswith('-pass-remarks-output='):
                Path(arg.split('=', 1)[1]).write_text('')
        return {'stderr': str(stderr)}
    monkeypatch.setattr(native, 'checked', checked)
    native.build(program, Path('/llvm'), tmp_path / 'candidate', manifest=manifest,
                 pipeline='function(instcombine)', opt_options=['-unroll-threshold=123'])
    opts = [c for c in calls if c[0] == '/llvm/opt']
    assert len(opts) == 2
    assert all(c[1:3] == ['-unroll-threshold=123', '-passes=function(instcombine)'] for c in opts)
    assert [c[3] for c in opts] == [u['ir'] for u in units]
    assert not any(c[0] == '/llvm/clang' and '-c' in c for c in calls)
    with pytest.raises(FileExistsError):
        native.build(program, Path('/llvm'), tmp_path / 'candidate', manifest=manifest, pipeline='x')


def test_failed_tu_has_no_o3_fallback_or_link(example, tmp_path, monkeypatch):
    program, _ = example
    calls = []
    def fail(argv, *args):
        calls.append(argv)
        raise RuntimeError('compile failed')
    monkeypatch.setattr(native, 'checked', fail)
    with pytest.raises(RuntimeError):
        native.build(program, Path('/llvm'), tmp_path / 'candidate')
    assert len(calls) == 1


def test_backend_only_adds_cbench_recovery_context(tmp_path):
    backend = Mock()
    adapter = CBenchBackend(backend, ROOT)
    for schema in ['direction_distiller.v1', 'source_oracle.v1']:
        adapter.complete_json('system', 'user', schema_hint=schema, out_dir=tmp_path)
        assert backend.complete_json.call_args.args == ('system', 'user')
    adapter.complete_json('system', 'user', schema_hint='recovery_planner.v2', out_dir=tmp_path)
    assert 'multiple C translation units' in backend.complete_json.call_args.args[0]
    assert backend.complete_json.call_args.args[0].endswith('system')


@pytest.mark.parametrize('field', ['hotspot', 'measurement', 'settings'])
def test_resume_rejects_changed_identity(tmp_path, field):
    path = tmp_path / 'identity.json'
    current = {k: 'original' for k in ['hotspot', 'measurement', 'settings']}
    check_identity(path, current, False)
    check_identity(path, current, True)
    with pytest.raises(ValueError, match='identity mismatch'):
        check_identity(path, {**current, field: 'changed'}, True)
    with pytest.raises(ValueError, match='already exists'):
        check_identity(path, current, False)


def test_resume_ignores_legacy_file_hashes(tmp_path):
    current = {'program': {'inputs': ['input.dat']}, 'hotspot': {'function': 'main'}}
    old = {**current, 'source_sha256': 'stale', 'catalog_sha256': 'stale',
           'prompts': {'file': 'stale'}, 'implementation': {'file': 'stale'},
           'toolchain': {'clang': 'stale'},
           'program': {'inputs': {'input.dat': 'stale'}, 'runner_sha256': 'stale'},
           'hotspot': {'function': 'main', 'source_sha256': 'stale'}}
    path = tmp_path / 'identity.json'
    write_json(path, old)
    check_identity(path, current, True)
