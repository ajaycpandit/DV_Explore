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


_CSS = """
*{box-sizing:border-box}
body{margin:0;font:14px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;height:100vh;display:flex;flex-direction:column;background:#f8fafc}
header{flex:0 0 auto;padding:12px 18px;background:#0f172a;color:#fff;display:flex;align-items:baseline;gap:14px}
header h1{margin:0;font-size:15px;font-weight:600}
header .sub{color:#94a3b8;font-size:12px}
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
.navchild{padding-left:34px}
.navchild2{padding-left:48px}
/* tree connector lines */
.navgroup{position:relative}
.navchildren{position:relative}
.navchildren .navchild{position:relative}
.navchildren .navchild::before{
  content:"";position:absolute;left:22px;top:0;bottom:50%;
  border-left:1.5px solid #cbd5e1;border-bottom:1.5px solid #cbd5e1;
  width:9px;
}
.navchildren .navchild:not(:last-child)::after{
  content:"";position:absolute;left:22px;top:50%;bottom:-2px;
  border-left:1.5px solid #cbd5e1;
}
.navchildren .navchild::before{border-bottom-left-radius:3px}
.tree-line{border-left:1.5px solid #e2e8f0;margin-left:22px;padding-left:0}
.b-area{background:#0ea5e9}.b-unit{background:#10b981}.b-em{background:#8b5cf6}
.b-cm{background:#f59e0b}.b-phase{background:#ec4899}.b-recipe{background:#ef4444}
.b-composite{background:#64748b}.b-uclass{background:#059669}
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
.fbd-wrap{display:flex;flex-direction:column;gap:14px}
.fbd-diagram-card{border:1px solid #e2e8f0;border-radius:8px;background:#fcfcfd;overflow:hidden}
.fbd-head{padding:10px 14px;background:#f1f5f9;font-weight:600;font-size:13px;border-bottom:1px solid #e2e8f0}
.fbd-sub{color:#64748b;font-weight:400;font-size:12px}
.fbd-svg-holder{padding:10px;overflow:auto;max-height:78vh}
.fbd-info-card{border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;background:#fff}
.fbd-info-card h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:#475569}
.fbd-comp-link{border-color:#475569}
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


def build_explorer_html(catalog, fname, phase_views=None, fbd_views=None):
    """phase_views: optional {phase_name: interactive_html} to embed as drill-down
    leaf views for Phase Class objects."""
    phase_views = phase_views or {}
    fbd_views = fbd_views or {}
    summary = {
        'Areas': len(catalog['areas']),
        'Unit instances': len(catalog['units']),
        'Unit classes': len(catalog['unit_classes']),
        'EM classes': len(catalog['em_classes']),
        'CM classes': len(catalog['cm_classes']),
        'Phase classes': len(catalog['phase_classes']),
        'Recipes': len(catalog['recipes']),
        'Composites': len(catalog['composites']),
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
        put('composite:' + c['name'], 'Composite', c)

    data_json = json.dumps({'objs': objs, 'summary': summary,
                            'unit_phases': catalog.get('unit_phases', {}),
                            'unit_ems': catalog.get('unit_ems', {}),
                            'em_cms': catalog.get('em_cms', {})})
    phase_views_json = json.dumps(phase_views)
    fbd_views_json = json.dumps(fbd_views)

    js = """
const DB = __DATA__;
const PHASE_VIEWS = __PHASE_VIEWS__;
const FBD_VIEWS = __FBD_VIEWS__;
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function badge(t){const m={'Area':'b-area','Unit Instance':'b-unit','EM Class':'b-em','CM Class':'b-cm','Phase Class':'b-phase','Recipe':'b-recipe','Composite':'b-composite','Unit Class':'b-uclass'};return m[t]||'b-composite';}

