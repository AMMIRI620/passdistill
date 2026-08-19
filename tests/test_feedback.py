from passdistill.agents.feedback import grouped_remark_feedback, parse_optimization_remarks, select_relevant_remark_events


def test_optimization_record_parser_keeps_complete_event_semantics():
    text = """--- !Missed
Pass:            loop-vectorize
Name:            UnsafeDep
DebugLoc:        { File: '2mm.c', Line: 89, Column: 5 }
Function:        kernel_2mm
Args:
  - String:          'loop not vectorized: '
  - Reason:          memory dependency
...
"""
    events = parse_optimization_remarks(text)
    assert len(events) == 1
    event = events[0]
    assert event.kind == "Missed"
    assert event.pass_name == "loop-vectorize"
    assert event.name == "UnsafeDep"
    assert event.function == "kernel_2mm"
    assert event.file == "2mm.c"
    assert event.line == 89
    assert event.column == 5
    assert "loop not vectorized" in event.message
    assert "memory dependency" in event.message
    formatted = event.format()
    assert "[Missed][loop-vectorize]" in formatted
    assert "Function:" not in formatted
    assert "String:" not in formatted
    assert "--- !Missed" not in formatted


def test_target_kernel_filtering_prefers_kernel_events():
    text = """--- !Passed
Pass:            inline
Name:            Inlined
DebugLoc:        { File: '2mm.c', Line: 20, Column: 1 }
Function:        init_array
Args:
  - String:          'inline noise'
...
--- !Missed
Pass:            loop-vectorize
Name:            UnsafeDep
DebugLoc:        { File: '2mm.c', Line: 89, Column: 5 }
Function:        kernel_2mm
Args:
  - String:          'loop not vectorized'
...
--- !Analysis
Pass:            asm-printer
Name:            InstructionMix
DebugLoc:        { File: '2mm.c', Line: 140, Column: 1 }
Function:        main
Args:
  - String:          'main noise'
...
"""
    selected = select_relevant_remark_events(parse_optimization_remarks(text), target_function="kernel_2mm", limit=10)
    assert [event.function for event in selected] == ["kernel_2mm"]
    feedback = grouped_remark_feedback(selected)
    assert "[Missed][loop-vectorize]" in feedback
    assert "init_array" not in feedback
    assert "main noise" not in feedback
