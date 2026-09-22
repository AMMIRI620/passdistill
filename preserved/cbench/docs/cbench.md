# cBench dataset 1 / mean of three

The new entry points are separate from `run_passdistill.py`; the latter's `--all`
continues to mean PolyBench. Existing PolyBench prompts, kernel-only candidate
compilation, fixed `polybench.c` object, stderr MD5 and median remain unchanged.

## Prepare and run

Extract the supplied archive into a **new empty directory**, without replacing
any existing checkout or baseline data. The current extraction is
`work/cbench-native`. From the repository root:

```sh
python3 scripts/prepare_cbench.py --root work/cbench-native --out artifacts/cbench-NEW
python3 scripts/smoke_cbench.py --manifest artifacts/cbench-NEW/hotspots.json --out artifacts/cbench-smoke-NEW
/tmp/passdistill-test-env/bin/python -m pytest -q tests
```

Preparation is serial across programs, builds, profiling and timing. Output
directories must not exist. It discovers the local `*/src/_ccc_info_datasets`
scope rather than a paper's program count. `--program NAME` is an explicit
supplementary subset, not the default. Failed preparation remains on disk.

Formal search (not launched by preparation or smoke):

```sh
python3 scripts/run_cbench.py --config configs/cbench_dataset1_mean3_formal.json \
  --manifest artifacts/cbench-NEW/hotspots.json --program automotive_bitcount \
  --out artifacts/cbench-formal-NEW
```

The formal config uses the existing checkout's OpenAI backend/model settings;
credentials are loaded through its existing mechanism. No credentials are stored
in preparation artifacts. The mock config is `cbench_dataset1_mean3.json`.
Blocked programs cannot enter Teacher search. `--resume` requires the exact
frozen snapshot and current matching source/input/catalog/policy/toolchain/host.

## Native protocol

`all_run__1_dataset` iterates dataset ID **1**, and `__run` reads the matching
four-line record in `_ccc_info_datasets`. The record contains the command and
native loop count, written to `_finfo_dataset`. The optional second argument to
`__run` overrides the native count. The older GroupTuner runner's `__run 1 1`
is an override, not a dataset definition. This adapter never uses it.

The runner executes the native command with its original arguments and shell
redirections, in a private `program/src` directory with the same relative input
layout. Source-side resources and referenced inputs are copied afresh before
each execution; old declared outputs are removed. The original input tree is
never a run directory. The native wrapper and CLI-internal loops are retained.
For example bitcount retains both 80 wrapper repetitions and argument 1125000.

Each full evaluation performs one independent correctness pre-run, then exactly
three timed complete workloads, with no framework warmup or retry. Staging,
MD5, build and log writing are outside the monotonic elapsed timer. Native I/O
and process execution remain inside it. Any failure/mismatch invalidates the
entire mean; successful partial samples and all failed observations remain in
`measurement.json`. Native checker output declarations are retained byte for
byte, even if this blocks noisy programs. qsort additionally checks
`sorted_output.dat`, confirmed in `qsort_large.c`; its `output.dat` CLI argument
is unused. Logs are distinct from functional files.

`runtime_sec()` reads explicit cBench mean records and legacy PolyBench median
records. cBench has no median field. Shared Teacher, Distiller, Recovery,
promotion, summary and resume use the same mean. Recovery resumes from saved
samples rather than interpreting a median as a mean.

## Build and profile

The native Makefile's dry-run compiler commands determine each TU and its flags;
there is no independent source glob defining the program. All TUs get Clang
22.1.3 GNU89 O3 frontend IR with `-g`, no fast-math, normal inlining and no PGO.
Legacy diagnostic relaxations and `-fcommon` are explicit in every command.
Native link dependencies and ABI flags are retained. `-no-pie` is explicit for
stable ELF addresses during symbolization; llc uses PIC objects and O3.
No candidate falls back to an O3 object on failure. Object and remark filenames
include a unique TU ID. The materialized pipeline and option list are frozen once
per candidate and applied to every original TU. Teacher source copies cannot
replace this manifest or its hash-checked frontend IR.

