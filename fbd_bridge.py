"""
FBD view bridge for the database explorer.

Generates Function Block Diagram views (SVG) for CM classes and FBD composites
in a database export, so the explorer's CM/Composite leaves drill down into the
real diagram. Mirrors phase_bridge but for function-block logic.

FHX-only: structure, wiring, composites, module interface. No configured tuning
or alarm values (those aren't in a class export).
"""

import re
import html
import fbd_parser
import fbd_render


def _extract_block(text, start):
    return fbd_parser._extract_block(text, start)


# ── shared expression popup (modal) assets ──────────────────────────────────
# Self-contained CSS + JS for the click-to-view expression popup. Included once
# per host page (explorer, cm_viewer, em_viewer). Expression blocks rendered by
# fbd_render carry data-expr + onclick="fbdShowExpr(this)"; the data travels with
# the SVG so no per-host data plumbing is needed.
EXPR_MODAL_CSS = """
.fbd-modal{display:none;position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:1000;
  align-items:center;justify-content:center;padding:24px}
.fbd-modal-box{background:#fff;border-radius:10px;max-width:840px;width:100%;max-height:86vh;
  display:flex;flex-direction:column;box-shadow:0 20px 50px rgba(0,0,0,.3)}
.fbd-modal-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;
  border-bottom:1px solid #e2e8f0;font-weight:600;font-size:14px}
.fbd-modal-head .sub{font-weight:400;color:#94a3b8;font-size:12px;margin-left:8px}
.fbd-modal-x{cursor:pointer;font-size:22px;line-height:1;color:#64748b;padding:0 4px}
.fbd-modal-x:hover{color:#0f172a}
.fbd-modal-body{padding:14px 16px;overflow:auto}
.fbd-modal-attr{font-size:11px;color:#475569;font-family:monospace;margin:12px 0 4px}
.fbd-modal-body pre{margin:0 0 6px;padding:12px 14px;background:#f8fafc;color:#334155;
  border:1px solid #e6ebf1;border-left:3px solid #6366f1;border-radius:6px;
  font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.6;
  white-space:pre;overflow:auto;box-shadow:inset 0 1px 2px rgba(15,23,42,.03)}
.fbd-modal-body pre .cm{color:#94a3b8;font-style:italic}
.fbd-modal-body pre .kw{color:#7c3aed;font-weight:600}
.fbd-modal-body pre .rf{color:#0e7490}
.fbd-modal-body pre .st{color:#b45309}
.fbd-modal-body pre .nm{color:#9333ea}

/* net highlighting */
.fbd-wire{cursor:pointer}
.fbd-pin{cursor:pointer}
svg.fbd.net-on .fbd-wire{opacity:.18}
svg.fbd.net-on .fb-term{opacity:.32}
svg.fbd.net-on .fbd-wire.net-hl{opacity:1;stroke:#ea580c;stroke-width:2.4}
svg.fbd.net-on .fb-term.net-hl{opacity:1}
svg.fbd.net-on .fb-term.net-hl rect{stroke:#ea580c;stroke-width:2;fill:#fff7ed}
svg.fbd .fbd-pin.net-hl{fill:#ea580c;r:3.4}
/* layout toggle */
.fbd-layout-toggle{display:inline-flex;gap:0;margin:0 0 8px;border:1px solid #cbd5e1;
  border-radius:7px;overflow:hidden;font-size:12px}
.fbd-layout-toggle .lay-btn{padding:5px 12px;background:#fff;border:0;cursor:pointer;
  color:#475569;font-weight:600}
.fbd-layout-toggle .lay-btn+.lay-btn{border-left:1px solid #cbd5e1}
.fbd-layout-toggle .lay-btn.active{background:#1e293b;color:#fff}
.fbd-net-hint{font-size:11px;color:#94a3b8;margin-left:10px}
.fbd-legend{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:2px 0 8px;
  padding:6px 10px;background:#f8fafc;border:1px solid #eef2f7;border-radius:7px;font-size:11px;color:#475569}
.fbd-leg-lbl{color:#94a3b8;font-weight:600}
.fbd-leg-item{display:inline-flex;align-items:center;gap:4px}
.fbd-leg-item svg{flex:0 0 auto}
"""

