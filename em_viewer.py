"""
Standalone Equipment Module (EM) viewer.

Takes a single EM export (.fhx) and produces a focused HTML view of that
equipment module. An EM is a hybrid: it has an FBD function-block layer
(acquire/release, monitors, commands, timers) AND command/state logic (SFC).
This viewer shows both:
  - the FBD function-block diagram (reusing the FBD engine)
  - the command/state logic (reusing the converter's EM SFC parser, when present)
  - the embedded control modules the EM references

Reuses the FBD engine (fbd_parser/render/bridge) and the converter's EM parser,
so the standalone tool stays in sync with the explorer and converter.

Usage:
    python em_viewer.py  path/to/EM_export.fhx  [output.html]
"""

import os
import sys
import re
import html
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'db_explorer'))
import fbd_parser
import fbd_render
import fbd_bridge

# converter core (for EM command/state SFC parsing) — loaded lazily
_CORE_DIR = os.environ.get('FHX_CORE_DIR',
                           os.path.join(_HERE, '..', 'db_explorer', 'core'))
_CORE = None
_SFC = None


def decode_fhx(raw):
    if raw[:2] == b'\xff\xfe':
        return raw.decode('utf-16-le', errors='replace').lstrip('\ufeff')
    if raw[:2] == b'\xfe\xff':
        return raw.decode('utf-16-be', errors='replace').lstrip('\ufeff')
    return raw.decode('utf-8', errors='replace')


def _load_core():
    """Load the converter's EM parser + interactive SFC HTML, without Flask."""
    global _CORE, _SFC
    if _CORE is not None:
        return _CORE, _SFC
    appfile = 'fhx_app.py' if os.path.exists(os.path.join(_CORE_DIR, 'fhx_app.py')) else 'app.py'
    sys.path.insert(0, _CORE_DIR)
    src = open(os.path.join(_CORE_DIR, appfile)).read()
    lines = [l for l in src.splitlines()
             if not (l.startswith('from flask') or l.startswith('from flask_cors')
                     or l.startswith('app = Flask') or l.startswith('CORS('))]
    body = '\n'.join(lines)
    body = body[:body.find('@app.route')]
    ns = {'__name__': 'fhx_core'}
    try:
        exec(compile(body, appfile, 'exec'), ns)
        import sfc_html
        _CORE, _SFC = ns, sfc_html
    except Exception:
        _CORE, _SFC = {}, None
    return _CORE, _SFC


def _em_modules(text):
    """Identify the EM module(s) in the export: MODULE_CLASS objects whose name
    starts with EM_ or that contain SFC/STEP state logic. Everything else with
    function blocks is an embedded CM."""
    ems, cms = [], []
    for o in fbd_parser.list_fbd_objects(text):
        if o['kind'] != 'MODULE_CLASS':
            continue
        fbd = fbd_parser.parse_module_fbd(text, o['name'])
        # detect EM by name prefix or presence of command/state composites
        is_em = o['name'].upper().startswith('EM') or _has_state_logic(text, o['name'])
        (ems if is_em else cms).append({'name': o['name'], 'n_blocks': o['n_blocks']})
    return ems, cms


def _has_state_logic(text, name):
    """Heuristic: does this module block contain SFC/STEP/COMMAND state logic?"""
    m = re.search(r'MODULE_CLASS\s+NAME="' + re.escape(name) + r'"', text)
    if not m:
        return False
    blk = fbd_parser._extract_block(text, m.end())
    return ('COMMAND_0000' in blk) or ('SFC_ALGORITHM' in blk) or ('STEP NAME=' in blk)


