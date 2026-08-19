from __future__ import annotations

KEYWORDS = (
    "vector",
    "interchange",
    "distribute",
    "unroll",
    "licm",
    "inline",
    "simplify",
    "dependence",
    "profit",
    "cost",
    "missed",
    "loop",
)


def filter_remarks(text: str, limit: int = 80) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if any(keyword in lower for keyword in KEYWORDS):
            lines.append(line)
            if len(lines) >= limit:
                break
    return lines
