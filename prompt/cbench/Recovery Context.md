Benchmark context: cBench, a whole program with multiple C translation units.
The Teacher modifies one fixed profiled hotspot to demonstrate optimization intent.
Recovery always starts from ORIGINAL unmodified frontend IR for ALL translation units.
Each candidate's pipeline is materialized once; the SAME pipeline and opt_options are
applied independently to every tunable TU, including files outside the hotspot, then linked.
Do not assume improvements local to the hotspot guarantee whole-program speedups.
No source changes from Teacher enter Recovery. Dataset 1 native loops are unchanged.
The objective is whole-program elapsed time, median of three valid runs on CPU 3 / NUMA 0,
subject to functional output correctness. There are no additional cBench restrictions on
the pass catalog, edit count, or parameter values. Use the existing candidate schema below.
