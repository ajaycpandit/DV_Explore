"""
build_sim_anim.py — SIMULATOR SPIKE (option A): render the phase RUN sequence as
an SVG SFC (using DeltaV's real step coordinates) and animate the sim_run walk
through it in the browser: active-step highlight, transition firing, an operator-
message ticker, and a per-step variable-change watch. Self-contained HTML.

    PYTHONPATH=$PWD python3 build_sim_anim.py   ->  /tmp/sim_anim.html
"""
import html
import json

import db_parser
import fonts
import sim_run

PHASE = 'CIP-SKD-WASH-PH'
WATCH_PREFIXES = ('^/P_MSG', '^/P_FIRST_PASS', '^/P_TASK_PTR',
                  '//#CIP_MASTER_EM#/A_COMMAND', '//#CIP_MASTER_EM#/CIP_CYCLE')


def _abbr(expr, n=46):
    e = ' '.join((expr or '').split())
    return (e[:n] + '…') if len(e) > n else e


def build():
    text = db_parser.decode_fhx(open('/tmp/cip.fhx', 'rb').read())
    sim = sim_run.PhaseSim(text, PHASE)
    sim.store['//#THISUNIT#/U_CIP_SYNC_UNIT.CV'] = 'CIP_UNIT_01'   # operator assigns sync unit
    sim.run()

    # geometry
    steps = {n: {'name': n, 'desc': sim.steps[n].get('description', ''),
                 'x': sim.steps[n]['x'], 'y': sim.steps[n]['y']} for n in sim.order}
    xs = [s['x'] for s in steps.values()]
    ys = [s['y'] for s in steps.values()]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    BW, BH, PAD = 150, 34, 60
    sx = lambda x: PAD + (x - minx) / max(1, (maxx - minx)) * 520
    sy = lambda y: PAD + (y - miny) / max(1, (maxy - miny)) * 2600
    W = 520 + BW + 2 * PAD
    H = 2600 + BH + 2 * PAD

    edges = []
    for frm in sim.order:
        for tn in sim.s2t.get(frm, []):
            to = sim.t2s.get(tn)
            to = to[0] if isinstance(to, list) else to
            if to in steps:
                edges.append({'frm': frm, 'to': to, 't': tn,
                              'label': _abbr(sim.trans.get(tn, ''))})

    # svg nodes/edges
    node_svg = []
    for n, s in steps.items():
        x, y = sx(s['x']), sy(s['y'])
        node_svg.append(
            f'<g class="stepnode" data-step="{n}">'
            f'<rect x="{x:.0f}" y="{y:.0f}" rx="7" width="{BW}" height="{BH}"/>'
            f'<text class="sn" x="{x+10:.0f}" y="{y+14:.0f}">{n}</text>'
            f'<text class="sd" x="{x+10:.0f}" y="{y+27:.0f}">{html.escape(s["desc"][:22])}</text></g>')
    edge_svg = []
    for e in edges:
        a, b = steps[e['frm']], steps[e['to']]
        x1, y1 = sx(a['x']) + BW / 2, sy(a['y']) + BH
        x2, y2 = sx(b['x']) + BW / 2, sy(b['y'])
        mid = (y1 + y2) / 2
        edge_svg.append(
            f'<path class="edge" data-from="{e["frm"]}" data-to="{e["to"]}" '
            f'd="M{x1:.0f},{y1:.0f} L{x1:.0f},{mid:.0f} L{x2:.0f},{mid:.0f} L{x2:.0f},{y2:.0f}"/>')

    # compact trace: per enter, the changed watch-vars (diff) + operator message
    trace, prev = [], {}
    for ev in sim.trace:
        if ev['kind'] == 'enter':
            cur = ev['store']
            diff = {k: cur[k] for k in cur
                    if str(cur.get(k)) != str(prev.get(k))}
            watch = {k: cur.get(k) for k in cur if k.startswith(WATCH_PREFIXES)}
            trace.append({'kind': 'enter', 'step': ev['step'], 'desc': ev['desc'],
                          'msg': cur.get('^/P_MSG1.CV', ''),
                          'nchg': len(diff), 'watch': watch})
            prev = cur
        else:
            trace.append({'kind': 'fire', 't': ev['t'], 'frm': ev['from'], 'to': ev['to']})

    data = json.dumps({'trace': trace}).replace('</', '<\\/')

    return f"""<!DOCTYPE html><html data-theme="light"><head><meta charset="utf-8">
<title>Phase Sim — {PHASE}</title><style>{fonts.FONT_CSS}
*{{box-sizing:border-box}}
body{{margin:0;font-family:'IBM Plex Sans',system-ui,sans-serif;color:#16202c;background:#f6f8fb}}
.top{{display:flex;align-items:center;gap:16px;padding:12px 18px;background:#fff;border-bottom:1px solid #dde4ec;position:sticky;top:0;z-index:10}}
.top h1{{font-size:15px;margin:0}}.top .sub{{color:#46566b;font-size:12px}}
.ctrls{{margin-left:auto;display:flex;align-items:center;gap:8px}}
button{{font-family:inherit;font-size:13px;border:1px solid #c7d2de;background:#fff;border-radius:8px;padding:7px 13px;cursor:pointer;font-weight:600}}
button.primary{{background:#1d4ed8;color:#fff;border-color:#1d4ed8}}
button:disabled{{opacity:.45;cursor:default}}
.wrap{{display:grid;grid-template-columns:1fr 340px;height:calc(100vh - 53px)}}
.diagram{{overflow:auto;position:relative}}
.side{{border-left:1px solid #dde4ec;background:#fff;overflow:auto;padding:14px 16px}}
.side h3{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#7689a0;margin:18px 0 8px}}
.msg{{font-size:15px;font-weight:600;color:#1d4ed8;min-height:22px;line-height:1.3}}
.nowstep{{font-family:'IBM Plex Mono';font-size:13px;color:#16202c;margin-top:3px}}
.wv{{display:grid;grid-template-columns:1fr auto;gap:4px 10px;font-size:12px;font-family:'IBM Plex Mono'}}
.wv .k{{color:#46566b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.wv .v{{font-weight:600;text-align:right}}
.tape{{font-size:12px;font-family:'IBM Plex Mono';line-height:1.7}}
.tape .e{{color:#7689a0}}.tape .cur{{color:#1d4ed8;font-weight:700}}
rect{{fill:#fff;stroke:#c7d2de;stroke-width:1.4}}
.stepnode .sn{{font:600 11px 'IBM Plex Mono';fill:#16202c}}
.stepnode .sd{{font:10px 'IBM Plex Sans';fill:#7689a0}}
.stepnode.visited rect{{stroke:#94a3b8}}
.stepnode.active rect{{fill:#1d4ed8;stroke:#1d4ed8}}
.stepnode.active .sn,.stepnode.active .sd{{fill:#fff}}
.stepnode.done rect{{fill:#ecfdf5;stroke:#10b981}}
.edge{{fill:none;stroke:#cbd5e1;stroke-width:1.4}}
.edge.hot{{stroke:#1d4ed8;stroke-width:2.6}}
.badge{{display:inline-block;background:#10b981;color:#fff;font-size:10px;padding:1px 7px;border-radius:10px;margin-left:6px}}
</style></head><body>
<div class="top"><div><h1>Phase Sequence Simulator <span class="sub">— {PHASE} (RUN logic)</span></h1>
<div class="sub">Spike: stepping the real SFC with the DeltaV expression evaluator · sync unit assigned, devices auto-confirm</div></div>
<div class="ctrls">
  <button id="reset">⟲ Reset</button>
  <button id="step">Step →</button>
  <button id="play" class="primary">▶ Play</button>
  <span class="sub" id="pos"></span>
</div></div>
<div class="wrap">
  <div class="diagram"><svg id="svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
    <g id="edges">{''.join(edge_svg)}</g><g id="nodes">{''.join(node_svg)}</g></svg></div>
  <div class="side">
    <h3>Operator message (P_MSG1)</h3><div class="msg" id="msg">—</div>
    <div class="nowstep" id="now">idle</div>
    <h3>Variable watch</h3><div class="wv" id="watch"></div>
    <h3>Walk tape</h3><div class="tape" id="tape"></div>
  </div>
</div>
<script>
const D={data}, T=D.trace;
let i=-1, timer=null;
const svg=document.getElementById('svg');
function nodes(){{return {{}};}}
function clearHot(){{document.querySelectorAll('.edge.hot').forEach(e=>e.classList.remove('hot'));}}
function setActive(step){{
  document.querySelectorAll('.stepnode.active').forEach(n=>{{n.classList.remove('active');n.classList.add('done');}});
  const n=document.querySelector('.stepnode[data-step="'+step+'"]');
  if(n){{n.classList.add('active','visited');n.scrollIntoView({{block:'center',behavior:'smooth'}});}}
}}
function renderWatch(w){{
  const el=document.getElementById('watch'); el.innerHTML='';
  Object.keys(w).sort().forEach(k=>{{
    const sk=k.replace('//#CIP_MASTER_EM#/','EM:').replace('^/','');
    el.innerHTML+='<div class="k" title="'+k+'">'+sk+'</div><div class="v">'+String(w[k])+'</div>';
  }});
}}
function apply(idx){{
  // rebuild visual state up to idx (so Reset/Step/scrub stay consistent)
  document.querySelectorAll('.stepnode').forEach(n=>n.classList.remove('active','visited','done'));
  clearHot();
  let lastEnter=null, msg='—', watch={{}}, tape='';
  for(let k=0;k<=idx;k++){{
    const ev=T[k];
    if(ev.kind==='enter'){{ lastEnter=ev.step; msg=ev.msg||msg; watch=ev.watch||watch;
      const nd=document.querySelector('.stepnode[data-step="'+ev.step+'"]'); if(nd)nd.classList.add('visited','done');
      tape+='<div class="e'+(k===idx?' cur':'')+'">▸ '+ev.step+'  '+(ev.desc||'')+'</div>'; }}
    else {{ tape+='<div class="e'+(k===idx?' cur':'')+'">  └ '+ev.t+' → '+ev.to+'</div>';
      if(k===idx){{const p=document.querySelector('.edge[data-from="'+ev.frm+'"][data-to="'+ev.to+'"]'); if(p)p.classList.add('hot');}} }}
  }}
  if(lastEnter){{const nd=document.querySelector('.stepnode[data-step="'+lastEnter+'"]'); if(nd){{nd.classList.remove('done');nd.classList.add('active');nd.scrollIntoView({{block:'center',behavior:'smooth'}});}}}}
  document.getElementById('msg').textContent=msg;
  document.getElementById('now').textContent=lastEnter?('at '+lastEnter):'idle';
  renderWatch(watch);
  document.getElementById('tape').innerHTML=tape;
  document.getElementById('pos').textContent=(idx+1)+' / '+T.length;
}}
function step(){{ if(i<T.length-1){{i++;apply(i);}} if(i>=T.length-1)stopPlay(); }}
function stopPlay(){{ if(timer){{clearInterval(timer);timer=null;document.getElementById('play').textContent='▶ Play';}} }}
document.getElementById('step').onclick=()=>{{stopPlay();step();}};
document.getElementById('reset').onclick=()=>{{stopPlay();i=-1;apply(-1);document.getElementById('msg').textContent='—';document.getElementById('now').textContent='idle';}};
document.getElementById('play').onclick=function(){{
  if(timer){{stopPlay();return;}}
  if(i>=T.length-1){{i=-1;}}
  this.textContent='⏸ Pause';
  timer=setInterval(step,700);
}};
apply(-1);
</script></body></html>"""


if __name__ == '__main__':
    open('/tmp/sim_anim.html', 'w').write(build())
    print('wrote /tmp/sim_anim.html')
