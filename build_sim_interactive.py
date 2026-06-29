"""
build_sim_interactive.py — SIMULATOR (Option 1): render the phase RUN sequence as
an SVG SFC (real DeltaV coords) and run it LIVE in the browser with the ported JS
engine (sim_eval.js + sim_engine.js). Unlike build_sim_anim.py (which baked a fixed
Python trace), here the browser owns the engine: edit a variable or hold a device
confirm and the walk re-evaluates and the path changes live.

    PYTHONPATH=$PWD python3 build_sim_interactive.py   ->  /tmp/sim_interactive.html

core/ untouched. The payload comes from sim_export.build_payload (quote-aware
transition expressions). The JS modules are inlined so the page is self-contained
and offline-safe (matches the explorer's run_local ethos).
"""
import html
import json
import os

import db_parser
import fonts
import sim_export

PHASE = os.environ.get('SIM_PHASE', 'CIP-SKD-WASH-PH')

# Watch list: operator message, phase bookkeeping, EM command/cycle, and the
# sync-unit + confirm counters that the operator interacts with.
WATCH_PREFIXES = ('^/P_MSG', '^/P_FIRST_PASS', '^/P_TASK_PTR',
                  '//#CIP_MASTER_EM#/A_COMMAND', '//#CIP_MASTER_EM#/CIP_CYCLE',
                  '//#THISUNIT#/U_CIP_SYNC_UNIT')

# Variables the operator can edit directly (label -> store key). These are the
# levers that change the path: the sync-unit assignment and first-pass flag.
EDITABLE = [
    ('Sync unit (U_CIP_SYNC_UNIT)', '//#THISUNIT#/U_CIP_SYNC_UNIT.CV', 'text'),
    ('First pass (P_FIRST_PASS)',   '^/P_FIRST_PASS.CV',                'bool'),
    ('Task pointer (P_TASK_PTR)',   '^/P_TASK_PTR.CV',                  'num'),
]


def _abbr(expr, n=52):
    e = ' '.join((expr or '').split())
    return (e[:n] + '\u2026') if len(e) > n else e