Sampling uses `perf record -e cycles:u --call-graph dwarf`. It does not silently
switch to software events, change perf permissions or feed profiles to LLVM.
Every sample's weight belongs only to the innermost accurately mapped source
function. Unmapped/library IPs remain excluded with their original weight.
Ranking retains full Self period counts and both total-event and project-only
denominators, deterministic tie breaks, carriers/TUs/symbols/inline chains.
`main` is eligible. Missing samples or source attribution produce blocked/null,
never a guessed hotspot. The now-enabled host has completed actual cycles:u recordings and DWARF/AST
source mapping. `perf script -G` supplies one sampled IP per event; call stacks
are retained in perf.data but are never summed into Self. Batched symbolization
and DWARF CU lookups retain the real binary symbol/TU identity; Clang AST byte
ranges, including macro argument names, locate definitions without confusing
prototypes or same-name functions. See `docs/cbench_dataset1_report.md` for the
current 24 ready / 8 blocked inventory and evidence.

The two-program smoke uses an explicitly labelled comment-only source fixture,
mock distillation and replay proposals. Clang/opt/llc, linking, MD5 and timing are
real. It checks a same-pipeline candidate, an inserted instcombine candidate,
editor rejection and real LLVM rejection. It claims neither an LLM optimization
nor hotspot-guided search when sampling is blocked.

## Sampling an existing frozen preparation

After host perf access is available, reuse the original search executables and
preserve the earlier baseline means:

```sh
python3 scripts/profile_cbench_frozen.py --manifest configs/cbench_hotspots_dataset1.json --out artifacts/cbench-record-NEW
python3 scripts/analyze_cbench_profiles.py --recordings artifacts/cbench-record-NEW --out artifacts/cbench-analysis-NEW
python3 scripts/smoke_cbench_frozen_search.py --manifest artifacts/cbench-analysis-NEW/hotspots.json --out artifacts/cbench-frozen-smoke-NEW
```

The last command exercises the shared Teacher → Distiller → Recovery loop using
the actual frozen primary hotspots of network_dijkstra and automotive_bitcount.
Only proposals/distillation are replay/mock. Builds, exact correctness and mean3
are real; resume checks the same snapshot and consumes no extra budget. It uses
one Teacher fixture and three Recovery attempts per program, not the formal
6/50 budget. The separate earlier `smoke_cbench.py` also tests real LLVM rejection.

## Formal 24-program batch

`run_cbench24.py` selects exactly the 24 ready entries from the frozen manifest,
snapshots the manifest and experiment configuration, and runs programs serially.
Credentials are loaded from the explicitly selected env file and are not copied
into artifacts. Each program has its own worker log, search history and result.
A failed program is recorded and the batch continues; it does not restart a
failed measurement until it happens to pass.

```sh
python3 -u scripts/run_cbench24.py \
  --config configs/cbench_dataset1_mean3_formal.json \
  --manifest configs/cbench_hotspots_dataset1.json \
  --env-file .passdistill.env --out artifacts/runs/cbench24-NEW
```

The active launch location is recorded in `artifacts/cbench-current-launch.json`.
The run directory's `batch_state.json` records the active program and completed
programs. Resume a stopped batch using the same command and directory plus
`--resume`; the configuration and hotspot snapshot must still match. Do not
start another copy while the existing runner holds `artifacts/cbench-formal.lock`.

## Current formal policy: median3 (user revision)

The user changed cBench aggregation to the **median of exactly three complete
valid workload runs**. Native repeats, dataset 1, zero extra warmups, exact output
checks and failure rejection remain unchanged. Older mean3 artifacts stay readable
as mean3; they are never resumed into the new median3 experiment.

The new baseline snapshot derives explicit `statistic="median"`, `median` and
`runtime_sec` from the original three valid samples, retaining their run evidence.
It has no disguised mean value in a median field. Hotspots are unchanged because
this aggregation change does not affect the workload or sampled Self selection.

```sh
python3 -u scripts/run_cbench24.py \
  --config configs/cbench_dataset1_median3_formal.json \
  --manifest configs/cbench_hotspots_dataset1_median3.json \
  --env-file .passdistill_dmxapi.env --out artifacts/runs/cbench24-median3-NEW
```

