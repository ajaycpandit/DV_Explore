"""
DeltaV Database Explorer — navigable HTML site generator.

Renders the parsed catalog as a single self-contained browsable site:
  - left navigation tree (Areas -> Units -> class; Library -> CM/EM/Phase classes)
  - object detail panel with identity, class<->instance links, and references
  - clickable cross-references (instance -> class, class -> instances)

This is the skeleton (navigation model proven end-to-end). Detailed per-object
views (SFC diagrams, parameters) plug in as "leaf" views in later iterations.
"""

import html
import json

import fbd_bridge  # for the shared expression-popup modal assets


_CSS = """
*{box-sizing:border-box}
body{margin:0;font:14px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;height:100vh;display:flex;flex-direction:column;background:#f8fafc}
header{flex:0 0 auto;padding:12px 18px;background:#0f172a;color:#fff;display:flex;align-items:baseline;gap:14px}
header h1{margin:0;font-size:15px;font-weight:600}
header .sub{color:#94a3b8;font-size:12px}
.hdr-export{margin-left:auto;display:flex;gap:8px;align-self:center}
.exp-btn{display:inline-flex;align-items:center;gap:4px;padding:5px 12px;border-radius:7px;
  background:#1e293b;border:1px solid #334155;color:#cbd5e1;font-size:12px;font-weight:600;
  text-decoration:none;cursor:pointer}
.exp-btn:hover{background:#334155;color:#fff;border-color:#475569}
.main{flex:1 1 auto;display:flex;overflow:hidden}
.nav{flex:0 0 320px;overflow:auto;background:#fff;border-right:1px solid #e2e8f0;padding:8px 0}
.detail{flex:1 1 auto;overflow:auto;padding:20px 26px}
.navsec{padding:6px 14px 2px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#94a3b8}
.navsec-tog{cursor:pointer;user-select:none;display:flex;align-items:center;gap:5px;padding-top:9px}
.navsec-tog:hover{color:#475569}
.secarrow{font-size:10px;width:10px;display:inline-block}
.navitem{padding:4px 14px 4px 20px;cursor:pointer;font-size:13px;border-left:3px solid transparent;display:flex;align-items:center;gap:7px}
.navitem:hover{background:#f1f5f9}
.navitem.sel{background:#eff6ff;border-left-color:#2563eb;font-weight:600}
.navitem .badge{font-size:10px;padding:0 6px;border-radius:8px;color:#fff;flex:0 0 auto}
.navitem .ic-badge{display:inline-flex;align-items:center;justify-content:center;padding:2px;width:18px;height:18px;border-radius:5px}
.navitem .ic-badge svg{display:block}
.navchild{padding-left:40px}
.navchild2{padding-left:54px}
.navinst{align-items:center;padding-top:3px;padding-bottom:3px}
.navinst .inst-tag{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.navinst .inst-cls{color:#a3acba;font-size:10.5px;margin-left:auto;padding-left:8px;
  font-family:ui-monospace,Menlo,monospace;white-space:nowrap;flex:0 0 auto}
.navinst.sel .inst-cls{color:#6d28d9}
.badge.b-inst{background:#ede9fe;color:#6d28d9}
.bigbtn{margin-top:12px;width:100%;padding:9px 12px;border:1px solid #c7d2fe;background:#eef2ff;
  color:#4338ca;font-weight:600;font-size:13px;border-radius:8px;cursor:pointer}
.bigbtn:hover{background:#e0e7ff}
.navsearch{position:relative;padding:8px 12px;border-bottom:1px solid #eef2f7;background:#fff;position:sticky;top:0;z-index:5}
.navsearch input{width:100%;box-sizing:border-box;padding:7px 10px;border:1px solid #cbd5e1;
  border-radius:7px;font-size:13px;outline:none}
.navsearch input:focus{border-color:#2563eb;box-shadow:0 0 0 2px rgba(37,99,235,.15)}
.navres{position:absolute;left:12px;right:12px;top:46px;background:#fff;border:1px solid #cbd5e1;
  border-radius:8px;box-shadow:0 12px 30px rgba(15,23,42,.16);max-height:60vh;overflow:auto;z-index:20}
.navres-item{padding:7px 11px;cursor:pointer;font-size:13px;display:flex;align-items:center;gap:8px;
  border-bottom:1px solid #f1f5f9}
.navres-item:last-child{border-bottom:0}
.navres-item.act,.navres-item:hover{background:#eff6ff}
.navres-item .rtype{font-size:10px;color:#fff;border-radius:8px;padding:0 6px;flex:0 0 auto}
.navres-item .rname{font-weight:600;color:#0f172a}
.navres-empty{padding:10px 11px;color:#94a3b8;font-size:12px}
.navmode{display:flex;gap:0;margin-top:6px;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;width:fit-content}
.navmode .nm-btn{padding:3px 10px;background:#fff;border:0;cursor:pointer;font-size:11px;color:#64748b;font-weight:600}
.navmode .nm-btn+.nm-btn{border-left:1px solid #e2e8f0}
.navmode .nm-btn.active{background:#0891b2;color:#fff}
.navres-item .rsnip{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#475569;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.navres-item .rsnip mark,.navres-item .rname mark{background:#fde68a;color:#92400e;padding:0 1px;border-radius:2px}
.navres-item .rsub{font-size:10px;color:#94a3b8}
.navres-item.col{flex-direction:column;align-items:flex-start;gap:2px}
/* tree connector lines */
.navgroup{position:relative}
.navchildren{position:relative}
.navchildren .navchild{position:relative}
.navchildren .navchild::before{
  content:"";position:absolute;left:26px;top:0;bottom:50%;
  border-left:1.5px solid #d8dee6;border-bottom:1.5px solid #d8dee6;
  width:10px;
}
.navchildren .navchild:not(:last-child)::after{
  content:"";position:absolute;left:26px;top:50%;bottom:-2px;
  border-left:1.5px solid #d8dee6;
}
.navchildren .navchild::before{border-bottom-left-radius:3px}
.tree-line{border-left:1.5px solid #e2e8f0;margin-left:22px;padding-left:0}
.b-area{background:#0ea5e9}.b-unit{background:#10b981}.b-em{background:#8b5cf6}
.b-cm{background:#f59e0b}.b-phase{background:#ec4899}.b-recipe{background:#ef4444}
.b-composite{background:#64748b}.b-uclass{background:#059669}.b-fbtype{background:#0d9488}
.tog{cursor:pointer;user-select:none;color:#64748b;width:12px;display:inline-block}
h2.dt{margin:0 0 4px;font-size:20px}
.dt-type{display:inline-block;font-size:11px;color:#fff;padding:2px 9px;border-radius:10px;margin-bottom:12px}
.dt-desc{color:#475569;margin:0 0 16px;font-size:14px}
.kv{display:grid;grid-template-columns:160px 1fr;gap:4px 14px;font-size:13px;margin-bottom:18px;max-width:760px}
.kv .k{color:#64748b}
.card{border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin-bottom:14px;background:#fff;max-width:860px}
.card h3{margin:0 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:.03em;color:#475569}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:3px 10px;border:1px solid #cbd5e1;border-radius:14px;font-size:12px;cursor:pointer;background:#fff}
.chip:hover{border-color:#2563eb;color:#2563eb;background:#eff6ff}
.link{color:#2563eb;cursor:pointer;text-decoration:underline}
.empty{color:#94a3b8;font-style:italic}
.welcome{color:#475569;max-width:680px}
.welcome h2{font-size:18px}
/* detail panel tree */
.dtree{margin:6px 0 0 4px}
.dtree .tnode{position:relative;padding:3px 0 3px 22px;font-size:13px}
.dtree .tnode::before{content:"";position:absolute;left:6px;top:0;height:14px;width:12px;border-left:1.5px solid #cbd5e1;border-bottom:1.5px solid #cbd5e1;border-bottom-left-radius:3px}
.dtree .tnode:not(:last-child)::after{content:"";position:absolute;left:6px;top:14px;bottom:-3px;border-left:1.5px solid #cbd5e1}
.dtree .troot{font-weight:600;padding:2px 0}
.tnode .link{font-size:13px}
.phaseframe{width:100%;height:75vh;border:1px solid #e2e8f0;border-radius:6px;background:#fff}
.emtabs{display:flex;gap:6px;margin-bottom:12px}
.emtab{padding:7px 15px;border:1px solid #e2e8f0;border-radius:7px;background:#fff;cursor:pointer;font-size:13px;font-weight:600;color:#475569}
.emtab.on{background:#0f172a;color:#fff;border-color:#0f172a}
.empanel{display:none}.empanel.on{display:block}
.fbd-wrap{display:flex;flex-direction:column;gap:14px}
.fbd-diagram-card{border:1px solid #e2e8f0;border-radius:8px;background:#fcfcfd;overflow:hidden}
.fbd-head{padding:10px 14px;background:#f1f5f9;font-weight:600;font-size:13px;border-bottom:1px solid #e2e8f0}
.fbd-sub{color:#64748b;font-weight:400;font-size:12px}
.fbd-svg-holder{padding:10px;overflow:auto;max-height:78vh}
.fbd-info-card{border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;background:#fff}
.fbd-info-card h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:#475569}
.fbd-comp-link{border-color:#475569}
.fbd-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:4px}
.fbd-table th{text-align:left;padding:5px 8px;background:#f1f5f9;color:#475569;font-size:11px;border-bottom:1px solid #e2e8f0}
.fbd-table td{padding:4px 8px;border-bottom:1px solid #f1f5f9;vertical-align:top}
.fbd-table code{font-size:11px;background:#f8fafc;padding:1px 4px;border-radius:3px}
.fb-composite rect:first-of-type{transition:fill .15s}
.fb{cursor:default}
.stat{display:inline-block;margin:0 18px 10px 0}
.stat b{font-size:22px;display:block}
.stat span{font-size:12px;color:#64748b}
"""


