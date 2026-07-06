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
from flask import Flask, request, send_file, Response, abort, jsonify

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
.prog{margin-top:16px;display:none}
.prog.on{display:block}
.prog .bar{height:12px;border-radius:8px;background:var(--border);overflow:hidden;position:relative;box-shadow:inset 0 1px 2px rgba(0,0,0,.08)}
.prog .fill{height:100%;width:0;border-radius:8px;transition:width .2s ease;background:linear-gradient(90deg,var(--accent),#7c9cff,#a78bfa,var(--accent));background-size:250% 100%;animation:dvshimmer 1.4s linear infinite;box-shadow:0 0 8px rgba(124,124,255,.5)}
.prog.indet .fill{width:40%;border-radius:6px;animation:dvslide 1.1s ease-in-out infinite,dvshimmer 1.6s linear infinite}
@keyframes dvslide{0%{margin-left:-40%}100%{margin-left:100%}}
@keyframes dvshimmer{to{background-position:-200% 0}}
.prog .lbl{margin-top:8px;font-size:12px;color:var(--ink-2);text-align:center;font-family:'IBM Plex Mono'}
.prog .lbl .pct{color:var(--ink);font-weight:600}
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
    <div class="prog" id="prog">
      <div class="bar"><div class="fill" id="fill"></div></div>
      <div class="lbl" id="plbl"><span class="pct" id="ppct">0%</span> uploading…</div>
    </div>
  </form>
  <div class="divider"></div>
  <div class="note">Large exports (e.g. a full area, 30&nbsp;MB) may take a minute to parse.</div>
  <div class="note" style="margin-top:8px">Need to convert instead?
    <a href="/tool/">Open the FHX Converter &rarr;</a></div>
</div>
<script>
var fi=document.getElementById('file'),fn=document.getElementById('fn'),btn=document.getElementById('btn');
// meaningful, moving status during the (signal-less) server parse phase: cycle through
// the real stages the parser goes through so the wait feels informative, not stuck.
var _parseTimer=null;
function startParseStages(plbl){
  var stages=[
    'Decoding the FHX export…',
    'Indexing control modules & EM classes…',
    'Parsing SFC steps and transitions…',
    'Resolving instances and I/O wiring…',
    'Building recipe hierarchy & deferrals…',
    'Rendering the explorer…'
  ];
  var i=0;
  function tick(){
    plbl.innerHTML='<span class="pct">Parsing</span> '+stages[Math.min(i,stages.length-1)];
    i++;
  }
  tick();
  if(_parseTimer) clearInterval(_parseTimer);
  _parseTimer=setInterval(function(){ if(i>=stages.length){ i=stages.length-1; } tick(); }, 1400);
}
fi.addEventListener('change',function(){ if(fi.files.length){fn.textContent=fi.files[0].name;btn.disabled=false;} });
var drop=document.getElementById('drop');
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.style.borderColor='var(--accent)';}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.style.borderColor='';}));
drop.addEventListener('drop',ev=>{if(ev.dataTransfer.files.length){fi.files=ev.dataTransfer.files;fn.textContent=ev.dataTransfer.files[0].name;btn.disabled=false;}});
document.getElementById('f').addEventListener('submit',function(ev){
  ev.preventDefault();
  if(!fi.files.length) return;
  var prog=document.getElementById('prog'), fill=document.getElementById('fill'),
      ppct=document.getElementById('ppct'), plbl=document.getElementById('plbl');
  btn.disabled=true; btn.textContent='Opening…';
  prog.classList.add('on'); prog.classList.remove('indet');
  fill.style.width='0'; ppct.textContent='0%';
  var xhr=new XMLHttpRequest();
  xhr.open('POST','/explore',true);
  // upload phase: real byte progress
  xhr.upload.addEventListener('progress',function(e){
    if(e.lengthComputable){
      var p=Math.round(e.loaded/e.total*100);
      fill.style.width=p+'%'; ppct.textContent=p+'%';
      if(p>=100){ // upload done -> server is now parsing (no granular signal)
        prog.classList.add('indet');
        startParseStages(plbl);
      }
    }
  });
  xhr.addEventListener('load',function(){
    if(_parseTimer) clearInterval(_parseTimer);
    if(xhr.status===200){
      plbl.innerHTML='<span class="pct">Done</span> — loading explorer…';
      // replace the whole document with the returned explorer HTML
      document.open(); document.write(xhr.responseText); document.close();
    } else if(xhr.status===502||xhr.status===504){
      prog.classList.remove('indet');
      fill.style.background='#dc2626'; fill.style.width='100%';
      plbl.innerHTML='<span class="pct" style="color:#dc2626">Error '+xhr.status+'</span> — the server timed out parsing this file.';
      btn.disabled=false; btn.textContent='Open in Explorer';
    } else {
      // the server returns a readable error PAGE naming the real exception —
      // show it so the actual cause is visible rather than a generic message.
      var body=xhr.responseText||'';
      if(body.indexOf('<')>=0 && body.length>40){
        document.open(); document.write(body); document.close();
      } else {
        prog.classList.remove('indet');
        fill.style.background='#dc2626'; fill.style.width='100%';
        plbl.innerHTML='<span class="pct" style="color:#dc2626">Error '+xhr.status+'</span> — '+
          (body?body.slice(0,300):'could not parse this export.');
        btn.disabled=false; btn.textContent='Open in Explorer';
      }
    }
  });
  xhr.addEventListener('error',function(){
    prog.classList.remove('indet');
    fill.style.background='#dc2626'; fill.style.width='100%';
    plbl.innerHTML='<span class="pct" style="color:#dc2626">Network error</span> — upload failed.';
    btn.disabled=false; btn.textContent='Open in Explorer';
  });
  var fd=new FormData(); fd.append('file', fi.files[0]);
  xhr.send(fd);
});
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
    page = UPLOAD_PAGE.replace('<style>', '<style>' + fonts.FONT_CSS, 1)
    try:
        import rail
        page = rail.inject(page, active='explorer', fixed=True)
    except Exception:
        pass  # landing page still works without the rail
    return page


