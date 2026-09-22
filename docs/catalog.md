# Fixed full catalog

Recovery Planner receives all 78 curated LLVM 22.1.3 passes and three options:
`allow-unroll-and-jam`, `force-vector-width`, `force-vector-interleave`.
No relevance filtering, alphabetical truncation, or artificial numeric value
grid is applied. Related-option metadata contains only retained options.

Both `baseline_pipeline_outline` and `current_pipeline_outline` contain all
anchors. `pipeline_outline(..., limit=N)` remains available for callers that
explicitly want a truncated view.

`set_pass_parameter` uses the pass schema:

- Boolean values select a declared positive/negative flag and remove its
  opposite (for example `pre: false` produces `no-pre`).
- A flag without a value produces the bare token. SROA modes and unroll
  optimization levels replace the previous mode/level.
- Only schema entries containing `=` produce key/value parameters; missing
  values and malformed syntax are rejected. LLVM still determines whether a
  value is semantically supported; no discrete value range is imposed.

Fragment validation distinguishes bare tokens from key/value tokens, so
`allowspeculation=False` is rejected before LLVM preflight.

New experiments save `catalog_snapshot.json` and the SHA-256 of the exact
catalog bytes in config, aggregate/kernel summaries, and recovery catalog
summaries. Resume rejects a missing or mismatched hash. Changing catalog
requires a new run ID. The configured next run is
`polybench30-deepseek-50-catalog78-perf-only-teacher-report-v1`.
