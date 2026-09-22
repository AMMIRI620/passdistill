import json
import tempfile
import unittest
from pathlib import Path

from passdistill.agents.catalog import load_static_catalog, relevant_catalog
from passdistill.pipeline import PipelineEditor, pipeline_outline
from passdistill.config import ExperimentConfig
from passdistill.orchestrator import run


class CatalogV2Tests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_static_catalog(Path.cwd())
        self.data = self.catalog.for_prompt()

    def edit(self, pipeline, pass_name, **fields):
        return PipelineEditor(pipeline, catalog=self.data).apply_candidate({"edits": [
            {"type": "set_pass_parameter", "target": {"anchor": pass_name + "#1"}, **fields}
        ]})

    def test_full_catalog_and_outlines(self):
        pipeline = "function(" + ",".join(["instcombine"] * 160) + ")"
        data = relevant_catalog(self.catalog, direction={}, baseline_pipeline=pipeline, current_pipeline=pipeline, limit=1)
        self.assertEqual(len(data["passes"]), 78)
        self.assertEqual(set(data["opt_options"]), {"allow-unroll-and-jam", "force-vector-width", "force-vector-interleave"})
        self.assertIn("instcombine#160", data["baseline_pipeline_outline"])
        self.assertIn("instcombine#160", data["current_pipeline_outline"])
        self.assertEqual(len(pipeline_outline(pipeline, limit=3)), 3)
        for entry in data["passes"].values():
            self.assertTrue(set(entry.get("related_options", [])) <= set(data["opt_options"]))

    def test_flags_modes_and_values(self):
        cases = [
            ("function(gvn<pre>)", "gvn", {"name": "pre", "value": False}, "function(gvn<no-pre>)"),
            ("function(gvn<no-pre>)", "gvn", {"name": "pre", "value": True}, "function(gvn<pre>)"),
            ("function(loop-mssa(licm<allowspeculation>))", "licm", {"name": "allowspeculation", "value": False}, "function(loop-mssa(licm<no-allowspeculation>))"),
            ("function(sroa<modify-cfg>)", "sroa", {"name": "preserve-cfg"}, "function(sroa<preserve-cfg>)"),
            ("function(instcombine<max-iterations=1>)", "instcombine", {"name": "max-iterations", "value": 4}, "function(instcombine<max-iterations=4>)"),
            ("function(simplifycfg)", "simplifycfg", {"name": "bonus-inst-threshold", "value": 8}, "function(simplifycfg<bonus-inst-threshold=8>)"),
            ("function(loop-unroll)", "loop-unroll", {"name": "full-unroll-max", "value": 16}, "function(loop-unroll<full-unroll-max=16>)"),
        ]
        for pipeline, name, edit, expected in cases:
            with self.subTest(edit=edit):
                result = self.edit(pipeline, name, **edit)
                self.assertTrue(result.valid, result.invalid_errors)
                self.assertEqual(result.pipeline, expected)

    def test_invalid_parameter_syntax_rejected_before_llvm(self):
        for name, params in [("licm", "allowspeculation=False"), ("gvn", "pre=true"), ("sroa", "preserve-cfg=None"), ("instcombine", "max-iterations"), ("instcombine", "max-iterations=")]:
            manager = "loop-mssa" if name == "licm" else "function"
            result = PipelineEditor("function(instcombine)", catalog=self.data).apply_candidate({"edits": [{"type": "insert_fragment", "target": {"parent_manager": "function"}, "fragment": [{"kind": "manager", "manager": manager, "passes": [{"kind": "pass", "name": name, "parameters": params}]}]}]})
            self.assertFalse(result.valid, params)
        self.assertFalse(self.edit("function(instcombine)", "instcombine", name="max-iterations").valid)

    def test_resume_hash_mismatch_preserves_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = ExperimentConfig(artifacts_root=Path(directory), run_id="old", resume=True)
            target = Path(directory) / "old"
            target.mkdir()
            text = json.dumps({**config.as_json(), "catalog_sha256": "outdated"}, default=str)
            (target / "config.json").write_text(text)
            with self.assertRaisesRegex(ValueError, "catalog hash"):
                run(config, kernel="2mm", all_kernels=False)
            self.assertEqual((target / "config.json").read_text(), text)


if __name__ == "__main__":
    unittest.main()
