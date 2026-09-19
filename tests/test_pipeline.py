from pathlib import Path

from passdistill.agents.catalog import load_static_catalog
from passdistill.pipeline import PipelineEditor, normalize_opt_option, parse_pipeline, split_pipeline


BASE = "module(function(loop-distribute,loop-vectorize,instcombine),verify)"


def catalog_dict():
    catalog = load_static_catalog(Path.cwd())
    return catalog.for_prompt(limit_passes=200, limit_options=80)


def legal_nested_edit(parent_id="SEARCH_BASELINE"):
    return {
        "candidate_id": "C1",
        "parent_id": parent_id,
        "edits": [
            {
                "type": "replace_region",
                "target": {
                    "parent_manager": "function",
                    "start_anchor": "loop-distribute#1",
                    "end_anchor": "loop-vectorize#1",
                },
                "replacement": [
                    {"kind": "pass", "name": "loop-distribute"},
                    {
                        "kind": "manager",
                        "manager": "loop",
                        "passes": [{"kind": "pass", "name": "loop-interchange"}],
                    },
                    {
                        "kind": "manager",
                        "manager": "loop-mssa",
                        "passes": [{"kind": "pass", "name": "licm"}],
                    },
                    {"kind": "pass", "name": "loop-vectorize"},
                ],
            }
        ],
        "opt_options": [],
    }


def test_split_pipeline_respects_nested_commas():
    text = "a,function(x,y<k=v;z=q>),c"
    assert split_pipeline(text) == ["a", "function(x,y<k=v;z=q>)", "c"]


def test_parse_serialize_round_trip_with_parameters_and_repeated_passes():
    pipeline = "module(function<eager-inv>(instcombine,loop(loop-interchange),loop-mssa(licm),loop-vectorize<force-vector-width=4>,instcombine),verify)"
    serialized = parse_pipeline(pipeline).serialize()
    assert serialized == pipeline
    assert parse_pipeline(serialized).serialize() == pipeline


def test_parse_expanded_o3_pipeline_round_trip_if_artifact_exists():
    path = Path("artifacts/runs/2mm-real-agent-smoke-v2/kernels/2mm/baseline/ir/o3_expanded_pipeline.txt")
    pipeline = path.read_text().strip() if path.exists() else BASE
    serialized = parse_pipeline(pipeline).serialize()
    assert parse_pipeline(serialized).serialize() == serialized


def test_nested_fragment_is_not_mechanically_collapsed_into_loop_manager():
    result = PipelineEditor(BASE, catalog=catalog_dict()).apply_candidate(legal_nested_edit())
    assert result.valid, result.invalid_errors
    assert "loop(loop-interchange)" in result.pipeline
    assert "loop-mssa(licm)" in result.pipeline
    assert "loop-vectorize" in result.pipeline
    assert "loop(loop-interchange,licm,loop-vectorize)" not in result.pipeline


def test_catalog_validation_rejects_illegal_scope_required_manager_unknowns():
    catalog = catalog_dict()
    function_pass_in_loop = {
        "edits": [
            {
                "type": "insert_fragment",
                "target": {"parent_manager": "loop", "anchor": "loop-interchange#1", "position": "after"},
                "fragment": [{"kind": "pass", "name": "gvn"}],
            }
        ]
    }
    loop_parent = "module(function(loop(loop-interchange),loop-vectorize),verify)"
    result = PipelineEditor(loop_parent, catalog=catalog).apply_candidate(function_pass_in_loop)
    assert not result.valid
    assert "gvn" in " ".join(result.invalid_errors)

    licm_in_plain_loop = {
        "edits": [
            {
                "type": "insert_fragment",
                "target": {"parent_manager": "loop"},
                "fragment": [{"kind": "pass", "name": "licm"}],
            }
        ]
    }
    result = PipelineEditor(loop_parent, catalog=catalog).apply_candidate(licm_in_plain_loop)
    assert not result.valid
    assert "requires manager loop-mssa" in " ".join(result.invalid_errors)

    unknown_pass = {
        "edits": [
            {
                "type": "insert_fragment",
                "target": {"parent_manager": "function"},
                "fragment": [{"kind": "pass", "name": "made-up-pass"}],
            }
        ]
    }
    result = PipelineEditor(BASE, catalog=catalog).apply_candidate(unknown_pass)
    assert not result.valid
    assert "unknown pass" in " ".join(result.invalid_errors)

    unknown_option = PipelineEditor(BASE, catalog=catalog).apply_candidate({"opt_options": [{"name": "made-up-option"}]})
    assert not unknown_option.valid
    assert "unknown opt option" in " ".join(unknown_option.invalid_errors)


def test_malformed_fragment_is_reported_as_invalid_candidate():
    malformed = {
        "edits": [
            {
                "type": "replace_region",
                "target": {
                    "parent_manager": "function",
                    "start_anchor": "loop-distribute#1",
                    "end_anchor": "loop-vectorize#1",
                },
                "replacement": [{"kind": "indvars", "name": "indvars"}],
            }
        ]
    }
    result = PipelineEditor(BASE, catalog=catalog_dict()).apply_candidate(malformed)
    assert not result.valid
    assert "unknown fragment node kind: indvars" in " ".join(result.invalid_errors)


