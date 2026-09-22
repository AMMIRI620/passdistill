"""Small, readable source views keyed by audited file/line locations, not name search."""
from pathlib import Path
import re

from passdistill.patching import _match_balanced, strip_code_fence


def split_hotspot(path: Path, hotspot: dict):
    lines = path.read_text().splitlines(keepends=True)
    start, end = hotspot['start_line'] - 1, hotspot['end_line']
    if not 0 <= start < end <= len(lines):
        raise ValueError('invalid hotspot line range')
    return ''.join(lines[:start]), ''.join(lines[start:end]), ''.join(lines[end:])


def replacement_function(text: str, original: str):
    text = strip_code_fence(text)
    # Requiring the original declaration also supports K&R and macro signatures.
    original_brace = original.index('{')
    signature = original[:original_brace]
    opening = text.find('{')
    if opening < 0 or re.sub(r'\s+', '', text[:opening]) != re.sub(r'\s+', '', signature):
        raise ValueError('source_patch must contain the complete function with its unchanged signature')
    closing = _match_balanced(text, opening, '{', '}')
    if text[closing+1:].strip():
        raise ValueError('source_patch contains text outside the target function')
    return text + '\n'


def declarations(text: str):
    """Elide top-level function bodies; keep types, globals, macros and prototypes.

    This is a syntactic view, not a C dependency resolver. Conditional compilation
    and local header context remain explicit for the model and compilation.
    """
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), text, flags=re.S)
    # Macro braces must not masquerade as C function bodies.
    masked = re.sub(r'^\s*#(?:[^\n\\]|\\[^\n]|\\\n)*',
                    lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), masked, flags=re.M)
    chunks, cursor, scan, boundary = [], 0, 0, 0
    while scan < len(masked):
        char = masked[scan]
        if char == '{':
            try:
                end = _match_balanced(masked, scan, '{', '}')
            except ValueError:
                # Preprocessor alternatives can make raw braces unbalanced.
                # Do not invent a parsed view: preserve this context verbatim.
                return text
            header = masked[boundary:scan].strip()
            function = ')' in header and '=' not in header and not re.search(r'\b(?:struct|union|enum)\s*\w*\s*$', header)
            if function:
                chunks.append(text[cursor:scan] + '; /* body omitted from read-only context */')
                cursor = end + 1
            elif '=' in header:
                chunks.append(text[cursor:scan] + '{ /* read-only initializer omitted */ }')
                cursor = end + 1
            scan = end
            boundary = end + 1
        elif char == ';':
            # K&R parameter declarations are harmless context if not elided.
            boundary = scan + 1
        scan += 1
    chunks.append(text[cursor:])
    return ''.join(chunks)


def readonly_context(source: Path, source_root: Path):
    """Hotspot TU declarations and local includes; never recursively include callees."""
    selected, pending = {}, [source]
    while pending:
        path = pending.pop()
        if path in selected:
            continue
        code = path.read_text(errors='replace')
        selected[path] = declarations(code)
        # Includes inside an elided constant initializer (e.g. mad rq_table.dat)
        # carry data, not declarations, and must not expand back into the prompt.
        for include in re.findall(r'^\s*#\s*include\s*["<]([^">]+)[">]', selected[path], re.M):
            for candidate in [(path.parent / include).resolve(), (source_root / include).resolve()]:
                if candidate.is_relative_to(source_root) and candidate.is_file():
                    pending.append(candidate)
                    break
    return '\n\n'.join(f'FILE {p.relative_to(source_root)} (read-only declarations)\n```c\n{code}\n```'
                       for p, code in sorted(selected.items()))
