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

import fonts  # embedded IBM Plex (offline-safe) — shared with the Explorer
import rail   # shared persistent app-switcher rail (one source for all 3 surfaces)

MOUNT = '/tool'

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.join(_HERE, 'core')
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import fhx_app  # noqa: E402  (the converter Flask app, with all its routes)

capp = fhx_app.app

# ── shared navigation rail ──
# The rail markup + CSS now live in rail.py (one source of truth shared by the
# landing page, explorer, and converter). We grab them with active='converter'.
# core/ files are never edited, so they stay byte-identical to b1.
_RAIL_CSS = rail.rail_css(fixed=True)
_RAIL_HTML = rail.rail_html(active='converter')


def _rewrite(html, embed=False):
    """Prefix the converter's absolute endpoint/link paths with MOUNT, then graft on
    the shared rail + embedded fonts so it matches the Explorer.

    embed=True serves a rail-less variant for hosting inside the Explorer shell
    (the Explorer already provides the rail); internal links keep the embed flag so
    navigating to the SFC Diagram stays rail-less too."""
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
    if embed:
        html = html.replace(f'href="{MOUNT}/diagram"', f'href="{MOUNT}/diagram?embed=1"')
        html = html.replace(f'href="{MOUNT}/"', f'href="{MOUNT}/?embed=1"')
        inject_head = (f'<style>{fonts.FONT_CSS}</style>'
                       '<style>body{padding-left:0!important}</style>')
        return html.replace('</head>', inject_head + '</head>', 1)
    inject_head = f'<style>{fonts.FONT_CSS}</style>{_RAIL_CSS}'
    html = html.replace('</head>', inject_head + '</head>', 1)
    html = html.replace('<body>', '<body>' + _RAIL_HTML, 1)
    return html


def _load(name, embed=False):
    with open(os.path.join(_CORE, name), encoding='utf-8') as fh:
        return _rewrite(fh.read(), embed=embed)


from flask import request  # noqa: E402

_INDEX_HTML = _load('index.html')
_DIAGRAM_HTML = _load('diagram.html')
_INDEX_EMBED = _load('index.html', embed=True)
_DIAGRAM_EMBED = _load('diagram.html', embed=True)


def _serve_index():
    return Response(_INDEX_EMBED if request.args.get('embed') else _INDEX_HTML,
                    mimetype='text/html')


def _serve_diagram():
    return Response(_DIAGRAM_EMBED if request.args.get('embed') else _DIAGRAM_HTML,
                    mimetype='text/html')


capp.view_functions['index'] = _serve_index
capp.view_functions['diagram_page'] = _serve_diagram