EXPR_MODAL_JS = """
function fbdEsc(s){return (s||'').replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
var FBD_STKW=/^(IF|THEN|ELSE|ELSIF|END_IF|CASE|OF|END_CASE|WHILE|DO|END_WHILE|FOR|TO|BY|END_FOR|REPEAT|UNTIL|END_REPEAT|RETURN|EXIT|AND|OR|NOT|XOR|MOD|TRUE|FALSE)$/;
function fbdHL(raw){
  var re=/(\\(\\*[\\s\\S]*?\\*\\))|("[^"]*")|('[^']*')|(\\b(?:IF|THEN|ELSE|ELSIF|END_IF|CASE|OF|END_CASE|WHILE|DO|END_WHILE|FOR|TO|BY|END_FOR|REPEAT|UNTIL|END_REPEAT|RETURN|EXIT|AND|OR|NOT|XOR|MOD|TRUE|FALSE)\\b)|(\\b\\d+\\.?\\d*\\b)/g;
  var out='',last=0,m;
  while((m=re.exec(raw))){
    if(m.index>last)out+=fbdEsc(raw.slice(last,m.index));
    var t=fbdEsc(m[0]),c=m[1]?'cm':m[2]?'st':m[3]?'rf':m[4]?'kw':'nm';
    out+='<span class="'+c+'">'+t+'</span>';
    last=re.lastIndex;
  }
  out+=fbdEsc(raw.slice(last));
  return out;
}
function fbdEnsureModal(){
  if(document.getElementById('fbdExprModal'))return;
  var o=document.createElement('div');o.id='fbdExprModal';o.className='fbd-modal';
  o.innerHTML='<div class="fbd-modal-box"><div class="fbd-modal-head"><span><b id="fbdExprTitle"></b><span class="sub" id="fbdExprSub"></span></span><span class="fbd-modal-x" onclick="fbdCloseExpr()">&times;</span></div><div class="fbd-modal-body" id="fbdExprBody"></div></div>';
  o.addEventListener('click',function(e){if(e.target===o)fbdCloseExpr();});
  document.body.appendChild(o);
  document.addEventListener('keydown',function(e){if(e.key==='Escape')fbdCloseExpr();});
}
function fbdShowExpr(el){
  fbdEnsureModal();
  var data=[];try{data=JSON.parse(el.getAttribute('data-expr'))||[];}catch(e){}
  document.getElementById('fbdExprTitle').textContent=el.getAttribute('data-name')||'Expression';
  document.getElementById('fbdExprSub').textContent=data.length+' expression'+(data.length!==1?'s':'');
  var h='',multi=data.length>1;
  data.forEach(function(d){
    if(multi)h+='<div class="fbd-modal-attr">'+fbdEsc(d.a)+' \\u00b7 '+fbdEsc(d.k)+'</div>';
    h+='<pre>'+fbdHL(d.e)+'</pre>';
  });
  document.getElementById('fbdExprBody').innerHTML=h||'<p>No expression.</p>';
  document.getElementById('fbdExprModal').style.display='flex';
}
function fbdCloseExpr(){var m=document.getElementById('fbdExprModal');if(m)m.style.display='none';}

// ── net highlighting: click a wire / pin / terminal to light up its whole net ──
function fbdNet(el){
  var net=el.getAttribute('data-net');
  var svg=el.closest('svg');
  if(!svg)return;
  var already=svg.classList.contains('net-on') && el.classList.contains('net-hl');
  svg.querySelectorAll('.net-hl').forEach(function(n){n.classList.remove('net-hl');});
  if(already || !net){svg.classList.remove('net-on');return;}
  svg.classList.add('net-on');
  svg.querySelectorAll('[data-net]').forEach(function(n){
    if(n.getAttribute('data-net')===net)n.classList.add('net-hl');
  });
  event.stopPropagation();
}
function fbdClearNet(svg){svg.classList.remove('net-on');
  svg.querySelectorAll('.net-hl').forEach(function(n){n.classList.remove('net-hl');});}

// ── layout toggle: switch a diagram between DeltaV and auto-arranged ──
function fbdSetLayout(btn,which){
  var wrap=btn.closest('.fbd-diagram-card');
  if(!wrap)return;
  wrap.querySelectorAll('.lay-btn').forEach(function(b){b.classList.toggle('active',b===btn);});
  wrap.querySelectorAll('.lay').forEach(function(l){
    l.style.display=l.classList.contains('lay-'+which)?'block':'none';
  });
}
"""