The new baseline table is `artifacts/cbench-median3-preparation-v1/REPORT.md`.
Shared Teacher/Distiller/Recovery and resume smoke evidence is in
`artifacts/cbench-median3-smoke-v1`. Both median3 and legacy mean3 are tested,
including their deliberately different ranking of [1,1,10] versus [3,3,3].

### Teacher diff repair and bitcount rerun

The cBench patch adapter now matches the entire old-side hunk exactly and uniquely
against the original project. It derives replacement content from the diff body,
so erroneous hunk counts and asymmetric context do not cause false rejection.
It never discards context; missing or ambiguous matches, reordered/overlapping
hunks, renames, unsafe paths, and native workload-control edits are rejected.
All file sections are parsed before replacement files are written. PolyBench's
patch adapter is unchanged. cBench patch failures record `status=patch_failed`,
`failure_stage=patch`, and `compile_attempted=false`.

The six original bitcount proposals are preserved as regression fixtures in
`tests/fixtures/cbench_teacher_patches/`. Their real build/correctness/median3
replay is written to `artifacts/cbench-patchfix-teacher-replay-v1` by:

```bash
python3 scripts/replay_cbench_teachers.py \
  --config configs/cbench_dataset1_median3_formal.json \
  --manifest artifacts/cbench-patchfix-preparation-v1/hotspots.json \
  --teachers artifacts/runs/cbench24-gpt56sol-median3-6t50r-20260921-150441/programs/automotive_bitcount/search/teachers \
  --program automotive_bitcount --out /tmp/cbench-bitcount-teacher-replay
```

A new frozen implementation identity retains the original baseline samples and
sampled hotspots. The fresh formal batch runs bitcount first, then previously
unstarted programs; completed old results remain in their original directory.
`artifacts/cbench-patchfix-control-v1` records the serial handoff, replay and launch.
The current launch is recorded in `artifacts/cbench-current-launch.json`. Watch:

```bash
python3 - <<'PY'
import json, subprocess
launch = json.load(open('artifacts/cbench-current-launch.json'))
subprocess.run(['tail', '-f', launch['run_dir'] + '/progress.log'])
PY
```

### API temperature compatibility

`OpenAICompatBackend` omits `temperature` in both ordinary requests and JSON
repair requests, for Responses and Chat Completions. The provider/model default
is used; `temperature=0` is not a compatibility fallback. Each request's
`request_settings.json` records `temperature_policy=omitted_provider_default`.
The model, API host, caching options, prompts, and measurement policy remain
unchanged. Transport failures are not automatically replayed; bounded JSON repair still adds
its repair conversation after a complete model response is received. Regression tests simulate a provider rejecting any
request containing `temperature`, including the repair path.

### Focused prompt context (hotspot-context-v1)

The formal experiment was stopped at the user's request; this change does not
restart it. Full original sources, full remarks, sampled hotspot evidence, and
candidate records remain on disk.

* Teacher: frozen primary hotspot metadata, its source file, recursively included
  local headers and syntactically identified project callees; unrelated source
  files are listed by path only. Header declarations and unrelated TEST/main
  bodies do not cause all project implementations to be included. Whole selected
  files preserve types/macros/globals. This is a conservative syntactic view, not
  a complete semantic dependency analysis; related edits remain allowed.
* Remarks: match source and TU as well as function/inline carrier, retain `main`,
  deduplicate, and omit instruction-mix/stack-size noise. Plain diagnostics with
  no function identity are retained only for the hotspot file/TU and explicitly
  labeled as file context; no function attribution is invented.
* Distiller: original focused source plus an exact diff, including any additional
  files modified by Teacher, and focused before/after remarks.
* Recovery: retain every candidate and exact edits/options/legacy operations,
  intern repeated configurations and remark sets, and reference them in history.
  Pass catalog, action choices, parameter domains and candidate budgets are unchanged.

New run directories record `prompt_context_identity.json`; missing or changed
context identity rejects resume. The old stopped experiments cannot be resumed
under the new context policy. The new frozen snapshot is
`artifacts/cbench-context-preparation-v1/hotspots.json`; baseline samples, native
repeat, median3 policy, and sampled hotspots are unchanged.