def _badge(otype):
    m = {'Area': 'b-area', 'Unit Instance': 'b-unit', 'EM Class': 'b-em',
         'CM Class': 'b-cm', 'Phase Class': 'b-phase', 'Recipe': 'b-recipe',
         'Composite': 'b-composite', 'Unit Class': 'b-uclass'}
    return m.get(otype, 'b-composite')


_NAV_BADGE_CLS = {'area': 'b-area', 'unit': 'b-unit', 'em': 'b-em', 'cm': 'b-cm',
                  'inst': 'b-inst', 'phase': 'b-phase', 'recipe': 'b-recipe',
                  'composite': 'b-composite', 'uclass': 'b-uclass', 'fbtype': 'b-fbtype'}
_NAV_TITLE = {'area': 'Area', 'unit': 'Unit', 'em': 'Equipment Module',
              'cm': 'Control Module', 'inst': 'Control Module instance', 'phase': 'Phase',
              'recipe': 'Recipe', 'composite': 'Composite', 'uclass': 'Unit Class',
              'fbtype': 'Function Block Type'}
_NAV_ICON = {
    'area': '<rect x="2" y="3.2" width="11" height="2.1" rx="1"/><rect x="2" y="6.5" width="11" height="2.1" rx="1"/><rect x="2" y="9.8" width="11" height="2.1" rx="1"/>',
    'unit': '<path d="M3.5 3h8v5.5a4 4 0 0 1-8 0z"/>',
    'uclass': '<path d="M3.5 3h8v5.5a4 4 0 0 1-8 0z" fill="none" stroke="#fff" stroke-width="1.4"/>',
    'em': '<path d="M7.5 1.8l4.6 2.7v5.4l-4.6 2.7l-4.6-2.7V4.5z"/>',
    'cm': '<rect x="4" y="4" width="7" height="7" rx="1.3"/><rect x="2" y="5.6" width="1.6" height="1.2"/><rect x="2" y="8" width="1.6" height="1.2"/><rect x="11.4" y="5.6" width="1.6" height="1.2"/><rect x="11.4" y="8" width="1.6" height="1.2"/>',
    'inst': '<rect x="4" y="4" width="7" height="7" rx="1.3"/><rect x="2" y="5.6" width="1.6" height="1.2"/><rect x="2" y="8" width="1.6" height="1.2"/><rect x="11.4" y="5.6" width="1.6" height="1.2"/><rect x="11.4" y="8" width="1.6" height="1.2"/>',
    'phase': '<path d="M4.5 3l7 4.5l-7 4.5z"/>',
    'recipe': '<path d="M4 2.3h4.7l2.8 2.8v7.6h-7.5z"/><rect x="5.4" y="7" width="4.2" height="0.9" rx="0.4" fill="#fff" opacity=".55"/><rect x="5.4" y="9" width="4.2" height="0.9" rx="0.4" fill="#fff" opacity=".55"/>',
    'composite': '<rect x="2.6" y="2.6" width="6.3" height="6.3" rx="1" fill="none" stroke="#fff" stroke-width="1.4"/><rect x="6.1" y="6.1" width="6.3" height="6.3" rx="1"/>',
    'fbtype': '<rect x="3.2" y="3.2" width="8.6" height="8.6" rx="1.6"/><rect x="5.4" y="5.4" width="4.2" height="4.2" rx="0.8" fill="#fff" opacity=".5"/>',
}