def build_fbd_views(text):
    """Return {object_name: fbd_view_html} for every module/composite/composite-
    definition in the export that contains a function block diagram. This
    includes nested composite definitions (e.g. C_C_ML_V01) so the explorer can
    drill from a CM into its composite blocks."""
    views = {}
    objs = fbd_parser.list_fbd_objects(text)
    # ground truth: a block is a composite only if its DEFINITION is an actual
    # FUNCTION_BLOCK_DEFINITION in this export (has its own diagram). Everything
    # else (ACT, CND, EDC, DCC, PDE, ...) is a standard DeltaV block type.
    comp_names = {o['name'] for o in objs if o['kind'] == 'FUNCTION_BLOCK_DEFINITION'}
    for o in objs:
        name = o['name']
        fbd = fbd_parser.parse_module_fbd(text, name)
        if not fbd or not fbd['blocks']:
            continue
        for b in fbd['blocks']:
            b['is_composite'] = b['definition'] in comp_names
        views[name] = build_fbd_view_html(fbd)
    return views


def build_param_index(text):
    return build_indexes(text)['params']


def build_indexes(text):
    """One pass over every FBD module, producing:
      params: param-name -> {defs, refs, wires, exprs, vals} cross-reference
      exprs:  flat list of {m, blk, attr, kind, e} for free-text expr search
    'vals' captures each parameter's configured value (ATTRIBUTE_INSTANCE CV)."""
    import re as _re
    objs = fbd_parser.list_fbd_objects(text)
    parsed = []
    known = set()
    for o in objs:
        fbd = fbd_parser.parse_module_fbd(text, o['name'])
        if not fbd:
            continue
        blk_text = ''
        mm = _re.search(_re.escape(o['kind']) + r'\s+NAME="' + _re.escape(o['name']) + r'"', text)
        if mm:
            blk_text = _extract_block(text, mm.end())
        parsed.append((o['name'], fbd, blk_text))
        for p in fbd.get('interface', []):
            known.add(p['name'])

    idx = {}
    exprs = []

    def E(p):
        return idx.setdefault(p, {'defs': [], 'refs': [], 'wires': [], 'exprs': [], 'vals': []})

    for mod, fbd, blk_text in parsed:
        for p in fbd.get('interface', []):
            E(p['name'])['defs'].append({'m': mod, 'dir': p['connection'],
                                         't': p['type'], 'g': p.get('group', ''),
                                         'ref': p.get('reference', '')})
            ref = p.get('reference', '')
            if ref and ref not in ('#IGNORE', ''):
                tok = ref.split('/')[-1]
                if tok and tok != p['name']:
                    E(tok)['refs'].append({'m': mod, 'from': p['name'], 'via': ref})
        for w in fbd['wires']:
            if w['src_block'] is None and w['dst_block']:
                E(w['source'])['wires'].append({'m': mod, 'blk': w['dst_block'],
                                                'port': w['dst_port'], 'dir': 'in'})
            elif w['dst_block'] is None and w['src_block']:
                E(w['destination'])['wires'].append({'m': mod, 'blk': w['src_block'],
                                                     'port': w['src_port'], 'dir': 'out'})
        for b in fbd['blocks']:
            for e in b.get('expressions', []):
                etext = e.get('expression', '')
                exprs.append({'m': mod, 'blk': b['name'], 'attr': e.get('attr', ''),
                              'kind': e.get('kind', ''), 'e': etext})
                for t in set(_re.findall(r'[A-Za-z_][A-Za-z0-9_]*', etext)) & known:
                    E(t)['exprs'].append({'m': mod, 'blk': b['name'],
                                          'attr': e.get('attr', ''), 'kind': e.get('kind', '')})
        # configured scalar values: ATTRIBUTE_INSTANCE NAME="param" { VALUE { CV=.. } }
        for vm in _re.finditer(r'ATTRIBUTE_INSTANCE\s+NAME="([^"/]+)"\s*\{\s*VALUE\s*\{\s*CV=("[^"]*"|[^}\s]+)', blk_text):
            pname, cv = vm.group(1), vm.group(2).strip('"')
            E(pname)['vals'].append({'m': mod, 'cv': cv})

    def _uniq(rows):
        seen, res = set(), []
        for r in rows:
            key = tuple(sorted(r.items()))
            if key not in seen:
                seen.add(key); res.append(r)
        return res

    params = {}
    for k, v in idx.items():
        if any(v[s] for s in ('defs', 'refs', 'wires', 'exprs', 'vals')):
            params[k] = {kk: _uniq(vv) for kk, vv in v.items()}
    return {'params': params, 'exprs': exprs}