@app.route('/explore', methods=['POST'])
def explore():
    import time
    f = request.files.get('file')
    if not f:
        return "No file uploaded.", 400
    raw = f.read()
    fname = (f.filename or 'export.fhx').rsplit('.', 1)[0]

    try:
        text = db_parser.decode_fhx(raw)
    except Exception as e:
        app.logger.exception('decode failed')
        return _explore_error('Could not decode the file', e, fname), 500

    return _render_explore(text, fname)


@app.route('/append', methods=['POST'])
def append():
    """Merge a second FHX (e.g. a recipe) on top of an already-imported export,
    keeping the original intact. The two exports' block text is concatenated so the
    combined database parses as one. Duplicate top-level blocks (same TYPE+NAME) are
    handled per `mode`: 'skip' keeps the original block, 'overwrite' keeps the new one.
    Requires the existing export token (so we can read the stashed original)."""
    import time
    token = request.form.get('token', '')
    mode = request.form.get('mode', 'skip')  # 'skip' | 'overwrite'
    f = request.files.get('file')
    if not f:
        return "No file uploaded.", 400
    base = _read_stash(token)
    if not base:
        # stash expired (the free host may have restarted). Accept an uploaded base
        # file as a fallback so the user can still merge without losing work.
        bf = request.files.get('base')
        if bf:
            try:
                base = db_parser.decode_fhx(bf.read())
            except Exception as e:
                app.logger.exception('append base decode failed')
                return _explore_error('Could not decode the base file', e, 'base'), 500
        else:
            return "Original import not found or expired — please reimport the base file.", 409
    raw = f.read()
    fname = (f.filename or 'append.fhx').rsplit('.', 1)[0]
    try:
        add = db_parser.decode_fhx(raw)
    except Exception as e:
        app.logger.exception('append decode failed')
        return _explore_error('Could not decode the appended file', e, fname), 500
    try:
        merged = _merge_fhx(base, add, mode)
    except Exception as e:
        app.logger.exception('merge failed')
        return _explore_error('Could not merge the files', e, fname), 500
    # Stash the merged text and hand back a token. The browser then does a REAL GET
    # navigation to /explore_stashed?t=..., which renders exactly like a fresh page
    # load. This avoids document.write(), whose post-load script execution is quirky
    # across browsers and was leaving async-embedded views (e.g. recipes) blank.
    try:
        merged_token = _stash_fhx(merged)
    except Exception as e:
        app.logger.exception('merged stash failed')
        return _explore_error('Could not stash the merged file', e, fname), 500
    return jsonify({'ok': True, 'token': merged_token,
                    'name': fname + ' (merged)'})


