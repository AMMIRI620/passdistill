# Recovery restart timing and intent checkpoints

## Current policy: no automatic remeasurement

At the user's request, recovery no longer remeasures baseline after teacher
generation, even when starting from zero candidates. Each kernel's initial
baseline measurement is retained; resume reuses the saved value. Existing v3
remeasurements and results are preserved, not retroactively recalculated.
The missing-intent resume fix remains enabled. Running workers already loaded
before this code change retain their code; newly launched kernel workers use
this policy.

## Historical v3 remeasurement policy (disabled)

Before a kernel's recovery starts with zero candidates, after all eligible
teachers have been distilled, remeasure the existing Search baseline executable.
Use the configured warmups, runs, CPU/NUMA pinning, and median statistic. Do not
recompile it or change the correctness reference. A failed/incomplete measurement
stops the search instead of falling back to stale timing.

The updated denominator is written to `baseline/baseline_summary.json` and used
by candidate evaluation, parent comparison, promotion, and final summaries.
`initial_search_baseline` preserves the original evaluation. Each attempt keeps
its raw measurements under `baseline/search_baseline/remeasure_N/`.

If any candidate exists (including invalid or interrupted candidates), preserve
the existing denominator on resume. This prevents mixing denominators within one
search. This policy does not eliminate drift during a long recovery search.

Teacher evaluation is saved before intent distillation. On resume, an eligible
teacher with no `intent.json` must finish distillation before recovery; it must
not be silently dropped. Reuse its source, runtime, and compiler remarks without
generating or measuring another teacher. Preserve failed API artifacts in the
original `distill/` directory; retries use `distill_resume_N/`. A repeated API
failure propagates and leaves the teacher pending. Correctness remains report-only.

The September 20 rerun uses
`configs/polybench30_gpt56sol_50_baseline_refresh_v3.json`: rerun syr2k, correlation,
and covariance, then the 15 unfinished kernels, under a new run ID. Previous
results are not overwritten. Teacher generation, catalog, recovery budgets,
promotion threshold, and evaluation policies are unchanged.

Launch from the repository root:

```bash
python3 -u scripts/run_polybench30_dmxapi_50.py \
  --config configs/polybench30_gpt56sol_50_baseline_refresh_v3.json \
  --env-file .passdistill_dmxapi.env --model gpt-5.6-sol
```

## Background runner and API switching

Run from the repository root. The controller defaults to the v3 config above;
pass `--config PATH` for another experiment. These commands preserve artifacts,
resume completed work, and append output to that run's `runner.log`:

```bash
# Start, or stop the existing experiment process group and resume using DMX.
python3 scripts/manage_polybench_run.py restart --env-file .passdistill_dmxapi.env

# Switch the same experiment to the provider in .passdistill.env.
python3 scripts/manage_polybench_run.py restart --env-file .passdistill.env

# Inspect live processes, or stop runner and all its child processes.
python3 scripts/manage_polybench_run.py status
python3 scripts/manage_polybench_run.py stop
```

The model always comes from the experiment config, not a different model name in
the env file. The controller validates credentials before stopping, identifies
only the selected experiment's process group, waits for termination, and refuses
to start over a held runner lock. After 10 seconds it kills remaining processes
in the same group. Each launch uses a separate session. API switches are recorded
in `api_transitions.jsonl` without secrets; existing provider-generated artifacts
are retained. Terminating local clients does not cancel an already submitted
request on the provider's server. This Linux controller requires visibility and
permission to signal the experiment's processes.