def build_fbd_view_html(fbd):
    """Compose the FBD leaf view: diagram + composite list + interface +
    connection table. Sectioned so the explorer can show it inline."""
    svg_deltav = fbd_render.render_fbd_svg(fbd, layout='deltav')
    svg_auto = fbd_render.render_fbd_svg(fbd, layout='auto')

    parts = []
    parts.append('<div class="fbd-wrap">')

    # diagram
    parts.append('<div class="fbd-diagram-card">')
    parts.append(f'<div class="fbd-head">Function Block Diagram — {html.escape(fbd["name"])}'
                 f'<span class="fbd-sub"> · {len(fbd["blocks"])} blocks · '
                 f'{len(fbd["wires"])} wires · Algorithm: FBD</span></div>')
    parts.append('<div class="fbd-layout-toggle">'
                 '<button class="lay-btn active" onclick="fbdSetLayout(this,\'deltav\')">DeltaV layout</button>'
                 '<button class="lay-btn" onclick="fbdSetLayout(this,\'auto\')">Auto-arrange</button>'
                 '</div><span class="fbd-net-hint">tip: click any wire, pin, or parameter to trace its net</span>')
    parts.append(fbd_render.type_legend_html())
    parts.append('<div class="fbd-svg-holder">'
                 f'<div class="lay lay-deltav">{svg_deltav}</div>'
                 f'<div class="lay lay-auto" style="display:none">{svg_auto}</div>'
                 '</div>')
    parts.append('</div>')

    # composite blocks (clickable drill-down targets)
    comps = [b for b in fbd['blocks'] if b['is_composite']]
    if comps:
        parts.append('<div class="fbd-info-card"><h4>Composite Blocks (click to drill in)</h4><div class="chips">')
        for c in comps:
            parts.append(
                f'<span class="chip fbd-comp-link" data-fbd="{html.escape(c["definition"])}">'
                f'{html.escape(c["name"])} · {html.escape(c["definition"])}</span>')
        parts.append('</div></div>')

    # structured-text expressions (ACT/CALC/CND/AT/DCC/...) — the real logic
    parts.append(_expressions_card(fbd))

    # structured text view — module parameter interface (I/O + internal refs)
    iface = fbd.get('interface', [])
    if iface:
        conn_label = {'INPUT': 'Input', 'OUTPUT': 'Output',
                      'INTERNAL_SOURCE': 'Internal (source)',
                      'INTERNAL_SINK': 'Internal (sink)', 'INTERNAL': 'Internal'}
        parts.append('<div class="fbd-info-card"><h4>Module Parameter Interface ('
                     + str(len(iface)) + ')</h4>')
        parts.append('<table class="fbd-table"><thead><tr><th>Parameter</th>'
                     '<th>Direction</th><th>Group</th><th>References</th>'
                     '</tr></thead><tbody>')
        for p in iface:
            ref = p['reference']
            ref_html = (f'<code>{html.escape(ref)}</code>'
                        if ref and ref != '#IGNORE'
                        else ('<span style="color:#94a3b8">—</span>'
                              if not ref else '<span style="color:#cbd5e1">(ignored)</span>'))
            parts.append(f'<tr><td><b>{html.escape(p["name"])}</b></td>'
                         f'<td>{conn_label.get(p["connection"], p["connection"])}</td>'
                         f'<td>{html.escape(p.get("group",""))}</td>'
                         f'<td>{ref_html}</td></tr>')
        parts.append('</tbody></table></div>')

    # structured text view — block inventory (documentation, always complete)
    parts.append('<div class="fbd-info-card"><h4>Block Inventory ('
                 + str(len(fbd['blocks'])) + ')</h4>')
    parts.append('<table class="fbd-table"><thead><tr><th>Block</th><th>Type</th>'
                 '<th>Kind</th><th>Description</th></tr></thead><tbody>')
    for b in sorted(fbd['blocks'], key=lambda z: z['name']):
        kind = 'Composite' if b['is_composite'] else 'Function Block'
        parts.append(f'<tr><td><b>{html.escape(b["name"])}</b></td>'
                     f'<td>{html.escape(b["definition"])}</td>'
                     f'<td>{kind}</td>'
                     f'<td>{html.escape(b.get("description",""))}</td></tr>')
    parts.append('</tbody></table></div>')

    # structured text view — connections (source -> destination)
    if fbd['wires']:
        parts.append('<div class="fbd-info-card"><h4>Connections ('
                     + str(len(fbd['wires'])) + ')</h4>')
        parts.append('<table class="fbd-table"><thead><tr><th>Source</th>'
                     '<th></th><th>Destination</th></tr></thead><tbody>')
        for w in fbd['wires']:
            parts.append(f'<tr><td><code>{html.escape(w["source"])}</code></td>'
                         f'<td style="color:#94a3b8">&#8594;</td>'
                         f'<td><code>{html.escape(w["destination"])}</code></td></tr>')
        parts.append('</tbody></table></div>')

    parts.append('</div>')
    return '\n'.join(parts)


