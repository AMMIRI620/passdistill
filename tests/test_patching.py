import json
from pathlib import Path

from passdistill.patching import apply_teacher_patch, extract_function_span, strip_code_fence


def test_extract_polybench_style_multiline_signature():
    text = """
static
void kernel_2mm(int ni,
                DATA_TYPE POLYBENCH_2D(tmp,NI,NJ,ni,nj),
                DATA_TYPE POLYBENCH_2D(A,NI,NK,ni,nk))
{
  if (ni) {
    tmp[0][0] = A[0][0];
  }
}
"""
    span = extract_function_span(text, "kernel_2mm")
    assert "POLYBENCH_2D(tmp,NI,NJ,ni,nj)" in span.text
    assert "if (ni)" in span.text


def test_strip_c_fence():
    assert strip_code_fence("```c\nstatic void kernel_x() {}\n```") == "static void kernel_x() {}"
    assert strip_code_fence("```C\nstatic void kernel_x() {}\n```") == "static void kernel_x() {}"
    assert strip_code_fence("```\nstatic void kernel_x() {}\n```") == "static void kernel_x() {}"


def test_malformed_parentheses_fails():
    try:
        extract_function_span("static void kernel_x(int a { }", "kernel_x")
    except ValueError as exc:
        assert "unmatched" in str(exc)
    else:
        raise AssertionError("expected unmatched parentheses failure")


def test_malformed_braces_fails():
    try:
        extract_function_span("static void kernel_x(int a) { if (a) { }", "kernel_x")
    except ValueError as exc:
        assert "unmatched" in str(exc)
    else:
        raise AssertionError("expected unmatched braces failure")


def test_apply_replaces_only_kernel_span(tmp_path):
    original = tmp_path / "orig.c"
    output = tmp_path / "out.c"
    original.write_text(
        "int keep_prefix = 1;\n"
        "static\nvoid kernel_2mm(int ni, DATA_TYPE POLYBENCH_2D(tmp,NI,NJ,ni,nj))\n{\n  tmp[0][0] = 0;\n}\n"
        "int keep_suffix = 2;\n"
    )
    replacement = """```c
static
void kernel_2mm(int ni, DATA_TYPE POLYBENCH_2D(tmp,NI,NJ,ni,nj))
{
  if (ni) {
    tmp[0][0] = 1;
  }
}
```"""
    apply_teacher_patch(original, replacement, output)
    patched = output.read_text()
    assert "int keep_prefix = 1;" in patched
    assert "int keep_suffix = 2;" in patched
    assert "tmp[0][0] = 1;" in patched
    assert "tmp[0][0] = 0;" not in patched


def test_real_2mm_kernel_extracts():
    source = Path("third_party/polybench-c-4.2.1-beta/linear-algebra/kernels/2mm/2mm.c").read_text()
    span = extract_function_span(source, "kernel_2mm")
    assert "POLYBENCH_2D(tmp,NI,NJ,ni,nj)" in span.text
    assert "#pragma scop" in span.text


def test_real_llm_smoke_directions_apply(tmp_path):
    parsed = Path("artifacts/runs/2mm-real-agent-smoke-v1/kernels/2mm/search/oracle_round_1/parsed_response.json")
    if not parsed.exists():
        return
    data = json.loads(parsed.read_text())
    original = Path("third_party/polybench-c-4.2.1-beta/linear-algebra/kernels/2mm/2mm.c")
    for direction in data["directions"]:
        output = tmp_path / f"{direction['direction_id']}.c"
        apply_teacher_patch(original, direction["source_patch"], output)
        patched = output.read_text()
        assert "static\nvoid kernel_2mm" in patched
        assert "init_array" in patched
        assert "print_array" in patched