def test_unknown_parent_pass_can_be_inherited_but_unknown_new_pass_is_invalid():
    catalog = catalog_dict()
    catalog["passes"].pop("callsite-splitting", None)
    parent = "module(function(callsite-splitting,instcombine),verify)"
    inherited = {
        "edits": [
            {
                "type": "insert_fragment",
                "target": {"parent_manager": "function", "anchor": "instcombine#1", "position": "after"},
                "fragment": [{"kind": "pass", "name": "gvn"}],
            }
        ]
    }
    result = PipelineEditor(parent, catalog=catalog).apply_candidate(inherited)
    assert result.valid, result.invalid_errors
    assert "callsite-splitting" in result.pipeline

    unknown = {
        "edits": [
            {
                "type": "insert_fragment",
                "target": {"parent_manager": "function", "anchor": "instcombine#1", "position": "after"},
                "fragment": [{"kind": "pass", "name": "unknown-new-pass"}],
            }
        ]
    }
    result = PipelineEditor(parent, catalog=catalog).apply_candidate(unknown)
    assert not result.valid
    assert "unknown-new-pass" in " ".join(result.invalid_errors)


def test_replacement_may_copy_unknown_parent_node_at_same_position():
    catalog = catalog_dict()
    catalog["passes"].pop("callsite-splitting", None)
    parent = "module(function(callsite-splitting,instcombine),verify)"
    copied = {
        "edits": [
            {
                "type": "replace_region",
                "target": {"parent_manager": "function", "start_anchor": "callsite-splitting#1", "end_anchor": "instcombine#1"},
                "replacement": [
                    {"kind": "pass", "name": "callsite-splitting"},
                    {"kind": "pass", "name": "gvn"},
                ],
            }
        ]
    }
    result = PipelineEditor(parent, catalog=catalog).apply_candidate(copied)
    assert result.valid, result.invalid_errors
    assert result.pipeline == "module(function(callsite-splitting,gvn),verify)"


def test_parent_refinement_materializes_from_parent_not_baseline():
    catalog = catalog_dict()
    r1 = PipelineEditor(BASE, catalog=catalog).apply_candidate(legal_nested_edit())
    assert r1.valid
    child = {
        "candidate_id": "R2_C1",
        "parent_id": "R1_C2",
        "edits": [
            {
                "type": "insert_fragment",
                "target": {"parent_manager": "function", "anchor": "loop-vectorize#1", "position": "after"},
                "fragment": [{"kind": "pass", "name": "instcombine"}],
            }
        ],
        "opt_options": [],
    }
    r2 = PipelineEditor(r1.pipeline, catalog=catalog).apply_candidate(child)
    baseline_branch = PipelineEditor(BASE, catalog=catalog).apply_candidate(child)
    assert r2.valid
    assert "loop(loop-interchange)" in r2.pipeline
    assert "loop-mssa(licm)" in r2.pipeline
    assert r2.pipeline != baseline_branch.pipeline


def test_opt_option_normalization_and_validation():
    assert normalize_opt_option("allow-unroll-and-jam", "true") == "-allow-unroll-and-jam=true"
    result = PipelineEditor(BASE, catalog=catalog_dict()).apply_candidate(
        {"opt_options": [{"name": "allow-unroll-and-jam", "value": "true"}]}
    )
    assert result.opt_options == ["-allow-unroll-and-jam=true"]


def test_integer_options_are_not_boolean_aliases():
    catalog = catalog_dict()
    for name in ("force-vector-interleave", "force-vector-width"):
        for value in ("0", "1", "2", "4", 0, 1):
            assert normalize_opt_option(name, value, catalog) == f"-{name}={value}"
            assert normalize_opt_option(name, value) == f"-{name}={value}"
    for value, expected in (("1", "true"), ("0", "false"), ("yes", "true"), ("no", "false")):
        assert normalize_opt_option("allow-unroll-and-jam", value, catalog) == f"-allow-unroll-and-jam={expected}"
    result = PipelineEditor(BASE, catalog=catalog).apply_candidate(
        {"opt_options": [{"name": "force-vector-interleave", "value": "1"}]}
    )
    assert result.valid
    assert result.opt_options == ["-force-vector-interleave=1"]


def test_catalog_accuracy_for_v4_relevant_passes():
    catalog = load_static_catalog(Path.cwd()).passes
    assert catalog["loop-unroll"]["scope"] == "function"
    assert catalog["loop-unroll"]["allowed_managers"] == ["function"]
    assert "O3" in catalog["loop-unroll"]["parameter_schema"]
    assert catalog["loop-unroll-and-jam"]["allowed_managers"] == ["loop", "loop-mssa"]
    assert catalog["loop-interchange"]["allowed_managers"] == ["loop", "loop-mssa"]
    assert catalog["loop-distribute"]["allowed_managers"] == ["function"]
    assert catalog["loop-vectorize"]["allowed_managers"] == ["function"]
    assert catalog["licm"]["required_manager"] == "loop-mssa"
    assert catalog["gvn"]["allowed_managers"] == ["function"]
    assert catalog["slp-vectorizer"]["allowed_managers"] == ["function"]
    assert catalog["loop-simplify"]["allowed_managers"] == ["function"]
    assert catalog["lcssa"]["allowed_managers"] == ["function"]
    assert catalog["indvars"]["allowed_managers"] == ["loop", "loop-mssa"]
    assert catalog["callsite-splitting"]["allowed_managers"] == ["function"]
