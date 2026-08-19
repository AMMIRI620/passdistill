#!/usr/bin/env python3
"""One-shot helper to inspect LLVM pass/option names.

Normal experiments read configs/llvm22.1.3_pass_catalog.json and do not call
opt --print-passes or opt --help-hidden at runtime.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


SECTION_TO_SCOPE = {
    "Module passes": "module",
    "Module passes with params": "module",
    "CGSCC passes": "cgscc",
    "CGSCC passes with params": "cgscc",
    "Function passes": "function",
    "Function passes with params": "function",
    "LoopNest passes": "loop",
    "Loop passes": "loop",
    "Loop passes with params": "loop",
}

RELEVANT_FOR_SANITY = [
    "loop-unroll",
    "loop-unroll-and-jam",
    "loop-interchange",
    "loop-distribute",
    "loop-vectorize",
    "licm",
    "gvn",
    "slp-vectorizer",
    "loop-simplify",
    "lcssa",
    "indvars",
    "callsite-splitting",
]


def parse_print_passes(text: str) -> dict[str, dict]:
    passes: dict[str, dict] = {}
    section = ""
    for raw in text.splitlines():
        if raw and not raw.startswith(" "):
            section = raw.rstrip(":")
            continue
        token = raw.strip()
        if not token or section not in SECTION_TO_SCOPE:
            continue
        name = token.split("<", 1)[0]
        entry = passes.setdefault(
            name,
            {
                "canonical_spelling": token,
                "scope": SECTION_TO_SCOPE[section],
                "source_section": section,
            },
        )
        if "<" in token and token.endswith(">"):
            entry["canonical_spelling"] = token
            entry["parameter_schema"] = [item for item in token.split("<", 1)[1][:-1].split(";") if item]
    return passes


def sanity_pipeline(scope: str, name: str, entry: dict) -> str:
    spelling = entry.get("canonical_spelling", name)
    if name == "licm":
        return "function(loop-mssa(licm))"
    if name == "loop-unroll":
        spelling = "loop-unroll<O3>"
    if name == "gvn":
        spelling = "gvn"
    if name == "loop-vectorize":
        spelling = "loop-vectorize"
    if name == "licm":
        spelling = "licm"
    if scope == "module":
        return spelling
    if scope == "cgscc":
        return f"cgscc({spelling})"
    if scope == "function":
        return f"function({spelling})"
    return f"function(loop({spelling}))"


def validate_relevant(opt: str, ir: Path | None, parsed: dict[str, dict]) -> dict[str, dict]:
    if ir is None:
        return {}
    results: dict[str, dict] = {}
    for name in RELEVANT_FOR_SANITY:
        entry = parsed.get(name)
        if not entry:
            results[name] = {"status": "missing_from_print_passes"}
            continue
        pipeline = sanity_pipeline(entry["scope"], name, entry)
        proc = subprocess.run([opt, "-disable-output", f"-passes={pipeline}", str(ir)], text=True, capture_output=True, check=False)
        results[name] = {
            "status": "accepted" if proc.returncode == 0 else "rejected",
            "pipeline": pipeline,
            "stderr": proc.stderr.strip()[:500],
        }
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opt", required=True, help="Path to LLVM opt")
    parser.add_argument("--ir", type=Path, help="Optional IR file for relevant textual-pipeline sanity checks")
    parser.add_argument("--out", type=Path, default=Path("configs/llvm_pass_catalog_raw.json"))
    args = parser.parse_args()
    version = subprocess.run([args.opt, "--version"], text=True, capture_output=True, check=False)
    passes = subprocess.run([args.opt, "--print-passes"], text=True, capture_output=True, check=False)
    hidden = subprocess.run([args.opt, "--help-hidden"], text=True, capture_output=True, check=False)
    parsed = parse_print_passes(passes.stdout)
    sanity = validate_relevant(args.opt, args.ir, parsed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "llvm_version_returncode": version.returncode,
                "llvm_version_stdout": version.stdout,
                "generated_passes": len(parsed),
                "parsed_passes": parsed,
                "validated_relevant_passes": sanity,
                "rejected_or_unsupported_textual_forms": [
                    {"pass": name, **result} for name, result in sanity.items() if result.get("status") != "accepted"
                ],
                "print_passes_returncode": passes.returncode,
                "print_passes_stdout": passes.stdout,
                "print_passes_stderr": passes.stderr,
                "help_hidden_returncode": hidden.returncode,
                "help_hidden_stdout": hidden.stdout,
                "help_hidden_stderr": hidden.stderr,
            },
            indent=2,
        )
    )
    return 0 if version.returncode == 0 and passes.returncode == 0 and hidden.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