@app.route('/explore_stashed')
def explore_stashed():
    """Render the explorer from an already-stashed FHX (used after /append so the
    merged view loads via a normal navigation rather than document.write)."""
    token = request.args.get('t', '')
    name = request.args.get('name', 'export') or 'export'
    text = _read_stash(token)
    if not text:
        return "That import has expired — please import the base file again.", 410
    return _render_explore(text, name)


def _merge_fhx(base, add, mode='skip'):
    """Concatenate two FHX exports into one combined database text.

    FHX is a flat sequence of top-level blocks. We drop the second file's SCHEMA/
    LOCALE preamble (keeping the base's), then append the rest. For de-duplication we
    look at top-level `KEYWORD ... NAME="..."` headers: if the same TYPE+NAME already
    exists in the base, we either skip the incoming block ('skip') or drop the base's
    copy so the incoming one wins ('overwrite')."""
    import re as _re
    # strip leading SCHEMA{...} and LOCALE{...} from the addition (base already has them)
    add_body = add
    for kw in ('SCHEMA', 'LOCALE'):
        m = _re.search(r'\b' + kw + r'\b', add_body)
        if m:
            try:
                blk = db_parser.extract_block(add_body, add_body.index('{', m.start()))
                end = add_body.index('{', m.start()) + len(blk)
                add_body = add_body[:m.start()] + add_body[end:]
            except Exception:
                pass

    # collect top-level block identities in the base (TYPE + NAME)
    def _identities(t):
        ids = set()
        for hm in _re.finditer(r'^([A-Z][A-Z_]+)\s+NAME="([^"]+)"', t, _re.M):
            ids.add((hm.group(1), hm.group(2)))
        return ids

    base_ids = _identities(base)

    # walk the addition's top-level blocks; skip/allow per dedup
    out_add = []
    # find each top-level NAMEd block header and its extent
    headers = list(_re.finditer(r'^([A-Z][A-Z_]+)\s+NAME="([^"]+)"', add_body, _re.M))
    if not headers:
        merged = base.rstrip() + "\n\n" + add_body.lstrip()
        return merged
    # if overwrite, remove clashing base blocks
    base_out = base
    if mode == 'overwrite':
        add_ids = _identities(add_body)
        for (typ, nm) in add_ids:
            bm = _re.search(r'^' + typ + r'\s+NAME="' + _re.escape(nm) + r'"', base_out, _re.M)
            if bm:
                try:
                    blk = db_parser.extract_block(base_out, base_out.index('{', bm.start()))
                    end = base_out.index('{', bm.start()) + len(blk)
                    base_out = base_out[:bm.start()] + base_out[end:]
                except Exception:
                    pass
    # build the addition, skipping clashes in skip mode
    idx = 0
    kept = []
    for i, hm in enumerate(headers):
        typ, nm = hm.group(1), hm.group(2)
        start = hm.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(add_body)
        seg = add_body[start:end]
        if mode == 'skip' and (typ, nm) in base_ids:
            continue
        kept.append(seg)
    merged = base_out.rstrip() + "\n\n" + "\n".join(kept)
    return merged



def _recipe_views_bundle(text):
    """Everything the UI needs about the recipes in an export, computed once and
    shared by the explorer render and the Recipes workspace's standalone import:
    (views, step_views, children, recs). Views carry formulas + cross-layer
    deferral maps exactly as before."""
    import recipe_bridge
    all_recs = recipe_bridge.parse_recipes(text)
    known = set(r['meta'].get('name') for r in all_recs if r['meta'].get('name'))
    children = recipe_bridge.all_step_children(all_recs)
    step_views = recipe_bridge.build_step_views(all_recs)
    by_name = {r['meta']['name']: r for r in all_recs}
    formulas_by_recipe = recipe_bridge.parse_formulas(text)
    deferral_maps = {}
    for parent in all_recs:
        proc = parent.get('procedure') or {}
        for _sn, s in (proc.get('steps') or {}).items():
            child = re.sub(r':\d+$', '', s.get('definition', ''))
            if child in by_name and child != parent['meta']['name']:
                dm = deferral_maps.setdefault(child, {})
                for d in s.get('deferred', []):
                    dm[d['name']] = d.get('deferred_to') or d['name']
    views = {}
    for rec in all_recs:
        nm = rec['meta'].get('name')
        if nm:
            views[nm] = recipe_bridge.build_recipe_html(
                rec, known_recipes=known, deferral_map=deferral_maps.get(nm, {}),
                formulas=formulas_by_recipe.get(nm, []))
    return views, step_views, children, all_recs

