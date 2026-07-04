"""
device_panel.py — inline SVG device glyphs + the client script that animates them
from the device feedback models (device_sim.js) as the simulator steps.

This is Stage 3: a read-only device panel that shows, for the current step, every
device being driven, rendered as a valve/motor/pump glyph that animates from its
commanded state to its feedback state (red/green, open/closed). It reuses the
per-step device registry produced by feedback_sim.

The glyphs are simple, legible SVG; a valve is a bowtie that fills green when open,
a motor/pump is a circle that turns green and spins when running.
"""

import json
import html


def build_device_panel_html(registry_json):
    """Return the HTML block (panel + embedded registry + animation script) that the
    sim overlay injects. registry_json is the JSON-serialisable device registry from
    feedback_sim.build_device_registry."""
    reg = json.dumps(registry_json).replace('</', '<\\/')
    return _PANEL_HTML.replace('__REGISTRY__', reg)


DEVICE_CSS = """
.dev-panel{border:1px solid var(--border,#e2e8f0);border-radius:9px;background:#fff;padding:10px 12px;margin-top:8px}
.dev-panel h4{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#64748b;margin:0 0 9px;font-weight:700}
.dev-grid{display:flex;flex-wrap:wrap;gap:10px}
.dev-item{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:78px;padding:8px 6px;border:1px solid #eef2f7;border-radius:8px;background:#fafbfc}
.dev-item svg{display:block}
.dev-name{font-size:10.5px;font-weight:600;color:#334155;text-align:center;word-break:break-word;max-width:88px}
.dev-tag{font-size:9.5px;color:#94a3b8;font-family:ui-monospace,Menlo,monospace}
.dev-state{font-size:10px;font-weight:700;padding:1px 7px;border-radius:5px}
.dev-state.on{background:#dcfce7;color:#166534}
.dev-state.off{background:#fee2e2;color:#991b1b}
.dev-state.moving{background:#fef9c3;color:#854d0e}
.dev-none{color:#94a3b8;font-size:12px;font-style:italic}
@keyframes devspin{to{transform:rotate(360deg)}}
.dev-rotor.spinning{animation:devspin 1.1s linear infinite;transform-origin:center}
"""


_PANEL_HTML = """
<div class="dev-panel" id="devPanel">
  <h4>Devices driven by this step</h4>
  <div class="dev-grid" id="devGrid"><span class="dev-none">Step the sequence to drive devices\u2026</span></div>
</div>
<script>
(function(){
  var REG=__REGISTRY__;
  var DS=window.DeviceSim;
  if(!DS){ return; }
  // clone initial device states so we can advance them
  var devices={};
  Object.keys(REG.devices||{}).forEach(function(role){ devices[role]=JSON.parse(JSON.stringify(REG.devices[role])); });

  function valveSVG(g){
    var fill=g.open?'#16a34a':'#cbd5e1';
    return '<svg width="46" height="34" viewBox="0 0 46 34">'
      +'<line x1="4" y1="17" x2="42" y2="17" stroke="#94a3b8" stroke-width="2"/>'
      +'<path d="M15 8 L31 26 L31 8 L15 26 Z" fill="'+fill+'" stroke="#475569" stroke-width="1.4"/>'
      +'</svg>';
  }
  function motorSVG(g){
    var fill=g.running?'#16a34a':'#ef4444';
    var spin=g.running?' spinning':'';
    return '<svg width="40" height="40" viewBox="0 0 40 40">'
      +'<circle cx="20" cy="20" r="15" fill="'+fill+'" stroke="#475569" stroke-width="1.5"/>'
      +'<g class="dev-rotor'+spin+'"><path d="M20 9 L20 31 M9 20 L31 20" stroke="#fff" stroke-width="2.2"/></g>'
      +'</svg>';
  }
  function analogSVG(g){
    var pct=Math.max(0,Math.min(100,g.pct||0));
    var h=Math.round(24*pct/100);
    return '<svg width="34" height="34" viewBox="0 0 34 34">'
      +'<rect x="9" y="5" width="16" height="24" rx="2" fill="#eef2f7" stroke="#94a3b8"/>'
      +'<rect x="9" y="'+(29-h)+'" width="16" height="'+h+'" rx="2" fill="#16a34a"/>'
      +'</svg>';
  }
  function glyphSVG(g){
    if(g.kind==='valve') return valveSVG(g);
    if(g.kind==='motor'||g.kind==='pump') return motorSVG(g);
    if(g.kind==='analog_valve') return analogSVG(g);
    return '<svg width="34" height="34"><rect x="6" y="6" width="22" height="22" rx="3" fill="#e2e8f0"/></svg>';
  }
  function stateClass(g){ if(g.moving) return 'moving'; if(g.open||g.running||(g.pct&&g.pct>1)) return 'on'; return 'off'; }

  function render(plan){
    var grid=document.getElementById('devGrid'); if(!grid) return;
    if(!plan||!plan.length){ grid.innerHTML='<span class="dev-none">This step drives no devices.</span>'; return; }
    grid.innerHTML='';
    plan.forEach(function(c){
      var st=devices[c.role]; if(!st) return;
      var g=DS.glyphState(st);
      var item=document.createElement('div'); item.className='dev-item';
      item.innerHTML=glyphSVG(g)
        +'<div class="dev-name">'+c.role+'</div>'
        +(c.tag&&c.tag!==c.role?'<div class="dev-tag">'+c.tag+'</div>':'')
        +'<div class="dev-state '+stateClass(g)+'">'+g.label+'</div>';
      grid.appendChild(item);
    });
  }

  // drive the devices for a given step name and animate to feedback
  var animTimer=null;
  window.__devStep=function(stepName){
    var plan=(REG.steps||{})[stepName]||[];
    plan.forEach(function(c){ var st=devices[c.role]; if(st) DS.command(st, c.command); });
    render(plan);
    if(animTimer) clearInterval(animTimer);
    var ticks=0;
    animTimer=setInterval(function(){
      var anyMoving=false;
      plan.forEach(function(c){ var st=devices[c.role]; if(st){ DS.advance(st, 0.2); if(!DS.settled(st)) anyMoving=true; } });
      render(plan);
      ticks++;
      if(!anyMoving || ticks>60){ clearInterval(animTimer); animTimer=null; }
    }, 120);
  };
  window.__devReset=function(){
    Object.keys(REG.devices||{}).forEach(function(role){ devices[role]=JSON.parse(JSON.stringify(REG.devices[role])); });
    var grid=document.getElementById('devGrid'); if(grid) grid.innerHTML='<span class="dev-none">Step the sequence to drive devices\u2026</span>';
  };
})();
</script>
"""