function show(id){
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

  // class <-> instance linking
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
  if(o._type==='EM Class' || o._type==='Recipe'){
    h+='<div class="card"><h3>Detail</h3><span class="empty">Detailed '+o._type+' view (logic, parameters, references) plugs in here.</span></div>';
  }
  document.getElementById('detail').innerHTML=h;
}

function toggle(el,e){e.stopPropagation();const ul=el.closest('.navgroup').querySelector('.navchildren');if(ul){ul.style.display=ul.style.display==='none'?'block':'none';el.textContent=ul.style.display==='none'?'▸':'▾';}}
function secToggle(sid,el){const b=document.getElementById(sid);if(!b)return;const open=b.style.display!=='none';b.style.display=open?'none':'block';const a=el.querySelector('.secarrow');if(a)a.textContent=open?'▸':'▾';}

// FBD composite drill-down: clicking a composite block/link shows its diagram.
function showFbd(defName, label){
  if(!FBD_VIEWS[defName]){return;}
  const d=document.getElementById('detail');
  let h='<h2 class="dt">'+esc(label||defName)+'</h2>';
  h+='<span class="dt-type b-composite">Composite Definition</span>';
  h+='<p class="dt-desc">Nested composite inside the parent module. <span class="link" onclick="history.back()">← back</span></p>';
  h+='<div class="card" style="max-width:none">'+FBD_VIEWS[defName]+'</div>';
  d.innerHTML=h;
  d.scrollTop=0;
  wireFbdLinks();
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
            .replace('__FBD_VIEWS__', _script_safe(fbd_views_json)))

    # ── build nav tree ──
    nav = []
    nav.append('<div class="navsec">Plant Areas</div>')
    for a in catalog['areas']:
        if not a['units']:
            continue
        nav.append(f'<div class="navgroup">')
        nav.append(f'<div class="navitem" data-id="area:{html.escape(a["name"])}" '
                   f'onclick="show(\'area:{html.escape(a["name"])}\')">'
                   f'<span class="tog" onclick="toggle(this,event)">▾</span>'
                   f'<span class="badge b-area">AREA</span>{html.escape(a["name"])}</div>')
        nav.append('<div class="navchildren">')
        for u in a['units']:
            nav.append(f'<div class="navitem navchild" data-id="unit:{html.escape(u["name"])}" '
                       f'onclick="show(\'unit:{html.escape(u["name"])}\')">'
                       f'<span class="badge b-unit">UNIT</span>{html.escape(u["name"])}</div>')
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
                       f'<span class="badge {badge_cls}">{badge_txt}</span>'
                       f'{html.escape(it["name"])}</div>')
        nav.append('</div>')

    nav_list('Unit Classes', catalog['unit_classes'], 'uclass', 'b-uclass', 'UCLS')
    nav_list('EM Classes', catalog['em_classes'], 'em', 'b-em', 'EM')
    nav_list('CM Classes', catalog['cm_classes'], 'cm', 'b-cm', 'CM', collapsed=True)
    nav_list('Phase Classes', catalog['phase_classes'], 'phase', 'b-phase', 'PH', collapsed=True)
    nav_list('Recipes', catalog['recipes'], 'recipe', 'b-recipe', 'RCP')
    nav_list('Composites', catalog['composites'], 'composite', 'b-composite', 'CMP', collapsed=True)

    welcome = '<div class="welcome"><h2>' + html.escape(fname) + '</h2>'
    welcome += '<p>DeltaV database explorer. Select an object from the navigation tree to view its details and references.</p>'
    for k, v in summary.items():
        welcome += f'<div class="stat"><b>{v}</b><span>{k}</span></div>'
    welcome += '</div>'

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DeltaV Database Explorer — {html.escape(fname)}</title>
<style>{_CSS}</style></head><body>
<header><h1>DeltaV Database Explorer</h1><span class="sub">{html.escape(fname)}</span></header>
<div class="main">
  <div class="nav">{''.join(nav)}</div>
  <div class="detail" id="detail">{welcome}</div>
</div>
<script>{js}</script>
</body></html>"""
