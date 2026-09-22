# PolyBench correctness policy

## Performance-only recovery candidates

Recovery candidates now use `candidate_evaluation_mode=performance_only`:
only the timing executable is built and run, with no candidate dump build or MD5
comparison. After a successful timing build, `correctness_ok` is treated as true
by experiment policy, not as evidence of output equivalence. Compilation errors,
runtime failures and timeouts still fail evaluation. Warmups, timing runs and
promotion rules are unchanged.

Teachers retain full-stderr MD5 comparisons, now with
`teacher_correctness_policy=report_only`: a mismatch is recorded but does not
prevent timing, intent distillation, or Recovery. Patch/build/run failures still
prevent a usable Teacher. Three Oracle rounds each request two Teachers (six
total); the existing Oracle feedback format is unchanged.

Search and kernel summaries include `teacher_correct_count`,
`teacher_incorrect_count`, and `teacher_unchecked_count`. The latter includes
failures that never reached output comparison, not confirmed numerical errors.
`valid_teacher_count` now means usable for Recovery, not correctness-passing.
The fastest Teacher may be incorrect; kernel summaries expose
`best_teacher_correctness_ok` so its performance/transfer metrics can be interpreted.

The O3 search
baseline still builds a dump executable to provide the Teacher reference.
Old candidate-MD5 runs cannot be resumed under this policy; use a new run ID.
This prevents mixing the two experimental acceptance criteria.

## Teacher validation and historical candidate validation

New experiments use `correctness_mode=stderr_md5` and
`correctness_reference=search_baseline`. Both `rtol` and `atol` must be zero.

The default expanded O3 pipeline is compiled and run to establish the reference
stderr. Its output is not required to match the separate direct Clang O3 build.
Teachers compare their complete saved stderr against that O3 pipeline reference
using MD5. Under report-only policy a mismatch does not block measurement.
Historical MD5-gated runs also checked recovery candidates and blocked measurement
on mismatch; their results must not be mixed with the new policy.
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
