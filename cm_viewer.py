"""
Standalone Control Module (CM) viewer.

Takes a single CM export (.fhx) and produces a focused HTML view of just that
control module: the function block diagram (sectioned, like the DeltaV print),
nested composite drill-down, module parameter interface, block inventory, and
connection list.

Reuses the FBD engine (fbd_parser / fbd_render / fbd_bridge) from the explorer,
so the two stay in sync. Independent of the full database explorer — feed it one
CM export to verify quickly.

Usage:
    python cm_viewer.py  path/to/CM_export.fhx  [output.html]
    # or import build_cm_html(text, name) / generate(infile, outfile)
"""

import os
import sys
import re
import html
import json

# reuse the explorer's FBD engine
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db_explorer'))
import fbd_parser
import fbd_render
import fbd_bridge


def decode_fhx(raw):
    if raw[:2] == b'\xff\xfe':
        return raw.decode('utf-16-le', errors='replace').lstrip('\ufeff')
    if raw[:2] == b'\xfe\xff':
        return raw.decode('utf-16-be', errors='replace').lstrip('\ufeff')
    return raw.decode('utf-8', errors='replace')


_CSS = """
*{box-sizing:border-box}
body{margin:0;font:14px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;background:#f8fafc}
header{padding:14px 22px;background:#0f172a;color:#fff}
header h1{margin:0;font-size:16px}
header .sub{color:#94a3b8;font-size:12px;margin-top:2px}
.wrap{max-width:1200px;margin:0 auto;padding:22px}
.idcard{margin-bottom:18px}
.idcard h2{margin:0 0 4px;font-size:22px}
.badge{display:inline-block;font-size:11px;color:#fff;background:#f59e0b;padding:2px 10px;border-radius:10px;margin-bottom:8px}
.idcard .desc{color:#475569;margin:0 0 6px}
.kv{display:grid;grid-template-columns:140px 1fr;gap:3px 14px;font-size:13px;color:#334155;max-width:760px}
.kv .k{color:#64748b}
.objlist{display:flex;flex-wrap:wrap;gap:7px;margin:8px 0 0}
.objlist .chip{padding:4px 11px;border:1px solid #cbd5e1;border-radius:14px;font-size:12px;cursor:pointer;background:#fff}
.objlist .chip:hover{border-color:#2563eb;color:#2563eb;background:#eff6ff}
.objlist .chip.sel{background:#0f172a;color:#fff;border-color:#0f172a}
.fbd-wrap{display:flex;flex-direction:column;gap:14px}
.fbd-diagram-card{border:1px solid #e2e8f0;border-radius:8px;background:#fcfcfd;overflow:hidden}
.fbd-head{padding:10px 14px;background:#f1f5f9;font-weight:600;font-size:13px;border-bottom:1px solid #e2e8f0}
.fbd-sub{color:#64748b;font-weight:400;font-size:12px}
.fbd-svg-holder{padding:10px;overflow:auto;max-height:80vh}
.fbd-info-card{border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;background:#fff}
.fbd-info-card h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:#475569}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:3px 10px;border:1px solid #cbd5e1;border-radius:14px;font-size:12px;cursor:pointer;background:#fff}
.chip:hover{border-color:#2563eb;color:#2563eb}
.fbd-comp-link{border-color:#475569}
.fbd-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:4px}
.fbd-table th{text-align:left;padding:5px 8px;background:#f1f5f9;color:#475569;font-size:11px;border-bottom:1px solid #e2e8f0}
.fbd-table td{padding:4px 8px;border-bottom:1px solid #f1f5f9;vertical-align:top}
.fbd-table code{font-size:11px;background:#f8fafc;padding:1px 4px;border-radius:3px}
.empty{color:#94a3b8;font-style:italic}
.link{color:#2563eb;cursor:pointer;text-decoration:underline}
"""


def _list_cms(text):
    """All CM-like modules in the export (MODULE_CLASS with function blocks),
    excluding EM modules (those have SFC state logic)."""
    cms = []
    for o in fbd_parser.list_fbd_objects(text):
        if o['kind'] != 'MODULE_CLASS':
            continue
        # an EM has SFC/STEP logic; a CM is pure FBD
        fbd = fbd_parser.parse_module_fbd(text, o['name'])
        cms.append({'name': o['name'], 'n_blocks': o['n_blocks']})
    return cms


