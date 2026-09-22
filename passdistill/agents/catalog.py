from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from passdistill.pipeline import local_region, pipeline_outline
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

    def for_prompt(
        self,
        *,
        limit_passes: int | None = None,
        limit_options: int | None = None,
    ) -> dict[str, Any]:
        """Return the full fixed action catalog.

        limit_passes / limit_options are retained only for backward compatibility
        with existing callers. They are intentionally ignored: PassDistill now
        exposes the complete curated catalog to the Recovery Planner and lets the
        model choose passes and parameters directly.
        """
        del limit_passes, limit_options
        return {
            "llvm_version": self.llvm_version,
            "managers": self.managers,
            "passes": {name: self.passes[name] for name in sorted(self.passes)},
            "opt_options": {
                name: self.opt_options[name] for name in sorted(self.opt_options)
            },
            "families": {
                name: self.families[name] for name in sorted(self.families)
            },
            "supported_edits": [
                "replace_region",
                "insert_fragment",
                "remove_node",
                "move_node",
                "set_pass_parameter",
            ],
        }


_CACHE: dict[tuple[Path, str], PassCatalog] = {}


def catalog_sha256(repo_root: Path) -> str:
    return hashlib.sha256((repo_root / "configs/llvm22.1.3_pass_catalog.json").read_bytes()).hexdigest()


def load_static_catalog(repo_root: Path, path: Path | None = None) -> PassCatalog:
    catalog_path = (
        path or repo_root / "configs" / "llvm22.1.3_pass_catalog.json"
    ).resolve()
    raw = catalog_path.read_bytes()
    cache_key = (catalog_path, hashlib.sha256(raw).hexdigest())
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    data = json.loads(raw)
    catalog = PassCatalog(
        llvm_version=data["llvm_version"],
        managers=data.get("managers", {}),
        passes=data.get("passes", {}),
        opt_options=data.get("opt_options", {}),
        families=data.get("families", {}),
        source=data.get("source", {}),
    )
    _CACHE[cache_key] = catalog
    return catalog


def relevant_catalog(
    catalog: PassCatalog,
    *,
    direction: dict[str, Any],
    baseline_pipeline: str,
    current_pipeline: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return the complete curated catalog plus pipeline context.

    The old implementation performed keyword/family/O3-based retrieval and then
    truncated pass names. That retrieval is intentionally removed. `direction`
    and `limit` remain in the signature only to avoid touching the recovery-search
    call sites; the Recovery Planner receives every curated pass and option.
    """
    del direction, limit
    result = catalog.for_prompt()
    result.update(
        {
            "catalog_policy": "full_catalog_no_retrieval",
            "baseline_local_pipeline": local_region(baseline_pipeline),
            "current_local_pipeline": local_region(current_pipeline),
            "current_pipeline_outline": pipeline_outline(current_pipeline),
            "baseline_pipeline_outline": pipeline_outline(baseline_pipeline),
        }
    )
    return result


def build_pass_catalog(
    config,
    out_dir: Path,
    baseline_pipeline: str | None = None,
) -> PassCatalog:
    del baseline_pipeline
    ensure_dir(out_dir)
    catalog = load_static_catalog(config.repo_root)
    write_json(
        out_dir / "catalog_summary.json",
        {
            "llvm_version": catalog.llvm_version,
            "source": catalog.source,
            "pass_count": len(catalog.passes),
            "option_count": len(catalog.opt_options),
            "catalog_policy": "full_catalog_no_retrieval",
            "runtime_probe": False,
            "catalog_sha256": catalog_sha256(config.repo_root),
        },
    )
    return catalog
