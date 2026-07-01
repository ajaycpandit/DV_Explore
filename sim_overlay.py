"""
sim_overlay.py — render the interactive simulator OVER the explorer's real SFC SVG.

Instead of drawing its own diagram (the earlier build_sim_interactive.py did), this
bridge injects a simulator overlay into the phase HTML that core/sfc_html already
produced. The overlay:
  * loads the ported engine (sim_eval.js + sim_engine.js) inline,
  * embeds the phase payload (sim_export) incl. operator-prompt metadata,
  * adds a "Simulate" panel (transport + variable edits + confirm holds + the
    operator-prompt control that appears when the walk halts at an OAR), and
  * drives the highlight by toggling classes on the EXISTING SVG elements
    (.step[data-step=...] / .trans[data-trans=...]) that core emits.

Result: the simulated diagram IS the explorer diagram, 1:1, because we never
redraw it. core/ stays byte-identical; everything is appended before </body>.

Entry point: inject(phase_html, payload) -> html with the overlay.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _read(name):
    return open(os.path.join(_HERE, name)).read()


# Highlight CSS layered on top of the explorer's own SVG styles. Scoped under
# body.sim-on so it only paints when the simulator is engaged, and uses !important
# sparingly to win over core's .step/.trans rules without editing them.
_OVERLAY_CSS = """
<style id="sim-overlay-css">
body.sim-on .step.sim-active rect{fill:#2563eb!important;stroke:#2563eb!important}
body.sim-on .step.sim-active .sid,body.sim-on .step.sim-active .sdesc{fill:#fff!important}
body.sim-on .step.sim-visited rect{stroke:#10b981!important}
body.sim-on .step.sim-done rect{fill:#ecfdf5!important;stroke:#10b981!important}
body.sim-on .step.sim-wait rect{fill:#fef3c7!important;stroke:#f59e0b!important}
body.sim-on .step.sim-prompt rect{fill:#ede9fe!important;stroke:#7c3aed!important;stroke-width:2.4!important}
body.sim-on .step.sim-timer rect{fill:#e0f2fe!important;stroke:#0284c7!important;stroke-width:2.4!important}
body.sim-on .trans.sim-taken line{stroke:#10b981!important;stroke-width:3!important}
body.sim-on .trans.sim-hot line{stroke:#2563eb!important;stroke-width:3.4!important}

/* item 5: keep the SFC +/- zoom controls visible while scrolling the diagram.
   core positions .controls absolute (scrolls away); pin to viewport, same corner. */
.controls{position:fixed!important;top:64px!important;z-index:50!important}

#sim-fab{position:fixed;right:18px;bottom:18px;z-index:60;background:#2563eb;color:#fff;
  border:none;border-radius:24px;padding:11px 18px;font:600 13px 'IBM Plex Sans',system-ui,sans-serif;
  box-shadow:0 4px 14px rgba(37,99,235,.35);cursor:pointer}

/* ── floating, draggable, resizable window ── */
#sim-win{position:fixed;right:22px;top:70px;width:370px;height:560px;min-width:300px;min-height:320px;
  z-index:9998;background:#fff;border:1px solid #cdd7e2;border-radius:12px;
  box-shadow:0 18px 50px -12px rgba(15,32,48,.34);display:none;flex-direction:column;overflow:hidden;
  font-family:'IBM Plex Sans',system-ui,sans-serif;resize:both}
#sim-win.open{display:flex}
#sim-win.min{height:auto!important;resize:none}
#sim-win.min .sim-scroll,#sim-win.min .sim-pin{display:none}

/* pinned header: title bar + transport + status + prompt — never scrolls away */
.sim-titlebar{background:#0f2030;color:#eaf1f8;padding:9px 12px;display:flex;align-items:center;gap:8px;cursor:move;user-select:none}
.sim-titlebar h2{font-size:13px;margin:0;font-weight:600;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sim-titlebar button{background:#16293a;color:#eaf1f8;border:1px solid #2c4358;border-radius:6px;
  padding:3px 8px;cursor:pointer;font-size:12px;line-height:1}
.sim-pin{background:#f8fafc;border-bottom:1px solid #e5ebf2;padding:9px 12px;flex-shrink:0}
.sim-scroll{overflow:auto;padding:12px;flex:1}
.sim-scroll h3{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#7689a0;margin:15px 0 7px;font-weight:700}
.sim-scroll h3:first-child{margin-top:0}

.sim-transport{display:flex;gap:7px}
.sim-transport button{flex:1;font:600 12px 'IBM Plex Sans';border:1px solid #c7d2de;background:#fff;
  border-radius:8px;padding:7px;cursor:pointer}
.sim-transport button.primary{background:#2563eb;color:#fff;border-color:#2563eb}
.sim-transport button:disabled{opacity:.4;cursor:default}
.sim-topline{display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap}
.sim-status{font:12px 'IBM Plex Mono';padding:4px 9px;border-radius:6px;display:inline-block}
.sim-status.run{background:#eff6ff;color:#1d4ed8}.sim-status.wait{background:#fef3c7;color:#92400e}
.sim-status.done{background:#ecfdf5;color:#047857}.sim-status.prompt{background:#ede9fe;color:#6d28d9}
.sim-status.timer{background:#e0f2fe;color:#0369a1}
.sim-pos{font:11px 'IBM Plex Mono';color:#7689a0}
.sim-nowstep{font:12px 'IBM Plex Mono';color:#16202c;margin-top:5px}
.sim-msg{font-size:13px;font-weight:600;color:#1d4ed8;min-height:18px;line-height:1.35;margin-top:6px}
.sim-msg .m2{display:block;font-weight:400;font-size:12px;color:#46566b;margin-top:2px}

.sim-prompt-box{border:1.5px solid #7c3aed;border-radius:10px;padding:10px;background:#faf8ff;margin-top:8px}
.sim-prompt-box .q{font-size:13px;font-weight:600;color:#5b21b6;margin-bottom:9px;line-height:1.35}
.sim-prompt-box .btns{display:flex;gap:8px;flex-wrap:wrap}
.sim-prompt-box button{font:600 13px 'IBM Plex Sans';border:none;border-radius:8px;padding:8px 16px;cursor:pointer;background:#7c3aed;color:#fff}
.sim-prompt-box button.no{background:#fff;color:#5b21b6;border:1px solid #c4b5fd}
.sim-prompt-box .vrow{display:flex;gap:8px;align-items:center;margin-top:4px}
.sim-prompt-box input{font:13px 'IBM Plex Mono';border:1px solid #c4b5fd;border-radius:7px;padding:6px 9px;width:90px}

/* timer countdown card */
.sim-timer-box{border:1.5px solid #0284c7;border-radius:10px;padding:10px;background:#f0f9ff;margin-top:8px}
.sim-timer-box .tt{font-size:12px;font-weight:600;color:#0369a1;display:flex;justify-content:space-between;align-items:center}
.sim-timer-box .clock{font:700 20px 'IBM Plex Mono';color:#0c4a6e;margin:5px 0}
.sim-timer-box .bar{height:6px;border-radius:4px;background:#bae6fd;overflow:hidden}
.sim-timer-box .bar > i{display:block;height:100%;background:#0284c7;width:0;transition:width .25s linear}
.sim-timer-box .btns{display:flex;gap:7px;margin-top:8px}
.sim-timer-box button{font:600 12px 'IBM Plex Sans';border:1px solid #7dd3fc;background:#fff;color:#0369a1;border-radius:7px;padding:5px 11px;cursor:pointer}
.sim-timer-box button.primary{background:#0284c7;color:#fff;border-color:#0284c7}

.sim-sect{border:1px solid #e8edf3;border-radius:9px;margin-top:10px;overflow:hidden}
.sim-sect > summary{cursor:pointer;list-style:none;padding:8px 11px;background:#f6f8fb;font-size:11px;
  font-weight:700;color:#46566b;text-transform:uppercase;letter-spacing:.05em;display:flex;align-items:center;gap:6px}
.sim-sect > summary::-webkit-details-marker{display:none}
.sim-sect > summary::before{content:"\\25b8";font-size:9px;transition:.15s;color:#94a3b8}
.sim-sect[open] > summary::before{transform:rotate(90deg)}
.sim-sect .body{padding:10px 11px}

.sim-edit{display:grid;grid-template-columns:1fr auto;gap:7px 10px;align-items:center;font-size:12px}
.sim-edit label{color:#46566b;font:11px 'IBM Plex Mono'}
.sim-edit input[type=text],.sim-edit input[type=number]{font:12px 'IBM Plex Mono';border:1px solid #c7d2de;border-radius:6px;padding:4px 7px;width:120px}
.sim-hint{font-size:11px;color:#7689a0;margin:6px 0 0;line-height:1.4}
.sim-watch{display:grid;grid-template-columns:1fr auto;gap:3px 10px;font:12px 'IBM Plex Mono'}
.sim-watch .k{color:#46566b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sim-watch .v{font-weight:600;text-align:right}.sim-watch .v.chg{color:#1d4ed8}

/* bottom steps/actions list — current step highlighted, transitions shown (item 3) */
.sim-tape{font:12px 'IBM Plex Mono';line-height:1.6;max-height:260px;overflow:auto}
.sim-tape .row{padding:2px 6px;border-radius:5px}
.sim-tape .row.step{color:#334155}
.sim-tape .row.cur{background:#dbeafe;color:#1d4ed8;font-weight:700}
.sim-tape .row.tr{color:#94a3b8;padding-left:18px}
.sim-tape .row.tr.cur{background:#eef2ff;color:#4f46e5}
.sim-tape .row.pr{color:#6d28d9;font-weight:700;padding-left:12px}
.sim-tape .row.act{color:#64748b;padding-left:18px;font-size:11px}
.sim-tape .row.act.setr{color:#0369a1}.sim-tape .row.act.err{color:#dc2626}
</style>
"""

# Watch shows internal/computed state. P_ variables (phase scratch the logic
# writes) and key EM/unit feedback — never editable, just observed.
_WATCH_PREFIXES = ['^/P_MSG', '^/P_FIRST_PASS', '^/P_TASK_PTR', '^/P_COND_SNAPSHOT',
                   '^/P_', '//#CIP_MASTER_EM#/A_COMMAND', '//#THISUNIT#/U_CIP_SYNC_UNIT',
                   '^/FAIL_MONITOR/OAR/INPUT']
# A few non-R_ device/timer levers that aren't recipe parameters but the operator
# may want to force while exploring (until T2 models them). Kept separate from R_.
_DEVICE_LEVERS = [
    ['Settle timer done', '//#UNIT_SUPPORT#/TMR1/TM_COMPLETE.CV', 'bool'],
    ['Sync unit', '//#THISUNIT#/U_CIP_SYNC_UNIT.CV', 'text'],
    ['Cond. snapshot (P_, forced)', '^/P_COND_SNAPSHOT.CV', 'real'],
]


def inject(phase_html, payload):
    eval_js = _read('sim_eval.js')
    engine_js = _read('sim_engine.js')
    payload_json = json.dumps(payload).replace('</', '<\\/')
    watch_json = json.dumps(_WATCH_PREFIXES)
    levers_json = json.dumps(_DEVICE_LEVERS)
    rparams_json = json.dumps(payload.get('r_params', [])).replace('</', '<\\/')
    timers_json = json.dumps(payload.get('timers', {})).replace('</', '<\\/')
    aliases_json = json.dumps(payload.get('aliases', {})).replace('</', '<\\/')

    overlay = _OVERLAY_CSS + f"""
<button id="sim-fab" onclick="SIM.toggle()">\u25b6 Simulate</button>
<div id="sim-win">
  <div class="sim-titlebar" id="sim-drag">
    <h2>Phase Simulator</h2>
    <button onclick="SIM.minimize()" id="sim-min" title="Minimize">\u2013</button>
    <button onclick="SIM.toggle()" title="Close">\u2715</button>
  </div>
  <!-- PINNED: transport + status + operator message + prompt + timer always visible -->
  <div class="sim-pin">
    <div class="sim-transport">
      <button onclick="SIM.reset()">\u27f2 Reset</button>
      <button onclick="SIM.step()">Step \u2192</button>
      <button class="primary" id="sim-play" onclick="SIM.play()">\u25b6 Play</button>
    </div>
    <div class="sim-topline">
      <span class="sim-status run" id="sim-status">ready</span>
      <span class="sim-pos" id="sim-pos"></span>
    </div>
    <div class="sim-nowstep" id="sim-now">idle</div>
    <div class="sim-msg" id="sim-msg">\u2014</div>
    <div id="sim-prompt-host"></div>
    <div id="sim-timer-host"></div>
  </div>
  <!-- SCROLLABLE body -->
  <div class="sim-scroll">
    <details class="sim-sect" id="sim-rsect">
      <summary>Recipe parameters (R_)</summary>
      <div class="body">
        <input id="sim-rfilter" placeholder="filter R_ parameters\u2026" style="width:100%;box-sizing:border-box;font:12px 'IBM Plex Mono';border:1px solid #c7d2de;border-radius:6px;padding:5px 8px;margin-bottom:7px">
        <div class="sim-edit" id="sim-rparams"></div>
      </div>
    </details>
    <details class="sim-sect">
      <summary>Device / timer levers</summary>
      <div class="body"><div class="sim-edit" id="sim-levers"></div>
      <p class="sim-hint">Manual stand-ins for device confirms and timers until the discrete engine models them.</p></div>
    </details>
    <details class="sim-sect" open>
      <summary>Variable watch</summary>
      <div class="body"><div class="sim-watch" id="sim-watch"></div></div>
    </details>
    <h3>Steps &amp; actions</h3><div class="sim-tape" id="sim-tape"></div>
  </div>
</div>
<script>{eval_js}</script>
<script>{engine_js}</script>
<script>
(function(){{
const PAYLOAD={payload_json}, WATCH={watch_json}, LEVERS={levers_json}, RPARAMS={rparams_json};
const TIMERS={timers_json}, ALIASES={aliases_json};
const RUNKEY=PAYLOAD.seq_key;     // the RUN-sequence block this sim drives
const overrides={{}}, heldConfirms={{}}, answers={{}};
let sim=null, idx=-1, timer=null, prevWatch={{}};

function runBlockEl(){{ return document.querySelector('.block[data-k="'+cssq(RUNKEY)+'"]') || document.querySelector('.block:not(.hidden)') || document; }}
function showRunBlock(){{
  // switch the explorer to the RUN-sequence tab so highlights land on the right diagram
  try {{ if(typeof showBlock==='function') showBlock(RUNKEY); }} catch(e){{}}
}}
function gStep(s){{ return runBlockEl().querySelector('.step[data-step="'+cssq(s)+'"]'); }}
function gTrans(t){{ return runBlockEl().querySelector('.trans[data-trans="'+cssq(t)+'"]'); }}
function cssq(s){{ return String(s).replace(/"/g,'\\\\"'); }}
function esc(s){{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}

function buildOverrides(){{ const o=Object.assign({{}},overrides); for(const k in heldConfirms)o[k]=heldConfirms[k]; return o; }}
function rewalk(){{ sim=new SimEngine.PhaseSim(PAYLOAD,{{overrides:buildOverrides(),answers:answers}}); sim.run(); idx=sim.trace.length-1; render(); }}

function clearViz(){{
  runBlockEl().querySelectorAll('.step').forEach(n=>n.classList.remove('sim-active','sim-visited','sim-done','sim-wait','sim-prompt'));
  runBlockEl().querySelectorAll('.trans').forEach(e=>e.classList.remove('sim-taken','sim-hot'));
}}

function render(){{
  clearViz();
  let lastEnter=null,msg='\u2014',msg2='',watch={{}},tape='',pausedAt=null,activeActs=[];
  const T=sim.trace;
  for(let k=0;k<=idx&&k<T.length;k++){{
    const ev=T[k];
    const isCur=(k===idx);
    if(ev.kind==='enter'){{
      lastEnter=ev.step; const st=ev.store; msg=st['^/P_MSG1.CV']||msg; msg2=st['^/P_MSG2.CV']||'';
      watch=watchOf(st); activeActs=ev.active_actions||[];
      const nd=gStep(ev.step); if(nd) nd.classList.add('sim-visited','sim-done');
      tape+='<div class="row step'+(isCur?' cur':'')+'">\u25b8 '+esc(ev.step)+'  '+esc(ev.desc||'')+'</div>';
      // item 3: show this step's action outcomes indented under it
      (ev.actions||[]).forEach(a=>{{
        let cls='act', tag='';
        if(a.kind==='activated'){{cls+=' setr'; tag='SET ';}}
        else if(a.kind==='deactivated'){{cls+=' setr'; tag='RESET ';}}
        else if(a.kind==='error'){{cls+=' err'; tag='ERR ';}}
        else if(a.kind==='unmodeled'){{tag=(a.qual||'?')+' ';}}
        tape+='<div class="row '+cls+'">\u21b3 '+esc(tag)+esc(a.body||'')+'</div>';
      }});
    }} else if(ev.kind==='fire'){{
      // item 3: transitions shown in the bottom panel
      const exprAbbr=transAbbr(ev.t);
      tape+='<div class="row tr'+(isCur?' cur':'')+'">\u2514 '+esc(ev.t)+' \u2192 '+esc(ev.to)+(exprAbbr?'  <span style="opacity:.7">['+esc(exprAbbr)+']</span>':'')+'</div>';
      const p=gTrans(ev.t); if(p){{ p.classList.add('sim-taken'); if(isCur)p.classList.add('sim-hot'); }}
    }} else if(ev.kind==='prompt'){{
      pausedAt=ev; tape+='<div class="row pr'+(isCur?' cur':'')+'">\u2691 operator prompt \u2014 '+esc(ev.descr.oar_type)+'</div>';
    }}
  }}
  const tail=sim.log[sim.log.length-1]||'';
  let cls='run',txt='running';
  const atEnd=idx>=T.length-1;
  const timerHere=atEnd&&lastEnter&&TIMERS[lastEnter]&&waitingHere(tail);
  if(sim.pausedPrompt&&atEnd){{ cls='prompt'; txt='waiting for operator'; }}
  else if(timerHere){{ cls='timer'; txt='timer running'; }}
  else if(waitingHere(tail)){{ cls='wait'; txt='waiting \u2014 condition not met'; }}
  else if(tail.indexOf('terminal')>=0){{ cls='done'; txt='sequence complete'; }}

  if(lastEnter){{ const nd=gStep(lastEnter); if(nd){{ nd.classList.remove('sim-done');
    nd.classList.add(cls==='prompt'?'sim-prompt':(cls==='timer'?'sim-timer':(cls==='wait'?'sim-wait':'sim-active')));
    nd.scrollIntoView&&nd.scrollIntoView({{block:'center',behavior:'smooth'}}); }} }}

  document.getElementById('sim-now').textContent = lastEnter?('at '+lastEnter+(activeActs.length?'  \u00b7 active: '+activeActs.join(', '):'')):'idle';
  document.getElementById('sim-msg').innerHTML=esc(msg)+(msg2?'<span class="m2">'+esc(msg2)+'</span>':'');
  const s=document.getElementById('sim-status'); s.className='sim-status '+cls; s.textContent=txt;
  document.getElementById('sim-pos').textContent=(idx+1)+' / '+T.length;
  renderWatch(watch);
  renderPrompt(cls==='prompt'?sim.pausedPrompt:null);
  renderTimer(cls==='timer'?lastEnter:null);
  const tp=document.getElementById('sim-tape'); tp.innerHTML=tape||'\u2014';
  const curRow=tp.querySelector('.row.cur'); if(curRow&&curRow.scrollIntoView) curRow.scrollIntoView({{block:'nearest'}});
  prevWatch=watch;
}}

function waitingHere(tail){{ return tail.indexOf('waiting')>=0 || tail.indexOf('no outgoing')>=0; }}
function transAbbr(tn){{ const e=(PAYLOAD.trans[tn]||'').replace(/\\s+/g,' ').trim(); return e.length>46?e.slice(0,46)+'\u2026':e; }}

function watchOf(store){{ const w={{}}; for(const k in store){{ for(const p of WATCH){{ if(k.indexOf(p)===0){{w[k]=store[k];break;}} }} }} return w; }}
function renderWatch(w){{ const el=document.getElementById('sim-watch'); el.innerHTML='';
  Object.keys(w).sort().forEach(k=>{{ const sk=k.replace('//#CIP_MASTER_EM#/','EM:').replace('//#THISUNIT#/','U:').replace('^/','').replace('FAIL_MONITOR/OAR/','OAR/');
    const chg=String(w[k])!==String(prevWatch[k])?' chg':'';
    el.insertAdjacentHTML('beforeend','<div class="k" title="'+esc(k)+'">'+esc(sk)+'</div><div class="v'+chg+'">'+esc(String(w[k]))+'</div>'); }});
}}

function renderPrompt(pp){{
  const host=document.getElementById('sim-prompt-host'); host.innerHTML='';
  if(!pp) return;
  const d=pp.descr, step=pp.step;
  // Use the LIVE computed messages from the store at the moment the prompt was
  // raised (P_MSG1/P_MSG2 are built by the step's actions, e.g. "Conductivity
  // value 999 is not in range..."). Fall back to the static descriptor text.
  let lm1=null, lm2=null;
  for(let k=0;k<sim.trace.length;k++){{ const ev=sim.trace[k];
    if(ev.kind==='enter'&&ev.step===step&&ev.store){{ lm1=ev.store['^/P_MSG1.CV']; lm2=ev.store['^/P_MSG2.CV']; }} }}
  const m1=(lm1!==undefined&&lm1!==null&&lm1!=='')?lm1:(d.msg1||'Operator response required');
  const m2=(lm2!==undefined&&lm2!==null&&lm2!=='')?lm2:(d.msg2||'');
  let inner='<div class="q">'+esc(m1)+(m2?'<br><span style="font-weight:400">'+esc(m2)+'</span>':'')+'</div>';
  if(d.release==='value'){{
    if((d.oar_type||'').toLowerCase().replace(/\\s/g,'')==='yesno'){{
      inner+='<div class="btns"><button onclick="SIM.answer(\\''+esc(step)+'\\',1)">Yes</button>'+
             '<button class="no" onclick="SIM.answer(\\''+esc(step)+'\\',0)">No</button></div>';
    }} else {{
      const opts=(d.choices||[]).map(c=>'<button onclick="SIM.answer(\\''+esc(step)+'\\','+c.value+')">'+esc(c.label||String(c.value))+'</button>').join('');
      inner+='<div class="btns">'+opts+'</div>'+
             '<div class="vrow"><input id="sim-vin" type="number" placeholder="value"><button onclick="SIM.answerInput(\\''+esc(step)+'\\')">Enter</button></div>';
    }}
  }} else {{
    inner+='<div class="btns"><button onclick="SIM.answer(\\''+esc(step)+'\\',1)">OK \u2014 acknowledge</button></div>';
  }}
  host.innerHTML='<div class="sim-prompt-box">'+inner+'</div>';
}}

function widgetFor(key,kind,cur,enumMembers,id){{
  if(kind==='bool') return '<input type="checkbox" id="'+id+'" '+(truthy(cur)?'checked':'')+'>';
  if(kind==='enum' && enumMembers){{
    const opts=enumMembers.map(m=>'<option value="'+esc(String(m.value))+'"'+(String(m.value)===String(cur)?' selected':'')+'>'+esc(m.label)+'</option>').join('');
    return '<select id="'+id+'" style="font:12px \\'IBM Plex Mono\\';border:1px solid #c7d2de;border-radius:6px;padding:4px;max-width:130px">'+opts+'</select>';
  }}
  if(kind==='int'||kind==='real'||kind==='num') return '<input type="number" step="'+(kind==='real'?'any':'1')+'" id="'+id+'" value="'+esc(String(cur))+'">';
  return '<input type="text" id="'+id+'" value="'+esc(String(cur))+'">';
}}
function readWidget(node,kind){{
  if(kind==='bool') return node.checked;
  if(kind==='int') return parseInt(node.value,10)||0;
  if(kind==='real'||kind==='num') return parseFloat(node.value)||0;
  if(kind==='enum') {{ const n=Number(node.value); return isNaN(n)?node.value:n; }}
  return node.value;
}}

function buildRParams(filter){{
  const el=document.getElementById('sim-rparams'); el.innerHTML='';
  const f=(filter||'').toLowerCase();
  RPARAMS.forEach(p=>{{
    if(f && p.name.toLowerCase().indexOf(f)<0 && (p.desc||'').toLowerCase().indexOf(f)<0) return;
    const id='r_'+p.name.replace(/[^A-Za-z0-9]/g,'_');
    let cur=(p.key in overrides)?overrides[p.key]:(PAYLOAD.seed[p.key]!==undefined?PAYLOAD.seed[p.key]:p.default);
    const unit=p.units?(' <span style="color:#94a3b8">'+esc(p.units)+'</span>'):'';
    const title=esc(p.key)+(p.desc?(' \u2014 '+esc(p.desc)):'')+(p.low!==''||p.high!==''?(' ['+esc(String(p.low))+'..'+esc(String(p.high))+']'):'');
    el.insertAdjacentHTML('beforeend','<label title="'+title+'">'+esc(p.name)+unit+'</label>'+widgetFor(p.key,p.kind,cur,p.enum,id));
    document.getElementById(id).addEventListener('change',function(){{ overrides[p.key]=readWidget(this,p.kind); stop(); rewalk(); }});
  }});
}}
function buildLevers(){{
  const el=document.getElementById('sim-levers'); el.innerHTML='';
  LEVERS.forEach(([label,key,kind])=>{{
    const id='l_'+key.replace(/[^A-Za-z0-9]/g,'_');
    let cur=(key in overrides)?overrides[key]:PAYLOAD.seed[key];
    if(cur===undefined||cur===null)cur=(kind==='bool'?false:((kind==='int'||kind==='real'||kind==='num')?0:''));
    el.insertAdjacentHTML('beforeend','<label title="'+esc(key)+'">'+esc(label)+'</label>'+widgetFor(key,kind,cur,null,id));
    document.getElementById(id).addEventListener('change',function(){{ overrides[key]=readWidget(this,kind); stop(); rewalk(); }});
  }});
}}
function buildEdit(){{ buildRParams(''); buildLevers();
  const ff=document.getElementById('sim-rfilter'); if(ff&&!ff._wired){{ ff._wired=1; ff.addEventListener('input',function(){{buildRParams(this.value);}}); }}
}}
function truthy(v){{ return v===true||v==='True'||(typeof v==='number'&&v!==0)||(typeof v==='string'&&v!==''&&v!=='0'&&v!=='False'); }}

function stepFwd(){{ if(idx<sim.trace.length-1){{idx++;render();}} if(idx>=sim.trace.length-1)stop(); }}
function stop(){{ if(timer){{clearInterval(timer);timer=null;document.getElementById('sim-play').textContent='\u25b6 Play';}} }}

// ── item 9: visual timer countdown (auto-completes) ─────────────────────────
let countdown=null;
function resolveDuration(ref){{
  // ref is an R_ param key like '^/R_CHEM_ADD_TM.CV'; read its current value
  const v=(ref in overrides)?overrides[ref]:PAYLOAD.seed[ref];
  const n=parseFloat(v); return (isFinite(n)&&n>0)?n:10;   // default 10s if unset/0
}}
function renderTimer(step){{
  const host=document.getElementById('sim-timer-host');
  if(!step||!TIMERS[step]){{ host.innerHTML=''; if(countdown){{clearInterval(countdown);countdown=null;}} return; }}
  if(host._step===step && host.innerHTML) return;   // already showing this timer
  host._step=step;
  const t=TIMERS[step]; const dur=resolveDuration(t.sp_ref);
  const durLabel=t.sp_ref.replace('^/','').replace('.CV','');
  host.innerHTML='<div class="sim-timer-box"><div class="tt"><span>\u23f1 Timer \u2014 '+esc(durLabel)+'</span>'+
    '<span id="sim-tclock" class="clock" style="font-size:14px">'+fmt(dur)+'</span></div>'+
    '<div class="bar"><i id="sim-tbar"></i></div>'+
    '<div class="btns"><button class="primary" id="sim-trun" onclick="SIM.runTimer(\\''+esc(step)+'\\')">\u25b6 Run timer</button>'+
    '<button onclick="SIM.skipTimer(\\''+esc(step)+'\\')">Skip \u2192 complete</button></div>'+
    '<p class="sim-hint">Visual countdown from '+esc(durLabel)+' ('+dur+'s). Auto-sets '+esc(t.complete_key.replace('//#','#').replace('#/','#/'))+' when done.</p></div>';
}}
function fmt(s){{ s=Math.max(0,Math.round(s)); const m=Math.floor(s/60),ss=s%60; return (m>0?(m+':'+String(ss).padStart(2,'0')):(s+'s')); }}

// ── item 8: draggable + resizable floating window ───────────────────────────
function initDrag(){{
  const win=document.getElementById('sim-win'), bar=document.getElementById('sim-drag');
  if(!win||!bar||bar._wired) return; bar._wired=1;
  let dx=0,dy=0,dragging=false;
  bar.addEventListener('mousedown',function(e){{
    if(e.target.tagName==='BUTTON') return;
    dragging=true; const r=win.getBoundingClientRect();
    dx=e.clientX-r.left; dy=e.clientY-r.top; win.style.right='auto'; win.style.left=r.left+'px'; win.style.top=r.top+'px';
    e.preventDefault();
  }});
  window.addEventListener('mousemove',function(e){{
    if(!dragging) return;
    let nx=e.clientX-dx, ny=e.clientY-dy;
    nx=Math.max(4,Math.min(nx,window.innerWidth-60)); ny=Math.max(4,Math.min(ny,window.innerHeight-40));
    win.style.left=nx+'px'; win.style.top=ny+'px';
  }});
  window.addEventListener('mouseup',function(){{ dragging=false; }});
}}

// record an operator answer for the SPECIFIC entry the walk is currently paused at,
// so prior loops' answers persist and a re-entered prompt asks again.
function recordAnswer(step,val){{
  const entry=(sim.pausedPrompt&&sim.pausedPrompt.step===step)?sim.pausedPrompt.entry:0;
  if(!answers[step]||!answers[step].byEntry) answers[step]={{byEntry:{{}}}};
  answers[step].byEntry[entry]={{input:val}};
}}

window.SIM={{
  toggle:function(){{ const w=document.getElementById('sim-win'); const on=w.classList.toggle('open');
    document.body.classList.toggle('sim-on',on);
    if(on){{ showRunBlock(); initDrag(); if(!sim){{buildEdit();rewalk();idx=-1;prevWatch={{}};render();}} }} }},
  minimize:function(){{ const w=document.getElementById('sim-win'); w.classList.toggle('min');
    document.getElementById('sim-min').textContent=w.classList.contains('min')?'\u25a1':'\u2013'; }},
  reset:function(){{ stop(); if(countdown){{clearInterval(countdown);countdown=null;}}
    Object.keys(answers).forEach(k=>delete answers[k]);
    Object.keys(overrides).forEach(k=>{{ if(k.indexOf('TM_COMPLETE')>=0) delete overrides[k]; }});
    idx=-1; prevWatch={{}}; rewalk(); idx=-1; render(); }},
  step:function(){{ stop(); stepFwd(); }},
  play:function(){{ if(timer){{stop();return;}} if(idx>=sim.trace.length-1)idx=-1;
    document.getElementById('sim-play').textContent='\u23f8 Pause'; timer=setInterval(stepFwd,650); }},
  answer:function(step,val){{ recordAnswer(step,val); stop(); rewalk(); }},
  answerInput:function(step){{ const v=parseFloat(document.getElementById('sim-vin').value)||0; recordAnswer(step,v); stop(); rewalk(); }},
  runTimer:function(step){{
    const t=TIMERS[step]; if(!t) return; if(countdown){{clearInterval(countdown);}}
    let dur=resolveDuration(t.sp_ref), left=dur;
    const clock=document.getElementById('sim-tclock'), bar=document.getElementById('sim-tbar'), btn=document.getElementById('sim-trun');
    if(btn){{btn.disabled=true;btn.textContent='running\u2026';}}
    countdown=setInterval(function(){{
      left-=0.5;
      if(clock) clock.textContent=fmt(left);
      if(bar) bar.style.width=Math.min(100,((dur-left)/dur*100))+'%';
      if(left<=0){{ clearInterval(countdown); countdown=null;
        overrides[t.complete_key]=true;     // auto-complete -> release the wait
        stop(); rewalk();
      }}
    }},500);
  }},
  skipTimer:function(step){{ const t=TIMERS[step]; if(!t) return;
    if(countdown){{clearInterval(countdown);countdown=null;}}
    overrides[t.complete_key]=true; stop(); rewalk(); }},
}};
}})();
</script>
"""

    if '</body>' in phase_html:
        return phase_html.replace('</body>', overlay + '</body>', 1)
    return phase_html + overlay


if __name__ == '__main__':
    import db_parser
    import phase_bridge
    import sim_export
    text = db_parser.decode_fhx(open('/tmp/cip.fhx', 'rb').read())
    phase = 'CIP-SKD-WASH-PH'
    blocks = phase_bridge.parse_phases_from_export(text)[phase]
    phase_html = phase_bridge.build_phase_view_html(phase, blocks, text)
    payload = sim_export.build_payload(text, phase)
    out = inject(phase_html, payload)
    open('/tmp/phase_with_sim.html', 'w').write(out)
    print('wrote /tmp/phase_with_sim.html', len(out), 'bytes')