Offline prompt comparison (no API calls):

```bash
python3 scripts/audit_cbench_context.py \
  --run artifacts/runs/cbench-patchfix-median3-6t50r-20260921-153207 \
  --recovery-context artifacts/runs/cbench24-gpt56sol-median3-6t50r-20260921-150441/programs/automotive_bitcount/search/recovery/T1_D1/planner_round_5/feedback_context.json \
  --out /tmp/cbench-context-audit
```

`artifacts/cbench-context-audit-v1/REPORT.md` compares saved real prompts to offline
reconstructions. Counts are characters, not estimates of API billing tokens.
`artifacts/cbench-context-smoke-v1/smoke.json` records successful mock/replay shared
searches with real LLVM builds, correctness checks, median3 timing and resume for
network_dijkstra and automotive_bitcount. No paid search was launched.

### Readable prompt format (hotspot-context-v2-readable)

cBench prompts use named Markdown sections, standard indented JSON (`null`,
`true`, `false`), and separate fenced C/diff blocks with project-relative paths.
Code fences grow when source comments contain backticks, preventing accidental
nested/terminated blocks. Baseline hotspot coordinates are labeled as such;
whole-program timing units and speedup direction are explicit. Source/remarks
and history are data, not instructions. A final section identifies the required
response schema. PolyBench formatting is unchanged.

Recovery references use readable `config_001` and `remarks_001` identifiers.
Both lookup tables are in the same message, with explicit resolution rules;
shared references do not merge candidates or timing measurements. Distiller
changes use per-file diffs, not diffs of context metadata. A changed selection
of context files is not described as creation/deletion of project files.

Rendered Teacher/Distiller/Recovery prompts and JSON/reference validation are
in `artifacts/cbench-context-readable-audit-v2`. User prompt character counts
are 13,664 / 14,683 / 156,391 for the saved bitcount examples, respectively.
Readable formatting retains reductions of 93.5% / 95.7% / 81.9% relative to the
original prompts; this is not a new API token measurement. No paid API call or
formal restart was performed. The current prepared snapshot is
`artifacts/cbench-context-readable-preparation-v2/hotspots.json`.

### Bitcount-only trial with the original PolyBench Teacher allocation

The requested Teacher schedule is now shared with PolyBench: three rounds,
requesting two proposals per round (2+2+2), six total; resume subtracts already
consumed slots within each round. The previous cBench-specific 3+2+1 branch was
removed. PolyBench's existing schedule is unchanged. Three prompt template files
were compared byte-for-byte to `/tmp/passdistill-pre-cbench/prompt`; all match.
The preexisting Recovery anchor/parameter explanations remain intact.

`artifacts/cbench-readable-bitcount-trial` contains the template audit, fresh
snapshot, test record and launch metadata for the authorized single-program
trial. It uses the existing DMX env and gpt-5.6-sol, readable focused prompts,
50 Recovery candidates and median of three complete native workload runs.
Only automotive_bitcount is selected; no other cBench program follows this trial.


### Retry policy: no ambiguous transport replay

The shared API backend retains its original `request_timeout_sec=900`, including
PolyBench. Transport failure (disconnect, EOF, timeout, partial response), HTTP
error, malformed response envelope and incomplete Responses result stop the
request without automatically submitting it again. A peer/proxy may close the
connection before 900 seconds; increasing the client timeout cannot keep that
remote connection alive. Unknown server outcome is recorded as `outcome_unknown`.

The `retries` budget now applies only to invalid JSON in a completed model
response. Repair requests remain bounded and never set temperature. Local save
failures also do not trigger regeneration. `request_settings.json` records the
retry policy and timeout; `request_status.json` records waiting, completion,
unknown/failure and JSON repair status. Raw response envelopes and error records
are retained. Tests cover both API endpoints, one-send behavior for disconnect,
timeout, SSL EOF, HTTP 400/502 and partial responses, plus bounded JSON repair.
No paid API call was needed to test this logic. The prior bitcount run exited
with API failure; this change does not restart it.
