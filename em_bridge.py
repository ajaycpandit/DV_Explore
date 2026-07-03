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


def _fix_sfc(html):
    """Relabel the core SFC reset-zoom button (fullscreen-looking glyph) to a
    clear '1:1' without editing core/."""
    return html.replace('title="Reset">\u2922</button>',
                        'title="Reset zoom to 100%">1:1</button>')


def em_cm_members(text, em_name):
    """Return the control modules embedded in an EM, with per-member ownership.
    Each is {name, module (class), ownership ('SHARED'|'PRIVATE'|''), desc}.
    Parsed from MODULE_BLOCK entries inside the EM's MODULE_CLASS block."""
    import re as _re
    m = _re.search(r'MODULE_CLASS\s+NAME="' + _re.escape(em_name) + r'"', text)
    if not m:
        return []
    blk = fbd_parser._extract_block(text, m.start())
    out = []
    for mb in _re.finditer(r'MODULE_BLOCK\s+NAME="([^"]+)"\s+MODULE="([^"]+)"\s*\{', blk):
        name, mod = mb.group(1), mb.group(2)
        body = fbd_parser._extract_block(blk, mb.end() - 1)
        own = _re.search(r'OWNERSHIP=(SHARED|PRIVATE)', body)
        desc = _re.search(r'DESCRIPTION="([^"]*)"', body)
        out.append({'name': name, 'module': mod,
                    'ownership': own.group(1) if own else '',
                    'desc': desc.group(1) if desc else ''})
    return out


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
        # parse_cdem_fhx returns commands for ALL EMs in the export; keep only this
        # EM's commands (each command carries its owning em_name). This fixes the
        # duplicate-command problem where every EM showed every EM's commands.
        # IMPORTANT: if this EM has NONE of its own commands, it is not a command-SFC
        # EM at all (e.g. a failure monitor / message module) — render nothing here
        # rather than falling back to every EM's commands.
        own = [c for c in commands if (c.get('em_name') or '') == em_name]
        if not own:
            return ''
        commands = own
        # de-dupe by command name within this EM (a command is a unit; it cannot
        # legitimately repeat inside the same EM), keeping the first occurrence.
        seen = set()
        deduped = []
        for c in commands:
            cn = c.get('command_name', 'CMD')
            if cn in seen:
                continue
            seen.add(cn)
            deduped.append(c)
        commands = deduped
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
                view = _fix_sfc(sfc.build_sfc_html({cname: block}, f"{em_name} — {cname}"))
                try:
                    import sfc_interact
                    view = sfc_interact.inject_interactions(view)
                except Exception:
                    pass
                cmd_views.append((cname, view))
            except Exception:
                continue
        return _commands_tabset(cmd_views)

    if ftype == 'em_sd':
        try:
            em_list = core['parse_sdem_fhx'](text)
        except Exception:
            return ''
        return _sdem_table_html(em_list, em_name)
    return ''


def _sdem_table_html(em_list, em_name):
    """Render a state-driven EM as a state table (states x devices -> targets),
    the way DeltaV presents an SDA. Self-contained doc for an iframe srcdoc."""
    em = next((e for e in em_list if e.get('em_name') == em_name), None)
    if not em and em_list:
        em = em_list[0]
    if not em or not em.get('states'):
        return ''
    devices = em['devices']
    states = em['states']
    desc = html.escape(em.get('em_description', ''))

    def _cell(v, dc):
        if dc:
            return '<td class="dc" title="Don\'t care">\u2014</td>'
        vv = (v or '').strip()
        cls = ''
        up = vv.upper()
        if up in ('OPEN', 'ON', 'TRUE', 'RUNNING', 'START'):
            cls = ' v-on'
        elif up in ('CLOSE', 'CLOSED', 'OFF', 'FALSE', 'STOP', 'STOPPED'):
            cls = ' v-off'
        return f'<td class="val{cls}">{html.escape(vv) if vv else "&nbsp;"}</td>'

    head = ''.join(f'<th class="dev" title="{html.escape(d)}">{html.escape(d)}</th>' for d in devices)
    rows = []
    for s in states:
        cells = ''.join(_cell(s['values'].get(d, ''), s['dont_care'].get(d, False)) for d in devices)
        en = '' if s.get('enabled', True) else ' class="disabled" title="State disabled"'
        rows.append(
            f'<tr{en}><td class="idx">{s["index"]}</td>'
            f'<td class="sname">{html.escape(s["state_name"])}</td>{cells}</tr>')
    body = '\n'.join(rows)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:'IBM Plex Sans',-apple-system,Segoe UI,Roboto,sans-serif;color:#16202c;background:#fff;font-size:13px}}
