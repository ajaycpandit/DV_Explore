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

MOUNT = '/tool'

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.join(_HERE, 'core')
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import fhx_app  # noqa: E402  (the converter Flask app, with all its routes)

capp = fhx_app.app

# ── shared navigation rail (identical to the Explorer's) ──
# Injected at serve time so both tools wear the same chrome and switching between
# them feels fluid. core/ files are never edited, so they stay byte-identical to b1.
_RAIL_CSS = """<style>
.dvx-rail{position:fixed;left:0;top:0;bottom:0;width:60px;background:#10202f;display:flex;
  flex-direction:column;align-items:center;padding:10px 0;gap:4px;z-index:9999;
  font-family:'IBM Plex Sans',system-ui,sans-serif}
body{padding-left:60px!important}
.dvx-brand{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;margin-bottom:14px;
  background:linear-gradient(140deg,#2563eb,#0e7490)}
.dvx-rbtn{width:42px;height:42px;border-radius:11px;color:#9fb4c9;display:grid;place-items:center;
  position:relative;transition:.15s;text-decoration:none}
.dvx-rbtn svg{width:21px;height:21px}
.dvx-rbtn:hover{background:rgba(255,255,255,.07);color:#cfe0f0}
.dvx-rbtn.active{background:rgba(96,165,250,.16);color:#fff}
.dvx-rbtn.active::before{content:"";position:absolute;left:-10px;top:9px;bottom:9px;width:3px;
  border-radius:3px;background:#60a5fa}
.dvx-rbtn .dvx-tip{position:absolute;left:50px;white-space:nowrap;background:#10202f;color:#e6edf3;
  padding:5px 9px;border-radius:7px;font-size:12px;opacity:0;pointer-events:none;transform:translateX(-4px);
  transition:.12s;box-shadow:0 8px 24px -12px rgba(0,0,0,.5);z-index:30}
.dvx-rbtn:hover .dvx-tip{opacity:1;transform:translateX(0)}
.dvx-spacer{flex:1}
</style>"""

_RAIL_HTML = f"""<nav class="dvx-rail">
  <div class="dvx-brand" title="DeltaV Strategy Workbench">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M12 2 4 6.5v9L12 20l8-4.5v-9L12 2Z"/><path d="M12 7v6M9 9.5h6"/></svg>
  </div>
  <a class="dvx-rbtn" href="/" title="Explorer">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
    <span class="dvx-tip">Explorer</span></a>
  <a class="dvx-rbtn active" href="{MOUNT}/" title="FHX Converter">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M4 12h16M4 17h10"/><path d="M17 15l3 2-3 2"/></svg>
    <span class="dvx-tip">FHX Converter</span></a>
  <div class="dvx-spacer"></div>
</nav>"""


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
