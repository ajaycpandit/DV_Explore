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
body.sim-on .trans.sim-taken line{stroke:#10b981!important;stroke-width:3!important}
body.sim-on .trans.sim-hot line{stroke:#2563eb!important;stroke-width:3.4!important}

#sim-fab{position:fixed;right:18px;bottom:18px;z-index:60;background:#2563eb;color:#fff;
  border:none;border-radius:24px;padding:11px 18px;font:600 13px 'IBM Plex Sans',system-ui,sans-serif;
  box-shadow:0 4px 14px rgba(37,99,235,.35);cursor:pointer}
#sim-panel{position:fixed;right:0;top:0;height:100vh;width:340px;z-index:55;background:#fff;
  border-left:1px solid #d7dee7;box-shadow:-6px 0 24px rgba(15,32,48,.10);transform:translateX(100%);
  transition:transform .22s ease;display:flex;flex-direction:column;font-family:'IBM Plex Sans',system-ui,sans-serif}
#sim-panel.open{transform:translateX(0)}
#sim-panel header{background:#0f2030;color:#eaf1f8;padding:12px 16px;display:flex;align-items:center;gap:10px}
#sim-panel header h2{font-size:14px;margin:0;font-weight:600;flex:1}
#sim-panel header button{background:#16293a;color:#eaf1f8;border:1px solid #2c4358;border-radius:7px;
  padding:5px 9px;cursor:pointer;font-size:12px}
#sim-body{overflow:auto;padding:14px 16px;flex:1}
#sim-body h3{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#7689a0;margin:16px 0 7px;font-weight:700}
#sim-body h3:first-child{margin-top:0}
.sim-transport{display:flex;gap:7px}
.sim-transport button{flex:1;font:600 12px 'IBM Plex Sans';border:1px solid #c7d2de;background:#fff;
  border-radius:8px;padding:7px;cursor:pointer}