def _render_explore(text, fname):
    """Shared explorer render used by both /explore and /append."""
    import time
    t_start = time.time()
    try:
        catalog = db_parser.parse_database(text)
    except Exception as e:
        app.logger.exception('parse_database failed')
        return _explore_error('Could not parse the database catalog', e, fname), 500

    try:
        export_token = _stash_fhx(text)
    except Exception:
        app.logger.exception('stash failed (non-fatal)')
        export_token = ''

    # Phase views are now built lazily (per-phase, on click) via /phase_view, so a
    # large export no longer pays to render every phase up front. We embed only the
    # list of phase names the explorer can drill into.
    phase_names = []
    if _HAS_PHASE:
        try:
            phase_names = list(phase_bridge.parse_phases_from_export(text).keys())
        except Exception:
            app.logger.exception('phase name list failed (non-fatal)')
            phase_names = []

    fbd_names, em_names, param_index, expr_index = [], [], {}, []
    try:
        import fbd_bridge
        fbd_names = fbd_bridge.list_fbd_names(text)
        # NOTE: the global search index (params/exprs) is the single biggest remaining
        # cost (~2.8s on a large export) because it re-parses every FBD. We defer it to
        # a lazy /search_index fetch on first search, so /explore stays fast.
    except Exception:
        app.logger.exception('fbd names failed (non-fatal)')
        fbd_names = []
    try:
        import em_bridge
        em_names = em_bridge.list_em_names(text)
    except Exception:
        app.logger.exception('em names failed (non-fatal)')
        em_names = []

    # recipe procedure views (batch recipes) — parsed and rendered eagerly since
    # they're small and there are usually only a few per export.
    recipe_views = {}
    recipe_step_views = {}
    try:
        recipe_views, recipe_step_views, children, _recs = _recipe_views_bundle(text)
        catalog['recipe_children'] = children
    except Exception:
        app.logger.exception('recipe view failed (non-fatal)')

    # #4: resolve each deployed EM instance's member ROLES (e.g. PRESS_INLET_VLV, from
    # the EM class) to the ACTUAL deployed CM tags (e.g. FP005-HV-001) so the nav tree
    # can show the real instance under the EM rather than the class-level role name.
    em_member_maps = {}
    try:
        import em_sim_export
        deployed = catalog.get('deployed_modules', {}) or {}
        em_class_names = set(catalog.get('em_class_index', {}) or {}) or \
            set(c.get('name') for c in (catalog.get('em_classes') or []))
        for tag, d in deployed.items():
            if d.get('cls') in em_class_names:
                mm = em_sim_export.instance_member_map(text, tag)
                if mm:
                    em_member_maps[tag] = mm
    except Exception:
        app.logger.exception('em member maps failed (non-fatal)')
    catalog['em_member_maps'] = em_member_maps

    try:
        html = db_explorer.build_explorer_html(catalog, fname, phase_names=phase_names,
                                               fbd_names=fbd_names, em_names=em_names,
                                               param_index=param_index, expr_index=expr_index,
                                               export_token=export_token,
                                               recipe_views=recipe_views,
                                               recipe_step_views=recipe_step_views)
    except Exception as e:
        app.logger.exception('build_explorer_html failed')
        return _explore_error('Could not render the explorer', e, fname), 500

    app.logger.info('explore OK: %s in %.1fs (%d phases, %.1f MB out)',
                    fname, time.time() - t_start, len(phase_names), len(html) / 1e6)
    return Response(html, mimetype='text/html')