def build():
    text = db_parser.decode_fhx(open('/tmp/cip.fhx', 'rb').read())
    payload = sim_export.build_payload(text, PHASE)

    order = payload['order']
    steps = payload['steps']
    s2t = payload['s2t']
    t2s = payload['t2s']
    trans = payload['trans']

    # geometry from real DeltaV coords
    xs = [steps[n]['x'] for n in order]
    ys = [steps[n]['y'] for n in order]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    BW, BH, PAD = 150, 34, 60
    spanx = max(1, (maxx - minx))
    spany = max(1, (maxy - miny))
    DRAWW, DRAWH = 520, 2600
    sx = lambda x: PAD + (x - minx) / spanx * DRAWW
    sy = lambda y: PAD + (y - miny) / spany * DRAWH
    W = DRAWW + BW + 2 * PAD
    H = DRAWH + BH + 2 * PAD

    # edges from the real connection graph
    edges = []
    for frm in order:
        for tn in s2t.get(frm, []):
            to = t2s.get(tn)
            if to in steps:
                edges.append({'frm': frm, 'to': to, 't': tn,
                              'label': _abbr(trans.get(tn, ''))})

    node_svg = []
    for n in order:
        s = steps[n]
        x, y = sx(s['x']), sy(s['y'])
        node_svg.append(
            f'<g class="stepnode" data-step="{html.escape(n, quote=True)}">'
            f'<rect x="{x:.0f}" y="{y:.0f}" rx="7" width="{BW}" height="{BH}"/>'
            f'<text class="sn" x="{x+10:.0f}" y="{y+14:.0f}">{html.escape(n)}</text>'
            f'<text class="sd" x="{x+10:.0f}" y="{y+27:.0f}">{html.escape(s["desc"][:22])}</text></g>')

    edge_svg = []
    for e in edges:
        a, b = steps[e['frm']], steps[e['to']]
        x1, y1 = sx(a['x']) + BW / 2, sy(a['y']) + BH
        x2, y2 = sx(b['x']) + BW / 2, sy(b['y'])
        mid = (y1 + y2) / 2
        edge_svg.append(
            f'<path class="edge" data-from="{html.escape(e["frm"], quote=True)}" '
            f'data-to="{html.escape(e["to"], quote=True)}" data-t="{html.escape(e["t"], quote=True)}" '
            f'd="M{x1:.0f},{y1:.0f} L{x1:.0f},{mid:.0f} L{x2:.0f},{mid:.0f} L{x2:.0f},{y2:.0f}"/>')

    # inline the JS engine modules (strip CommonJS export tails; expose globals)
    here = os.path.dirname(os.path.abspath(__file__))
    eval_js = open(os.path.join(here, 'sim_eval.js')).read()
    engine_js = open(os.path.join(here, 'sim_engine.js')).read()

    payload_json = json.dumps(payload).replace('</', '<\\/')
    watch_prefixes_json = json.dumps(list(WATCH_PREFIXES))
    editable_json = json.dumps(EDITABLE)

    return f"""<!DOCTYPE html><html data-theme="light"><head><meta charset="utf-8">
<title>Phase Sim (interactive) \u2014 {html.escape(PHASE)}</title><style>{fonts.FONT_CSS}
*{{box-sizing:border-box}}
body{{margin:0;font-family:'IBM Plex Sans',system-ui,sans-serif;color:#16202c;background:#f6f8fb}}
.top{{display:flex;align-items:center;gap:16px;padding:12px 18px;background:#0f2030;color:#eaf1f8;border-bottom:1px solid #0b1824;position:sticky;top:0;z-index:10}}
.top h1{{font-size:15px;margin:0;font-weight:600}}
.top .sub{{color:#9db4ca;font-size:12px}}
.ctrls{{margin-left:auto;display:flex;align-items:center;gap:8px}}
button{{font-family:inherit;font-size:13px;border:1px solid #2c4358;background:#16293a;color:#eaf1f8;border-radius:8px;padding:7px 13px;cursor:pointer;font-weight:600}}
button:hover{{background:#1d3349}}
button.primary{{background:#2563eb;color:#fff;border-color:#2563eb}}
button:disabled{{opacity:.4;cursor:default}}
.wrap{{display:grid;grid-template-columns:1fr 360px;height:calc(100vh - 53px)}}
.diagram{{overflow:auto;position:relative;background:#fbfcfe}}
.side{{border-left:1px solid #dde4ec;background:#fff;overflow:auto;padding:14px 16px}}
.side h3{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#7689a0;margin:18px 0 8px;font-weight:700}}
.side h3:first-child{{margin-top:2px}}
.msg{{font-size:15px;font-weight:600;color:#1d4ed8;min-height:22px;line-height:1.3}}
.nowstep{{font-family:'IBM Plex Mono';font-size:13px;color:#16202c;margin-top:3px}}
.status{{font-family:'IBM Plex Mono';font-size:12px;margin-top:4px;padding:4px 8px;border-radius:6px;display:inline-block}}
.status.running{{background:#eff6ff;color:#1d4ed8}}
.status.waiting{{background:#fef3c7;color:#92400e}}
.status.done{{background:#ecfdf5;color:#047857}}
.edit{{display:grid;grid-template-columns:1fr auto;gap:8px 10px;align-items:center;font-size:12px}}
.edit label{{color:#46566b;font-family:'IBM Plex Mono';font-size:11px}}
.edit input[type=text],.edit input[type=number]{{font-family:'IBM Plex Mono';font-size:12px;border:1px solid #c7d2de;border-radius:6px;padding:4px 7px;width:130px}}
.edit input[type=checkbox]{{width:16px;height:16px}}
.hint{{font-size:11px;color:#7689a0;margin:6px 0 0;line-height:1.4}}
.confirms{{font-size:12px;font-family:'IBM Plex Mono';max-height:160px;overflow:auto;border:1px solid #eef2f7;border-radius:8px;padding:6px}}
.confirms .row{{display:grid;grid-template-columns:1fr auto;gap:6px;align-items:center;padding:2px 0}}
.confirms .row.held{{color:#b45309;font-weight:600}}
.confirms button{{font-size:10px;padding:2px 8px;background:#fff;color:#16202c;border:1px solid #c7d2de}}
.confirms button.heldbtn{{background:#fde68a;border-color:#f59e0b}}
.wv{{display:grid;grid-template-columns:1fr auto;gap:4px 10px;font-size:12px;font-family:'IBM Plex Mono'}}
.wv .k{{color:#46566b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.wv .v{{font-weight:600;text-align:right}}
.wv .v.chg{{color:#1d4ed8}}
.tape{{font-size:12px;font-family:'IBM Plex Mono';line-height:1.7;max-height:220px;overflow:auto}}
.tape .e{{color:#7689a0}}.tape .cur{{color:#1d4ed8;font-weight:700}}
.tape .wait{{color:#b45309}}
rect{{fill:#fff;stroke:#c7d2de;stroke-width:1.4}}
.stepnode .sn{{font:600 11px 'IBM Plex Mono';fill:#16202c}}
.stepnode .sd{{font:10px 'IBM Plex Sans';fill:#7689a0}}
.stepnode.visited rect{{stroke:#94a3b8}}
.stepnode.active rect{{fill:#2563eb;stroke:#2563eb}}
.stepnode.active .sn,.stepnode.active .sd{{fill:#fff}}
.stepnode.done rect{{fill:#ecfdf5;stroke:#10b981}}
.stepnode.waiting rect{{fill:#fef3c7;stroke:#f59e0b}}
.edge{{fill:none;stroke:#cbd5e1;stroke-width:1.4}}
.edge.hot{{stroke:#2563eb;stroke-width:2.6}}
.edge.taken{{stroke:#10b981;stroke-width:2}}
</style></head><body>
<div class="top">
  <div><h1>Phase Sequence Simulator <span class="sub">\u2014 {html.escape(PHASE)} \u00b7 interactive</span></h1>
  <div class="sub">Live engine in-browser \u00b7 edit a variable or hold a confirm and the path re-walks</div></div>
  <div class="ctrls">
    <button id="reset">\u27f2 Reset</button>
    <button id="step">Step \u2192</button>
    <button id="play" class="primary">\u25b6 Play</button>
    <span class="sub" id="pos"></span>
  </div>
</div>
<div class="wrap">
  <div class="diagram"><svg id="svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
    <g id="edges">{''.join(edge_svg)}</g><g id="nodes">{''.join(node_svg)}</g></svg></div>
  <div class="side">
    <h3>Status</h3>
    <div class="nowstep" id="now">idle</div>
    <span class="status running" id="status">ready</span>
    <h3>Operator message (P_MSG1)</h3><div class="msg" id="msg">\u2014</div>
    <h3>Operator inputs</h3>
    <div class="edit" id="editpanel"></div>
    <p class="hint">Changing an input reseeds and re-walks from the start. The sync unit drives the S0000 branch; hold a confirm below to stall a step mid-walk.</p>
    <h3>Device confirms (tie-backs)</h3>
    <div class="confirms" id="confirms"></div>
    <p class="hint">Each step advances when its PENDING_CONFIRMS = 0. Hold one non-zero to simulate a device that hasn't reached target \u2014 the walk waits there.</p>
    <h3>Variable watch</h3><div class="wv" id="watch"></div>
    <h3>Walk tape</h3><div class="tape" id="tape"></div>
  </div>
</div>
<script>
{eval_js}
</script>
<script>
{engine_js}
</script>
<script>
const PAYLOAD = {payload_json};
const WATCH_PREFIXES = {watch_prefixes_json};
const EDITABLE = {editable_json};

// operator-controlled overrides + confirm holds, applied on every (re)seed
const overrides = {{ '//#THISUNIT#/U_CIP_SYNC_UNIT.CV': 'CIP_UNIT_01' }};
const heldConfirms = {{}};   // stepKey -> held value (non-zero)

let sim = null, traceIdx = -1, timer = null;

function buildOverrides(){{
  const o = Object.assign({{}}, overrides);
  for(const k in heldConfirms){{ o[k] = heldConfirms[k]; }}
  return o;
}}

function rewalk(){{
  sim = new SimEngine.PhaseSim(PAYLOAD, {{ overrides: buildOverrides() }});
  sim.run();
  traceIdx = sim.trace.length - 1;   // land on final state after a full re-walk
  render();
}}

function watchPrefixed(store){{
  const w = {{}};
  for(const k in store){{
    for(const p of WATCH_PREFIXES){{ if(k.indexOf(p)===0){{ w[k]=store[k]; break; }} }}
  }}
  return w;
}}

// reconstruct visual + side state up to traceIdx
let prevWatch = {{}};
function render(){{
  document.querySelectorAll('.stepnode').forEach(n=>n.classList.remove('active','visited','done','waiting'));
  document.querySelectorAll('.edge').forEach(e=>e.classList.remove('hot','taken'));

  let lastEnter=null, msg='\u2014', watch={{}}, tape='', store={{}};
  const T = sim.trace;
  for(let k=0;k<=traceIdx && k<T.length;k++){{
    const ev=T[k];
    if(ev.kind==='enter'){{
      lastEnter=ev.step; store=ev.store; msg=(store['^/P_MSG1.CV']||msg); watch=watchPrefixed(store);
      const nd=document.querySelector('.stepnode[data-step="'+cssq(ev.step)+'"]');
      if(nd) nd.classList.add('visited','done');
      tape += '<div class="e'+(k===traceIdx?' cur':'')+'">\u25b8 '+ev.step+'  '+(ev.desc||'')+'</div>';
    }} else {{
      tape += '<div class="e'+(k===traceIdx?' cur':'')+'">  \u2514 '+ev.t+' \u2192 '+ev.to+'</div>';
      const p=document.querySelector('.edge[data-from="'+cssq(ev.from)+'"][data-to="'+cssq(ev.to)+'"]');
      if(p){{ p.classList.add('taken'); if(k===traceIdx) p.classList.add('hot'); }}
    }}
  }}

  // determine end status from the log tail
  const tail = sim.log[sim.log.length-1] || '';
  let statusCls='running', statusTxt='running';
  if(tail.indexOf('waiting')>=0){{ statusCls='waiting'; statusTxt='waiting \u2014 condition not met'; }}
  else if(tail.indexOf('terminal')>=0){{ statusCls='done'; statusTxt='sequence complete'; }}

  if(lastEnter){{
    const nd=document.querySelector('.stepnode[data-step="'+cssq(lastEnter)+'"]');
    if(nd){{ nd.classList.remove('done'); nd.classList.add(statusCls==='waiting'?'waiting':'active'); nd.scrollIntoView({{block:'center',behavior:'smooth'}}); }}
  }}

  document.getElementById('msg').textContent = msg;
  document.getElementById('now').textContent = lastEnter ? ('at '+lastEnter) : 'idle';
  const st=document.getElementById('status'); st.className='status '+statusCls; st.textContent=statusTxt;
  renderWatch(watch);
  document.getElementById('tape').innerHTML = tape || '<div class="e">\u2014</div>';
  document.getElementById('pos').textContent = (traceIdx+1)+' / '+T.length;
  prevWatch = watch;
}}

function renderWatch(w){{
  const el=document.getElementById('watch'); el.innerHTML='';
  Object.keys(w).sort().forEach(k=>{{
    const sk=k.replace('//#CIP_MASTER_EM#/','EM:').replace('//#THISUNIT#/','U:').replace('^/','');
    const chg = String(w[k])!==String(prevWatch[k]) ? ' chg' : '';
    el.insertAdjacentHTML('beforeend',
      '<div class="k" title="'+esc(k)+'">'+esc(sk)+'</div><div class="v'+chg+'">'+esc(String(w[k]))+'</div>');
  }});
}}

function cssq(s){{ return String(s).replace(/"/g,'\\\\"'); }}
function esc(s){{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}

// ── operator inputs ──────────────────────────────────────────────────────────
function buildEditPanel(){{
  const el=document.getElementById('editpanel'); el.innerHTML='';
  EDITABLE.forEach(([label,key,kind])=>{{
    const id='ed_'+key.replace(/[^A-Za-z0-9]/g,'_');
    let cur = (key in overrides) ? overrides[key] : (PAYLOAD.seed[key]);
    if(cur===undefined||cur===null) cur = (kind==='bool'?false:(kind==='num'?0:''));
    let input;
    if(kind==='bool') input='<input type="checkbox" id="'+id+'" '+(truthy(cur)?'checked':'')+'>';
    else if(kind==='num') input='<input type="number" id="'+id+'" value="'+esc(String(cur))+'">';
    else input='<input type="text" id="'+id+'" value="'+esc(String(cur))+'">';
    el.insertAdjacentHTML('beforeend','<label title="'+esc(key)+'">'+esc(label)+'</label>'+input);
    const node=document.getElementById(id);
    node.addEventListener('change',()=>{{
      let v;
      if(kind==='bool') v=node.checked;
      else if(kind==='num') v=parseFloat(node.value)||0;
      else v=node.value;
      overrides[key]=v;
      stopPlay(); rewalk();
    }});
  }});
}}
function truthy(v){{ return v===true || v==='True' || (typeof v==='number'&&v!==0) || (typeof v==='string'&&v!=='' && v!=='0' && v!=='False'); }}

function buildConfirmPanel(){{
  const el=document.getElementById('confirms'); el.innerHTML='';
  PAYLOAD.order.forEach(stepKey=>{{
    const ckey = stepKey+'/PENDING_CONFIRMS.CV';
    const held = (ckey in heldConfirms);
    el.insertAdjacentHTML('beforeend',
      '<div class="row'+(held?' held':'')+'"><span>'+esc(stepKey)+'</span>'+
      '<button class="'+(held?'heldbtn':'')+'" data-ckey="'+esc(ckey)+'">'+(held?'held \u25cf':'hold')+'</button></div>');
  }});
  el.querySelectorAll('button').forEach(b=>{{
    b.addEventListener('click',()=>{{
      const ck=b.dataset.ckey;
      if(ck in heldConfirms) delete heldConfirms[ck];
      else heldConfirms[ck]=1;       // non-zero = device not yet confirmed
      stopPlay(); buildConfirmPanel(); rewalk();
    }});
  }});
}}

// ── transport ────────────────────────────────────────────────────────────────
function stepFwd(){{ if(traceIdx<sim.trace.length-1){{ traceIdx++; render(); }} if(traceIdx>=sim.trace.length-1) stopPlay(); }}
function stopPlay(){{ if(timer){{ clearInterval(timer); timer=null; document.getElementById('play').textContent='\u25b6 Play'; }} }}

document.getElementById('step').onclick=()=>{{ stopPlay(); stepFwd(); }};
document.getElementById('reset').onclick=()=>{{ stopPlay(); traceIdx=-1; prevWatch={{}}; render(); }};
document.getElementById('play').onclick=function(){{
  if(timer){{ stopPlay(); return; }}
  if(traceIdx>=sim.trace.length-1) traceIdx=-1;
  this.textContent='\u23f8 Pause';
  timer=setInterval(stepFwd,700);
}};

buildEditPanel();
buildConfirmPanel();
rewalk();
traceIdx=-1; prevWatch={{}}; render();   // start idle; press Play/Step to walk
</script>
</body></html>"""


if __name__ == '__main__':
    open('/tmp/sim_interactive.html', 'w').write(build())
    print('wrote /tmp/sim_interactive.html')