def build_cm_html(text, fname='CM Export'):
    # gather every FBD object (CMs + nested composite definitions) for views/drilldown
    fbd_views = fbd_bridge.build_fbd_views(text)

    # primary CMs = MODULE_CLASS objects (pick the most substantial as default)
    cms = _list_cms(text)
    if not cms:
        return f"<html><body style='font-family:sans-serif;padding:40px'>" \
               f"<h2>No control module found</h2>" \
               f"<p>This export does not contain a MODULE_CLASS with function blocks.</p></body></html>"
    cms.sort(key=lambda c: -c['n_blocks'])
    default = cms[0]['name']

    # identity for the default CM
    fbd0 = fbd_parser.parse_module_fbd(text, default)
    desc = fbd0.get('description', '')
    catm = re.search(r'MODULE_CLASS\s+NAME="' + re.escape(default) + r'"\s+CATEGORY="([^"]*)"', text)
    category = catm.group(1) if catm else ''

    data = json.dumps({'views': fbd_views, 'default': default,
                       'cms': [c['name'] for c in cms]})

    def _safe(s):
        return s.replace('</', '<\\/')

    js = """
const D = __DATA__;
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function showCM(name){
  document.querySelectorAll('.cm-pick').forEach(c=>c.classList.toggle('sel',c.dataset.n===name));
  const v=D.views[name];
  document.getElementById('cmview').innerHTML = v || '<p class="empty">No diagram for '+esc(name)+'</p>';
  wireFbd();
}
function showFbd(def,label){
  if(!D.views[def])return;
  document.getElementById('cmview').innerHTML =
    '<p><span class="link" onclick="showCM(D.default)">\\u2190 back to module</span></p>'+D.views[def];
  wireFbd();
}
function wireFbd(){
  document.querySelectorAll('.fbd-comp-link').forEach(el=>{
    el.onclick=()=>showFbd(el.getAttribute('data-fbd'), el.textContent);
  });
  document.querySelectorAll('.fb-composite').forEach(g=>{
    const def=g.getAttribute('data-composite');
    if(def&&D.views[def]){g.style.cursor='pointer';g.onclick=()=>showFbd(def,g.getAttribute('data-name'));}
  });
}
window.addEventListener('DOMContentLoaded',()=>{ showCM(D.default); });
"""
    js = js.replace('__DATA__', _safe(data))

    # CM picker chips (only if more than one CM in the export)
    picker = ''
    if len(cms) > 1:
        picker = '<div class="objlist">' + ''.join(
            f'<span class="chip cm-pick" data-n="{html.escape(c["name"])}" '
            f'onclick="showCM(\'{html.escape(c["name"])}\')">{html.escape(c["name"])} '
            f'· {c["n_blocks"]} blocks</span>' for c in cms) + '</div>'

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CM Viewer — {html.escape(default)}</title><style>{_CSS}</style></head><body>
<header><h1>Control Module Viewer</h1><div class="sub">{html.escape(fname)}</div></header>
<div class="wrap">
  <div class="idcard">
    <h2 id="cmname">{html.escape(default)}</h2>
    <span class="badge">Control Module · FBD</span>
    <p class="desc">{html.escape(desc)}</p>
    <div class="kv">
      {'<div class="k">Category</div><div>'+html.escape(category)+'</div>' if category else ''}
      <div class="k">Modules in export</div><div>{len(cms)}</div>
    </div>
    {picker}
  </div>
  <div id="cmview"></div>
</div>
<script>{js}</script>
</body></html>"""


def generate(infile, outfile=None):
    raw = open(infile, 'rb').read()
    text = decode_fhx(raw)
    fname = os.path.splitext(os.path.basename(infile))[0]
    doc = build_cm_html(text, fname)
    outfile = outfile or os.path.splitext(infile)[0] + '_CM_view.html'
    open(outfile, 'w', encoding='utf-8').write(doc)
    return outfile


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python cm_viewer.py  CM_export.fhx  [output.html]")
        sys.exit(1)
    out = generate(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print("Wrote", out)
