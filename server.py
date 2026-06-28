"""
DeltaV Database Explorer — web app.

Upload a DeltaV database FHX export and get a live, navigable explorer:
areas, units, equipment/control/phase classes, recipes, composites, with
class<->instance cross-linking and interactive phase drill-down.

Deploys on Render as a standard Python web service (no Dockerfile needed):
  Build command:  pip install -r requirements.txt
  Start command:  gunicorn server:app
"""

import io
import os
import re
import secrets
import tempfile
from flask import Flask, request, send_file, Response, abort

import db_parser
import db_explorer
import fonts

# phase drill-down is optional; only available if the parsing core is present
try:
    import phase_bridge
    _HAS_PHASE = True
except Exception:
    _HAS_PHASE = False

app = Flask(__name__)

# Mount the FHX Converter (Backup 1) under /tool so one deployment serves both
# the explorer (/) and the converter wizard (/tool/). Optional — explorer still
# works if the converter core is unavailable.
try:
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    import converter_app
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {converter_app.MOUNT: converter_app.capp})
    _HAS_CONVERTER = True
except Exception:
    _HAS_CONVERTER = False

# uploaded FHX is stashed here so the explorer's Export buttons can regenerate
# Excel/Word from the original text via the converter core.
_STASH = os.path.join(tempfile.gettempdir(), 'dvexp_stash')
os.makedirs(_STASH, exist_ok=True)


def _stash_fhx(text):
    token = secrets.token_urlsafe(12)
    with open(os.path.join(_STASH, token + '.fhx'), 'w', encoding='utf-8') as fh:
        fh.write(text)
    return token


