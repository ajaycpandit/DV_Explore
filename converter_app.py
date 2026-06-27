"""
Mount adapter for the FHX Converter (Backup 1).

The converter is a self-contained Flask app living in ./core/fhx_app.py. We mount
it under a path prefix (MOUNT) inside the explorer's deployment via a WSGI
dispatcher, so a single Render service serves BOTH tools:

    /          -> DeltaV Database Explorer (this project)
    /tool/     -> FHX Converter wizard (the original converter UI, unchanged)

The converter's frontend (index.html / diagram.html) calls its endpoints with
ABSOLUTE paths (fetch('/detect'), fetch('/convert'), href="/diagram", ...). Under
a prefix those would miss, so we serve path-rewritten copies whose calls target
'<MOUNT>/...'. The dispatcher strips the prefix before the converter sees the
request, so the converter's own routes are untouched and core/ does not drift.
"""

import os
import sys

from flask import Response

MOUNT = '/tool'

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.join(_HERE, 'core')
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import fhx_app  # noqa: E402  (the converter Flask app, with all its routes)

capp = fhx_app.app


def _rewrite(html):
    """Prefix the converter's absolute endpoint/link paths with MOUNT."""
    repl = [
        ("'/detect'", f"'{MOUNT}/detect'"),
        ("'/convert'", f"'{MOUNT}/convert'"),
        ("'/parse'", f"'{MOUNT}/parse'"),
        ("'/batch'", f"'{MOUNT}/batch'"),
        ('href="/diagram"', f'href="{MOUNT}/diagram"'),
        ('href="/"', f'href="{MOUNT}/"'),
    ]
    for a, b in repl:
        html = html.replace(a, b)
    # add a link back to the Explorer (injected after the prefixing pass so its
    # own href is not rewritten)
    explorer_btn = (
        '<nav class="h-nav"><a class="h-navbtn" href="/" '
        'style="text-decoration:none">'
        '<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" '
        'viewBox="0 0 12 12"><path d="M1 4l5-3 5 3v6a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1z"/></svg>'
        'Explorer</a>')
    html = html.replace('<nav class="h-nav">', explorer_btn, 1)
    return html


def _load(name):
    with open(os.path.join(_CORE, name), encoding='utf-8') as fh:
        return _rewrite(fh.read())


_INDEX_HTML = _load('index.html')
_DIAGRAM_HTML = _load('diagram.html')

# Override the two HTML-serving views so they (a) are path-independent (no reliance
# on CWD for send_file) and (b) return the MOUNT-prefixed markup.
capp.view_functions['index'] = lambda: Response(_INDEX_HTML, mimetype='text/html')
capp.view_functions['diagram_page'] = lambda: Response(_DIAGRAM_HTML, mimetype='text/html')