def _explore_error(what, exc, fname):
    """Return a readable error page instead of a bare 500, so the cause is visible."""
    import html as _h, traceback
    msg = _h.escape(f'{type(exc).__name__}: {exc}')
    tb = _h.escape(traceback.format_exc())
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<title>Parse error</title>'
        '<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:60px auto;'
        'padding:0 20px;color:#16202c;line-height:1.5}h1{font-size:20px}'
        '.err{background:#fef2f2;border:1px solid #fca5a5;border-radius:8px;padding:14px;'
        'font-family:monospace;font-size:13px;color:#991b1b;white-space:pre-wrap;word-break:break-word}'
        'details{margin-top:14px}summary{cursor:pointer;color:#6b7280;font-size:13px}'
        'pre{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;'
        'overflow:auto;font-size:12px;color:#334155;white-space:pre-wrap;word-break:break-word}'
        'a{color:#1d4ed8}</style></head><body>'
        f'<h1>{_h.escape(what)}</h1>'
        f'<p>The file <b>{_h.escape(fname)}</b> could not be fully processed.</p>'
        f'<div class="err">{msg}</div>'
        f'<details><summary>Show technical details</summary><pre>{tb}</pre></details>'
        '<p><a href="/">&larr; Try another file</a></p></body></html>'
    )


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


@app.route('/em_members')
def em_members():
    """Resolve an EM instance's member roles to their actual deployed CM tags (#1/#2)."""
    token = request.args.get('t', '')
    tag = request.args.get('tag', '')
    text = _read_stash(token)
    if not text:
        return jsonify({'error': 'expired', 'members': {}})
    try:
        import em_sim_export
        return jsonify({'tag': tag, 'members': em_sim_export.instance_member_map(text, tag)})
    except Exception as e:
        app.logger.exception('em_members failed')
        return jsonify({'error': str(e), 'members': {}})


@app.route('/inst_params')
def inst_params():
    """Per-instance parameter values for a deployed module tag (lazy)."""
    token = request.args.get('t', ''); tag = request.args.get('tag', '')
    text = _read_stash(token)
    if not text:
        return jsonify({'error': 'expired', 'params': []})
    try:
        return jsonify({'tag': tag, 'params': db_parser.parse_instance_params(text, tag)})
    except Exception as e:
        app.logger.exception('inst_params failed')
        return jsonify({'error': str(e), 'params': []})


@app.route('/search_index')
def search_index():
    """Build the global search index (params + expressions) on demand — deferred
    from /explore because it re-parses every FBD (~seconds on large exports)."""
    token = request.args.get('t', '')
    text = _read_stash(token)
    if not text:
        return jsonify({'error': 'expired'})
    try:
        import fbd_bridge
        ix = fbd_bridge.build_indexes(text)
        return jsonify({'params': ix['params'], 'exprs': ix['exprs']})
    except Exception as e:
        app.logger.exception('search_index failed')
        return jsonify({'params': {}, 'exprs': [], 'error': str(e)})


@app.route('/fbd_view')
def fbd_view():
    """Lazily build one CM/composite FBD view on demand (JSON: {name, html})."""
    import html as _h
    token = request.args.get('t', ''); name = request.args.get('n', '')
    text = _read_stash(token)
    if not text:
        return jsonify({'error': 'Session expired — re-open the export.'})
    try:
        import fbd_bridge
        fv = fbd_bridge.build_fbd_views(text, only=name)
        return jsonify({'name': name, 'html': fv.get(name, '')})
    except Exception as e:
        app.logger.exception('fbd_view failed')
        return jsonify({'error': _h.escape(str(e))})


@app.route('/em_view')
def em_view():
    """Lazily build one EM view on demand (JSON: {fbd, state, cms})."""
    import html as _h
    token = request.args.get('t', ''); name = request.args.get('n', '')
    text = _read_stash(token)
    if not text:
        return jsonify({'error': 'Session expired — re-open the export.'})
    try:
        import em_bridge
        ev = em_bridge.build_em_views(text, only=name)
        return jsonify(ev.get(name) or {'error': 'not found'})
    except Exception as e:
        app.logger.exception('em_view failed')
        return jsonify({'error': _h.escape(str(e))})


