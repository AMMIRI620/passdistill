from passdistill.correctness import compare_text


def test_numeric_float_tolerance():
    result = compare_text("begin 1 1.0000 end", "begin 1 1.00001 end", rtol=1e-4, atol=1e-8)
    assert result.ok


def test_non_numeric_text_must_match():
    result = compare_text("begin D end", "begin E end", rtol=1e-4, atol=1e-8)
    assert not result.ok


def test_integer_exact_compare():
    result = compare_text("1 2 3", "1 2 4", rtol=1.0, atol=1.0)
    assert not result.ok

