from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from passdistill.pipeline import local_region, pass_name, pipeline_outline, split_pipeline
from passdistill.util import ensure_dir, write_json


@dataclass
class PassCatalog:
    llvm_version: str
    managers: dict[str, Any]
    passes: dict[str, Any]
    opt_options: dict[str, Any]
    families: dict[str, list[str]] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)

    @property
    def hidden_option_names(self) -> list[str]:
        return sorted(self.opt_options)

    def for_prompt(self, *, limit_passes: int = 50, limit_options: int = 40) -> dict[str, Any]:
        names = sorted(self.passes)[:limit_passes]
        options = sorted(self.opt_options)[:limit_options]
        return {
            "llvm_version": self.llvm_version,
            "managers": self.managers,
            "passes": {name: self.passes[name] for name in names},
            "opt_options": {name: self.opt_options[name] for name in options},
            "supported_edits": [
                "replace_region",
                "insert_fragment",
                "remove_node",
                "move_node",
                "set_pass_parameter",
            ],
        }


_CACHE: dict[Path, PassCatalog] = {}


def load_static_catalog(repo_root: Path, path: Path | None = None) -> PassCatalog:
    catalog_path = (path or repo_root / "configs" / "llvm22.1.3_pass_catalog.json").resolve()
    if catalog_path in _CACHE:
        return _CACHE[catalog_path]
    data = json.loads(catalog_path.read_text())
    catalog = PassCatalog(
        llvm_version=data["llvm_version"],
        managers=data.get("managers", {}),
        passes=data.get("passes", {}),
        opt_options=data.get("opt_options", {}),
        families=data.get("families", {}),
        source=data.get("source", {}),
    )
    _CACHE[catalog_path] = catalog
    return catalog


def _terms_from_direction(direction: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    guidance = direction.get("search_guidance", {}) if isinstance(direction, dict) else {}
    for key in (
        "candidate_passes",
        "candidate_parameters",
        "ordering_hypotheses",
        "prerequisite_transformations",
        "alternative_realizations",
    ):
        values = guidance.get(key, [])
        if isinstance(values, str):
            values = [values]
        for value in values:
            text = str(value).lower()
            for token in text.replace("/", " ").replace(",", " ").split():
                terms.add(token.strip("`'\".;:()[]{}"))
    for key in ("optimization_intent", "summary", "target_description"):
        for token in str(direction.get(key, "")).lower().replace("/", " ").replace(",", " ").split():
            terms.add(token.strip("`'\".;:()[]{}"))
    return {term for term in terms if term}


def _pipeline_passes(pipeline: str) -> set[str]:
    names: set[str] = set()
    for item in split_pipeline(pipeline):
        names.add(pass_name(item))
        if "(" in item:
            names |= _pipeline_passes(item[item.find("(") + 1 : -1])
    return names


def relevant_catalog(
    catalog: PassCatalog,
    *,
    direction: dict[str, Any],
    baseline_pipeline: str,
    current_pipeline: str,
    limit: int = 50,
) -> dict[str, Any]:
    selected: set[str] = set()
    terms = _terms_from_direction(direction)
    pipeline_names = _pipeline_passes(local_region(current_pipeline).get("nodes_text", "")) if False else set()
    pipeline_names |= set(local_region(current_pipeline).get("outline", [])) if False else set()
    pipeline_names |= _pipeline_passes(baseline_pipeline)
    pipeline_names |= _pipeline_passes(current_pipeline)

    for name, entry in catalog.passes.items():
        family = str(entry.get("family", ""))
        if name in pipeline_names or name in terms or family in terms:
            selected.add(name)
        for term in terms:
            if term and term in name:
                selected.add(name)
    for name in list(selected):
        entry = catalog.passes.get(name, {})
        family = entry.get("family")
        if family and family in catalog.families:
            selected.update(catalog.families[family][:8])
        for related in entry.get("related_passes", []):
            selected.add(related)
        hints = entry.get("soft_hints", {})
        for values in hints.values():
            selected.update(values)

    default_focus = [
        "loop-distribute",
        "loop-interchange",
        "licm",
        "loop-vectorize",
        "slp-vectorizer",
        "vector-combine",
        "gvn",
        "instcombine",
        "loop-simplify",
        "lcssa",
        "indvars",
        "loop-versioning-licm",
        "loop-unroll-and-jam",
    ]
    selected.update(default_focus)
    selected = {name for name in selected if name in catalog.passes}
    ordered = sorted(selected)[:limit]

    option_names: set[str] = set()
    for name in ordered:
        option_names.update(catalog.passes[name].get("related_options", []))
    for option, entry in catalog.opt_options.items():
        related = set(entry.get("related_passes", []))
        if related & set(ordered):
            option_names.add(option)
    option_names = {name for name in option_names if name in catalog.opt_options}

    return {
        "llvm_version": catalog.llvm_version,
        "managers": catalog.managers,
        "passes": {name: catalog.passes[name] for name in ordered},
        "opt_options": {name: catalog.opt_options[name] for name in sorted(option_names)},
        "supported_edits": [
            "replace_region",
            "insert_fragment",
            "remove_node",
            "move_node",
            "set_pass_parameter",
        ],
        "baseline_local_pipeline": local_region(baseline_pipeline),
        "current_local_pipeline": local_region(current_pipeline),
        "full_pipeline_outline": pipeline_outline(current_pipeline, limit=100),
    }


def build_pass_catalog(config, out_dir: Path, baseline_pipeline: str | None = None) -> PassCatalog:
    ensure_dir(out_dir)
    catalog = load_static_catalog(config.repo_root)
    write_json(
        out_dir / "catalog_summary.json",
        {
            "llvm_version": catalog.llvm_version,
            "source": catalog.source,
            "pass_count": len(catalog.passes),
            "option_count": len(catalog.opt_options),
            "runtime_probe": False,
        },
    )
    return catalog