@app.route('/recipe_import', methods=['POST'])
def recipe_import():
    """Standalone recipe import for the Recipes workspace (like the Converter's own
    upload): parses the file in isolation — the explorer session is untouched — and
    returns the views plus a tree the client renders into the workspace list. The
    file is stashed under its own token so the workspace's Excel exports work."""
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file uploaded.'}), 400
    try:
        text = db_parser.decode_fhx(f.read())
    except Exception as e:
        app.logger.exception('recipe import decode failed')
        return jsonify({'error': f'Could not decode the file: {e}'}), 400
    try:
        views, step_views, children, recs = _recipe_views_bundle(text)
        if not recs:
            return jsonify({'error': 'No BATCH_RECIPE objects found in this file.'}), 422
        token = _stash_fhx(text)
        tree = []
        by_type = {'PROCEDURE': [], 'UNIT_PROCEDURE': [], 'OPERATION': []}
        for r in recs:
            t = (r['meta'].get('type') or 'PROCEDURE').upper()
            by_type.setdefault(t if t in by_type else 'PROCEDURE', []).append(r)
        labels = {'PROCEDURE': 'Procedures', 'UNIT_PROCEDURE': 'Unit Procedures',
                  'OPERATION': 'Operations'}
        for t in ('PROCEDURE', 'UNIT_PROCEDURE', 'OPERATION'):
            grp = by_type.get(t, [])
            if grp:
                tree.append({'cat': labels[t],
                             'items': [{'name': r['meta']['name'],
                                        'children': children.get(r['meta']['name'], [])}
                                       for r in grp]})
        return jsonify({'token': token, 'name': f.filename or 'recipes.fhx',
                        'views': views, 'step_views': step_views, 'tree': tree})
    except Exception as e:
        app.logger.exception('recipe import failed')
        return jsonify({'error': f'Could not parse recipes: {e}'}), 500


