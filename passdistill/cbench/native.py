"""cBench native multi-TU build and isolated dataset execution.

Build and staging primitives are retained from the validated cBench implementation;
search scheduling and PolyBench evaluation are deliberately outside this module.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import statistics
import subprocess
import time

from passdistill.types import TimingResult
from passdistill.util import write_json
from .control import checkpoint

def command(argv, cwd, log, timeout=300, env=None):
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
    elapsed = time.perf_counter() - started
    log.with_suffix('.stdout').write_bytes(stdout)
    log.with_suffix('.stderr').write_bytes(stderr)
    record = dict(argv=list(map(str, argv)), cwd=str(cwd), returncode=proc.returncode,
                  timed_out=timed_out, elapsed_sec=elapsed, stdout=str(log.with_suffix('.stdout')),
                  stderr=str(log.with_suffix('.stderr')))
    write_json(log.with_suffix('.json'), record)
    return record


def checked(argv, cwd, log, timeout=300):
    r = command(argv, cwd, log, timeout)
    if r['returncode'] or r['timed_out']:
        raise RuntimeError(f'{log}: '+Path(r['stderr']).read_text(errors='replace')[-4000:])
    return r


def frontend(program, llvm_bin, out):
    checkpoint('frontend ' + program['program'])
    out.mkdir(parents=True, exist_ok=False)
    units = []
    for u in program['tus']:
        path = out/(u['id']+'.ll')
        args = [str(llvm_bin/'clang'), *u['flags'], '-Xclang', '-disable-llvm-passes',
                '-S', '-emit-llvm', u['source'], '-o', str(path)]
        checked(args, program['source_dir'], out/(u['id']+'_frontend'))
        units.append({**u, 'ir':str(path), 'frontend_argv':args})
    manifest = out/'manifest.json'
    write_json(manifest, units)
    return manifest


def build(program, llvm_bin, out, *, manifest=None, pipeline=None, opt_options=(), source_dir=None):
    checkpoint('build ' + program['program'])
    out.mkdir(parents=True, exist_ok=False)
    objects, logs, remarks = [], [], []
    # The caller materializes the candidate ONCE; all TUs receive these exact values.
    write_json(out/'configuration.json', dict(pipeline=pipeline, opt_options=list(opt_options),
               deployment_scope='all tunable translation units', tus=[u['id'] for u in program['tus']]))
    units = json.loads(Path(manifest).read_text()) if manifest else program['tus']
    if manifest and [(u['id'], u['source'], u['flags']) for u in units] != [
            (u['id'], u['source'], u['flags']) for u in program['tus']]:
        raise ValueError('frontend manifest does not cover the exact original TU set and flags')
    for u in units:
        obj = out/(u['id']+'.o')
        if manifest:
            optimized = out/(u['id']+'.ll')
            remark = out/(u['id']+'.opt.yaml')
            args = [str(llvm_bin/'opt'), *opt_options, '-passes='+pipeline, u['ir'], '-S', '-o', str(optimized),
                    '-pass-remarks=.*', '-pass-remarks-missed=.*', '-pass-remarks-analysis=.*',
                    '-pass-remarks-output='+str(remark)]
            logs.append(checked(args, program['source_dir'], out/(u['id']+'_opt')))
            remarks.append(f"TU {u['id']} FILE {u['source']} PHASE opt\n"+remark.read_text())
            logs.append(checked([str(llvm_bin/'llc'), '-O=3', '-filetype=obj', '-relocation-model=pic',
                                 str(optimized), '-o', str(obj)], program['source_dir'], out/(u['id']+'_llc')))
        else:
            cwd = source_dir or program['source_dir']
            remark = out/(u['id']+'.opt.yaml')
            logs.append(checked([str(llvm_bin/'clang'), *u['flags'], '-c', u['source'], '-o', str(obj),
                                 '-fsave-optimization-record', '-foptimization-record-file='+str(remark)],
                                cwd, out/(u['id']+'_clang')))
            remarks.append(f"TU {u['id']} FILE {u['source']} PHASE clang\n"+remark.read_text())
        objects.append(str(obj))
    binary = out/'a.out'
    logs.append(checked([str(llvm_bin/'clang'), *objects, *program['link_flags'], '-o', str(binary)],
                        source_dir or program['source_dir'], out/'link'))
    (out/'remarks.txt').write_text('\n'.join(remarks))
    return binary


def stage(program, binary, out):
    # Isolate both mutable inputs and outputs, before the timer starts.
    src = Path(program['source_dir'])
    cwd = out/'tree'/program['program']/'src'
    shutil.copytree(src, cwd)
    for name in program['inputs']:
        target = (cwd/name).resolve()
        if not target.is_relative_to((out/'tree').resolve()):
            raise ValueError('input escapes staging tree')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src/name, target)
    for name in program['outputs']:
        (cwd/name).unlink(missing_ok=True)
    shutil.copy2(binary, cwd/'a.out')
    (cwd/'_finfo_dataset').write_text(str(program['native_repeat'])+'\n')
    return cwd


def execute(program, binary, out, cpu=3, numa_node=0, timeout=300):
    cwd = stage(program, binary, out)
    env = {'PATH': '/usr/bin:/bin', **program['environment']}
    # Never silently fall back to unpinned execution if numactl is unavailable.
    argv = ['numactl', f'--physcpubind={cpu}', f'--membind={numa_node}',
            'bash', '-c', 'exec ./a.out ' + program['command']]
    record = command(argv, cwd, out / 'execution', timeout, env)
    hashes = {}
    if record['returncode'] == 0 and not record['timed_out']:
        for name in program['outputs']:
            path = cwd / name
            if not path.is_file():
                record['output_error'] = 'missing functional output ' + name
                break
            hashes[name] = hashlib.md5(path.read_bytes()).hexdigest()
    record.update(output_md5=hashes, native_repeat=program['native_repeat'], dataset_id='1',
                  cpu=cpu, numa_node=numa_node)
    record['valid'] = (record['returncode'] == 0 and not record['timed_out']
                       and len(hashes) == len(program['outputs']) and bool(hashes))
    write_json(out / 'run.json', record)
    return record


def median_timing(samples, valid):
    complete = valid and len(samples) == 3 and all(math.isfinite(t) and t > 0 for t in samples)
    return TimingResult(measured=list(samples), median=statistics.median(samples) if complete else None)


def measure(program, binary, out, *, cpu=3, numa_node=0, reference=None, timeout=300):
    """One correctness pre-run followed by exactly three complete executions.

    Staging and byte hashing are outside each timer. A failure invalidates the
    candidate without retries, partial medians, or outlier filtering.
    """
    checkpoint('measure ' + program['program'])
    pre = execute(program, binary, out / 'correctness_prerun', cpu, numa_node, timeout)
    expected = reference if reference is not None else pre['output_md5']
    records, samples = [pre], []
    valid = pre['valid'] and pre['output_md5'] == expected
    if valid:
        for i in range(3):
            record = execute(program, binary, out / f'timed_{i+1}', cpu, numa_node, timeout)
            records.append(record)
            if not record['valid'] or record['output_md5'] != expected:
                valid = False
                break
            samples.append(record['elapsed_sec'])
    timing = median_timing(samples, valid)
    result = dict(timing=timing, correctness_ok=timing.median is not None,
                  reference_md5=expected, runs=records, policy=dict(
                      dataset_id='1', native_repeat=program['native_repeat'], runs=3,
                      statistic='median', cpu=cpu, numa_node=numa_node,
                      scope='whole program elapsed seconds; staging/hashing excluded'))
    write_json(out / 'measurement.json', result)
    return result
