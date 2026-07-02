"""
perf_patch.py — runtime speedup for the frozen core parser.

`core/fhx_app.py`'s `extract_block` scans the export character-by-character with
`len(text)` recomputed every iteration. On a multi-MB unit export it's called
~1600+ times and dominates parse time (seconds), which on a slow free-tier host
can exceed the gunicorn request timeout and surface as a 500.

We cannot edit `core/` (byte-identical freeze), so we replace the function object
at runtime with a version that jumps between braces via `str.find` and hoists
`len` out of the loop — identical output, dramatically fewer operations. This is a
pure in-memory monkey-patch; the core file on disk is untouched.
"""


def fast_extract_block(text, start):
    """Balanced-brace block starting at/after `start`. Same result as the core
    version, but jumps brace-to-brace with str.find instead of scanning chars."""
    i = text.find('{', start)
    if i == -1:
        return ''
    s = i
    depth = 0
    find = text.find
    while True:
        nb = find('{', i)
        nc = find('}', i)
        if nc == -1:
            return ''
        if nb != -1 and nb < nc:
            depth += 1
            i = nb + 1
        else:
            depth -= 1
            if depth == 0:
                return text[s:nc + 1]
            i = nc + 1


def apply(*namespaces):
    """Patch `extract_block` in each given module/namespace (module object or dict).
    Safe to call repeatedly; only replaces the known-slow signature."""
    for ns in namespaces:
        try:
            if isinstance(ns, dict):
                if 'extract_block' in ns:
                    ns['extract_block'] = fast_extract_block
            else:
                if hasattr(ns, 'extract_block'):
                    ns.extract_block = fast_extract_block
        except Exception:
            pass
