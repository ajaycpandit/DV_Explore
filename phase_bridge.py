"""
Phase viewer integration for the database explorer.

Bridges the explorer to the converter's validated parsing core: parses each
PHASE_CLASS in a database export and generates the interactive phase viewer
(SFC diagram + parameters + monitors + attributes) so a Phase Class leaf in the
explorer drills down into the real logic.

The parsing core (app.py helpers + sfc_html) is imported from the converter
project. In the standalone repo these become a shared module; here we load them
from the existing fhx-app directory.
"""

import os
import sys
import re

# Locate the converter's parsing core (shared parsing logic).
_CORE_DIR = os.environ.get('FHX_CORE_DIR', '/home/claude/deltav_tool/fhx-app')


def _load_core():
    """Import the converter's phase parser + interactive HTML builder.

    app.py is a Flask app; we exec the non-Flask portion (everything before the
    first @app.route) to get the pure parsing/build functions without starting a
    server. sfc_html is a clean module and imports directly.
    """
    sys.path.insert(0, _CORE_DIR)
    src = open(os.path.join(_CORE_DIR, 'app.py')).read()
    lines = [l for l in src.splitlines()
             if not (l.startswith('from flask') or l.startswith('from flask_cors')
                     or l.startswith('app = Flask') or l.startswith('CORS('))]
    body = '\n'.join(lines)
    body = body[:body.find('@app.route')]
    ns = {'__name__': 'fhx_core'}
    exec(compile(body, 'app.py', 'exec'), ns)
    import sfc_html
    return ns, sfc_html


_CORE = None
_SFC = None


def _core():
    global _CORE, _SFC
    if _CORE is None:
        _CORE, _SFC = _load_core()
    return _CORE, _SFC


def parse_phases_from_export(text):
    """Return {phase_name: phase_blocks} for every PHASE_CLASS in the export,
    using the converter's multi-phase parser."""
    core, _ = _core()
    if len(re.findall(r'PHASE_CLASS\s+NAME="', text)) > 1:
        return core['parse_multiphase_fhx'](text)
    # single phase: wrap under its PHASE_CLASS name
    pc = re.search(r'PHASE_CLASS\s+NAME="([^"]+)"', text)
    name = pc.group(1) if pc else 'PHASE'
    return {name: core['parse_phase_fhx'](text)}


def build_phase_view_html(phase_name, blocks):
    """Generate the self-contained interactive phase viewer HTML for one phase."""
    _, sfc_html = _core()
    return sfc_html.build_sfc_html(blocks, phase_name)


def phase_view_map(text):
    """Return {phase_name: interactive_html} for all phases in the export."""
    phases = parse_phases_from_export(text)
    out = {}
    for pname, blocks in phases.items():
        try:
            out[pname] = build_phase_view_html(pname, blocks)
        except Exception as e:
            out[pname] = f"<html><body><p>Could not render {pname}: {e}</p></body></html>"
    return out
