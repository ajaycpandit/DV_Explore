"""
sfc_interact.py — inject pan + transition-click interaction into an SFC HTML view
that does NOT have the full simulator overlay (EM command SFCs, and any standalone
SFC view). Reuses the same UX as the simulator: grab-to-pan the diagram, and click a
transition to see its expression in the side panel.

The core SFC builder (frozen) emits `const DATA = {...}` with per-block `trans`
(name -> {expr, desc}) and transition elements carrying `data-trans`. This injector
reads that DATA directly, so it needs no separate payload.
"""

INTERACT_JS = r"""
<script>
(function(){
  function curBlockData(){
    try{
      if(typeof DATA==='undefined') return null;
      var key=(typeof curBlock!=='undefined')?curBlock:Object.keys(DATA)[0];
      return DATA[key]||null;
    }catch(e){ return null; }
  }
  // ── transition click -> show expression in the panel ──
  function showTrans(g){
    var tn=g.getAttribute('data-trans'); if(!tn) return;
    var bd=curBlockData();
    var t=(bd&&bd.trans&&bd.trans[tn])||{};
    var expr=(t.expr!==undefined?t.expr:(typeof t==='string'?t:''))||'';
    var desc=t.desc||'';
    document.querySelectorAll('.step.sel,.trans.sel').forEach(function(n){n.classList.remove('sel');});
    g.classList.add('sel');
    var panel=document.getElementById('panel');
    if(!panel){
      // no side panel in this view — create a floating one
      panel=document.createElement('div');
      panel.id='panel'; panel.className='sfc-ipanel';
      document.body.appendChild(panel);
    }
    panel.innerHTML='<h3 style="margin:0 0 6px;font-size:12px;color:#7c3aed">'+esc(tn)+' — transition</h3>'
      +(desc?'<div style="color:#64748b;font-size:12px;margin-bottom:4px">'+esc(desc)+'</div>':'')
      +'<div style="font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#334155;white-space:pre-wrap;word-break:break-word">'
      +esc(expr||'(no expression — state transition)')+'</div>';
    panel.style.display='block';
  }
  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  function wireTrans(){
    document.querySelectorAll('.trans[data-trans]').forEach(function(g){
      if(g._wired) return; g._wired=1; g.style.cursor='pointer';
      g.addEventListener('click',function(e){ e.stopPropagation(); showTrans(g); });
    });
  }
  // ── grab-to-pan the diagram ──
  function syncWidth(){
    document.querySelectorAll('.diagram svg').forEach(function(svg){
      var vb=(svg.getAttribute('viewBox')||'').split(/\s+/);
      var vbw=parseFloat(vb[2])||0, vbh=parseFloat(vb[3])||0; if(!vbw) return;
      var z=1; var tr=svg.style.transform||''; var m=tr.match(/scale\(([-0-9.]+)\)/); if(m) z=parseFloat(m[1])||1;
      var dia=svg.closest('.diagram'); var avail=dia?dia.clientWidth:0; if(!avail||avail<50) return;
      svg.style.transform='none'; svg.style.transformOrigin='0 0'; svg.style.minWidth='0';
      svg.style.width=(avail*z)+'px'; if(vbh) svg.style.height=((avail*z)*(vbh/vbw))+'px';
    });
  }
  function initPan(){
    var dia=document.querySelector('.diagram'); if(!dia||dia._pan) return; dia._pan=1;
    syncWidth();
    ['zoomIn','zoomOut','zoomReset'].forEach(function(fn){
      if(typeof window[fn]==='function' && !window[fn]._w){ var o=window[fn]; var w=function(){o.apply(this,arguments);setTimeout(syncWidth,0);}; w._w=1; window[fn]=w; }
    });
    var panning=false,sx=0,sy=0,sl=0,st=0;
    dia.style.cursor='grab';
    dia.addEventListener('mousedown',function(e){
      if(e.target.closest('.step, .trans, .controls, button, a')) return;
      panning=true; sx=e.clientX; sy=e.clientY; sl=dia.scrollLeft; st=dia.scrollTop;
      dia.style.cursor='grabbing'; e.preventDefault();
    });
    window.addEventListener('mousemove',function(e){ if(!panning)return; dia.scrollLeft=sl-(e.clientX-sx); dia.scrollTop=st-(e.clientY-sy); });
    window.addEventListener('mouseup',function(){ if(panning){panning=false;dia.style.cursor='grab';} });
    window.addEventListener('resize',syncWidth);
    // #3 (SFC scrolling): make the wheel useful over the diagram. Shift+wheel scrolls
    // horizontally; Ctrl/Cmd+wheel zooms (if the view exposes zoom fns); a plain wheel
    // scrolls the diagram vertically only while the pointer is over it and there's room,
    // otherwise it falls through to the page so you're never "trapped".
    dia.addEventListener('wheel',function(e){
      if(e.ctrlKey||e.metaKey){
        if(typeof window.zoomIn==='function' && typeof window.zoomOut==='function'){
          e.preventDefault(); (e.deltaY<0?window.zoomIn:window.zoomOut)(); setTimeout(syncWidth,0);
        }
        return;
      }
      if(e.shiftKey){ dia.scrollLeft += (e.deltaY||e.deltaX); e.preventDefault(); return; }
      // plain wheel: scroll the diagram vertically only if it can still scroll that way
      var canDown=dia.scrollTop < (dia.scrollHeight-dia.clientHeight-1) && e.deltaY>0;
      var canUp=dia.scrollTop>0 && e.deltaY<0;
      if(canDown||canUp){ dia.scrollTop += e.deltaY; e.preventDefault(); }
      // else: let the page scroll normally (no preventDefault)
    },{passive:false});
  }
  function initAll(){ try{initPan();}catch(e){} try{wireTrans();}catch(e){} try{interleaveTrans();}catch(e){} }

  // ── #obs4: interleave each step's transitions right after its action rows in the
  // table (the core buildTable lists steps+actions but groups/omits transitions) ──
  function interleaveTrans(){
    var tbody=document.querySelector('#tbody, table tbody'); if(!tbody) return;
    if(tbody.querySelector('.trow')) return; // already done
    var bd=curBlockData();
    var trans=(bd&&bd.trans)||window.__SFC_TRANS__||null;
    var s2t=window.__SFC_S2T__||(bd&&(bd.step_to_trans||bd.s2t))||null;
    var t2s=window.__SFC_T2S__||(bd&&(bd.trans_to_step||bd.t2s))||null;
    if(!trans||!s2t) return;
    function rowsFor(step){
      var ts=s2t[step]||[]; var html='';
      (Array.isArray(ts)?ts:[ts]).forEach(function(tn){
        var t=trans[tn]||{}; var expr=(t.expr!==undefined?t.expr:(typeof t==='string'?t:''))||'';
        var to=''; if(t2s){ var v=t2s[tn]; to=Array.isArray(v)?v[0]:(v||''); }
        html+='<tr class="arow trow"><td style="color:#7c3aed">\u25c7 '+esc(tn)+'</td><td>\u2192 '+esc(to||'?')+'</td><td>transition</td><td>T</td><td class="expr">'+esc(expr||'(state transition)')+'</td><td></td></tr>';
      });
      return html;
    }
    var rows=Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    var pending=null;
    function stepNameOf(tr){ var td=tr.querySelector('td'); if(!td) return ''; var m=(td.textContent||'').match(/^([A-Za-z0-9_]+)/); return m?m[1]:''; }
    for(var i=0;i<rows.length;i++){
      if(rows[i].classList.contains('step-row')){
        if(pending){ var hp=rowsFor(pending); if(hp) rows[i].insertAdjacentHTML('beforebegin',hp); }
        pending=stepNameOf(rows[i]);
      }
    }
    if(pending){ var hf=rowsFor(pending); if(hf) tbody.insertAdjacentHTML('beforeend',hf); }
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',initAll);
  else initAll();
  // re-init after block-tab switches (core rebuilds the SVG)
  document.addEventListener('click',function(e){
    if(e.target && (e.target.closest('.blocktab')||e.target.closest('.tab')||e.target.closest('.ctab'))) setTimeout(initAll,40);
  });
  [200,600].forEach(function(ms){ setTimeout(initAll,ms); });
})();
</script>
<style>
.sfc-ipanel{position:fixed;right:14px;bottom:14px;max-width:420px;max-height:40vh;overflow:auto;
  background:#fff;border:1px solid #e2e8f0;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.18);
  padding:12px 14px;z-index:9998;display:none}
.trans.sel rect,.trans.sel path{stroke:#7c3aed!important;stroke-width:2px!important}
.step.sel rect{stroke:#2563eb!important;stroke-width:2.5px!important}
</style>
"""


def inject_interactions(sfc_html, s2t=None, t2s=None, trans=None):
    """Insert the pan + transition-click script before </body> (or append).
    Optionally embeds step->transition maps so the table can interleave transitions
    after their steps even though the core DATA doesn't carry those maps."""
    if not sfc_html:
        return sfc_html
    extra = ''
    if s2t is not None:
        import json
        extra = ('<script>window.__SFC_S2T__=' + json.dumps(s2t).replace('</', '<\\/')
                 + ';window.__SFC_T2S__=' + json.dumps(t2s or {}).replace('</', '<\\/')
                 + ';window.__SFC_TRANS__=' + json.dumps(trans or {}).replace('</', '<\\/')
                 + ';</script>')
    payload = extra + INTERACT_JS
    if '</body>' in sfc_html:
        return sfc_html.replace('</body>', payload + '</body>', 1)
    return sfc_html + payload
