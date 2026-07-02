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

import sfc_expr_fix  # bridge: quote-aware repair of truncated transition expressions

# The parsing core lives inside this repo under ./core (copied from the converter).
# Falls back to an env-var path for local dev against the original converter.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.environ.get('FHX_CORE_DIR', os.path.join(_HERE, 'core'))
_APP_FILE = 'fhx_app.py' if os.path.exists(os.path.join(_CORE_DIR, 'fhx_app.py')) else 'app.py'


def _load_core():
    """Import the converter's phase parser + interactive HTML builder.

    fhx_app.py is the converter's Flask app; we exec the non-Flask portion
    (everything before the first @app.route) to get the pure parsing/build
    functions without starting a server. sfc_html imports directly.
    """
    sys.path.insert(0, _CORE_DIR)
    src = open(os.path.join(_CORE_DIR, _APP_FILE)).read()
    lines = [l for l in src.splitlines()
             if not (l.startswith('from flask') or l.startswith('from flask_cors')
                     or l.startswith('app = Flask') or l.startswith('CORS('))]
    body = '\n'.join(lines)
    body = body[:body.find('@app.route')]
    ns = {'__name__': 'fhx_core'}
    exec(compile(body, _APP_FILE, 'exec'), ns)
    try:
        import perf_patch          # fast extract_block for the frozen core parser
        perf_patch.apply(ns)
    except Exception:
        pass
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


def _fix_sfc_chrome(html):
    """Post-process the core SFC page chrome (without editing core/): the reset-zoom
    button shipped a fullscreen-looking glyph that read as confusing — relabel it to
    an unambiguous '1:1'. Also inject a tiny listener so the parent's ISA-88 state
    model can switch this viewer to a given logic block."""
    html = html.replace('title="Reset">\u2922</button>',
                        'title="Reset zoom to 100%">1:1</button>')
    listener = (
        "<script>window.addEventListener('message',function(e){"
        "var d=e.data||{};if(!d.s88block)return;"
        "var want=String(d.s88block).toUpperCase();"
        "var tabs=document.querySelectorAll('.tab');"
        "for(var i=0;i<tabs.length;i++){"
        "var txt=(tabs[i].textContent||'').trim().toUpperCase();"
        "var k=(tabs[i].dataset.k||'').toUpperCase();"
        "if(txt===want||k===want||(want==='FAIL_MONITOR'&&(txt.indexOf('MONITOR')>=0||k.indexOf('MONITOR')>=0))){"
        "tabs[i].click();tabs[i].scrollIntoView({block:'nearest'});break;}}"
        "});</script>")
    if '</body>' in html:
        html = html.replace('</body>', listener + '</body>', 1)
    else:
        html += listener
    return html


def build_phase_view_html(phase_name, blocks, text=None):
    """Generate the self-contained interactive phase viewer HTML for one phase.

    If the raw export `text` is supplied, transition expressions truncated by the
    core parser are repaired first (quote-aware re-extraction) so the displayed
    SFC shows full conditions like  '...U_CIP_SYNC_UNIT.CV' != "".
    """
    _, sfc_html = _core()
    if text is not None:
        try:
            sfc_expr_fix.repair_phase_blocks(text, blocks)
        except Exception:
            pass  # never let the repair break rendering; fall back to core output
    return _fix_sfc_chrome(sfc_html.build_sfc_html(blocks, phase_name))


def phase_view_map(text, with_sim=True):
    """Return {phase_name: interactive_html} for all phases in the export.

    When with_sim is True, each phase view gets the interactive simulator overlay
    (Simulate button -> live walk over the real SFC, operator-prompt handling).
    The overlay is injected post-render and falls back silently if the phase has
    no steppable RUN sequence, so the explorer is unaffected on failure.
    """
    phases = parse_phases_from_export(text)
    out = {}
    for pname, blocks in phases.items():
        try:
            html_doc = build_phase_view_html(pname, blocks, text)
            if with_sim:
                html_doc = _maybe_add_sim(text, pname, html_doc)
            out[pname] = html_doc
        except Exception as e:
            out[pname] = f"<html><body><p>Could not render {pname}: {e}</p></body></html>"
    return out


def _maybe_add_sim(text, phase_name, phase_html):
    """Inject the simulator overlay for phase_name, or return phase_html unchanged
    if the phase has no steppable sequence / the sim modules aren't available."""
    try:
        import sim_export
        import sim_overlay
        payload = sim_export.build_payload(text, phase_name)
        if not payload.get('order'):
            return phase_html
        return sim_overlay.inject(phase_html, payload)
    except Exception:
        return phase_html  # explorer phase view still works without the sim
