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

#sim-fab{position:fixed;right:18px;bottom:18px;z-index:9997;background:#2563eb;color:#fff;
  border:none;border-radius:24px;padding:11px 18px;font:600 13px 'IBM Plex Sans',system-ui,sans-serif;
  box-shadow:0 4px 14px rgba(37,99,235,.35);cursor:pointer}
#sim-fab.hidden{display:none}

/* ── dockable simulator: bottom strip / left / right / floating ── */
#sim-dock{position:fixed;z-index:9998;background:#fff;display:none;flex-direction:column;
  font-family:'IBM Plex Sans',system-ui,sans-serif;box-shadow:0 -8px 28px -14px rgba(15,32,48,.30)}
#sim-dock.open{display:flex}

/* BOTTOM (default): full-width strip, diagram gets bottom padding */
#sim-dock.dock-bottom{left:0;right:0;bottom:0;height:var(--sim-h,320px);border-top:1px solid #cbd5e2}
body.sim-on.mode-bottom{padding-bottom:var(--sim-h,320px)!important}
body.sim-on.mode-bottom.sim-min{padding-bottom:44px!important}

/* LEFT: full-height column on the left, diagram gets left padding */
#sim-dock.dock-left{left:0;top:0;bottom:0;width:var(--sim-w,380px);border-right:1px solid #cbd5e2;
  box-shadow:8px 0 28px -14px rgba(15,32,48,.30)}
body.sim-on.mode-left{padding-left:var(--sim-w,380px)!important}
body.sim-on.mode-left.sim-min{padding-left:0!important}

/* RIGHT: full-height column on the right */
#sim-dock.dock-right{right:0;top:0;bottom:0;width:var(--sim-w,380px);border-left:1px solid #cbd5e2;
  box-shadow:-8px 0 28px -14px rgba(15,32,48,.30)}
body.sim-on.mode-right{padding-right:var(--sim-w,380px)!important}
body.sim-on.mode-right.sim-min{padding-right:0!important}

/* FLOAT: free-floating draggable panel, no body padding */
#sim-dock.dock-float{left:var(--sim-x,80px);top:var(--sim-y,90px);width:var(--sim-fw,440px);
  height:var(--sim-fh,480px);border:1px solid #cbd5e2;border-radius:12px;overflow:hidden;
  box-shadow:0 20px 55px -14px rgba(15,32,48,.40)}

#sim-dock.min{height:44px!important}
#sim-dock.dock-left.min,#sim-dock.dock-right.min{height:44px!important;bottom:auto}
#sim-dock.min .sim-dockbody{display:none}

/* resize grips per mode */
#sim-grip{background:#eef2f7;flex-shrink:0}
#sim-dock.dock-bottom #sim-grip{height:6px;cursor:ns-resize;border-bottom:1px solid #e5ebf2;order:-1}
#sim-dock.dock-left #sim-grip,#sim-dock.dock-right #sim-grip{display:none}
#sim-dock.dock-float #sim-grip{display:none}
/* side/float resize edges */
#sim-edge{position:absolute;background:transparent;z-index:5}
#sim-dock.dock-left #sim-edge{right:0;top:0;bottom:0;width:6px;cursor:ew-resize;display:block}
#sim-dock.dock-right #sim-edge{left:0;top:0;bottom:0;width:6px;cursor:ew-resize;display:block}
#sim-dock.dock-float #sim-edge{right:0;bottom:0;width:16px;height:16px;cursor:nwse-resize;display:block}
#sim-dock.dock-bottom #sim-edge{display:none}
#sim-edge:hover{background:#cbd5e2}