.hd{{padding:12px 16px;border-bottom:1px solid #dde4ec;position:sticky;top:0;background:#fff;z-index:6}}
.hd .t{{font-weight:600;font-size:15px}}
.hd .s{{color:#46566b;font-size:12px;margin-top:2px}}
.hd .meta{{margin-top:7px;display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:#7689a0}}
.hd .meta b{{color:#16202c;font-weight:600}}
.scroll{{overflow:auto;max-height:calc(100vh - 0px)}}
table{{border-collapse:separate;border-spacing:0;width:max-content;min-width:100%}}
th,td{{border-bottom:1px solid #eef2f7;border-right:1px solid #eef2f7;padding:6px 10px;text-align:center;white-space:nowrap}}
thead th{{position:sticky;top:0;background:#f3f6fa;font-size:11px;color:#46566b;font-weight:600;z-index:3;border-bottom:1px solid #dde4ec}}
th.idx,td.idx{{width:40px;color:#7689a0;font-family:'IBM Plex Mono',monospace;font-size:11px;position:sticky;left:0;background:#fff;z-index:2}}
thead th.idx{{z-index:4;background:#f3f6fa}}
th.sname,td.sname{{text-align:left;position:sticky;left:40px;background:#fff;z-index:2;font-weight:500;min-width:210px;box-shadow:1px 0 0 #dde4ec}}
thead th.sname{{z-index:4;background:#f3f6fa}}
.dev{{font-family:'IBM Plex Mono',monospace}}
td.val{{font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:#16202c}}
td.v-on{{color:#047857;font-weight:600;background:#ecfdf5}}
td.v-off{{color:#64748b;background:#f8fafc}}
td.dc{{color:#cbd5e1}}
tr.disabled{{opacity:.5}}
tr:hover td{{background:#eff6ff}}
tr:hover td.idx,tr:hover td.sname{{background:#eff6ff}}
</style></head><body>
<div class="hd"><div class="t">{html.escape(em_name)} <span style="font-weight:400;color:#7689a0">— State Driven EM</span></div>
<div class="s">{desc}</div>
<div class="meta"><span><b>{len(states)}</b> states</span><span><b>{len(devices)}</b> devices</span>
<span>States are defined by the EM's named set; each cell is the target the device is driven to in that state (&ldquo;&mdash;&rdquo; = don't care).</span></div></div>
<div class="scroll"><table><thead><tr><th class="idx">#</th><th class="sname">State</th>{head}</tr></thead>
<tbody>{body}</tbody></table></div>
</body></html>"""


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


def build_em_views(text, only=None):
    """Return {em_name: {fbd, state, cms}} for every EM in the export, for the
    explorer's EM leaves. If `only` is given, build just that one EM (and only
    its FBD), which is dramatically cheaper on large exports."""
    ems, cms = em_modules(text)
    if only is not None:
        ems = [e for e in ems if e['name'] == only]
    out = {}
    for em in ems:
        name = em['name']
        # build only this EM's FBD, not every FBD in the export
        fbd_one = fbd_bridge.build_fbd_views(text, only=name)
        # this EM's own control-module members, with per-member ownership (#5/#6)
        members = em_cm_members(text, name)
        out[name] = {
            'fbd': fbd_one.get(name, ''),
            'state': command_state_html(text, name),
            'cms': cms,          # kept for back-compat (global CM list)
            'members': members,  # EM's embedded CMs with ownership
        }
    return out


def list_em_names(text):
    """EM names for lazy loading, without building any views."""
    ems, _ = em_modules(text)
    return [e['name'] for e in ems]


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
