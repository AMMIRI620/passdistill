"""Candidate progress across all Teacher directions, including resume history."""
from datetime import datetime
import math

from passdistill.util import read_json, write_json


class Progress:
    def __init__(self, out, program, index, total, search, clang, teacher_budget, recovery_budget):
        self.out, self.program, self.index, self.total = out, program, index, total
        self.search, self.clang = search, clang
        self.budgets = {'Teacher': teacher_budget, 'Recovery': recovery_budget}
        self.entries = {'Teacher': {}, 'Recovery': {}}
        teachers = out / 'teacher_history.json'
        if teachers.exists():
            for entry in read_json(teachers):
                self._remember('Teacher', entry)
        for path in sorted((out / 'recovery').glob('*/candidates/*/candidate_summary.json')):
            self._remember('Recovery', read_json(path))

    def _remember(self, stage, entry):
        key = entry['direction_id'] if stage == 'Teacher' else entry['candidate_id']
        self.entries[stage][key] = entry
        return key

    @staticmethod
    def valid(stage, entry):
        runtime = entry.get('runtime')
        return (isinstance(runtime, (float, int)) and math.isfinite(runtime) and runtime > 0
                and entry.get('compile_ok') and entry.get('correctness_ok')
                and (stage == 'Teacher' or entry.get('status') == 'measured'))

    def snapshot(self):
        teacher = min((e['runtime'] for e in self.entries['Teacher'].values() if self.valid('Teacher', e)), default=None)
        recoveries = [('SEARCH_BASELINE', self.search)] + [
            (key, e['runtime']) for key, e in self.entries['Recovery'].items() if self.valid('Recovery', e)]
        best_id, best = min(recoveries, key=lambda item: item[1])
        return dict(best_teacher_vs_search=self.search / teacher if teacher else None,
                    best_teacher_vs_clang=self.clang / teacher if teacher else None,
                    best_recovery_vs_search=self.search / best,
                    best_recovery_vs_clang=self.clang / best, best_recovery_id=best_id,
                    teachers=len(self.entries['Teacher']), recoveries=len(self.entries['Recovery']))

    def update(self, stage, entry):
        key = self._remember(stage, entry)
        runtime = entry.get('runtime') if self.valid(stage, entry) else None
        status = entry.get('status')
        if not status:
            status = ('measured' if runtime else 'patch_failed' if entry.get('error', '').startswith('patch failed:')
                      else 'compile_failed' if not entry.get('compile_ok') else
                      'correctness_failed' if not entry.get('correctness_ok') else 'runtime_failed')
        self.emit(stage, key, status, runtime)

    def emit(self, stage='Summary', key='-', status='running', runtime=None):
        summary = self.snapshot()
        write_json(self.out / 'progress.json', summary)
        def ratio(value):
            return f'{value:.4f}x' if value is not None else 'n/a'
        count = f'{len(self.entries[stage])}/{self.budgets[stage]}' if stage in self.budgets else '-'
        print(f'{datetime.now().astimezone().isoformat(timespec="seconds")} '
              f'[{self.index}/{self.total} {self.program}] {stage}={count} id={key} status={status} '
              f'runtime={f"{runtime:.6f}s" if runtime else "n/a"} '
              f'current_vs_search={ratio(self.search / runtime if runtime else None)} '
              f'current_vs_clang={ratio(self.clang / runtime if runtime else None)} '
              + ' '.join(f'{field}={ratio(summary[field])}' for field in (
                  'best_teacher_vs_search', 'best_teacher_vs_clang', 'best_recovery_vs_search', 'best_recovery_vs_clang'))
              + f' best_recovery_id={summary["best_recovery_id"]}', flush=True)