def _nav_badge(key):
    cls = _NAV_BADGE_CLS.get(key, 'b-composite')
    title = _NAV_TITLE.get(key, key)
    return (f'<span class="badge ic-badge {cls}" title="{title}">'
            f'<svg viewBox="0 0 15 15" width="12" height="12" fill="#fff" aria-hidden="true">'
            f'{_NAV_ICON.get(key, "")}</svg></span>')


def build_explorer_html(catalog, fname, phase_views=None, fbd_views=None, em_views=None,
                        param_index=None, expr_index=None, export_token=None):
    """phase_views: optional {phase_name: interactive_html} to embed as drill-down
    leaf views for Phase Class objects."""
    phase_views = phase_views or {}
    fbd_views = fbd_views or {}
    em_views = em_views or {}
    summary = {
        'Areas': len(catalog['areas']),
        'Unit instances': len(catalog['units']),
        'Unit classes': len(catalog['unit_classes']),
        'EM classes': len(catalog['em_classes']),
        'CM classes': len(catalog['cm_classes']),
        'Phase classes': len(catalog['phase_classes']),
        'Recipes': len(catalog['recipes']),
        'Composite classes': len([c for c in catalog['composites'] if c.get('scope') == 'class']),
        'FB types': len(catalog['fb_types']),
    }

    # build a flat object dict for JS: id -> full record
    objs = {}

    def put(oid, otype, rec):
        objs[oid] = dict(rec, _id=oid, _type=otype)

    for a in catalog['areas']:
        put('area:' + a['name'], 'Area', a)
    for u in catalog['units']:
        put('unit:' + u['name'], 'Unit Instance', u)
    for c in catalog['unit_classes']:
        put('uclass:' + c['name'], 'Unit Class',
            dict(c, instances=catalog['instances_by_class'].get(c['name'], [])))
    for c in catalog['em_classes']:
        put('em:' + c['name'], 'EM Class', c)
    for c in catalog['cm_classes']:
        put('cm:' + c['name'], 'CM Class', c)
    for p in catalog['phase_classes']:
        put('phase:' + p['name'], 'Phase Class', p)
    for r in catalog['recipes']:
        put('recipe:' + r['name'], 'Recipe', r)
    for c in catalog['composites']:
        disp = c.get('description') if c.get('anonymous') and c.get('description') else c['name']
        put('composite:' + c['name'], 'Composite', dict(c, _disp=disp))
    for t in catalog['fb_types']:
        put('fbtype:' + t['name'], 'FB Type', t)

    data_json = json.dumps({'objs': objs, 'summary': summary,
                            'unit_phases': catalog.get('unit_phases', {}),
                            'unit_ems': catalog.get('unit_ems', {}),
                            'em_cms': catalog.get('em_cms', {}),
                            'used_by': catalog.get('class_used_by', {}),
                            'instances': catalog.get('instances', {}),
                            'parent_instances': catalog.get('parent_instances', {})})
    phase_views_json = json.dumps(phase_views)
    fbd_views_json = json.dumps(fbd_views)
    em_views_json = json.dumps(em_views)
    param_index_json = json.dumps(param_index or {})
    expr_index_json = json.dumps(expr_index or [])

    js = """
const DB = __DATA__;
const PHASE_VIEWS = __PHASE_VIEWS__;
const FBD_VIEWS = __FBD_VIEWS__;
const EM_VIEWS = __EM_VIEWS__;
const PARAM_INDEX = __PARAM_INDEX__;
const EXPR_INDEX = __EXPR_INDEX__;
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function badge(t){const m={'Area':'b-area','Unit Instance':'b-unit','EM Class':'b-em','CM Class':'b-cm','Phase Class':'b-phase','Recipe':'b-recipe','Composite':'b-composite','Unit Class':'b-uclass','FB Type':'b-fbtype'};return m[t]||'b-composite';}
function badgeColor(t){const m={'b-area':'#0ea5e9','b-unit':'#6366f1','b-em':'#0f766e','b-cm':'#7c3aed','b-phase':'#b45309','b-recipe':'#be123c','b-composite':'#475569','b-uclass':'#2563eb','b-fbtype':'#334155'};if(t==='Parameter')return '#0891b2';if(t==='Instance')return '#6d28d9';return m[badge(t)]||'#475569';}

// ── global search: Names | Expressions | Values ──
var SIDX=null, SRES=[], SSEL=-1, SMODE='names';
function searchIndex(){
  if(SIDX)return SIDX;
  SIDX=[];
  for(var id in DB.objs){var o=DB.objs[id];SIDX.push({id:id,name:o.name||'',type:o._type||'',desc:o.description||''});}
  for(var pn in PARAM_INDEX){SIDX.push({id:'param:'+pn,name:pn,type:'Parameter',desc:''});}
  for(var iid in (DB.instances||{})){var ins=DB.instances[iid];SIDX.push({id:'inst:'+iid,name:ins.tag,type:'Instance',desc:ins.cls});}
  SIDX.sort(function(a,b){return a.name.localeCompare(b.name);});
  return SIDX;
}
function escRe(s){return s.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');}
function hiQ(t,q){if(!q)return esc(t);try{return esc(t).replace(new RegExp('('+escRe(q)+')','ig'),'<mark>$1</mark>');}catch(e){return esc(t);}}
function navMode(btn,m){
  SMODE=m;
  document.querySelectorAll('.navmode .nm-btn').forEach(b=>b.classList.toggle('active',b===btn));
  var q=document.getElementById('navq');
  q.placeholder=(m==='expr'?'Search expression logic…':m==='values'?'Search configured values…':'Search…  (Ctrl-K)');
  navSearch(q.value); q.focus();
}
function navSearch(q){
  var box=document.getElementById('navres');
  q=(q||'').trim();
  if(!q){box.style.display='none';box.innerHTML='';SRES=[];SSEL=-1;return;}
  var ql=q.toLowerCase(), out=[], h='';
  if(SMODE==='expr'){
    for(var i=0;i<EXPR_INDEX.length && out.length<60;i++){
      var pos=(EXPR_INDEX[i].e||'').toLowerCase().indexOf(ql);
      if(pos>=0) out.push({i:i,pos:pos});
    }
    SRES=out;SSEL=out.length?0:-1;
    if(!out.length){box.innerHTML='<div class="navres-empty">No expression contains "'+esc(q)+'"</div>';box.style.display='block';return;}
    out.forEach(function(r,k){
      var e=EXPR_INDEX[r.i], st=Math.max(0,r.pos-22);
      var snip=(st>0?'…':'')+e.e.slice(st,r.pos+q.length+44).replace(/\\s+/g,' ');
      h+='<div class="navres-item col'+(k===0?' act':'')+'" data-i="'+r.i+'" onmousedown="openExpr(this.dataset.i)">'+
         '<span class="rsub"><span class="rtype" style="background:#7c3aed">'+esc(e.m)+'</span> '+esc(e.blk)+' · '+esc(e.attr)+'</span>'+
         '<span class="rsnip">'+hiQ(snip,q)+'</span></div>';
    });
  } else if(SMODE==='values'){
    for(var pn in PARAM_INDEX){
      var vals=PARAM_INDEX[pn].vals||[];
      for(var j=0;j<vals.length;j++){
        if(String(vals[j].cv).toLowerCase().indexOf(ql)>=0){ out.push({name:pn,cv:vals[j].cv,m:vals[j].m}); break; }
      }
      if(out.length>=60)break;
    }
    SRES=out;SSEL=out.length?0:-1;
    if(!out.length){box.innerHTML='<div class="navres-empty">No configured value matches "'+esc(q)+'"</div>';box.style.display='block';return;}
    out.forEach(function(r,k){
      h+='<div class="navres-item'+(k===0?' act':'')+'" data-id="param:'+esc(r.name)+'" onmousedown="navPick(this.dataset.id)">'+
         '<span class="rtype" style="background:#0891b2">Value</span>'+
         '<span class="rname">'+esc(r.name)+' = '+hiQ(String(r.cv),q)+'</span>'+
         '<span class="rsub" style="margin-left:6px">'+esc(r.m)+'</span></div>';
    });
  } else {
    var idx=searchIndex();
    for(var i=0;i<idx.length && out.length<40;i++){
      var e=idx[i];
      if(e.name.toLowerCase().indexOf(ql)>=0 || e.type.toLowerCase().indexOf(ql)>=0) out.push(e);
    }
    SRES=out;SSEL=out.length?0:-1;
    if(!out.length){box.innerHTML='<div class="navres-empty">No matches for "'+esc(q)+'"</div>';box.style.display='block';return;}
    out.forEach(function(e,k){
      h+='<div class="navres-item'+(k===0?' act':'')+'" data-id="'+esc(e.id)+'" onmousedown="navPick(this.dataset.id)">'+
         '<span class="rtype" style="background:'+badgeColor(e.type)+'">'+esc(e.type)+'</span>'+
         '<span class="rname">'+hiQ(e.name,q)+'</span></div>';
    });
  }
  box.innerHTML=h;box.style.display='block';
}
function openExpr(i){
  var e=EXPR_INDEX[i]; if(!e)return;
  document.getElementById('navres').style.display='none';
  fbdEnsureModal();
  document.getElementById('fbdExprTitle').textContent=e.blk+' · '+e.attr;
  document.getElementById('fbdExprSub').textContent=e.m+(e.kind?' ('+e.kind+')':'');
  document.getElementById('fbdExprBody').innerHTML='<pre>'+fbdHL(e.e)+'</pre>';
  document.getElementById('fbdExprModal').style.display='flex';
}
function navPick(id){
  document.getElementById('navres').style.display='none';
  document.getElementById('navq').value='';
  SRES=[];SSEL=-1;
  show(id);
}
function navSearchKey(ev){
  var box=document.getElementById('navres');
  if(ev.key==='Escape'){box.style.display='none';ev.target.value='';SRES=[];return;}
  if(!SRES.length)return;
  if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){
    ev.preventDefault();
    SSEL+=(ev.key==='ArrowDown'?1:-1);
    if(SSEL<0)SSEL=SRES.length-1; if(SSEL>=SRES.length)SSEL=0;
    var items=box.querySelectorAll('.navres-item');
    items.forEach(function(it,i){it.classList.toggle('act',i===SSEL);});
    if(items[SSEL])items[SSEL].scrollIntoView({block:'nearest'});
  } else if(ev.key==='Enter' && SSEL>=0){
    ev.preventDefault();
    var r=SRES[SSEL];
    if(SMODE==='expr') openExpr(r.i);
    else if(SMODE==='values') navPick('param:'+r.name);
    else navPick(r.id);
  }
}
document.addEventListener('keydown',function(e){
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();var q=document.getElementById('navq');if(q){q.focus();q.select();}}
});
document.addEventListener('click',function(e){
  var s=document.querySelector('.navsearch');
  if(s&&!s.contains(e.target)){var b=document.getElementById('navres');if(b)b.style.display='none';}
});

function renderObj(id){
  const o=DB.objs[id]; if(!o)return;
  document.querySelectorAll('.navitem').forEach(n=>n.classList.toggle('sel',n.dataset.id===id));
  let h='<h2 class="dt">'+esc(o.name)+'</h2>';
  h+='<span class="dt-type '+badge(o._type)+'">'+o._type+'</span>';
  if(o.description) h+='<p class="dt-desc">'+esc(o.description)+'</p>';
  // key-values
  h+='<div class="kv">';
  if(o.category) h+='<div class="k">Category</div><div>'+esc(o.category)+'</div>';
  if(o.area) h+='<div class="k">Area</div><div><span class="link" onclick="show(\\'area:'+esc(o.area)+'\\')">'+esc(o.area)+'</span></div>';
  if(o.area_path) h+='<div class="k">Area path</div><div>'+esc(o.area_path)+'</div>';
  if(o.control_type) h+='<div class="k">Control type</div><div>'+esc(o.control_type)+'</div>';
  if(o.type && o._type==='Recipe') h+='<div class="k">Recipe type</div><div>'+esc(o.type)+'</div>';
  h+='</div>';

  // "Used by" — every place this class is referenced as a child module
  // (EM embedding a CM, unit embedding an EM, ...). Grouped by parent.
  if(['CM Class','EM Class','Unit Class','Composite'].includes(o._type)){
    const refs=(DB.used_by&&DB.used_by[o.name])||[];
    if(refs.length){
      const byParent={};
      refs.forEach(r=>{(byParent[r.parent]=byParent[r.parent]||[]).push(r.instance);});
      const parents=Object.keys(byParent).sort();
      h+='<div class="card"><h3>Used by ('+parents.length+(parents.length===1?' object':' objects')+', '+refs.length+' instance'+(refs.length===1?'':'s')+')</h3><div class="dtree">';
      parents.forEach(p=>{
        const pid=(DB.objs['em:'+p]?'em:':DB.objs['cm:'+p]?'cm:':DB.objs['uclass:'+p]?'uclass:':'')+p;
        const plink=DB.objs[pid]?'<span class="link" onclick="show(\\''+pid+'\\')">'+esc(p)+'</span>':esc(p);
        h+='<div class="troot">'+plink+'</div>';
        byParent[p].forEach(inst=>{h+='<div class="tnode"><span style="color:#475569">'+esc(inst)+'</span></div>';});
      });
      h+='</div></div>';
    }
  }

  if(o._type==='Unit Instance' && o.class){
    const cid='uclass:'+o.class;
    const has=DB.objs[cid];
    h+='<div class="card"><h3>Class</h3>';
    h+= has ? '<span class="chip" onclick="show(\\''+cid+'\\')">'+esc(o.class)+'</span>'
            : '<span class="empty">'+esc(o.class)+' (class not in this export)</span>';
    h+='</div>';
  }
  if(o._type==='Unit Class' && o.instances){
    h+='<div class="card"><h3>Instances ('+o.instances.length+')</h3><div class="chips">';
    if(o.instances.length) o.instances.forEach(n=>{h+='<span class="chip" onclick="show(\\'unit:'+esc(n)+'\\')">'+esc(n)+'</span>';});
    else h+='<span class="empty">No instances in this export</span>';
    h+='</div></div>';
  }
  if(o._type==='Area' && o.units){
    h+='<div class="card"><h3>Units ('+o.units.length+')</h3><div class="dtree"><div class="troot">'+esc(o.name)+'</div>';
    o.units.forEach(u=>{h+='<div class="tnode"><span class="link" onclick="show(\\'unit:'+esc(u.name)+'\\')">'+esc(u.name)+'</span> <span style="color:#94a3b8">· '+esc(u.class)+'</span></div>';});
    h+='</div></div>';
  }
  // Unit Class -> its phases and EMs (tree)
  if(o._type==='Unit Class'){
    const phs=DB.unit_phases[o.name]||[], ems=DB.unit_ems[o.name]||[];
    if(phs.length||ems.length){
      h+='<div class="card"><h3>Contains</h3><div class="dtree"><div class="troot">'+esc(o.name)+'</div>';
      ems.forEach(e=>{h+='<div class="tnode"><span class="link" onclick="show(\\'em:'+esc(e)+'\\')">'+esc(e)+'</span> <span style="color:#94a3b8">· EM</span></div>';});
      phs.forEach(p=>{h+='<div class="tnode"><span class="link" onclick="show(\\'phase:'+esc(p)+'\\')">'+esc(p)+'</span> <span style="color:#94a3b8">· Phase</span></div>';});
      h+='</div></div>';
    }
  }
  // EM Class -> its CMs (tree)
  if(o._type==='EM Class'){
    const cms=DB.em_cms[o.name]||[];
    if(cms.length){
      h+='<div class="card"><h3>Control Modules</h3><div class="dtree"><div class="troot">'+esc(o.name)+'</div>';
      cms.forEach(c=>{h+='<div class="tnode"><span class="link" onclick="show(\\'cm:'+esc(c)+'\\')">'+esc(c)+'</span></div>';});
      h+='</div></div>';
    }
  }
  // placeholder for future leaf views
  if(o._type==='Phase Class'){
    if(PHASE_VIEWS[o.name]){
      h+='<div class="card" style="max-width:none"><h3>Phase logic — interactive</h3>';
      h+='<iframe class="phaseframe" srcdoc="'+PHASE_VIEWS[o.name].replace(/&/g,"&amp;").replace(/"/g,"&quot;")+'"></iframe>';
      h+='</div>';
    } else {
      h+='<div class="card"><h3>Phase logic</h3><span class="empty">No parsed logic available for this phase in this export.</span></div>';
    }
  }
  // CM Class / Composite -> Function Block Diagram (FHX structure/wiring)
  if(o._type==='CM Class' || o._type==='Composite'){
    if(FBD_VIEWS[o.name]){
      h+='<div class="card" style="max-width:none">'+FBD_VIEWS[o.name]+'</div>';
      setTimeout(wireFbdLinks, 0);
    } else {
      h+='<div class="card"><h3>Detail</h3><span class="empty">No function block diagram in this export (this object may be an expression/action block or referenced type).</span></div>';
    }
  }
  // EM Class -> full view: Function Blocks + Command/State Logic + Control Modules
  if(o._type==='EM Class'){
    const ev=EM_VIEWS[o.name];
    if(ev){
      h+='<div class="card" style="max-width:none">';
      h+='<div class="emtabs">';
      h+='<button class="emtab on" data-e="fb" onclick="emTab(this,\\'fb\\')">Function Blocks</button>';
      if(ev.state) h+='<button class="emtab" data-e="state" onclick="emTab(this,\\'state\\')">Command / State Logic</button>';
      if(ev.cms&&ev.cms.length) h+='<button class="emtab" data-e="cms" onclick="emTab(this,\\'cms\\')">Control Modules ('+ev.cms.length+')</button>';
      h+='</div>';
      h+='<div class="empanel on" data-e="fb" id="empanel_fb">'+(ev.fbd||'<span class="empty">No function block layer.</span>')+'</div>';
      if(ev.state) h+='<div class="empanel" data-e="state"><iframe class="phaseframe" srcdoc="'+ev.state.replace(/&/g,"&amp;").replace(/"/g,"&quot;")+'"></iframe></div>';
      if(ev.cms&&ev.cms.length){
        h+='<div class="empanel" data-e="cms"><div class="chips">';
        ev.cms.forEach(c=>{h+='<span class="chip" onclick="show(\\'cm:'+esc(c.name)+'\\')">'+esc(c.name)+' · '+c.n_blocks+' blocks</span>';});
        h+='</div></div>';
      }
      h+='</div>';
      setTimeout(wireFbdLinks,0);
    } else {
      h+='<div class="card"><h3>Detail</h3><span class="empty">No parsed EM view available in this export.</span></div>';
    }
  }
  if(o._type==='Recipe'){
    h+='<div class="card"><h3>Detail</h3><span class="empty">Detailed Recipe view (procedure tree, parameters) plugs in here.</span></div>';
  }
  if(o._type==='FB Type'){
    h+='<div class="card"><h3>Standard DeltaV Function Block</h3>';
    if(o.glossary) h+='<p style="margin:0 0 8px">'+esc(o.glossary)+'</p>';
    h+='<div class="kv"><div class="k">DeltaV description</div><div>'+esc(o.description||'—')+'</div>';
    h+='<div class="k">Type code</div><div><code>'+esc(o.name)+'</code></div></div>';
    h+='<p class="empty" style="margin-top:10px">A primitive block type provided by DeltaV (not a user composite). Instances of it appear inside control/equipment module diagrams.</p>';
    h+='</div>';
  }
  document.getElementById('detail').innerHTML=h;
}

function toggle(el,e){e.stopPropagation();const ul=el.closest('.navgroup').querySelector('.navchildren');if(ul){ul.style.display=ul.style.display==='none'?'block':'none';el.textContent=ul.style.display==='none'?'▸':'▾';}}
function secToggle(sid,el){const b=document.getElementById(sid);if(!b)return;const open=b.style.display!=='none';b.style.display=open?'none':'block';const a=el.querySelector('.secarrow');if(a)a.textContent=open?'▸':'▾';}

// ── view stack so the back button returns to the previous view ──
let VIEW_STACK=[];
function renderEntry(e){
  if(e.k==='obj') renderObj(e.id);
  else if(e.k==='fbd') renderFbd(e.def,e.label);
  else if(e.k==='param') renderParam(e.name);
  else if(e.k==='inst') renderInstance(e.iid);
  const d=document.getElementById('detail'); if(d) d.scrollTop=0;
}
function navTo(e){ VIEW_STACK.push(e); renderEntry(e); }
function goBack(){ if(VIEW_STACK.length>1){ VIEW_STACK.pop(); renderEntry(VIEW_STACK[VIEW_STACK.length-1]); } }
function show(id){
  if(id && id.indexOf('param:')===0){ var pn=id.slice(6); if(PARAM_INDEX[pn]) navTo({k:'param',name:pn}); return; }
  if(id && id.indexOf('inst:')===0){ var iid=id.slice(5); if(DB.instances&&DB.instances[iid]) navTo({k:'inst',iid:iid}); return; }
  if(DB.objs[id]) navTo({k:'obj',id:id});
}
function showFbd(def,label){ if(FBD_VIEWS[def]) navTo({k:'fbd',def:def,label:label}); }
function showParam(name){ if(PARAM_INDEX[name]) navTo({k:'param',name:name}); }
function showInst(parent,tag){ var iid=parent+'\\u0001'+tag; if(DB.instances&&DB.instances[iid]) navTo({k:'inst',iid:iid}); }

// link to a module by name, resolving to whatever navigable view exists for it
function modLink(name){
  var c=['em:'+name,'cm:'+name,'composite:'+name,'uclass:'+name,'phase:'+name];
  for(var i=0;i<c.length;i++){ if(DB.objs[c[i]]) return '<span class="link" onclick="show(\\''+c[i]+'\\')">'+esc(name)+'</span>'; }
  if(FBD_VIEWS[name]) return '<span class="link" onclick="showFbd(\\''+esc(name)+'\\',\\''+esc(name)+'\\')">'+esc(name)+'</span>';
  return esc(name);
}

// ── parameter cross-reference card (database-wide) ──
function renderParam(name){
  var v=PARAM_INDEX[name];
  document.querySelectorAll('.navitem').forEach(n=>n.classList.remove('sel'));
  var back = VIEW_STACK.length>1 ? ' <span class="link" onclick="goBack()">← back</span>' : '';
  var h='<h2 class="dt">'+esc(name)+'</h2><span class="dt-type" style="background:#0891b2">Parameter</span>';
  h+='<p class="dt-desc">Database-wide cross-reference: everywhere this parameter / signal is defined, wired, referenced, or used in logic.'+back+'</p>';
  if(!v){ h+='<div class="card"><span class="empty">No usage found.</span></div>'; document.getElementById('detail').innerHTML=h; return; }
  function tbl(title,rows,head,fn){
    if(!rows.length)return '';
    var s='<div class="card"><h3>'+title+' ('+rows.length+')</h3><table class="fbd-table"><thead><tr>'+head+'</tr></thead><tbody>';
    rows.forEach(function(r){s+='<tr>'+fn(r)+'</tr>';});
    return s+'</tbody></table></div>';
  }
  h+=tbl('Defined in', v.defs, '<th>Module</th><th>Direction</th><th>Type</th><th>Group</th><th>Reference</th>',
    function(d){return '<td>'+modLink(d.m)+'</td><td>'+esc(d.dir)+'</td><td>'+esc(d.t)+'</td><td>'+esc(d.g||'—')+'</td><td>'+(d.ref?'<code>'+esc(d.ref)+'</code>':'—')+'</td>';});
  h+=tbl('Configured values', v.vals||[], '<th>Module</th><th>Value</th>',
    function(x){return '<td>'+modLink(x.m)+'</td><td>'+(x.cv===''?'<span style="color:#94a3b8">(empty)</span>':'<code>'+esc(x.cv)+'</code>')+'</td>';});
  h+=tbl('Wired to logic', v.wires, '<th>Module</th><th>Block · Pin</th><th>Direction</th>',
    function(w){return '<td>'+modLink(w.m)+'</td><td><code>'+esc(w.blk)+'/'+esc(w.port)+'</code></td><td>'+(w.dir==='in'?'→ into block':'← from block')+'</td>';});
  h+=tbl('Referenced by', v.refs, '<th>Module</th><th>Parameter</th><th>Via reference</th>',
    function(r){return '<td>'+modLink(r.m)+'</td><td><b>'+esc(r.from)+'</b></td><td><code>'+esc(r.via)+'</code></td>';});
  h+=tbl('Used in expressions', v.exprs, '<th>Module</th><th>Block</th><th>Attribute</th><th>Kind</th>',
    function(e){return '<td>'+modLink(e.m)+'</td><td>'+esc(e.blk)+'</td><td><code>'+esc(e.attr)+'</code></td><td>'+esc(e.kind||'—')+'</td>';});
  var d=document.getElementById('detail'); d.innerHTML=h; d.scrollTop=0;
}

// jump from an instance to the class that defines its logic/parameters
function viewClass(cls){
  var c=['cm:'+cls,'composite:'+cls,'em:'+cls,'uclass:'+cls];
  for(var i=0;i<c.length;i++){ if(DB.objs[c[i]]){ show(c[i]); return; } }
  if(FBD_VIEWS[cls]) showFbd(cls,cls);
}

// ── CM instance card: identity + class link + siblings + inherited values ──
function renderInstance(iid){
  var d=DB.instances&&DB.instances[iid]; if(!d){return;}
  document.querySelectorAll('.navitem').forEach(n=>n.classList.remove('sel'));
  document.querySelectorAll('.navinst').forEach(function(n){
    n.classList.toggle('sel', n.dataset.parent+'\\u0001'+n.dataset.tag===iid);
  });
  var back = VIEW_STACK.length>1 ? ' <span class="link" onclick="goBack()">← back</span>' : '';
  var h='<h2 class="dt">'+esc(d.tag)+'</h2><span class="dt-type" style="background:#6d28d9">CM instance</span>';
  h+='<p class="dt-desc">Instance of '+modLink(d.cls)+' · in '+modLink(d.parent)+'.'+back+'</p>';
  h+='<div class="card"><h3>Identity</h3><div class="kv">';
  h+='<div class="k">Tag</div><div><code>'+esc(d.tag)+'</code></div>';
  h+='<div class="k">Class</div><div>'+modLink(d.cls)+'</div>';
  h+='<div class="k">Parent EM</div><div>'+modLink(d.parent)+'</div>';
  h+='<div class="k">Description</div><div>'+esc(d.desc||'—')+'</div>';
  h+='<div class="k">Ownership</div><div>'+esc(d.ownership||'—')+'</div>';
  if(d.category) h+='<div class="k">Category</div><div style="font-size:12px">'+esc(d.category)+'</div>';
  h+='</div>';
  h+='<button class="bigbtn" onclick="viewClass(\\''+esc(d.cls)+'\\')">View class logic &amp; parameters →</button>';
  h+='</div>';
  var sibs=(DB.parent_instances[d.parent]||[]).map(function(x){return DB.instances[x];})
            .filter(function(s){return s && s.cls===d.cls && s.tag!==d.tag;});
  if(sibs.length){
    h+='<div class="card"><h3>Sibling instances of this class ('+sibs.length+')</h3><div class="chips">';
    sibs.forEach(function(s){ h+='<span class="chip" onclick="showInst(\\''+esc(s.parent)+'\\',\\''+esc(s.tag)+'\\')">'+esc(s.tag)+'</span>'; });
    h+='</div></div>';
  }
  var vals=[];
  for(var pn in PARAM_INDEX){ (PARAM_INDEX[pn].vals||[]).forEach(function(v){ if(v.m===d.cls) vals.push({p:pn,cv:v.cv}); }); }
  if(vals.length){
    h+='<div class="card"><h3>Configured values <span style="font-weight:400;color:#94a3b8">('+vals.length+')</span></h3>';
    h+='<p class="empty" style="margin:0 0 8px">Inherited from class '+esc(d.cls)+'. This instance has no parameter overrides in the export.</p>';
    h+='<table class="fbd-table"><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>';
    vals.forEach(function(v){ h+='<tr><td><span class="link" onclick="showParam(\\''+esc(v.p)+'\\')">'+esc(v.p)+'</span></td><td>'+(v.cv===''?'<span style="color:#94a3b8">(empty)</span>':'<code>'+esc(v.cv)+'</code>')+'</td></tr>'; });
    h+='</tbody></table></div>';
  }
  var dd=document.getElementById('detail'); dd.innerHTML=h; dd.scrollTop=0;
}

// FBD composite drill-down: clicking a composite block/link shows its diagram.
function renderFbd(defName, label){
  if(!FBD_VIEWS[defName]){return;}
  const d=document.getElementById('detail');
  let h='<h2 class="dt">'+esc(label||defName)+'</h2>';
  h+='<span class="dt-type b-composite">Composite Definition</span>';
  const back = VIEW_STACK.length>1 ? ' <span class="link" onclick="goBack()">← back</span>' : '';
  h+='<p class="dt-desc">Nested composite inside the parent module.'+back+'</p>';
  h+='<div class="card" style="max-width:none">'+FBD_VIEWS[defName]+'</div>';
  d.innerHTML=h;
  d.scrollTop=0;
  wireFbdLinks();
}
function emTab(btn,which){
  const card=btn.closest('.card');
  card.querySelectorAll('.emtab').forEach(t=>t.classList.toggle('on',t===btn));
  card.querySelectorAll('.empanel').forEach(p=>p.classList.toggle('on',p.dataset.e===which));
  if(which==='fb') wireFbdLinks();
}
function wireFbdLinks(){
  document.querySelectorAll('.fbd-comp-link').forEach(el=>{
    el.onclick=()=>{ const def=el.getAttribute('data-fbd'); showFbd(def, el.textContent); };
  });
  // also make composite blocks in the SVG clickable
  document.querySelectorAll('.fb-composite').forEach(g=>{
    const def=g.getAttribute('data-composite');
    if(def && FBD_VIEWS[def]){ g.style.cursor='pointer'; g.onclick=()=>showFbd(def, g.getAttribute('data-name')); }
  });
}
"""
    # Escape '</' as '<\/' in the embedded JSON so the HTML parser doesn't see a
    # closing </script> when the data (e.g. an embedded phase-viewer HTML)
    # contains its own </script> tags. In JSON/JS strings '\/' is a valid escape
    # for '/', so the data round-trips identically; only the HTML parser's naive
    # tag scan is affected.
    def _script_safe(s):
        return s.replace('</', '<\\/')
    js = (js.replace('__DATA__', _script_safe(data_json))
            .replace('__PHASE_VIEWS__', _script_safe(phase_views_json))
            .replace('__FBD_VIEWS__', _script_safe(fbd_views_json))
            .replace('__EM_VIEWS__', _script_safe(em_views_json))
            .replace('__PARAM_INDEX__', _script_safe(param_index_json))
            .replace('__EXPR_INDEX__', _script_safe(expr_index_json)))

    # ── build nav tree ──
    nav = []
    nav.append('<div class="navsearch"><input id="navq" autocomplete="off" '
               'placeholder="Search…  (Ctrl-K)" '
               'oninput="navSearch(this.value)" onkeydown="navSearchKey(event)">'
               '<div class="navmode">'
               '<button class="nm-btn active" onclick="navMode(this,\'names\')">Names</button>'
               '<button class="nm-btn" onclick="navMode(this,\'expr\')">Expressions</button>'
               '<button class="nm-btn" onclick="navMode(this,\'values\')">Values</button>'
               '</div>'
               '<div id="navres" class="navres" style="display:none"></div></div>')
    nav.append('<div class="navsec">Plant Areas</div>')
    for a in catalog['areas']:
        if not a['units']:
            continue
        nav.append(f'<div class="navgroup">')
        nav.append(f'<div class="navitem" data-id="area:{html.escape(a["name"])}" '
                   f'onclick="show(\'area:{html.escape(a["name"])}\')">'
                   f'<span class="tog" onclick="toggle(this,event)">▾</span>'
                   f'{_nav_badge("area")}{html.escape(a["name"])}</div>')
        nav.append('<div class="navchildren">')
        for u in a['units']:
            nav.append(f'<div class="navitem navchild" data-id="unit:{html.escape(u["name"])}" '
                       f'onclick="show(\'unit:{html.escape(u["name"])}\')">'
                       f'{_nav_badge("unit")}{html.escape(u["name"])}</div>')
        nav.append('</div></div>')

    sec_id = [0]
    def nav_list(title, items, prefix, badge_cls, badge_txt, collapsed=False):
        if not items:
            return
        sec_id[0] += 1
        sid = f'sec{sec_id[0]}'
        arrow = '▸' if collapsed else '▾'
        disp = 'none' if collapsed else 'block'
        nav.append(f'<div class="navsec navsec-tog" onclick="secToggle(\'{sid}\',this)">'
                   f'<span class="secarrow">{arrow}</span> {title} ({len(items)})</div>')
        nav.append(f'<div class="navsecbody" id="{sid}" style="display:{disp}">')
        for it in sorted(items, key=lambda x: x['name']):
            nav.append(f'<div class="navitem" data-id="{prefix}:{html.escape(it["name"])}" '
                       f'onclick="show(\'{prefix}:{html.escape(it["name"])}\')">'
                       f'{_nav_badge(prefix)}'
                       f'{html.escape(it["name"])}</div>')
        nav.append('</div>')

    nav_list('Unit Classes', catalog['unit_classes'], 'uclass', 'b-uclass', 'UCLS')

    # EM Classes — each EM nests its child CM *instances* (the actual deployed
    # tags), labeled "TAG (CLASS)". The class itself stays in the CM Classes
    # section below; these nodes are the usage/instance view.
    parent_instances = catalog.get('parent_instances', {})
    instances = catalog.get('instances', {})
    if catalog['em_classes']:
        sec_id[0] += 1
        sid = f'sec{sec_id[0]}'
        nav.append(f'<div class="navsec navsec-tog" onclick="secToggle(\'{sid}\',this)">'
                   f'<span class="secarrow">▾</span> EM Classes ({len(catalog["em_classes"])})</div>')
        nav.append(f'<div class="navsecbody" id="{sid}" style="display:block">')
        for em in sorted(catalog['em_classes'], key=lambda x: x['name']):
            ename = em['name']
            iids = parent_instances.get(ename, [])
            if iids:
                nav.append('<div class="navgroup">')
                nav.append(f'<div class="navitem" data-id="em:{html.escape(ename)}" '
                           f'onclick="show(\'em:{html.escape(ename)}\')">'
                           f'<span class="tog" onclick="toggle(this,event)">▾</span>'
                           f'{_nav_badge("em")}{html.escape(ename)}</div>')
                nav.append('<div class="navchildren">')
                for iid in iids:
                    inst = instances.get(iid, {})
                    tag, cls = inst.get('tag', ''), inst.get('cls', '')
                    nav.append(f'<div class="navitem navchild navinst" '
                               f'data-parent="{html.escape(ename)}" data-tag="{html.escape(tag)}" '
                               f'onclick="showInst(this.dataset.parent,this.dataset.tag)" '
                               f'title="{html.escape(tag)} (instance of {html.escape(cls)})">'
                               f'{_nav_badge("inst")}'
                               f'<span class="inst-tag">{html.escape(tag)}</span>'
                               f'<span class="inst-cls">({html.escape(cls)})</span></div>')
                nav.append('</div></div>')
            else:
                nav.append(f'<div class="navitem" data-id="em:{html.escape(ename)}" '
                           f'onclick="show(\'em:{html.escape(ename)}\')">'
                           f'{_nav_badge("em")}{html.escape(ename)}</div>')
        nav.append('</div>')

    # CM Classes — all CM classes in the database (also nested under their EM
    # above; here as a flat index so the full set is browsable).
    nav_list('CM Classes', catalog['cm_classes'], 'cm', 'b-cm', 'CM', collapsed=True)
    nav_list('Phase Classes', catalog['phase_classes'], 'phase', 'b-phase', 'PH', collapsed=True)
    nav_list('Recipes', catalog['recipes'], 'recipe', 'b-recipe', 'RCP')

    # Composites — show only reusable *class* (library) composites in the
    # big-picture view. Object-local (__HEX__, no category) composites are
    # excluded here; they remain reachable by drilling into their parent diagram.
    class_comps = [c for c in catalog['composites'] if c.get('scope') == 'class']
    if class_comps:
        sec_id[0] += 1
        sid = f'sec{sec_id[0]}'
        nav.append(f'<div class="navsec navsec-tog" onclick="secToggle(\'{sid}\',this)">'
                   f'<span class="secarrow">▸</span> Composite Classes ({len(class_comps)})</div>')
        nav.append(f'<div class="navsecbody" id="{sid}" style="display:none">')
        for c in sorted(class_comps, key=lambda x: x['name']):
            nav.append(f'<div class="navitem" data-id="composite:{html.escape(c["name"])}" '
                       f'onclick="show(\'composite:{html.escape(c["name"])}\')" title="{html.escape(c["name"])}">'
                       f'{_nav_badge("composite")}{html.escape(c["name"])}</div>')
        nav.append('</div>')

    # Function Block Types (standard DeltaV primitives referenced by the modules)
    nav_list('Function Block Types', catalog['fb_types'], 'fbtype', 'b-fbtype', 'FB', collapsed=True)

    welcome = '<div class="welcome"><h2>' + html.escape(fname) + '</h2>'
    welcome += '<p>DeltaV database explorer. Select an object from the navigation tree to view its details and references.</p>'
    for k, v in summary.items():
        welcome += f'<div class="stat"><b>{v}</b><span>{k}</span></div>'
    welcome += '</div>'

    export_html = ''
    if export_token:
        ft = html.escape(fname, quote=True)
        tk = html.escape(export_token, quote=True)
        export_html = (
            f'<div class="hdr-export">'
            f'<a class="exp-btn" href="/export?token={tk}&amp;fmt=excel&amp;name={ft}" '
            f'title="Download an Excel workbook generated from this database">&#8681; Excel</a>'
            f'<a class="exp-btn" href="/export?token={tk}&amp;fmt=word&amp;name={ft}" '
            f'title="Download a Word DDS document generated from this database">&#8681; Word DDS</a>'
            f'</div>')

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DeltaV Database Explorer — {html.escape(fname)}</title>
<style>{_CSS}
{fbd_bridge.EXPR_MODAL_CSS}</style></head><body>
<header><h1>DeltaV Database Explorer</h1><span class="sub">{html.escape(fname)}</span>{export_html}</header>
<div class="main">
  <div class="nav">{''.join(nav)}</div>
  <div class="detail" id="detail">{welcome}</div>
</div>
<script>{js}
{fbd_bridge.EXPR_MODAL_JS}</script>
</body></html>"""
