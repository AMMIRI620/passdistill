from __future__ import annotations

import math
import hashlib
import re
from pathlib import Path

from .types import CorrectnessResult

_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _tokenize(text: str) -> list[str]:
    return text.split()


def _is_number(token: str) -> bool:
    return bool(_NUMBER_RE.match(token))


def compare_text(
    expected: str,
    actual: str,
    *,
    rtol: float,
    atol: float,
    max_reported: int = 5,
) -> CorrectnessResult:
    """Legacy numeric comparison for offline analysis; evaluators use stderr MD5."""
    left = _tokenize(expected)
    right = _tokenize(actual)
    if len(left) != len(right):
        return CorrectnessResult(
            ok=False,
            message=f"token count differs: expected {len(left)}, got {len(right)}",
            mismatches=abs(len(left) - len(right)),
        )

    samples: list[str] = []
    mismatches = 0
    for index, (a, b) in enumerate(zip(left, right)):
        if _is_number(a) and _is_number(b):
            if "." not in a and "e" not in a.lower() and "." not in b and "e" not in b.lower():
                ok = int(a) == int(b)
            else:
                ok = math.isclose(float(a), float(b), rel_tol=rtol, abs_tol=atol)
        else:
            ok = a == b
        if not ok:
            mismatches += 1
            if len(samples) < max_reported:
                samples.append(f"#{index}: {a!r} != {b!r}")
    return CorrectnessResult(
        ok=mismatches == 0,
        message="; ".join(samples),
        mismatches=mismatches,
    )


def compare_files(expected: Path, actual: Path, *, rtol: float, atol: float) -> CorrectnessResult:
    return compare_text(expected.read_text(errors="replace"), actual.read_text(errors="replace"), rtol=rtol, atol=atol)


def stderr_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_stderr_md5(expected: Path, actual: Path) -> CorrectnessResult:
    """Compare complete saved stderr, without tokenization or whitespace changes."""
    expected_md5 = stderr_md5(expected)
    actual_md5 = stderr_md5(actual)
    ok = expected_md5 == actual_md5
    return CorrectnessResult(
        ok=ok,
        message="stderr MD5 matches O3 pipeline reference" if ok else "stderr MD5 differs from O3 pipeline reference",
        mismatches=0 if ok else 1,
        expected_md5=expected_md5,
        actual_md5=actual_md5,
    )