_CSS = """
*{box-sizing:border-box}
body{margin:0;font:14px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;background:#f8fafc}
header{padding:14px 22px;background:#0f172a;color:#fff}
header h1{margin:0;font-size:16px}
header .sub{color:#94a3b8;font-size:12px;margin-top:2px}
.wrap{max-width:1200px;margin:0 auto;padding:22px}
.idcard{margin-bottom:16px}
.idcard h2{margin:0 0 4px;font-size:22px}
.badge{display:inline-block;font-size:11px;color:#fff;background:#8b5cf6;padding:2px 10px;border-radius:10px;margin-bottom:8px}
.idcard .desc{color:#475569;margin:0 0 6px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:3px 14px;font-size:13px;color:#334155;max-width:760px}
.kv .k{color:#64748b}
.tabs{display:flex;gap:6px;margin:14px 0}
.tab{padding:7px 16px;border:1px solid #e2e8f0;border-radius:7px;background:#fff;cursor:pointer;font-size:13px;font-weight:600;color:#475569}
.tab.on{background:#0f172a;color:#fff;border-color:#0f172a}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:6px}
.chip{padding:4px 11px;border:1px solid #cbd5e1;border-radius:14px;font-size:12px;cursor:pointer;background:#fff}
.chip:hover{border-color:#2563eb;color:#2563eb}
.chip.sel{background:#0f172a;color:#fff;border-color:#0f172a}
.fbd-wrap{display:flex;flex-direction:column;gap:14px}
.fbd-diagram-card{border:1px solid #e2e8f0;border-radius:8px;background:#fcfcfd;overflow:hidden}
.fbd-head{padding:10px 14px;background:#f1f5f9;font-weight:600;font-size:13px;border-bottom:1px solid #e2e8f0}
.fbd-sub{color:#64748b;font-weight:400;font-size:12px}
.fbd-svg-holder{padding:10px;overflow:auto;max-height:80vh}
.fbd-info-card{border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;background:#fff}
.fbd-info-card h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:#475569}
.fbd-comp-link{border-color:#475569}
.fbd-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:4px}
.fbd-table th{text-align:left;padding:5px 8px;background:#f1f5f9;color:#475569;font-size:11px;border-bottom:1px solid #e2e8f0}
.fbd-table td{padding:4px 8px;border-bottom:1px solid #f1f5f9;vertical-align:top}
.fbd-table code{font-size:11px;background:#f8fafc;padding:1px 4px;border-radius:3px}
.stateframe{width:100%;height:78vh;border:1px solid #e2e8f0;border-radius:6px;background:#fff}
.empty{color:#94a3b8;font-style:italic}
.link{color:#2563eb;cursor:pointer;text-decoration:underline}
.panel{display:none}.panel.on{display:block}
"""