@app.route('/recipe_pfc_xlsx')
def recipe_pfc_xlsx():
    """Download the converter-style PFC report for one recipe object: Overview,
    Parameters (formulas side-by-side), Procedure walk with transitions, Deferrals."""
    token = request.args.get('t', '')
    name = request.args.get('n', '')
    text = _read_stash(token)
    if not text:
        abort(410, 'That import has expired — please reimport the base file.')
    try:
        import recipe_bridge
        formulas_by_recipe = recipe_bridge.parse_formulas(text)
        for rec in recipe_bridge.parse_recipes(text):
            if rec['meta'].get('name') == name:
                buf = recipe_bridge.build_pfc_report_xlsx(
                    rec, formulas_by_recipe.get(name, []))
                fname = re.sub(r'[^A-Za-z0-9_.-]', '_', name) + '_PFC_Report.xlsx'
                return send_file(buf, as_attachment=True, download_name=fname,
                                 mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        abort(404, 'Recipe object not found.')
    except Exception as e:
        app.logger.exception('pfc report failed')
        abort(500, f'Could not build PFC report: {e}')


@app.route('/recipe_deferrals_all_xlsx')
def recipe_deferrals_all_xlsx():
    """Download the deferrals audit for EVERY recipe object in the import as one
    workbook (one sheet per object) — the Recipes workspace's bulk export."""
    token = request.args.get('t', '')
    text = _read_stash(token)
    if not text:
        abort(410, 'That import has expired — please reimport the base file.')
    try:
        import recipe_bridge
        recs = recipe_bridge.parse_recipes(text)
        buf = recipe_bridge.build_deferrals_all_xlsx(recs)
        return send_file(buf, as_attachment=True, download_name='Recipe_Deferrals_All.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        app.logger.exception('deferrals all xlsx failed')
        abort(500, f'Could not build deferrals workbook: {e}')


@app.route('/recipe_deferrals_xlsx')
def recipe_deferrals_xlsx():
    """Download the deferrals audit for one recipe object as .xlsx, matching the
    manual DeltaV Recipe Studio audit format (Step / Parameter Name / Deferred
    Parameter), but generated automatically and covering every step."""
    token = request.args.get('t', '')
    name = request.args.get('n', '')
    text = _read_stash(token)
    if not text:
        abort(410, 'That import has expired — please reimport the base file.')
    try:
        import recipe_bridge
        for rec in recipe_bridge.parse_recipes(text):
            if rec['meta'].get('name') == name:
                rows = recipe_bridge.build_deferrals_rows(rec)
                buf = recipe_bridge.build_deferrals_xlsx(name, rows)
                fname = re.sub(r'[^A-Za-z0-9_.-]', '_', name) + '_Deferrals.xlsx'
                return send_file(buf, as_attachment=True, download_name=fname,
                                 mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        abort(404, 'Recipe object not found.')
    except Exception as e:
        app.logger.exception('deferrals xlsx failed')
        abort(500, f'Could not build deferrals report: {e}')


@app.route('/recipe_view')
def recipe_view():
    """Fallback: build a recipe's procedure view on demand (in case the embedded
    RECIPE_VIEWS is unavailable). Params: t=token, n=recipe name."""
    token = request.args.get('t', '')
    name = request.args.get('n', '')
    text = _read_stash(token)
    if not text:
        return jsonify({'error': 'expired', 'html': ''})
    try:
        import recipe_bridge
        all_recs = recipe_bridge.parse_recipes(text)
        known = set(r['meta'].get('name') for r in all_recs if r['meta'].get('name'))
        formulas_by_recipe = recipe_bridge.parse_formulas(text)
        for rec in all_recs:
            if rec['meta'].get('name') == name or not name:
                return jsonify({'name': rec['meta'].get('name'),
                                'html': recipe_bridge.build_recipe_html(
                                    rec, known_recipes=known,
                                    formulas=formulas_by_recipe.get(rec['meta'].get('name'), []))})
        return jsonify({'error': 'not found', 'html': ''})
    except Exception as e:
        app.logger.exception('recipe_view failed')
        return jsonify({'error': str(e), 'html': ''})


@app.route('/em_sim')
def em_sim():
    """Build a single EM command's SFC with the simulator injected, so command-driven
    EMs can be walked like phases (#11). Params: t=token, e=em_name, c=command_name."""
    import html as _h
    token = request.args.get('t', '')
    em = request.args.get('e', '')
    cmd = request.args.get('c', '')
    tag = request.args.get('tag', '')
    text = _read_stash(token)
    if not text:
        return Response('<p>Session expired — please re-open the export.</p>', mimetype='text/html')
    try:
        import em_sim_export
        if not cmd:
            # no command specified: return the list of commands as JSON
            return jsonify({'em': em, 'commands': em_sim_export.list_em_commands(text, em)})
        view = em_sim_export.build_em_command_sim_view(text, em, cmd, tag=tag)
        if not view:
            return Response(f'<p>Command "{_h.escape(cmd)}" not found in {_h.escape(em)}.</p>',
                            mimetype='text/html')
        return Response(view, mimetype='text/html')
    except Exception as e:
        app.logger.exception('em_sim failed')
        return Response(f'<p>Could not build EM simulation: {_h.escape(str(e))}</p>', mimetype='text/html')


@app.route('/studio_view')
def studio_view():
    """Build the Studio deep-view payload for one object (phase to start)."""
    token = request.args.get('t', '')
    name = request.args.get('n', '')
    text = _read_stash(token)
    if not text:
        return jsonify({'error': 'Session expired — re-open the export.'})
    try:
        import studio_bridge
        return jsonify(studio_bridge.build_phase_studio(text, name))
    except Exception as e:
        app.logger.exception('studio_view failed')
        return jsonify({'error': str(e)})


@app.route('/phase_view')
def phase_view():
    """Lazily build a single phase's interactive view on demand, so /explore
    doesn't have to build every phase up front (the big cost on large exports)."""
    import html as _h
    token = request.args.get('t', '')
    name = request.args.get('p', '')
    text = _read_stash(token)
    if not text:
        return Response('<p>Session expired — please re-open the export.</p>', mimetype='text/html')
    if not _HAS_PHASE:
        return Response('<p>Phase view unavailable.</p>', mimetype='text/html')
    try:
        vm = phase_bridge.phase_view_map(text, only=name)
        htmlv = vm.get(name)
        if not htmlv:
            return Response(f'<p>Phase "{_h.escape(name)}" not found.</p>', mimetype='text/html')
        return Response(htmlv, mimetype='text/html')
    except Exception as e:
        app.logger.exception('phase_view failed')
        return Response(f'<p>Could not build phase view: {_h.escape(str(e))}</p>', mimetype='text/html')


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
