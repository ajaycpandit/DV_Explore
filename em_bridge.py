"""
Shared Equipment Module (EM) bridge.

Single source of truth for building EM views, imported by BOTH the database
explorer (db_explorer.py) and the standalone EM viewer (em_viewer.py), so the
two stay in sync.

An EM is a hybrid object:
  - an FBD function-block layer (acquire/release, monitors, timers, commands)
  - command/state logic: a command-driven EM (em_cd) is a set of commands, each
    with its own SFC; a state-driven EM (em_sd) parses like phase state logic
  - embedded control modules it references

This module returns the building blocks (fbd view, command views, embedded CM
list) plus a ready-made composed leaf for the explorer.

FHX-only: structure, wiring, composites, command logic. No configured values.
"""

import os
import sys
import re
import html
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
import fbd_parser
import fbd_bridge

# converter core (EM SFC parsing) loaded lazily from ./core
_CORE_DIR = os.environ.get('FHX_CORE_DIR', os.path.join(_HERE, 'core'))
_CORE = None
_SFC = None


def _load_core():
    global _CORE, _SFC
    if _CORE is not None:
        return _CORE, _SFC
    appfile = 'fhx_app.py' if os.path.exists(os.path.join(_CORE_DIR, 'fhx_app.py')) else 'app.py'
    sys.path.insert(0, _CORE_DIR)
    try:
        src = open(os.path.join(_CORE_DIR, appfile)).read()
        lines = [l for l in src.splitlines()
                 if not (l.startswith('from flask') or l.startswith('from flask_cors')
                         or l.startswith('app = Flask') or l.startswith('CORS('))]
        body = '\n'.join(lines)
        body = body[:body.find('@app.route')]
        ns = {'__name__': 'fhx_core'}
        exec(compile(body, appfile, 'exec'), ns)
        import sfc_html
        _CORE, _SFC = ns, sfc_html
    except Exception:
        _CORE, _SFC = {}, None
    return _CORE, _SFC


def _has_state_logic(text, name):
    m = re.search(r'MODULE_CLASS\s+NAME="' + re.escape(name) + r'"', text)
    if not m:
        return False
    blk = fbd_parser._extract_block(text, m.end())
    return ('COMMAND_0000' in blk) or ('SFC_ALGORITHM' in blk) or ('STEP NAME=' in blk)


def em_modules(text):
    """Split the export's modules into EMs and embedded CMs."""
    ems, cms = [], []
    for o in fbd_parser.list_fbd_objects(text):
        if o['kind'] != 'MODULE_CLASS':
            continue
        is_em = o['name'].upper().startswith('EM') or _has_state_logic(text, o['name'])
        (ems if is_em else cms).append({'name': o['name'], 'n_blocks': o['n_blocks']})
    return ems, cms


def command_state_html(text, em_name):
    """Interactive command/state view for an EM. A command-driven EM becomes a
    tabbed set of command SFCs; a state-driven EM renders like phase logic."""
    core, sfc = _load_core()
    if not core or not sfc:
        return ''
    try:
        ftype = core['detect_fhx_type'](text)
    except Exception:
        return ''

    if ftype == 'em_cd':
        try:
            commands = core['parse_cdem_fhx'](text)
        except Exception:
            return ''
        if not commands:
            return ''
        cmd_views = []
        for c in commands:
            cname = c.get('command_name', 'CMD')
            block = {
                'instance_name': cname,
                'description': c.get('fb_description', ''),
                'ordered_steps': c.get('ordered_steps', []),
                'transitions': c.get('transitions', {}),
                'step_to_trans': c.get('step_to_trans', {}),
                'trans_to_step': c.get('trans_to_step', {}),
            }
            try:
                view = sfc.build_sfc_html({cname: block}, f"{em_name} — {cname}")
                cmd_views.append((cname, view))
            except Exception:
                continue
        return _commands_tabset(cmd_views)

    if ftype == 'em_sd':
        try:
            blocks = core['parse_sdem_fhx'](text)
            return sfc.build_sfc_html(blocks, em_name)
        except Exception:
            return ''
    return ''


def _commands_tabset(cmd_views):
    if not cmd_views:
        return ''
    views = {name: v for name, v in cmd_views}
    tabs = ''.join(
        f'<button class="ctab{" on" if i == 0 else ""}" onclick="pick(\'{html.escape(name)}\')" '
        f'data-c="{html.escape(name, quote=True)}">{html.escape(name)}</button>'
        for i, (name, _) in enumerate(cmd_views))
    data = json.dumps(views).replace('</', '<\\/')
    first = cmd_views[0][0]
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,sans-serif}}
.ctabs{{display:flex;flex-wrap:wrap;gap:5px;padding:8px;background:#f1f5f9;position:sticky;top:0;z-index:5}}
.ctab{{padding:6px 13px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;cursor:pointer;font-size:12px;font-weight:600;color:#475569}}
.ctab.on{{background:#0f172a;color:#fff;border-color:#0f172a}}
#cv{{height:calc(100% - 46px)}}#cv iframe{{width:100%;height:100%;border:0}}
html,body{{height:100%}}
</style></head><body>
<div class="ctabs">{tabs}</div>
<div id="cv"></div>
<script>
const V=__D__;
function pick(n){{document.querySelectorAll('.ctab').forEach(t=>t.classList.toggle('on',t.dataset.c===n));
  const f=document.createElement('iframe');f.srcdoc=V[n];document.getElementById('cv').innerHTML='';document.getElementById('cv').appendChild(f);}}
pick('{html.escape(first)}');
</script></body></html>""".replace('__D__', data)


def build_em_views(text):
    """Return {em_name: {fbd, state, cms}} for every EM in the export, for the
    explorer's EM leaves."""
    ems, cms = em_modules(text)
    fbd_views = fbd_bridge.build_fbd_views(text)
    out = {}
    for em in ems:
        name = em['name']
        out[name] = {
            'fbd': fbd_views.get(name, ''),
            'state': command_state_html(text, name),
            'cms': cms,
        }
    return out


def build_em_leaf(text, em_name):
    """Compose the EM detail leaf for the explorer: tabs for Function Blocks,
    Command/State Logic, and embedded Control Modules. Returns a dict with the
    pieces so the caller can embed them (the command/state HTML is returned
    separately so it can go in an iframe srcdoc)."""
    fbd_views = fbd_bridge.build_fbd_views(text)
    ems, cms = em_modules(text)
    fbd_view = fbd_views.get(em_name, '')
    state_html = command_state_html(text, em_name)
    return {
        'fbd_view': fbd_view,
        'state_html': state_html,
        'embedded_cms': cms,
        'fbd_views': fbd_views,
    }
