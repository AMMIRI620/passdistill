# PolyBench correctness policy

New experiments use `correctness_mode=stderr_md5` and
`correctness_reference=search_baseline`. Both `rtol` and `atol` must be zero.

The default expanded O3 pipeline is compiled and run to establish the reference
stderr. Its output is not required to match the separate direct Clang O3 build.
Teachers and recovery candidates compare their complete saved stderr against
that O3 pipeline reference using MD5. A mismatch prevents performance measurement.
Whitespace, newlines, array labels, and numeric spelling are all significant;
there is no tokenization, stripping, or numeric tolerance in this check.

Subprocess output is captured as text, as in the local GroupTuner evaluator.
The saved stderr is hashed without further normalization. PolyBench headers and
printing functions are unchanged: 2mm doubles still use `%0.2lf`. Equality of
these printed dumps does not imply bitwise equality of the underlying doubles.

Each evaluated teacher/candidate stores `correctness.json` with `expected_md5`,
`actual_md5`, and `ok`. Baseline and experiment summaries record the policy and
reference MD5. Direct Clang O3 timing remains available as a performance metric;
changing the correctness reference does not redefine the speedup denominators.

Artifacts from the earlier tolerant/Clang-reference policy are preserved.
Resuming them under the new policy is rejected before replacing their config.
Choose a new `run_id` and generate fresh teachers and recovery history for an
experiment using this policy.