.sim-dockbar{background:#0f2030;color:#eaf1f8;padding:6px 12px;display:flex;align-items:center;gap:10px;flex-shrink:0}
#sim-dock.dock-float .sim-dockbar,#sim-dock.dock-left .sim-dockbar,#sim-dock.dock-right .sim-dockbar{cursor:move}
.sim-dockbar h2{font-size:13px;margin:0;font-weight:600;white-space:nowrap}
.sim-dockbar .sim-transport{display:flex;gap:6px}
.sim-dockbar .sim-transport button{font:600 12px 'IBM Plex Sans';border:1px solid #2c4358;background:#16293a;color:#eaf1f8;
  border-radius:7px;padding:5px 12px;cursor:pointer}
.sim-dockbar .sim-transport button.primary{background:#2563eb;border-color:#2563eb}
.sim-dockbar .sim-transport button:disabled{opacity:.4;cursor:default}
.sim-dockbar .sim-status{font:12px 'IBM Plex Mono';padding:3px 9px;border-radius:6px}
.sim-dockbar .spacer{flex:1}
.sim-dockbar .sim-pos{font:11px 'IBM Plex Mono';color:#9db4ca}
.sim-dockbar .iconbtn{background:#16293a;color:#eaf1f8;border:1px solid #2c4358;border-radius:6px;padding:3px 9px;cursor:pointer;font-size:12px;line-height:1}
.sim-dockbar .iconbtn.on{background:#2563eb;border-color:#2563eb}
.sim-dockbar .dockmenu{display:flex;gap:3px;margin-right:2px}

.sim-status.run{background:#1e3a5f;color:#93c5fd}.sim-status.wait{background:#5c4813;color:#fcd34d}
.sim-status.done{background:#14432a;color:#6ee7b7}.sim-status.prompt{background:#3b2a5c;color:#c4b5fd}
.sim-status.timer{background:#0c3a52;color:#7dd3fc}

/* dock body: 3 columns in bottom mode; stacks vertically in left/right/float */
.sim-dockbody{flex:1;display:grid;grid-template-columns:minmax(300px,1fr) minmax(360px,1.5fr);
  gap:0;overflow:hidden;min-height:0;position:relative}
#sim-dock.dock-left .sim-dockbody,#sim-dock.dock-right .sim-dockbody,#sim-dock.dock-float .sim-dockbody{
  grid-template-columns:1fr;grid-auto-rows:min-content;overflow:auto}
#sim-dock.dock-left .sim-col,#sim-dock.dock-right .sim-col,#sim-dock.dock-float .sim-col{
  border-right:none;border-bottom:1px solid #eef2f7}
.sim-col{overflow:auto;padding:11px 13px;border-right:1px solid #eef2f7;min-height:0}
.sim-col:last-child{border-right:none}
.sim-col h3{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#7689a0;margin:0 0 8px;font-weight:700}
.sim-col h3.mt{margin-top:14px}
/* right-side tabbed pane (Option B) */
.sim-tab-col{padding:0;display:flex;flex-direction:column;overflow:hidden}
#sim-dock.dock-left .sim-tab-col,#sim-dock.dock-right .sim-tab-col,#sim-dock.dock-float .sim-tab-col{overflow:visible}
.sim-tabs{display:flex;gap:2px;padding:8px 10px 0;border-bottom:1px solid #eef2f7;flex-shrink:0;background:#fafbfc}
.sim-tab{font:600 12px 'IBM Plex Sans';border:none;background:transparent;color:#7689a0;padding:7px 13px;
  cursor:pointer;border-radius:7px 7px 0 0;border-bottom:2px solid transparent;margin-bottom:-1px}
.sim-tab:hover{color:#334155;background:#f1f5f9}
.sim-tab.on{color:#1d4ed8;border-bottom-color:#2563eb;background:#fff}
.sim-tabwrap{flex:1;overflow:auto;padding:11px 13px;min-height:0}
#sim-dock.dock-left .sim-tabwrap,#sim-dock.dock-right .sim-tabwrap,#sim-dock.dock-float .sim-tabwrap{overflow:visible}
.sim-tabpanel{display:none}
.sim-tabpanel.on{display:block}
.sim-tape-legend{font:11px 'IBM Plex Mono';color:#94a3b8;margin-bottom:8px}
/* narrow docks (left/right/float): stack everything, tabs become section headers */
#sim-dock.dock-left .sim-tabs,#sim-dock.dock-right .sim-tabs,#sim-dock.dock-float .sim-tabs{display:none}
#sim-dock.dock-left .sim-tabpanel,#sim-dock.dock-right .sim-tabpanel,#sim-dock.dock-float .sim-tabpanel{display:block;margin-bottom:6px}
#sim-dock.dock-left .sim-tabwrap,#sim-dock.dock-right .sim-tabwrap,#sim-dock.dock-float .sim-tabwrap{padding:11px 13px}

.sim-nowstep{font:12px 'IBM Plex Mono';color:#16202c;margin-bottom:6px}
.sim-msg{font-size:13px;font-weight:600;color:#1d4ed8;min-height:18px;line-height:1.35;margin-bottom:6px}
.sim-msg .m2{display:block;font-weight:400;font-size:12px;color:#46566b;margin-top:2px}

.sim-prompt-box{border:1.5px solid #7c3aed;border-radius:10px;padding:11px;background:#faf8ff}
.sim-prompt-box .q{font-size:13px;font-weight:600;color:#5b21b6;margin-bottom:9px;line-height:1.35}
.sim-prompt-box .btns{display:flex;gap:8px;flex-wrap:wrap}
.sim-prompt-box button{font:600 14px 'IBM Plex Sans';border:none;border-radius:8px;padding:9px 20px;cursor:pointer;background:#7c3aed;color:#fff}
.sim-prompt-box button.no{background:#fff;color:#5b21b6;border:1px solid #c4b5fd}
.sim-prompt-box .vrow{display:flex;gap:8px;align-items:center;margin-top:6px}
.sim-prompt-box input{font:13px 'IBM Plex Mono';border:1px solid #c4b5fd;border-radius:7px;padding:6px 9px;width:90px}

.sim-timer-box{border:1.5px solid #0284c7;border-radius:10px;padding:11px;background:#f0f9ff;margin-top:8px}
.sim-timer-box .tt{font-size:12px;font-weight:600;color:#0369a1;display:flex;justify-content:space-between;align-items:center}
.sim-timer-box .clock{font:700 16px 'IBM Plex Mono';color:#0c4a6e}
.sim-timer-box .bar{height:6px;border-radius:4px;background:#bae6fd;overflow:hidden;margin:6px 0}
.sim-timer-box .bar > i{display:block;height:100%;background:#0284c7;width:0;transition:width .25s linear}
.sim-timer-box .btns{display:flex;gap:7px}
.sim-timer-box button{font:600 12px 'IBM Plex Sans';border:1px solid #7dd3fc;background:#fff;color:#0369a1;border-radius:7px;padding:5px 11px;cursor:pointer}
.sim-timer-box button.primary{background:#0284c7;color:#fff;border-color:#0284c7}

.sim-sect{border:1px solid #e8edf3;border-radius:9px;margin-bottom:9px;overflow:hidden}
.sim-sect > summary{cursor:pointer;list-style:none;padding:7px 10px;background:#f6f8fb;font-size:11px;
  font-weight:700;color:#46566b;text-transform:uppercase;letter-spacing:.05em;display:flex;align-items:center;gap:6px}
.sim-sect > summary::-webkit-details-marker{display:none}
.sim-sect > summary::before{content:"\\25b8";font-size:9px;transition:.15s;color:#94a3b8}
.sim-sect[open] > summary::before{transform:rotate(90deg)}
.sim-sect .body{padding:9px 10px}

.sim-edit{display:grid;grid-template-columns:1fr auto;gap:6px 10px;align-items:center;font-size:12px}
.sim-edit label{color:#46566b;font:11px 'IBM Plex Mono'}
.sim-edit input[type=text],.sim-edit input[type=number]{font:12px 'IBM Plex Mono';border:1px solid #c7d2de;border-radius:6px;padding:4px 7px;width:110px}
.sim-hint{font-size:11px;color:#7689a0;margin:6px 0 0;line-height:1.4}
.sim-watch{display:grid;grid-template-columns:1fr auto;gap:3px 10px;font:12px 'IBM Plex Mono'}
.sim-watch .k{color:#46566b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sim-watch .v{font-weight:600;text-align:right}.sim-watch .v.chg{color:#1d4ed8}

/* steps/actions list with per-action status glyphs (item 3) */
.sim-tape{font:12px 'IBM Plex Mono';line-height:1.55}
.sim-tape .row{padding:2px 6px;border-radius:5px}
.sim-tape .row.step{color:#334155;font-weight:600}
.sim-tape .row.cur{background:#dbeafe;color:#1d4ed8}
.sim-tape .row.tr{color:#94a3b8;padding-left:18px;font-weight:400}
.sim-tape .row.tr.cur{background:#eef2ff;color:#4f46e5}
.sim-tape .row.pr{color:#6d28d9;font-weight:700;padding-left:14px}
.sim-tape .row.act{color:#64748b;padding-left:20px;font-size:11px;font-weight:400;display:flex;gap:6px;align-items:baseline}
.sim-tape .row.act .g{flex-shrink:0;width:12px;display:inline-block;text-align:center}
.sim-tape .row.act.done .g{color:#10b981}
.sim-tape .row.act.active .g{color:#0284c7}
.sim-tape .row.act.pending{color:#b0bac6}.sim-tape .row.act.pending .g{color:#cbd5e1}
.sim-tape .row.act.err{color:#dc2626}.sim-tape .row.act.err .g{color:#dc2626}
.sim-tape .row.act.setr .g{color:#0369a1}
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
    ['Acid conductivity (sensor)', '//#COND_ACID#/PV.CV', 'real'],
    ['Conductivity snapshot (checked)', '^/P_COND_SNAPSHOT.CV', 'real'],
    ['Recipient ready (T0200)', '^/D_RECV_SYNC_MSG.CV', 'text'],
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
<div id="sim-dock" class="dock-bottom">
  <div id="sim-grip" title="Drag to resize"></div>
  <div id="sim-edge" title="Drag to resize"></div>
  <div class="sim-dockbar" id="sim-dockbar">
    <h2>Phase Simulator</h2>
    <div class="sim-transport">
      <button onclick="SIM.reset()">\u27f2 Reset</button>
      <button onclick="SIM.back()" id="sim-back">\u2190 Back</button>
      <button onclick="SIM.step()" id="sim-fwd">Step \u2192</button>
      <button class="primary" id="sim-play" onclick="SIM.play()">\u25b6 Play</button>
    </div>
    <span class="sim-status run" id="sim-status">ready</span>
    <span class="sim-pos" id="sim-pos"></span>
    <div class="spacer"></div>
    <div class="dockmenu" title="Dock position">
      <button class="iconbtn" id="dock-left" onclick="SIM.dock('left')" title="Dock left">\u25e7</button>
      <button class="iconbtn" id="dock-bottom" onclick="SIM.dock('bottom')" title="Dock bottom">\u2b13</button>
      <button class="iconbtn" id="dock-right" onclick="SIM.dock('right')" title="Dock right">\u25e8</button>
      <button class="iconbtn" id="dock-float" onclick="SIM.dock('float')" title="Float">\u29c9</button>
    </div>
    <button class="iconbtn" onclick="SIM.minimize()" id="sim-min" title="Minimize">\u2013</button>
    <button class="iconbtn" onclick="SIM.toggle()" title="Close">\u2715</button>
  </div>
  <div class="sim-dockbody">
    <!-- LEFT: operator + transport context, always visible -->
    <div class="sim-col sim-op-col">
      <h3>Operator</h3>
      <div class="sim-nowstep" id="sim-now">idle</div>
      <div class="sim-msg" id="sim-msg">\u2014</div>
      <div id="sim-prompt-host"></div>
      <div id="sim-timer-host"></div>
      <button id="sim-rerun" onclick="SIM.rerunStep()" title="Re-execute the current step's actions from a clean re-walk"
        style="display:none;margin-top:8px;font:600 11px 'IBM Plex Sans';border:1px solid #c7d2de;background:#fff;color:#334155;border-radius:7px;padding:5px 10px;cursor:pointer">\u21bb Re-run this step</button>
    </div>
    <!-- RIGHT: tabbed pane (Inputs / Steps & Actions / Watch) -->
    <div class="sim-col sim-tab-col">
      <div class="sim-tabs">
        <button class="sim-tab on" data-t="inputs" onclick="SIM.tab(this,'inputs')">Inputs</button>
        <button class="sim-tab" data-t="steps" onclick="SIM.tab(this,'steps')">Steps &amp; Actions</button>
        <button class="sim-tab" data-t="watch" onclick="SIM.tab(this,'watch')">Watch</button>
      </div>
      <div class="sim-tabwrap">
        <!-- Inputs tab -->
        <div class="sim-tabpanel on" data-t="inputs">
          <details class="sim-sect" id="sim-rsect" open>
            <summary>Recipe parameters (R_)</summary>
            <div class="body">
              <input id="sim-rfilter" placeholder="filter\u2026" style="width:100%;box-sizing:border-box;font:12px 'IBM Plex Mono';border:1px solid #c7d2de;border-radius:6px;padding:4px 7px;margin-bottom:7px">
              <div class="sim-edit" id="sim-rparams"></div>
            </div>
          </details>
          <details class="sim-sect" open>
            <summary>Device / timer levers</summary>
            <div class="body"><div class="sim-edit" id="sim-levers"></div></div>
          </details>
        </div>
        <!-- Steps & Actions tab -->
        <div class="sim-tabpanel" data-t="steps">
          <div class="sim-tape-legend">\u2713 done \u00b7 \u25cf active \u00b7 \u25cb pending</div>
          <div class="sim-tape" id="sim-tape"></div>
        </div>
        <!-- Watch tab -->
        <div class="sim-tabpanel" data-t="watch">
          <div class="sim-watch" id="sim-watch"></div>
        </div>
      </div>
    </div>
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
function rewalk(anchor){{
  // remember if we were paused at a prompt (step+entry) so a parameter edit
  // doesn't retroactively erase the decision point we're looking at (Issue A):
  // the recheck should take effect AFTER the answer / on the next loop, not by
  // making the current pending prompt vanish.
  let want=anchor;
  if(!want && sim){{
    const cur=(idx>=0&&idx<sim.trace.length)?sim.trace[idx]:null;
    if(cur&&cur.kind==='prompt') want={{step:cur.step, entry:cur.entry}};
    else if(sim.pausedPrompt&&idx>=sim.trace.length-1) want={{step:sim.pausedPrompt.step, entry:sim.pausedPrompt.entry}};
  }}
  sim=new SimEngine.PhaseSim(PAYLOAD,{{overrides:buildOverrides(),answers:answers}}); sim.run();
  idx=sim.trace.length-1;
  if(want){{
    // re-anchor to the same prompt (same step & entry) if it still exists in the new walk
    for(let k=0;k<sim.trace.length;k++){{
      const ev=sim.trace[k];
      if(ev.kind==='prompt'&&ev.step===want.step&&ev.entry===want.entry){{ idx=k; break; }}
    }}
  }}
  render();
}}

function clearViz(){{
  runBlockEl().querySelectorAll('.step').forEach(n=>n.classList.remove('sim-active','sim-visited','sim-done','sim-wait','sim-prompt'));
  runBlockEl().querySelectorAll('.trans').forEach(e=>e.classList.remove('sim-taken','sim-hot'));
}}

function render(){{
  clearViz();
  let lastEnter=null,msg='\u2014',msg2='',watch={{}},tape='',pausedAt=null,activeActs=[];
  const T=sim.trace;
  // active SFC actions (S set, not yet R reset) at the current position
  let curActive=[];
  for(let k=0;k<=idx&&k<T.length;k++){{ if(T[k].kind==='enter'&&T[k].active_actions) curActive=T[k].active_actions; }}

  // ── Issue B: on a loop-back, steps that will re-execute must reset to gray.
  // Find the start of the CURRENT pass: the last time the walk looped backward
  // (re-entered a step it had already entered) at or before idx. Only steps
  // entered within [passStart .. idx] are shown green ("done this pass"); anything
  // before the loop-back is treated as not-yet-re-executed (gray). This makes the
  // loop visible: the green trail rewinds to gray and re-lights on each iteration.
  let passStart=0;
  {{
    let seen={{}};
    for(let k=0;k<=idx&&k<T.length;k++){{
      const ev=T[k];
      if(ev.kind==='enter'){{
        if(seen[ev.step]!==undefined){{ passStart=k; seen={{}}; }}  // re-entry -> new pass begins here
        seen[ev.step]=k;
      }}
    }}
  }}

  for(let k=0;k<=idx&&k<T.length;k++){{
    const ev=T[k];
    const isCur=(k===idx);
    if(ev.kind==='enter'){{
      lastEnter=ev.step; const st=ev.store; msg=st['^/P_MSG1.CV']||msg; msg2=st['^/P_MSG2.CV']||'';
      watch=watchOf(st); activeActs=ev.active_actions||[];
      // only paint the step green if it belongs to the CURRENT pass (post last loop-back)
      if(k>=passStart){{ const nd=gStep(ev.step); if(nd) nd.classList.add('sim-visited','sim-done'); }}
      tape+='<div class="row step'+(isCur?' cur':'')+'">\u25b8 '+esc(ev.step)+'  '+esc(ev.desc||'')+'</div>';
      // item 3: action outcomes with status glyphs (\u2713 done \u00b7 \u25cf active \u00b7 \u25cb pending)
      (ev.actions||[]).forEach(a=>{{
        let cls='act', glyph='\u2713', tag='';
        if(a.kind==='activated'){{cls+=' setr active'; glyph='\u25cf'; tag='SET ';}}
        else if(a.kind==='deactivated'){{cls+=' setr done'; glyph='\u2713'; tag='RESET ';}}
        else if(a.kind==='error'){{cls+=' err'; glyph='\u26a0'; tag='ERR ';}}
        else if(a.kind==='unmodeled'){{cls+=' pending'; glyph='\u25cb'; tag=(a.qual||'?')+' ';}}
        else {{cls+=' done'; glyph='\u2713';}}
        // if a SET action is still active at the CURRENT position, mark it active not done
        if((a.kind==='activated') && curActive.indexOf(a.body)<0){{ cls=cls.replace('active','done'); glyph='\u2713'; }}
        tape+='<div class="row '+cls+'"><span class="g">'+glyph+'</span><span>'+esc(tag)+esc(a.body||'')+'</span></div>';
      }});
    }} else if(ev.kind==='fire'){{
      // item 3: transitions shown in the bottom panel
      const exprAbbr=transAbbr(ev.t);
      const looped=(ev.to&&isLoopBack(T,k));
      tape+='<div class="row tr'+(isCur?' cur':'')+'">\u2514 '+esc(ev.t)+' \u2192 '+esc(ev.to)+(looped?' \u21ba':'')+(exprAbbr?'  <span style="opacity:.7">['+esc(exprAbbr)+']</span>':'')+'</div>';
      // only light the transition if it's part of the current pass
      if(k>=passStart){{ const p=gTrans(ev.t); if(p){{ p.classList.add('sim-taken'); if(isCur)p.classList.add('sim-hot'); }} }}
    }} else if(ev.kind==='prompt'){{
      pausedAt=ev; tape+='<div class="row pr'+(isCur?' cur':'')+'">\u2691 operator prompt \u2014 '+esc(ev.descr.oar_type)+'</div>';
    }}
  }}
  // item 3: show upcoming (pending) events after the current position, dimmed
  for(let k=idx+1;k<T.length;k++){{
    const ev=T[k];
    if(ev.kind==='enter'){{
      tape+='<div class="row step pending" style="opacity:.5">\u25cb '+esc(ev.step)+'  '+esc(ev.desc||'')+'</div>';
    }} else if(ev.kind==='fire'){{
      tape+='<div class="row tr pending" style="opacity:.45">\u2514 '+esc(ev.t)+' \u2192 '+esc(ev.to)+'</div>';
    }} else if(ev.kind==='prompt'){{
      tape+='<div class="row pr pending" style="opacity:.5">\u2691 prompt \u2014 '+esc(ev.descr.oar_type)+'</div>';
    }}
  }}
  const tail=sim.log[sim.log.length-1]||'';
  let cls='run',txt='running';
  const atEnd=idx>=T.length-1;
  // is the CURRENT position a prompt event? (covers mid-trace prompts from loops)
  const curEv=(idx>=0&&idx<T.length)?T[idx]:null;
  const curPrompt=(curEv&&curEv.kind==='prompt')?curEv:null;
  const timerHere=atEnd&&lastEnter&&TIMERS[lastEnter]&&waitingHere(tail);
  if(curPrompt||(sim.pausedPrompt&&atEnd)){{ cls='prompt'; txt='waiting for operator'; }}
  else if(timerHere){{ cls='timer'; txt='timer running'; }}
  else if(waitingHere(tail)&&atEnd){{ cls='wait'; txt='waiting \u2014 condition not met';
    // surface WHICH transition is blocking and its expression, so a stall on an
    // external/unsimulated signal (e.g. T0200 recipient handshake) is self-explaining.
    if(lastEnter){{
      const outs=PAYLOAD.s2t[lastEnter]||[];
      if(outs.length){{ const bt=outs[0];
        msg='Waiting on '+bt+' \u2192 '+(PAYLOAD.t2s[bt]||'?');
        msg2=(PAYLOAD.trans[bt]||'').replace(/\\s+/g,' ').trim();
      }}
    }}
  }}
  else if(tail.indexOf('terminal')>=0&&atEnd){{ cls='done'; txt='sequence complete'; }}
  // the prompt descriptor to present: current-position prompt, else the final pause
  const promptToShow = curPrompt ? {{step:curPrompt.step, descr:curPrompt.descr, entry:curPrompt.entry}}
                                 : (atEnd?sim.pausedPrompt:null);

  if(lastEnter){{ const nd=gStep(lastEnter); if(nd){{ nd.classList.remove('sim-done');
    nd.classList.add(cls==='prompt'?'sim-prompt':(cls==='timer'?'sim-timer':(cls==='wait'?'sim-wait':'sim-active')));
    nd.scrollIntoView&&nd.scrollIntoView({{block:'center',behavior:'smooth'}}); }} }}

  document.getElementById('sim-now').textContent = lastEnter?('at '+lastEnter+(activeActs.length?'  \u00b7 active: '+activeActs.join(', '):'')):'idle';
  const rr=document.getElementById('sim-rerun'); if(rr) rr.style.display=(lastEnter&&idx>=0)?'inline-block':'none';
  document.getElementById('sim-msg').innerHTML=esc(msg)+(msg2?'<span class="m2">'+esc(msg2)+'</span>':'');
  const s=document.getElementById('sim-status'); s.className='sim-status '+cls; s.textContent=txt;
  // meaningful position: which step we're on out of steps walked (not raw events)
  let stepNum=0, stepTotal=0;
  for(let k=0;k<T.length;k++){{ if(T[k].kind==='enter'){{ stepTotal++; if(k<=idx) stepNum++; }} }}
  document.getElementById('sim-pos').textContent = stepNum>0?('step '+stepNum+'/'+stepTotal):'\u2014';
  const bb=document.getElementById('sim-back'); if(bb) bb.disabled=(idx<=-1);
  const fb=document.getElementById('sim-fwd'); if(fb) fb.disabled=(idx>=T.length-1);
  renderWatch(watch);
  shownPromptEntry = (cls==='prompt'&&promptToShow) ? promptToShow.entry : null;
  renderPrompt(cls==='prompt'?promptToShow:null);
  // item 1 safety: if a prompt is active, make sure it's actually visible —
  // un-minimize the dock and scroll the operator column to the prompt box.
  if(cls==='prompt'){{
    const dock=document.getElementById('sim-dock');
    if(dock.classList.contains('min')) SIM.minimize();
    const pb=document.querySelector('#sim-prompt-host .sim-prompt-box');
    if(pb&&pb.scrollIntoView) pb.scrollIntoView({{block:'nearest'}});
  }}
  renderTimer(cls==='timer'?lastEnter:null);
  const tp=document.getElementById('sim-tape'); tp.innerHTML=tape||'\u2014';
  const curRow=tp.querySelector('.row.cur'); if(curRow&&curRow.scrollIntoView) curRow.scrollIntoView({{block:'nearest'}});
  prevWatch=watch;
}}

function waitingHere(tail){{ return tail.indexOf('waiting')>=0 || tail.indexOf('no outgoing')>=0; }}
function transAbbr(tn){{ const e=(PAYLOAD.trans[tn]||'').replace(/\\s+/g,' ').trim(); return e.length>46?e.slice(0,46)+'\u2026':e; }}
// a fire is a loop-back if its target step was already entered earlier in the trace
function isLoopBack(T,k){{
  const to=T[k].to; if(!to) return false;
  for(let j=0;j<k;j++){{ if(T[j].kind==='enter'&&T[j].step===to) return true; }}
  return false;
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
  // Use the LIVE computed messages from the store at the moment the prompt was
  // raised (P_MSG1/P_MSG2 are built by the step's actions, e.g. "Conductivity
  // value 999 is not in range..."). Fall back to the static descriptor text.
  let lm1=null, lm2=null;
  for(let k=0;k<=idx&&k<sim.trace.length;k++){{ const ev=sim.trace[k];
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

function stepFwd(){{
  if(idx<sim.trace.length-1){{ idx++; render(); }}
  // stop auto-play at ANY prompt event (each loop's prompt), not just the trace end,
  // so the operator is asked at every iteration rather than Play batching through them.
  const ev=sim.trace[idx];
  if(idx>=sim.trace.length-1 || (ev&&ev.kind==='prompt')) stop();
}}
function stepBack(){{ if(idx>-1){{idx--;render();}} }}
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

// ── resize (grip for bottom, edge for side/float) + drag (side/float) ───────
let curMode='bottom';
function setMode(mode){{
  const dock=document.getElementById('sim-dock');
  ['bottom','left','right','float'].forEach(m=>{{
    dock.classList.toggle('dock-'+m, m===mode);
    document.body.classList.toggle('mode-'+m, m===mode);
    const b=document.getElementById('dock-'+m); if(b) b.classList.toggle('on', m===mode);
  }});
  curMode=mode;
}}
function initResize(){{
  const dock=document.getElementById('sim-dock');
  const grip=document.getElementById('sim-grip'), edge=document.getElementById('sim-edge'), bar=document.getElementById('sim-dockbar');
  if(dock._wired) return; dock._wired=1;
  let mode=null, sx=0, sy=0, sw=0, sh=0, ox=0, oy=0;
  function down(kind){{ return function(e){{
    if(e.target.tagName==='BUTTON') return;
    mode=kind; sx=e.clientX; sy=e.clientY;
    const r=dock.getBoundingClientRect(); sw=r.width; sh=r.height; ox=r.left; oy=r.top;
    e.preventDefault(); document.body.style.userSelect='none';
  }}; }}
  if(grip) grip.addEventListener('mousedown',down('h'));       // bottom height
  if(edge) edge.addEventListener('mousedown',function(e){{ down(curMode==='float'?'fxy':'w')(e); }});  // side width / float corner
  if(bar) bar.addEventListener('mousedown',function(e){{ if(curMode==='float'||curMode==='left'||curMode==='right') down('move')(e); }});
  window.addEventListener('mousemove',function(e){{
    if(!mode) return;
    if(mode==='h'){{ let h=window.innerHeight-e.clientY; h=Math.max(120,Math.min(h,window.innerHeight-100));
      document.documentElement.style.setProperty('--sim-h',h+'px'); }}
    else if(mode==='w'){{ let w = curMode==='left' ? e.clientX : (window.innerWidth-e.clientX);
      w=Math.max(260,Math.min(w,window.innerWidth-120)); document.documentElement.style.setProperty('--sim-w',w+'px'); }}
    else if(mode==='fxy'){{ let w=sw+(e.clientX-sx), h=sh+(e.clientY-sy);
      w=Math.max(300,Math.min(w,window.innerWidth-20)); h=Math.max(240,Math.min(h,window.innerHeight-20));
      document.documentElement.style.setProperty('--sim-fw',w+'px'); document.documentElement.style.setProperty('--sim-fh',h+'px'); }}
    else if(mode==='move' && curMode==='float'){{
      let x=ox+(e.clientX-sx), y=oy+(e.clientY-sy);
      x=Math.max(4,Math.min(x,window.innerWidth-80)); y=Math.max(4,Math.min(y,window.innerHeight-40));
      document.documentElement.style.setProperty('--sim-x',x+'px'); document.documentElement.style.setProperty('--sim-y',y+'px'); }}
    else if(mode==='move' && (curMode==='left'||curMode==='right')){{
      // dragging the bar on a side dock: if pulled toward center, pop to float at cursor
      if(Math.abs(e.clientX-sx)>60 || Math.abs(e.clientY-sy)>40){{
        document.documentElement.style.setProperty('--sim-x',(e.clientX-60)+'px');
        document.documentElement.style.setProperty('--sim-y',Math.max(4,e.clientY-16)+'px');
        SIM.dock('float'); mode='move';
      }}
    }}
  }});
  window.addEventListener('mouseup',function(){{ mode=null; document.body.style.userSelect=''; }});
}}

// ── item 3: click a transition to show its expression in the side panel ─────
// (core only shows transition expressions on hover; steps get a persistent panel
// on click. This adds the same persistent view for transitions. core is frozen,
// so we wire it from the overlay.)
function initTransClick(){{
  const blkEl=runBlockEl(); if(!blkEl||blkEl===document) return;
  blkEl.querySelectorAll('.trans').forEach(function(g){{
    if(g._transClick) return; g._transClick=1;
    g.style.cursor='pointer';
    g.addEventListener('click',function(e){{
      e.stopPropagation();
      showTransitionPanel(g.dataset.trans, g);
    }});
  }});
}}
function showTransitionPanel(tn, g){{
  runBlockEl().querySelectorAll('.step.sel,.trans.sel').forEach(n=>n.classList.remove('sel'));
  if(g) g.classList.add('sel');
  const expr=(PAYLOAD.trans&&PAYLOAD.trans[tn])||'';
  const to=(PAYLOAD.t2s&&PAYLOAD.t2s[tn])||'';
  const from=(PAYLOAD.order||[]).find(s=>(PAYLOAD.s2t[s]||[]).indexOf(tn)>=0)||'';
  let aliasNote='';
  const used=[...new Set((expr.match(/\\/\\/#([A-Za-z0-9_]+)#\\//g)||[]).map(x=>x.replace(/\\/\\/#|#\\//g,'')))];
  used.forEach(a=>{{ if(ALIASES[a]) aliasNote+='<div class="meta">#'+esc(a)+'# \u2192 '+esc(ALIASES[a].module||'')+(ALIASES[a].desc?' ('+esc(ALIASES[a].desc)+')':'')+'</div>'; }});
  const panel=document.getElementById('panel');
  if(panel){{
    panel.innerHTML='<h3>'+esc(tn)+' \u2014 transition</h3>'+
      '<div class="act"><div class="h">'+esc(from)+' \u2192 '+esc(to)+'</div>'+
      '<div class="expr">'+esc(expr||'(no expression)')+'</div>'+aliasNote+'</div>';
  }}
}}

// ── item 2: hand-drag panning of the SFC (grab to scroll the .diagram box) ──
function syncSvgWidth(){{
  // core sizes the SVG with min-width:100% + CSS transform:scale() for zoom.
  // A CSS transform does NOT grow the container's scrollWidth, so there's no
  // horizontal scroll range to pan through. We give the SVG an explicit width
  // equal to viewBoxWidth * currentZoom, so the container can actually scroll
  // horizontally (and the existing scale transform lines up on top of it).
  document.querySelectorAll('.block:not(.hidden) svg.sfc').forEach(function(svg){{
    const vb=(svg.getAttribute('viewBox')||'').split(/\\s+/);
    const vbw=parseFloat(vb[2])||0, vbh=parseFloat(vb[3])||0; if(!vbw) return;
    // read the zoom scale core applied via transform:scale(z), then NEUTRALIZE it
    // (otherwise explicit width + transform would double-scale) and drive both
    // dimensions by explicit size so the container scrolls on both axes.
    let z=1; const tr=svg.style.transform||''; const m=tr.match(/scale\\(([-0-9.]+)\\)/); if(m) z=parseFloat(m[1])||1;
    const dia=svg.closest('.diagram'); const avail=dia?dia.clientWidth:0;
    if(!avail||avail<50) return;   // not laid out yet — leave core's sizing intact
    const baseW=avail;   // at zoom 1 the SVG fits the container width (min-width:100%)
    svg.style.transform='none';
    svg.style.transformOrigin='0 0';
    svg.style.minWidth='0';
    svg.style.width=(baseW*z)+'px';
    if(vbh) svg.style.height=((baseW*z)*(vbh/vbw))+'px';
  }});
}}
function initPan(){{
  const dia=document.querySelector('.diagram');
  if(!dia||dia._panWired) return; dia._panWired=1;
  syncSvgWidth();
  // re-sync when zoom buttons are used (core's applyZoom changes the transform)
  ['zoomIn','zoomOut','zoomReset'].forEach(function(fn){{
    if(typeof window[fn]==='function' && !window[fn]._wrapped){{
      const orig=window[fn]; const w=function(){{ orig.apply(this,arguments); setTimeout(syncSvgWidth,0); }};
      w._wrapped=1; window[fn]=w;
    }}
  }});
  let panning=false, sx=0, sy=0, sl=0, st=0;
  dia.style.cursor='grab';
  dia.addEventListener('mousedown',function(e){{
    if(e.target.closest('.step, .trans, .controls, button, a')) return;  // keep step/trans clicks
    panning=true; sx=e.clientX; sy=e.clientY; sl=dia.scrollLeft; st=dia.scrollTop;
    dia.style.cursor='grabbing'; e.preventDefault();
  }});
  window.addEventListener('mousemove',function(e){{
    if(!panning) return;
    dia.scrollLeft=sl-(e.clientX-sx); dia.scrollTop=st-(e.clientY-sy);
  }});
  window.addEventListener('mouseup',function(){{ if(panning){{ panning=false; dia.style.cursor='grab'; }} }});
  window.addEventListener('resize',syncSvgWidth);
}}

// record an operator answer for the SPECIFIC entry the walk is currently paused at,
// so prior loops' answers persist and a re-entered prompt asks again.
let shownPromptEntry=null;   // entry index of the prompt currently displayed
function recordAnswer(step,val){{
  // use the entry of the prompt actually on screen (could be a mid-trace loop
  // prompt reached via Play/Step), falling back to the final pause.
  let entry=shownPromptEntry;
  if(entry===null||entry===undefined) entry=(sim.pausedPrompt&&sim.pausedPrompt.step===step)?sim.pausedPrompt.entry:0;
  if(!answers[step]||!answers[step].byEntry) answers[step]={{byEntry:{{}}}};
  answers[step].byEntry[entry]={{input:val}};
}}

window.SIM={{
  tab:function(btn,which){{
    var col=btn.closest('.sim-tab-col'); if(!col) return;
    col.querySelectorAll('.sim-tab').forEach(function(t){{t.classList.toggle('on',t===btn);}});
    col.querySelectorAll('.sim-tabpanel').forEach(function(p){{p.classList.toggle('on',p.dataset.t===which);}});
  }},
  toggle:function(){{ const d=document.getElementById('sim-dock'); const on=d.classList.toggle('open');
    document.body.classList.toggle('sim-on',on);
    document.getElementById('sim-fab').classList.toggle('hidden',on);
    if(on){{ showRunBlock(); setMode(curMode); initResize(); initPan(); initTransClick(); if(!sim){{buildEdit();rewalk();idx=-1;prevWatch={{}};render();}} }}
    else {{ document.body.classList.remove('sim-min','mode-bottom','mode-left','mode-right','mode-float'); }} }},
  dock:function(mode){{ const wasMin=document.getElementById('sim-dock').classList.contains('min');
    if(wasMin) SIM.minimize(); setMode(mode); }},
  minimize:function(){{ const d=document.getElementById('sim-dock'); const m=d.classList.toggle('min');
    document.body.classList.toggle('sim-min',m);
    document.getElementById('sim-min').textContent=m?'\u25a1':'\u2013'; }},
  reset:function(){{ stop(); if(countdown){{clearInterval(countdown);countdown=null;}}
    Object.keys(answers).forEach(k=>delete answers[k]);
    Object.keys(overrides).forEach(k=>{{ if(k.indexOf('TM_COMPLETE')>=0) delete overrides[k]; }});
    idx=-1; prevWatch={{}}; rewalk(); idx=-1; render(); }},
  step:function(){{ stop(); if(idx>=sim.trace.length-1) idx=-1; stepFwd(); }},
  back:function(){{ stop(); stepBack(); }},
  play:function(){{ if(timer){{stop();return;}} if(idx>=sim.trace.length-1)idx=-1;
    document.getElementById('sim-play').textContent='\u23f8 Pause'; timer=setInterval(stepFwd,650); }},
  answer:function(step,val){{ recordAnswer(step,val); stop(); rewalk(); }},
  rerunStep:function(){{
    // re-execute the current step by re-anchoring the walk to this step's entry
    // (a fresh walk with current inputs), so its actions run again and any lever/
    // param change since is reflected. Useful to re-evaluate a step in place.
    if(!sim||idx<0) return;
    // find the step at the current position
    let step=null, entryN=0, seen={{}};
    for(let k=0;k<=idx&&k<sim.trace.length;k++){{ const ev=sim.trace[k];
      if(ev.kind==='enter'){{ if(ev.step) seen[ev.step]=(seen[ev.step]||0); if(k===idx||(idx<sim.trace.length&&sim.trace[idx].kind!=='enter'&&ev.step)) {{}} }} }}
    // simplest: current lastEnter step
    for(let k=idx;k>=0;k--){{ if(sim.trace[k].kind==='enter'){{ step=sim.trace[k].step; break; }} }}
    if(!step) return;
    stop();
    rewalk();  // fresh walk with current inputs
    // re-anchor idx to the first enter of that step
    for(let k=0;k<sim.trace.length;k++){{ if(sim.trace[k].kind==='enter'&&sim.trace[k].step===step){{ idx=k; break; }} }}
    render();
  }},
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

// ── enable hand-pan and transition-click on the SFC as soon as the phase view
// loads, so they work BEFORE the simulator is opened. Operates on whatever
// block is visible; re-runs when the user switches blocks.
function initTransClickAll(){{
  document.querySelectorAll('.block .trans').forEach(function(g){{
    if(g._transClick) return; g._transClick=1;
    g.style.cursor='pointer';
    g.addEventListener('click',function(e){{
      e.stopPropagation();
      var tn=g.dataset.trans;
      if(tn) showTransitionPanel(tn, g);
    }});
  }});
}}
function _initExplorerInteractions(){{
  try{{ initPan(); }}catch(e){{}}
  try{{ initTransClickAll(); }}catch(e){{}}
}}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',_initExplorerInteractions);
else _initExplorerInteractions();
document.addEventListener('click',function(e){{
  if(e.target && (e.target.closest('.blocktab')||e.target.closest('.tab')||e.target.closest('.controls'))){{
    setTimeout(_initExplorerInteractions, 30);
  }}
}});
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