# one-time scoped styling for the expressions card; works in any host page
# (explorer detail panel, cm_viewer, em_viewer) without editing their CSS.
_EXPR_STYLE = """<style>
.fbd-expr details{border:1px solid #e2e8f0;border-radius:6px;margin:6px 0;background:#fff}
.fbd-expr summary{cursor:pointer;padding:8px 12px;font-size:13px;list-style:none;
  display:flex;align-items:center;gap:8px;user-select:none}
.fbd-expr summary::-webkit-details-marker{display:none}
.fbd-expr summary::before{content:"\\25B8";color:#94a3b8;font-size:11px}
.fbd-expr details[open] summary::before{content:"\\25BE"}
.fbd-expr summary:hover{background:#f8fafc}
.fbd-expr .ename{font-weight:600;color:#0f172a}
.fbd-expr .etype{font-size:11px;color:#fff;background:#64748b;padding:1px 7px;border-radius:9px}
.fbd-expr .etype.action{background:#059669}.fbd-expr .etype.condition{background:#d97706}
.fbd-expr .etype.expression{background:#db2777}
.fbd-expr .etype.fail{background:#dc2626}.fbd-expr .etype.interlock{background:#b45309}
.fbd-expr .etype.permissive{background:#2563eb}
.fbd-expr .ecount{font-size:11px;color:#94a3b8;margin-left:auto}
.fbd-expr .ebody{padding:2px 12px 12px}
.fbd-expr .eattr{font-size:11px;color:#475569;margin:8px 0 3px;font-family:monospace}
.fbd-expr pre{margin:0;padding:11px 14px;background:#f8fafc;color:#334155;
  border:1px solid #e6ebf1;border-left:3px solid #6366f1;border-radius:6px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;
  line-height:1.6;white-space:pre;overflow:auto;max-height:360px;
  box-shadow:inset 0 1px 2px rgba(15,23,42,.03)}
.fbd-expr pre .cm{color:#94a3b8;font-style:italic}
.fbd-expr pre .kw{color:#7c3aed;font-weight:600}
.fbd-expr pre .rf{color:#0e7490}
.fbd-expr pre .st{color:#b45309}
.fbd-expr pre .nm{color:#9333ea}
</style>"""


