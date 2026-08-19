from pathlib import Path

from passdistill.agents.source_oracle import propose_teachers


class RecordingBackend:
    def __init__(self):
        self.user = ""

    def complete_json(self, system, user, *, schema_hint, out_dir):
        self.user = user
        out_dir.mkdir(parents=True, exist_ok=True)
        return {"directions": []}


def test_source_oracle_prompt_contains_only_target_kernel(tmp_path):
    source = """
static void init_array(int n) {}

static
void kernel_2mm(int ni, double A[ni])
{
  for (int i = 0; i < ni; i++) {
    A[i] = A[i] + 1.0;
  }
}

static void print_array(int n) {}

int main(int argc, char** argv) { return 0; }
"""
    remarks = """--- !Missed
Pass:            loop-vectorize
Name:            UnsafeDep
DebugLoc:        { File: '2mm.c', Line: 7, Column: 3 }
Function:        kernel_2mm
Args:
  - String:          'loop not vectorized: dependency'
...
--- !Passed
Pass:            inline
Name:            Inlined
DebugLoc:        { File: '2mm.c', Line: 2, Column: 1 }
Function:        init_array
Args:
  - String:          'irrelevant inline'
...
"""
    backend = RecordingBackend()
    propose_teachers(
        backend,
        kernel_name="2mm",
        original_source=source,
        baseline_remarks=remarks,
        baseline_runtime=1.0,
        history=[],
        round_index=1,
        max_candidates=3,
        remaining_teacher_budget=3,
        out_dir=tmp_path,
        repo_root=Path.cwd(),
    )
    assert "Target function: kernel_2mm" in backend.user
    assert "Teacher round: 1" in backend.user
    assert "Requested new directions this round: 3" in backend.user
    assert "Generate exactly 3 meaningfully different teacher directions." in backend.user
    assert "remaining teacher budget after this request" not in backend.user
    assert "kernel_2mm" in backend.user
    assert "static void init_array" not in backend.user
    assert "static void print_array" not in backend.user
    assert "int main" not in backend.user
    assert "Pass Catalog" not in backend.user
    assert "expanded O3" not in backend.user
    assert "manager/adaptor" not in backend.user
    assert "Recovery candidate pipeline" not in backend.user
    assert "[Missed][loop-vectorize]" in backend.user
    assert "Pass:            inline" not in backend.user
    assert "String:" not in backend.user
    assert "--- !Missed" not in backend.user
    assert (tmp_path / "structured_remarks.json").exists()