.sim-transport button.primary{background:#2563eb;color:#fff;border-color:#2563eb}
.sim-status{font:12px 'IBM Plex Mono';margin-top:8px;padding:5px 9px;border-radius:6px;display:inline-block}
.sim-status.run{background:#eff6ff;color:#1d4ed8}.sim-status.wait{background:#fef3c7;color:#92400e}
.sim-status.done{background:#ecfdf5;color:#047857}.sim-status.prompt{background:#ede9fe;color:#6d28d9}
.sim-msg{font-size:14px;font-weight:600;color:#1d4ed8;min-height:20px;line-height:1.35}
.sim-msg .m2{display:block;font-weight:400;font-size:12px;color:#46566b;margin-top:2px}
.sim-prompt-box{border:1.5px solid #7c3aed;border-radius:10px;padding:11px;background:#faf8ff;margin-top:4px}
.sim-prompt-box .q{font-size:13px;font-weight:600;color:#5b21b6;margin-bottom:9px;line-height:1.35}
.sim-prompt-box .btns{display:flex;gap:8px;flex-wrap:wrap}
.sim-prompt-box button{font:600 13px 'IBM Plex Sans';border:none;border-radius:8px;padding:8px 16px;cursor:pointer;background:#7c3aed;color:#fff}
.sim-prompt-box button.no{background:#fff;color:#5b21b6;border:1px solid #c4b5fd}
.sim-prompt-box .vrow{display:flex;gap:8px;align-items:center;margin-top:4px}
.sim-prompt-box input{font:13px 'IBM Plex Mono';border:1px solid #c4b5fd;border-radius:7px;padding:6px 9px;width:90px}
.sim-edit{display:grid;grid-template-columns:1fr auto;gap:7px 10px;align-items:center;font-size:12px}
.sim-edit label{color:#46566b;font:11px 'IBM Plex Mono'}
.sim-edit input[type=text],.sim-edit input[type=number]{font:12px 'IBM Plex Mono';border:1px solid #c7d2de;border-radius:6px;padding:4px 7px;width:120px}
.sim-hint{font-size:11px;color:#7689a0;margin:6px 0 0;line-height:1.4}
.sim-watch{display:grid;grid-template-columns:1fr auto;gap:3px 10px;font:12px 'IBM Plex Mono'}
.sim-watch .k{color:#46566b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sim-watch .v{font-weight:600;text-align:right}.sim-watch .v.chg{color:#1d4ed8}
.sim-tape{font:12px 'IBM Plex Mono';line-height:1.7;max-height:200px;overflow:auto}
.sim-tape .cur{color:#1d4ed8;font-weight:700}.sim-tape .pr{color:#6d28d9;font-weight:700}.sim-tape .w{color:#b45309}
</style>
"""

# Watch + editable config (same intent as the standalone build).
_WATCH_PREFIXES = ['^/P_MSG', '^/P_FIRST_PASS', '^/P_TASK_PTR', '^/P_COND_SNAPSHOT',
                   '//#CIP_MASTER_EM#/A_COMMAND', '//#THISUNIT#/U_CIP_SYNC_UNIT',
                   '^/FAIL_MONITOR/OAR/INPUT']
_EDITABLE = [
    ['Sync unit', '//#THISUNIT#/U_CIP_SYNC_UNIT.CV', 'text'],
    ['First pass', '^/P_FIRST_PASS.CV', 'bool'],
    ['Cond. snapshot', '^/P_COND_SNAPSHOT.CV', 'num'],
    ['Settle timer done', '//#UNIT_SUPPORT#/TMR1/TM_COMPLETE.CV', 'bool'],
]


def inject(phase_html, payload):
    eval_js = _read('sim_eval.js')
    engine_js = _read('sim_engine.js')
    payload_json = json.dumps(payload).replace('</', '<\\/')
    watch_json = json.dumps(_WATCH_PREFIXES)
    edit_json = json.dumps(_EDITABLE)

    overlay = _OVERLAY_CSS + f"""
<button id="sim-fab" onclick="SIM.toggle()">\u25b6 Simulate</button>
<div id="sim-panel"><header><h2>Phase Simulator</h2>
  <button onclick="SIM.toggle()">\u2715</button></header>
  <div id="sim-body">
    <div class="sim-transport">
      <button onclick="SIM.reset()">\u27f2 Reset</button>
      <button onclick="SIM.step()">Step \u2192</button>
      <button class="primary" id="sim-play" onclick="SIM.play()">\u25b6 Play</button>
    </div>
    <span class="sim-status run" id="sim-status">ready</span>
    <h3>Operator message</h3><div class="sim-msg" id="sim-msg">\u2014</div>
    <div id="sim-prompt-host"></div>
    <h3>Operator inputs</h3><div class="sim-edit" id="sim-edit"></div>
    <p class="sim-hint">Editing an input reseeds and re-walks. The walk halts at operator prompts (purple) until you answer.</p>
    <h3>Variable watch</h3><div class="sim-watch" id="sim-watch"></div>
    <h3>Walk tape</h3><div class="sim-tape" id="sim-tape"></div>
  </div>
</div>
<script>{eval_js}</script>
<script>{engine_js}</script>
<script>
(function(){{
const PAYLOAD={payload_json}, WATCH={watch_json}, EDITABLE={edit_json};
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
  let lastEnter=null,msg='\u2014',msg2='',watch={{}},tape='',pausedAt=null;
  const T=sim.trace;
  for(let k=0;k<=idx&&k<T.length;k++){{
    const ev=T[k];
    if(ev.kind==='enter'){{
      lastEnter=ev.step; const st=ev.store; msg=st['^/P_MSG1.CV']||msg; msg2=st['^/P_MSG2.CV']||'';
      watch=watchOf(st);
      const nd=gStep(ev.step); if(nd) nd.classList.add('sim-visited','sim-done');
      tape+='<div class="'+(k===idx?'cur':'')+'">\u25b8 '+esc(ev.step)+'  '+esc(ev.desc||'')+'</div>';
    }} else if(ev.kind==='fire'){{
      tape+='<div class="'+(k===idx?'cur':'')+'">  \u2514 '+esc(ev.t)+' \u2192 '+esc(ev.to)+'</div>';
      const p=gTrans(ev.t); if(p){{ p.classList.add('sim-taken'); if(k===idx)p.classList.add('sim-hot'); }}
    }} else if(ev.kind==='prompt'){{
      pausedAt=ev; tape+='<div class="pr'+(k===idx?' cur':'')+'">  \u2691 operator prompt \u2014 '+esc(ev.descr.oar_type)+'</div>';
    }}
  }}
  const tail=sim.log[sim.log.length-1]||'';
  let cls='run',txt='running';
  if(sim.pausedPrompt&&idx>=T.length-1){{ cls='prompt'; txt='waiting for operator'; }}
  else if(tail.indexOf('waiting')>=0){{ cls='wait'; txt='waiting \u2014 condition not met'; }}
  else if(tail.indexOf('terminal')>=0){{ cls='done'; txt='sequence complete'; }}

  if(lastEnter){{ const nd=gStep(lastEnter); if(nd){{ nd.classList.remove('sim-done');
    nd.classList.add(cls==='prompt'?'sim-prompt':(cls==='wait'?'sim-wait':'sim-active'));
    nd.scrollIntoView&&nd.scrollIntoView({{block:'center',behavior:'smooth'}}); }} }}

  document.getElementById('sim-msg').innerHTML=esc(msg)+(msg2?'<span class="m2">'+esc(msg2)+'</span>':'');
  const s=document.getElementById('sim-status'); s.className='sim-status '+cls; s.textContent=txt;
  renderWatch(watch); renderPrompt(cls==='prompt'?sim.pausedPrompt:null);
  document.getElementById('sim-tape').innerHTML=tape||'\u2014';
  prevWatch=watch;
}}

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
  let inner='<div class="q">'+esc(d.msg1||'Operator response required')+(d.msg2?'<br><span style="font-weight:400">'+esc(d.msg2)+'</span>':'')+'</div>';
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

function buildEdit(){{ const el=document.getElementById('sim-edit'); el.innerHTML='';
  EDITABLE.forEach(([label,key,kind])=>{{
    const id='e_'+key.replace(/[^A-Za-z0-9]/g,'_');
    let cur=(key in overrides)?overrides[key]:PAYLOAD.seed[key];
    if(cur===undefined||cur===null)cur=(kind==='bool'?false:(kind==='num'?0:''));
    let inp;
    if(kind==='bool')inp='<input type="checkbox" id="'+id+'" '+(truthy(cur)?'checked':'')+'>';
    else if(kind==='num')inp='<input type="number" id="'+id+'" value="'+esc(String(cur))+'">';
    else inp='<input type="text" id="'+id+'" value="'+esc(String(cur))+'">';
    el.insertAdjacentHTML('beforeend','<label title="'+esc(key)+'">'+esc(label)+'</label>'+inp);
    document.getElementById(id).addEventListener('change',function(){{
      let v; if(kind==='bool')v=this.checked; else if(kind==='num')v=parseFloat(this.value)||0; else v=this.value;
      overrides[key]=v; stop(); rewalk();
    }});
  }});
}}
function truthy(v){{ return v===true||v==='True'||(typeof v==='number'&&v!==0)||(typeof v==='string'&&v!==''&&v!=='0'&&v!=='False'); }}

function stepFwd(){{ if(idx<sim.trace.length-1){{idx++;render();}} if(idx>=sim.trace.length-1)stop(); }}
function stop(){{ if(timer){{clearInterval(timer);timer=null;document.getElementById('sim-play').textContent='\u25b6 Play';}} }}

window.SIM={{
  toggle:function(){{ const p=document.getElementById('sim-panel'); const on=p.classList.toggle('open');
    document.body.classList.toggle('sim-on',on); if(on){{showRunBlock(); if(!sim){{buildEdit();rewalk();idx=-1;prevWatch={{}};render();}}}} }},
  reset:function(){{ stop(); answers&&Object.keys(answers).forEach(k=>delete answers[k]); idx=-1; prevWatch={{}}; rewalk(); idx=-1; render(); }},
  step:function(){{ stop(); stepFwd(); }},
  play:function(){{ if(timer){{stop();return;}} if(idx>=sim.trace.length-1)idx=-1;
    document.getElementById('sim-play').textContent='\u23f8 Pause'; timer=setInterval(stepFwd,650); }},
  answer:function(step,val){{ answers[step]={{input:val}}; stop(); rewalk(); }},
  answerInput:function(step){{ const v=parseFloat(document.getElementById('sim-vin').value)||0; answers[step]={{input:v}}; stop(); rewalk(); }},
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