def _state_logic_html(text, em_name):
    """Build the EM command/state view via the converter core.

    A command-driven EM (em_cd) is a collection of commands, each with its own
    SFC (ordered_steps/transitions). We render each command as its own diagram.
    A state-driven EM (em_sd) parses like phase state logic.
    """
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
        # build one interactive SFC view per command, wrapped as a tabbed set
        cmd_views = []
        for c in commands:
            cname = c.get('command_name', 'CMD')
            # adapt the command dict into the block shape build_sfc_html expects:
            # a single logic block keyed by command name.
            block = {
                'instance_name': cname,
                'description': c.get('fb_description', ''),
                'ordered_steps': c.get('ordered_steps', []),
                'transitions': c.get('transitions', {}),
                'step_to_trans': c.get('step_to_trans', {}),
                'trans_to_step': c.get('trans_to_step', {}),
            }
            blocks = {cname: block}
            try:
                view = sfc.build_sfc_html(blocks, f"{em_name} — {cname}")
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
    """Wrap multiple command SFC views into a tabbed structure (returns a
    self-contained HTML doc to embed in an iframe)."""
    if not cmd_views:
        return ''
    import json as _json
    views = {name: v for name, v in cmd_views}
    tabs = ''.join(
        f'<button class="ctab{" on" if i == 0 else ""}" onclick="pick(\'{html.escape(name)}\')" '
        f'data-c="{html.escape(name, quote=True)}">{html.escape(name)}</button>'
        for i, (name, _) in enumerate(cmd_views))
    data = _json.dumps(views).replace('</', '<\\/')
    first = cmd_views[0][0]
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,sans-serif}}
.ctabs{{display:flex;flex-wrap:wrap;gap:5px;padding:8px;background:#f1f5f9;position:sticky;top:0}}
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


def build_em_html(text, fname='EM Export'):
    ems, cms = _em_modules(text)
    fbd_views = fbd_bridge.build_fbd_views(text)

    if not ems:
        # fall back: treat the largest module as the EM
        if cms:
            ems = [cms[0]]; cms = cms[1:]
        else:
            return "<html><body style='font-family:sans-serif;padding:40px'>" \
                   "<h2>No equipment module found</h2></body></html>"
    ems.sort(key=lambda c: -c['n_blocks'])
    em = ems[0]['name']

    fbd = fbd_parser.parse_module_fbd(text, em)
    desc = fbd.get('description', '') if fbd else ''
    catm = re.search(r'MODULE_CLASS\s+NAME="' + re.escape(em) + r'"\s+CATEGORY="([^"]*)"', text)
    category = catm.group(1) if catm else ''

    em_fbd_view = fbd_views.get(em, '<p class="empty">No function block layer.</p>')
    state_html = _state_logic_html(text, em)

    def _safe(s):
        return s.replace('</', '<\\/')

    data = json.dumps({'views': fbd_views, 'em': em,
                       'state': state_html, 'cms': [c['name'] for c in cms]})

    js = """
const D = __DATA__;
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function tab(which){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.dataset.t===which));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',p.dataset.t===which));
  if(which==='fbd') wireFbd();
}
function showFbd(def,label){
  if(!D.views[def])return;
  document.getElementById('fbdpanel').innerHTML =
    '<p><span class="link" onclick="showEMfbd()">\\u2190 back</span></p>'+D.views[def];
  wireFbd();
}
function showEMfbd(){ document.getElementById('fbdpanel').innerHTML = D.views[D.em]; wireFbd(); }
function wireFbd(){
  document.querySelectorAll('.fbd-comp-link').forEach(el=>{
    el.onclick=()=>showFbd(el.getAttribute('data-fbd'), el.textContent);
  });
  document.querySelectorAll('.fb-composite').forEach(g=>{
    const def=g.getAttribute('data-composite');
    if(def&&D.views[def]){g.style.cursor='pointer';g.onclick=()=>showFbd(def,g.getAttribute('data-name'));}
  });
}
window.addEventListener('DOMContentLoaded',()=>{ tab('fbd'); });
"""
    js = js.replace('__DATA__', _safe(data))

    cm_chips = ''
    if cms:
        cm_chips = '<div class="fbd-info-card"><h4>Embedded Control Modules (' + str(len(cms)) + ')</h4><div class="chips">' + \
            ''.join(f'<span class="chip">{html.escape(c["name"])} · {c["n_blocks"]} blocks</span>' for c in cms) + \
            '</div></div>'

    state_panel = (f'<iframe class="stateframe" srcdoc="{html.escape(state_html, quote=True)}"></iframe>'
                   if state_html else '<p class="empty">No command/state logic parsed for this EM.</p>')

    has_state = 'on' if False else ''  # fbd default
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EM Viewer — {html.escape(em)}</title><style>{_CSS}</style></head><body>
<header><h1>Equipment Module Viewer</h1><div class="sub">{html.escape(fname)}</div></header>
<div class="wrap">
  <div class="idcard">
    <h2>{html.escape(em)}</h2>
    <span class="badge">Equipment Module</span>
    <p class="desc">{html.escape(desc)}</p>
    <div class="kv">
      {'<div class="k">Category</div><div>'+html.escape(category)+'</div>' if category else ''}
      <div class="k">Embedded CMs</div><div>{len(cms)}</div>
    </div>
  </div>
  <div class="tabs">
    <div class="tab on" data-t="fbd" onclick="tab('fbd')">Function Blocks</div>
    <div class="tab" data-t="state" onclick="tab('state')">Command / State Logic</div>
    <div class="tab" data-t="cms" onclick="tab('cms')">Control Modules</div>
  </div>
  <div class="panel on" data-t="fbd"><div id="fbdpanel">{em_fbd_view}</div></div>
  <div class="panel" data-t="state">{state_panel}</div>
  <div class="panel" data-t="cms">{cm_chips or '<p class="empty">No embedded control modules in this export.</p>'}</div>
</div>
<script>{js}</script>
</body></html>"""


def generate(infile, outfile=None):
    raw = open(infile, 'rb').read()
    text = decode_fhx(raw)
    fname = os.path.splitext(os.path.basename(infile))[0]
    doc = build_em_html(text, fname)
    outfile = outfile or os.path.splitext(infile)[0] + '_EM_view.html'
    open(outfile, 'w', encoding='utf-8').write(doc)
    return outfile


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python em_viewer.py  EM_export.fhx  [output.html]")
        sys.exit(1)
    out = generate(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print("Wrote", out)
