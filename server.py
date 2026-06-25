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
from flask import Flask, request, send_file, Response

import db_parser
import db_explorer

# phase drill-down is optional; only available if the parsing core is present
try:
    import phase_bridge
    _HAS_PHASE = True
except Exception:
    _HAS_PHASE = False

app = Flask(__name__)

UPLOAD_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DeltaV Database Explorer</title>
<style>
*{box-sizing:border-box}
body{margin:0;font:15px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:38px 40px;max-width:560px;width:92%}
h1{margin:0 0 6px;font-size:22px;color:#fff}
p{color:#94a3b8;margin:0 0 22px;font-size:14px;line-height:1.5}
.drop{display:block;border:2px dashed #475569;border-radius:10px;padding:40px 24px;text-align:center;
  cursor:pointer;transition:.18s;background:#0f172a}
.drop:hover{border-color:#3b82f6;background:#172033}
.drop input{display:none}
.drop .ic{font-size:34px}
.drop .t{margin-top:8px;color:#cbd5e1}
.drop .h{margin-top:4px;color:#64748b;font-size:12px}
button{margin-top:18px;width:100%;padding:12px;border:0;border-radius:8px;background:#2563eb;color:#fff;
  font-size:15px;font-weight:600;cursor:pointer}
button:hover{background:#1d4ed8}
button:disabled{background:#475569;cursor:not-allowed}
.fn{margin-top:14px;color:#93c5fd;font-size:13px;text-align:center;word-break:break-all}
.note{margin-top:18px;color:#64748b;font-size:12px;text-align:center}
</style></head><body>
<div class="card">
  <h1>DeltaV Database Explorer</h1>
  <p>Upload a DeltaV database FHX export to browse areas, units, equipment &amp;
     control modules, phases, recipes, and composites — with class/instance
     cross-linking and interactive phase logic.</p>
  <form method="POST" action="/explore" enctype="multipart/form-data" id="f">
    <label class="drop" id="drop">
      <div class="ic">&#128194;</div>
      <div class="t">Drop an FHX file here or click to browse</div>
      <div class="h">.fhx export from DeltaV</div>
      <input type="file" name="file" id="file" accept=".fhx" required>
    </label>
    <div class="fn" id="fn"></div>
    <button type="submit" id="btn" disabled>Build Explorer</button>
  </form>
  <div class="note">Large exports (e.g. full Area, 30&nbsp;MB) may take a minute to parse.</div>
</div>
<script>
var fi=document.getElementById('file'),fn=document.getElementById('fn'),btn=document.getElementById('btn');
fi.addEventListener('change',function(){
  if(fi.files.length){fn.textContent=fi.files[0].name;btn.disabled=false;}
});
var drop=document.getElementById('drop');
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.style.borderColor='#3b82f6';}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.style.borderColor='';}));
drop.addEventListener('drop',ev=>{if(ev.dataTransfer.files.length){fi.files=ev.dataTransfer.files;fn.textContent=ev.dataTransfer.files[0].name;btn.disabled=false;}});
document.getElementById('f').addEventListener('submit',function(){btn.disabled=true;btn.textContent='Building…';});
</script>
</body></html>"""


@app.route('/')
def index():
    return UPLOAD_PAGE


@app.route('/explore', methods=['POST'])
def explore():
    f = request.files.get('file')
    if not f:
        return "No file uploaded.", 400
    raw = f.read()
    fname = (f.filename or 'export.fhx').rsplit('.', 1)[0]
    text = db_parser.decode_fhx(raw)

    catalog = db_parser.parse_database(text)

    phase_views = {}
    if _HAS_PHASE:
        try:
            phase_views = phase_bridge.phase_view_map(text)
        except Exception:
            phase_views = {}   # explorer still works without drill-down

    fbd_views, em_views = {}, {}
    try:
        import fbd_bridge
        fbd_views = fbd_bridge.build_fbd_views(text)
    except Exception:
        fbd_views = {}
    try:
        import em_bridge
        em_views = em_bridge.build_em_views(text)
    except Exception:
        em_views = {}

    html = db_explorer.build_explorer_html(catalog, fname, phase_views=phase_views,
                                           fbd_views=fbd_views, em_views=em_views)
    return Response(html, mimetype='text/html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  DeltaV Database Explorer running at  http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=False)