# DeltaV structured-text keywords for light syntax highlighting
_ST_KW = ('IF', 'THEN', 'ELSE', 'ELSIF', 'END_IF', 'CASE', 'OF', 'END_CASE',
          'WHILE', 'DO', 'END_WHILE', 'FOR', 'TO', 'BY', 'END_FOR', 'REPEAT',
          'UNTIL', 'END_REPEAT', 'RETURN', 'EXIT', 'AND', 'OR', 'NOT', 'XOR',
          'MOD', 'TRUE', 'FALSE')
_ST_TOKEN = re.compile(
    r'(?P<cm>\(\*[\s\S]*?\*\))'
    r'|(?P<st>"[^"]*")'
    r'|(?P<rf>\'[^\']*\')'
    r'|(?P<kw>\b(?:' + '|'.join(_ST_KW) + r')\b)'
    r'|(?P<nm>\b\d+\.?\d*\b)')


def _highlight_st(raw):
    """Light syntax highlighting for DeltaV structured text. Operates on the raw
    expression (not pre-escaped): comments, quoted strings, single-quoted
    parameter references, keywords, and numbers are wrapped in colored spans;
    everything else is HTML-escaped. Comments/strings are matched as whole tokens
    so keywords inside them are not falsely highlighted."""
    out = []
    pos = 0
    for m in _ST_TOKEN.finditer(raw):
        if m.start() > pos:
            out.append(html.escape(raw[pos:m.start()]))
        cls = m.lastgroup
        out.append(f'<span class="{cls}">{html.escape(m.group())}</span>')
        pos = m.end()
    if pos < len(raw):
        out.append(html.escape(raw[pos:]))
    return ''.join(out)


def _expressions_card(fbd):
    """Build the 'Block Expressions' card: one collapsible section per block that
    carries structured-text logic (ACT/CALC/CND/AT/DCC/...), with each expression
    shown as formatted code. Returns '' when the object has no expressions."""
    blocks_with = [b for b in fbd['blocks'] if b.get('expressions')]
    if not blocks_with:
        return ''
    blocks_with.sort(key=lambda b: b['name'])
    total = sum(len(b['expressions']) for b in blocks_with)

    p = [_EXPR_STYLE, '<div class="fbd-info-card fbd-expr">',
         f'<h4>Block Expressions ({len(blocks_with)} block'
         f'{"s" if len(blocks_with) != 1 else ""}, {total} expression'
         f'{"s" if total != 1 else ""})</h4>']
    for i, b in enumerate(blocks_with):
        exprs = b['expressions']
        # distinct kind tags for the summary
        kinds = []
        for e in exprs:
            if e['kind'] not in kinds:
                kinds.append(e['kind'])
        tags = ''.join(f'<span class="etype {k.lower()}">{html.escape(k)}</span>'
                       for k in kinds)
        open_attr = ''  # all collapsed by default
        p.append(f'<details{open_attr}><summary>'
                 f'<span class="ename">{html.escape(b["name"])}</span>'
                 f'<span style="color:#94a3b8;font-size:12px">{html.escape(b["definition"])}</span>'
                 f'{tags}<span class="ecount">{len(exprs)} expression'
                 f'{"s" if len(exprs) != 1 else ""}</span></summary><div class="ebody">')
        multi = len(exprs) > 1
        for e in exprs:
            if multi:
                p.append(f'<div class="eattr">{html.escape(e["attr"])} · {html.escape(e["kind"])}</div>')
            code = _highlight_st(e['expression'])
            p.append(f'<pre>{code}</pre>')
        p.append('</div></details>')
    p.append('</div>')
    return '\n'.join(p)


def fbd_block_table(fbd):
    """Block inventory rows (name, type, composite?) — used by the doc table."""
    return [{'name': b['name'], 'type': b['definition'],
             'composite': b['is_composite'], 'desc': b.get('description', '')}
            for b in fbd['blocks']]


def fbd_connection_table(fbd):
    """Wire/connection rows (source -> destination)."""
    return [{'source': w['source'], 'destination': w['destination']}
            for w in fbd['wires']]