def _read_stash(token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', token or ''):
        return None
    path = os.path.join(_STASH, token + '.fhx')
    if not os.path.isfile(path):
        return None
    return open(path, encoding='utf-8').read()


_EXPORT_OPTS = {
    'summary': True, 'transitions': True, 'expressions': True,
    'columns': ['step', 'description', 'action', 'qualifier', 'expression',
                'delay', 'confirm_expression'],
    'procedure': True, 'parameters': True, 'formulas': True,
    'step_params': False, 'all_params': False, 'show_limits': True,
    'diagram_detail': False,
}

UPLOAD_PAGE = """<!DOCTYPE html><html lang="en" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DeltaV Strategy Workbench</title>
<style>
:root{--canvas:#f6f8fb;--surface:#ffffff;--surface-2:#f3f6fa;--border:#dde4ec;--border-strong:#c7d2de;
  --ink:#16202c;--ink-2:#46566b;--ink-3:#7689a0;--accent:#1d4ed8;--accent-soft:#e7eefb;--link:#0e7490;
  --shadow:0 1px 2px rgba(16,32,47,.04),0 18px 40px -18px rgba(16,32,47,.22);--grid:rgba(29,78,216,.05);}
[data-theme="dark"]{--canvas:#0e141b;--surface:#161e27;--surface-2:#1b2531;--border:#28333f;--border-strong:#3a4856;
  --ink:#e6edf3;--ink-2:#a7b6c6;--ink-3:#73879b;--accent:#60a5fa;--accent-soft:#16263d;--link:#38bdf8;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 20px 50px -20px rgba(0,0,0,.6);--grid:rgba(96,165,250,.06);}
*{box-sizing:border-box}
body{margin:0;font-family:'IBM Plex Sans',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);
  background:linear-gradient(var(--grid) 1px,transparent 1px) 0 0/26px 26px,
    linear-gradient(90deg,var(--grid) 1px,transparent 1px) 0 0/26px 26px,var(--canvas);
  min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.mode{position:fixed;top:18px;right:18px;width:38px;height:38px;border-radius:10px;border:1px solid var(--border);
  background:var(--surface);color:var(--ink-2);display:grid;place-items:center;cursor:pointer}
.mode:hover{border-color:var(--border-strong);color:var(--ink)}
.mode svg{width:19px;height:19px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:34px 38px 30px;
  max-width:560px;width:100%;box-shadow:var(--shadow)}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:20px}
.brand .mk{width:40px;height:40px;border-radius:11px;display:grid;place-items:center;
  background:linear-gradient(140deg,#2563eb,#0e7490)}
.brand .nm{font-weight:600;font-size:16px;letter-spacing:-.01em}
.brand .nm small{display:block;color:var(--ink-3);font-weight:500;font-size:12px;font-family:'IBM Plex Mono'}
h1{margin:0 0 6px;font-size:23px;letter-spacing:-.015em}
p.lead{color:var(--ink-2);margin:0 0 22px;font-size:13.5px;line-height:1.55}
.drop{display:block;border:1.5px dashed var(--border-strong);border-radius:13px;padding:38px 24px;text-align:center;
  cursor:pointer;transition:.18s;background:var(--surface-2)}
.drop:hover{border-color:var(--accent);background:var(--accent-soft)}
.drop input{display:none}
.drop .ic{color:var(--accent)}.drop .ic svg{width:34px;height:34px}
.drop .t{margin-top:10px;color:var(--ink);font-weight:500}
.drop .h{margin-top:4px;color:var(--ink-3);font-size:12px;font-family:'IBM Plex Mono'}
button{margin-top:18px;width:100%;padding:12px;border:0;border-radius:10px;background:var(--accent);color:#fff;
  font-size:14.5px;font-weight:600;cursor:pointer;box-shadow:var(--shadow);font-family:inherit}
button:hover{filter:brightness(1.06)}
button:disabled{opacity:.5;cursor:not-allowed;filter:none}
.fn{margin-top:14px;color:var(--link);font-size:13px;text-align:center;word-break:break-all;font-family:'IBM Plex Mono'}
.note{margin-top:18px;color:var(--ink-3);font-size:12px;text-align:center;line-height:1.5}
.note a{color:var(--link);text-decoration:none;font-weight:600}
.note a:hover{text-decoration:underline}
.divider{height:1px;background:var(--border);margin:20px 0 0}
</style></head><body>
<button class="mode" id="mode" onclick="tgl()" title="Toggle light / dark">
  <svg id="mi" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/></svg>
</button>
<div class="card">
  <div class="brand">
    <div class="mk"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M12 2 4 6.5v9L12 20l8-4.5v-9L12 2Z"/><path d="M12 7v6M9 9.5h6"/></svg></div>
    <div class="nm">DeltaV Strategy Workbench<small>FHX database explorer &amp; converter</small></div>
  </div>
  <h1>Open a database</h1>
  <p class="lead">Upload a DeltaV FHX export to browse areas, units, equipment &amp; control
     modules, phases, recipes and composites — with class/instance cross-linking,
     interactive logic diagrams, and one-click validation exports.</p>
  <form method="POST" action="/explore" enctype="multipart/form-data" id="f">
    <label class="drop" id="drop">
      <div class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 15V3M8 7l4-4 4 4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg></div>
      <div class="t">Drop an FHX file here, or click to browse</div>
      <div class="h">.fhx export from DeltaV</div>
      <input type="file" name="file" id="file" accept=".fhx" required>
    </label>
    <div class="fn" id="fn"></div>
    <button type="submit" id="btn" disabled>Open in Explorer</button>
  </form>
  <div class="divider"></div>
  <div class="note">Large exports (e.g. a full area, 30&nbsp;MB) may take a minute to parse.</div>
  <div class="note" style="margin-top:8px">Need to convert instead?
    <a href="/tool/">Open the FHX Converter &rarr;</a></div>
</div>
<script>
var fi=document.getElementById('file'),fn=document.getElementById('fn'),btn=document.getElementById('btn');
fi.addEventListener('change',function(){ if(fi.files.length){fn.textContent=fi.files[0].name;btn.disabled=false;} });
var drop=document.getElementById('drop');
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.style.borderColor='var(--accent)';}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.style.borderColor='';}));
drop.addEventListener('drop',ev=>{if(ev.dataTransfer.files.length){fi.files=ev.dataTransfer.files;fn.textContent=ev.dataTransfer.files[0].name;btn.disabled=false;}});
document.getElementById('f').addEventListener('submit',function(){btn.disabled=true;btn.textContent='Opening…';});
var SUN='<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/>';
var MOON='<path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.5 6.5 0 0 0 9.8 9.8Z"/>';
function tgl(){var d=document.documentElement,m=d.dataset.theme==='dark'?'light':'dark';d.dataset.theme=m;
  document.getElementById('mi').innerHTML=(m==='dark'?MOON:SUN);try{localStorage.setItem('dvexp_mode',m);}catch(e){}}
(function(){try{var m=localStorage.getItem('dvexp_mode');if(m){document.documentElement.dataset.theme=m;
  document.getElementById('mi').innerHTML=(m==='dark'?MOON:SUN);}}catch(e){}})();
</script>
</body></html>"""


@app.route('/')
def index():
    return UPLOAD_PAGE.replace('<style>', '<style>' + fonts.FONT_CSS, 1)


@app.route('/explore', methods=['POST'])
def explore():
    f = request.files.get('file')
    if not f:
        return "No file uploaded.", 400
    raw = f.read()
    fname = (f.filename or 'export.fhx').rsplit('.', 1)[0]
    text = db_parser.decode_fhx(raw)

    catalog = db_parser.parse_database(text)
    export_token = _stash_fhx(text)

    phase_views = {}
    if _HAS_PHASE:
        try:
            phase_views = phase_bridge.phase_view_map(text)
        except Exception:
            phase_views = {}   # explorer still works without drill-down

    fbd_views, em_views, param_index, expr_index = {}, {}, {}, []
    try:
        import fbd_bridge
        fbd_views = fbd_bridge.build_fbd_views(text)
        _ix = fbd_bridge.build_indexes(text)
        param_index, expr_index = _ix['params'], _ix['exprs']
    except Exception:
        fbd_views = {}
    try:
        import em_bridge
        em_views = em_bridge.build_em_views(text)
    except Exception:
        em_views = {}

    html = db_explorer.build_explorer_html(catalog, fname, phase_views=phase_views,
                                           fbd_views=fbd_views, em_views=em_views,
                                           param_index=param_index, expr_index=expr_index,
                                           export_token=export_token)
    return Response(html, mimetype='text/html')


def _extract_object_fhx(text, obj):
    """Slice out the FHX block for a single object (obj = 'phase:NAME' | 'em:NAME')
    so it can be exported on its own. Returns None when the object can't be located."""
    if ':' not in obj:
        return None
    typ, name = obj.split(':', 1)
    if typ == 'phase':
        m = re.search(r'PHASE_CLASS\s+NAME="' + re.escape(name) + r'"', text)
    elif typ == 'em':
        m = re.search(r'MODULE_CLASS\s+NAME="' + re.escape(name) + r'"', text)
    else:
        return None
    if not m:
        return None
    return db_parser.extract_block(text, m.start())


@app.route('/export')
def export():
    """Regenerate an Excel workbook or Word DDS from the stashed FHX, reusing the
    converter core. fmt = excel | word | data_excel. When obj=<type>:<name> is given,
    export just that object (e.g. a single phase) instead of the whole database."""
    token = request.args.get('token', '')
    fmt = request.args.get('fmt', 'excel')
    obj = request.args.get('obj', '')
    text = _read_stash(token)
    if text is None:
        abort(404, 'Export source expired — re-open the database to export again.')
    if obj:
        sub = _extract_object_fhx(text, obj)
        if sub is None:
            abort(404, 'That object could not be located for export.')
        text = sub
    fname = re.sub(r'[^A-Za-z0-9_.-]', '_', request.args.get('name', 'export'))
    try:
        import phase_bridge as _pb
        ns, _ = _pb._core()
        ftype = ns['detect_fhx_type'](text)
        buf, _sheets = ns['parse_and_build'](text, ftype, fname, _EXPORT_OPTS, fmt)
    except Exception as e:
        abort(500, f'Export failed: {e}')
    if fmt == 'word':
        return send_file(buf, as_attachment=True, download_name=fname + '_DDS.docx',
                         mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    return send_file(buf, as_attachment=True, download_name=fname + '.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  DeltaV Database Explorer running at  http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=False)
