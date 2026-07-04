"""
recipe_bridge.py — parse and render DeltaV BATCH_RECIPE procedures.

A BATCH_RECIPE export contains:
  - recipe metadata (author, product, batch sizes, description, version)
  - FORMULA_PARAMETER entries (recipe-level inputs, grouped Recipe/Report/…)
  - UNIT_ALIAS entries (which units the procedure binds to)
  - a PFC_ALGORITHM: the procedure function chart — an SFC at the procedure
    level whose STEPs reference unit procedures / operations, connected by
    TRANSITIONs (with expressions) via STEP_TRANSITION_CONNECTION and
    TRANSITION_STEP_CONNECTION edges.

This module is additive and does not touch core/. It reuses db_parser.extract_block
for brace matching.
"""

import re
import html

import db_parser


def _blk(text, start_brace_search_from):
    return db_parser.extract_block(text, text.index('{', start_brace_search_from))


def parse_recipes(text):
    """Parse ALL BATCH_RECIPE blocks in the export into a list of structured dicts."""
    out = []
    for m in re.finditer(r'BATCH_RECIPE(?:\s+NAME="([^"]+)")?', text):
        try:
            blk = db_parser.extract_block(text, text.index('{', m.start()))
        except Exception:
            continue
        name = m.group(1) or ''
        out.append(_parse_one_recipe(blk, name))
    return out


def parse_recipe(text):
    """Back-compat: parse the FIRST BATCH_RECIPE, or None if absent."""
    recs = parse_recipes(text)
    return recs[0] if recs else None


def _parse_one_recipe(blk, name):
    """Parse a single BATCH_RECIPE block body into a structured dict."""

    def _scalar(key):
        mm = re.search(key + r'="([^"]*)"', blk)
        if mm:
            return mm.group(1)
        mm = re.search(key + r'=([^\s{][^\r\n]*)', blk)
        return mm.group(1).strip() if mm else ''

    # derive name from DESCRIPTION or a NAME= if not on the header
    if not name:
        nm = re.search(r'\bNAME="([^"]+)"', blk[:200])
        name = nm.group(1) if nm else (_scalar('DESCRIPTION')[:30] or 'RECIPE')

    meta = {
        'name': name,
        'description': _scalar('DESCRIPTION'),
        'author': _scalar('AUTHOR'),
        'abstract': _scalar('ABSTRACT'),
        'product_code': _scalar('PRODUCT_CODE'),
        'product_name': _scalar('PRODUCT_NAME'),
        'version': _scalar('VERSION'),
        'batch_units': _scalar('BATCH_UNITS'),
        'default_batch_size': _scalar('DEFAULT_BATCH_SIZE'),
        'min_batch_size': _scalar('MINIMUM_BATCH_SIZE'),
        'max_batch_size': _scalar('MAXIMUM_BATCH_SIZE'),
        'approval': _scalar('RECIPE_APPROVAL_INFO'),
    }

    params = []
    for pm in re.finditer(r'FORMULA_PARAMETER\s+NAME="([^"]+)"\s+TYPE=(\w+)\s*\{', blk):
        pbody = db_parser.extract_block(blk, pm.end() - 1)
        grp = re.search(r'GROUP="([^"]*)"', pbody)
        conn = re.search(r'CONNECTION=(\w+)', pbody)
        locked = 'IS_PARAMETER_LOCKED=T' in pbody
        params.append({
            'name': pm.group(1), 'type': pm.group(2),
            'group': grp.group(1) if grp else '',
            'connection': conn.group(1) if conn else '',
            'locked': locked,
        })

    aliases = []
    for am in re.finditer(r'UNIT_ALIAS\s+NAME="([^"]+)"\s*\{', blk):
        abody = db_parser.extract_block(blk, am.end() - 1)
        desc = re.search(r'DESCRIPTION="([^"]*)"', abody)
        aliases.append({'name': am.group(1),
                        'desc': desc.group(1) if desc else ''})

    proc = _parse_pfc(blk)
    return {'meta': meta, 'params': params, 'aliases': aliases, 'procedure': proc}


def _parse_pfc(blk):
    """Parse the PFC_ALGORITHM into steps, transitions, and edges (with coords)."""
    pm = re.search(r'PFC_ALGORITHM\s*\{', blk)
    if not pm:
        return None
    pfc = db_parser.extract_block(blk, pm.end() - 1)

    steps = {}
    for sm in re.finditer(r'(INITIAL_)?STEP\s+NAME="([^"]+)"\s+DEFINITION="([^"]+)"\s*\{', pfc):
        sname, sdef = sm.group(2), sm.group(3)
        sbody = db_parser.extract_block(pfc, sm.end() - 1)
        desc = re.search(r'DESCRIPTION="([^"]*)"', sbody)
        rect = re.search(r'RECTANGLE=\s*\{\s*X=(-?\d+)\s+Y=(-?\d+)\s+H=(\d+)\s+W=(\d+)', sbody)
        ualias = re.search(r'UNIT_ALIAS="([^"]*)"', sbody)
        sparams = []
        deferred = []
        for spm in re.finditer(r'STEP_PARAMETER\s+NAME="([^"]+)"\s*\{', sbody):
            spb = db_parser.extract_block(sbody, spm.end() - 1)
            origin = re.search(r'ORIGIN=(\w+)', spb)
            grp = re.search(r'GROUP="([^"]*)"', spb)
            dto = re.search(r'DEFERRED_TO="([^"]*)"', spb)
            val = re.search(r'VALUE="([^"]*)"', spb) or re.search(r'VALUE=([^\s{][^\r\n]*)', spb)
            entry = {'name': spm.group(1),
                     'origin': origin.group(1) if origin else '',
                     'group': grp.group(1) if grp else '',
                     'deferred_to': dto.group(1) if dto else '',
                     'value': (val.group(1).strip() if val else '')}
            sparams.append(entry)
            if entry['origin'] == 'DEFERRED':
                deferred.append(entry)
        steps[sname] = {
            'name': sname, 'definition': sdef,
            'desc': desc.group(1) if desc else '',
            'initial': bool(sm.group(1)),
            'params': sparams,
            'deferred': deferred,
            'unit_alias': ualias.group(1) if ualias else '',
            'x': int(rect.group(1)) if rect else None,
            'y': int(rect.group(2)) if rect else None,
            'h': int(rect.group(3)) if rect else 40,
            'w': int(rect.group(4)) if rect else 140,
        }

    transitions = {}
    for tm in re.finditer(r'TRANSITION\s+NAME="([^"]+)"\s*\{', pfc):
        tbody = db_parser.extract_block(pfc, tm.end() - 1)
        expr = re.search(r'EXPRESSION="((?:[^"\\]|\\.)*)"', tbody)
        desc = re.search(r'DESCRIPTION="([^"]*)"', tbody)
        transitions[tm.group(1)] = {
            'name': tm.group(1),
            'expr': (expr.group(1) if expr else '').replace('\r\n', ' ').replace('\n', ' ').strip(),
            'desc': desc.group(1) if desc else '',
        }

    s2t, t2s = [], []
    for cm in re.finditer(r'STEP_TRANSITION_CONNECTION\s+STEP="([^"]+)"\s+TRANSITION="([^"]+)"', pfc):
        s2t.append((cm.group(1), cm.group(2)))
    for cm in re.finditer(r'TRANSITION_STEP_CONNECTION\s+TRANSITION="([^"]+)"\s+STEP="([^"]+)"', pfc):
        t2s.append((cm.group(1), cm.group(2)))

    return {'steps': steps, 'transitions': transitions, 's2t': s2t, 't2s': t2s}


def _render_pfc_svg(proc):
    """Render the procedure as an SVG SFC diagram using the step X/Y coordinates.
    Transitions are placed on the edges between their source and target steps."""
    steps = proc['steps']
    trans = proc['transitions']
    s2t, t2s = proc['s2t'], proc['t2s']

    # step positions; some steps (START pseudo) have none — synthesize a top slot
    coords = {n: (s['x'], s['y'], s['w'], s['h']) for n, s in steps.items()
              if s['x'] is not None}
    if not coords:
        return ''  # no coordinates, can't draw

    # index edges
    step_outs = {}
    for s, t in s2t:
        step_outs.setdefault(s, []).append(t)
    trans_outs = {}
    for t, s in t2s:
        trans_outs.setdefault(t, []).append(s)
    trans_in = {}
    for s, t in s2t:
        trans_in.setdefault(t, []).append(s)

    # place each transition at the midpoint between its source step(s) and target(s)
    tpos = {}
    for tn in trans:
        srcs = [coords[s] for s in trans_in.get(tn, []) if s in coords]
        tgts = [coords[s] for s in trans_outs.get(tn, []) if s in coords]
        pts = srcs + tgts
        if pts:
            cx = sum(p[0] + p[2] / 2 for p in pts) / len(pts)
            cy = sum(p[1] + p[3] / 2 for p in pts) / len(pts)
            tpos[tn] = (cx, cy)

    # compute viewbox
    xs = [c[0] for c in coords.values()] + [c[0] + c[2] for c in coords.values()]
    ys = [c[1] for c in coords.values()] + [c[1] + c[3] for c in coords.values()]
    pad = 40
    minx, maxx = min(xs) - pad, max(xs) + pad
    miny, maxy = min(ys) - pad, max(ys) + pad
    W, H = maxx - minx, maxy - miny

    def sx(x):
        return x - minx

    def sy(y):
        return y - miny

    svg = [f'<svg class="pfc-svg" viewBox="0 0 {W} {H}" '
           f'xmlns="http://www.w3.org/2000/svg" style="min-width:{min(W, 900)}px">']
    svg.append('<defs><marker id="pfcarr" markerWidth="8" markerHeight="8" refX="6" refY="4" '
               'orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#94a3b8"/></marker></defs>')

    # edges: step -> transition -> step
    def center(name):
        x, y, w, h = coords[name]
        return sx(x) + w / 2, sy(y) + h / 2

    def ortho(x1, y1, x2, y2, arrow=False):
        # L-shaped connector: vertical from source, then horizontal to target — matches
        # the phase SFC's straight-line style (#5) rather than a diagonal.
        mid = f'{x1:.0f},{y1:.0f} {x1:.0f},{y2:.0f} {x2:.0f},{y2:.0f}'
        mk = ' marker-end="url(#pfcarr)"' if arrow else ''
        return (f'<polyline points="{mid}" fill="none" stroke="#94a3b8" '
                f'stroke-width="1.4"{mk}/>')

    for s, t in s2t:
        if s not in coords or t not in tpos:
            continue
        x1, y1 = center(s)
        x2, y2 = tpos[t][0] - minx, tpos[t][1] - miny
        svg.append(ortho(x1, y1, x2, y2))
    for t, s in t2s:
        if s not in coords or t not in tpos:
            continue
        x1, y1 = tpos[t][0] - minx, tpos[t][1] - miny
        x2, y2 = center(s)
        svg.append(ortho(x1, y1, x2, y2, arrow=True))

    # step boxes
    for n, (x, y, w, h) in coords.items():
        s = steps[n]
        fill = '#0f172a' if n == 'START' else '#ffffff'
        txtcol = '#fff' if n == 'START' else '#16202c'
        initial = s.get('initial')
        stroke = '#16a34a' if initial else '#334155'
        sw = 2.5 if initial else 1.5
        label = html.escape(n)
        defn = html.escape(s.get('definition', ''))
        svg.append(f'<g class="pfc-step" data-step="{html.escape(n, quote=True)}">')
        svg.append(f'<rect x="{sx(x)}" y="{sy(y)}" width="{w}" height="{h}" rx="5" '
                   f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        svg.append(f'<text x="{sx(x) + w/2:.0f}" y="{sy(y) + 16:.0f}" text-anchor="middle" '
                   f'font-size="11" font-weight="600" fill="{txtcol}">{label}</text>')
        if defn and n != 'START':
            svg.append(f'<text x="{sx(x) + w/2:.0f}" y="{sy(y) + 30:.0f}" text-anchor="middle" '
                       f'font-size="9" fill="#64748b">{defn[:22]}</text>')
        svg.append('</g>')

    # transition bars + labels
    for tn, (cx, cy) in tpos.items():
        px, py = cx - minx, cy - miny
        td = trans.get(tn, {})
        has_expr = bool(td.get('expr'))
        color = '#7c3aed' if has_expr else '#94a3b8'
        svg.append(f'<g class="pfc-trans" data-trans="{html.escape(tn, quote=True)}" '
                   f'style="cursor:pointer">')
        svg.append(f'<rect x="{px-30:.0f}" y="{py-7:.0f}" width="60" height="14" rx="3" '
                   f'fill="#fff" stroke="{color}" stroke-width="1.3"/>')
        svg.append(f'<text x="{px:.0f}" y="{py+3:.0f}" text-anchor="middle" font-size="9" '
                   f'font-weight="600" fill="{color}">{html.escape(tn[:12])}</text>')
        svg.append('</g>')

    svg.append('</svg>')
    return '\n'.join(svg)


# ───────────────────────── rendering ─────────────────────────

def build_recipe_html(recipe, known_recipes=None):
    known_recipes = known_recipes or set()
    """Render a parsed recipe as an HTML view: metadata + parameters + a
    procedure flow (steps and transitions with expressions)."""
    if not recipe:
        return '<span class="empty">No recipe in this export.</span>'
    meta = recipe['meta']
    h = []

    # procedure diagram (SVG) + flow (the main content)
    proc = recipe.get('procedure')
    if proc and proc['steps']:
        diagram = _render_pfc_svg(proc)
        h.append('<div class="card" style="max-width:none"><h3>Procedure diagram ('
                 + str(len(proc['steps'])) + ' steps, '
                 + str(len(proc['transitions'])) + ' transitions)</h3>')
        if diagram:
            # embed transition expressions as data attributes for click-to-view
            # (handled by the explorer's delegated handler — inline <script> injected
            # via innerHTML would never execute).
            import json as _json
            texpr = {tn: td.get('expr', '') for tn, td in proc['transitions'].items()}
            pid = 'pfcPanel_' + _safe_id(recipe['meta']['name'])
            h.append('<div class="pfc-toolbar">'
                     '<button class="pfc-zbtn" data-pfc-zoom="out" title="Zoom out">\u2212</button>'
                     '<button class="pfc-zbtn" data-pfc-zoom="reset" title="Reset">\u25a1</button>'
                     '<button class="pfc-zbtn" data-pfc-zoom="in" title="Zoom in">+</button>'
                     '<span class="pfc-hint2">drag to pan \u00b7 scroll to zoom</span></div>')
            h.append('<div class="pfc-wrap" data-pfc-expr="'
                     + html.escape(_json.dumps(texpr), quote=True)
                     + '" data-pfc-panel="' + pid + '"><div class="pfc-zoomlayer">' + diagram + '</div></div>')
            h.append('<div class="pfc-panel" id="' + pid
                     + '"><span class="pfc-hint">Click a transition in the diagram to see its expression.</span></div>')
        else:
            h.append('<span class="empty">Diagram coordinates unavailable; see the flow below.</span>')
        h.append('</div>')

        # textual flow (steps + transitions interleaved)
        h.append('<div class="card" style="max-width:none"><h3>Procedure flow</h3>')
        h.append(_render_flow(proc, known_recipes))
        h.append('</div>')

    # formula parameters, grouped
    params = recipe.get('params', [])
    if params:
        by_group = {}
        for p in params:
            by_group.setdefault(p['group'] or 'Ungrouped', []).append(p)
        h.append('<div class="card"><h3>Formula parameters (' + str(len(params)) + ')</h3>')
        for g in sorted(by_group):
            h.append('<div class="rp-group">' + html.escape(g) + '</div>')
            h.append('<table class="fbd-table"><thead><tr><th>Name</th><th>Type</th>'
                     '<th>Connection</th><th>Locked</th></tr></thead><tbody>')
            for p in by_group[g]:
                h.append('<tr><td><code>' + html.escape(p['name']) + '</code></td><td>'
                         + html.escape(p['type']) + '</td><td>' + html.escape(p['connection'])
                         + '</td><td>' + ('yes' if p['locked'] else '') + '</td></tr>')
            h.append('</tbody></table>')
        h.append('</div>')

    # unit aliases
    aliases = recipe.get('aliases', [])
    if aliases:
        h.append('<div class="card"><h3>Unit aliases (' + str(len(aliases)) + ')</h3>'
                 '<table class="fbd-table"><thead><tr><th>Alias</th><th>Description</th></tr></thead><tbody>')
        for a in aliases:
            h.append('<tr><td><code>' + html.escape(a['name']) + '</code></td><td>'
                     + html.escape(a['desc']) + '</td></tr>')
        h.append('</tbody></table></div>')

    return '\n'.join(h)


def _render_flow(proc, known_recipes=None):
    """Render the procedure as steps interleaved with their outgoing transitions.
    known_recipes: set of recipe names present in the export, so a step whose
    definition references one becomes a drill-down link (#3)."""
    known_recipes = known_recipes or set()
    steps, trans = proc['steps'], proc['transitions']
    s2t, t2s = proc['s2t'], proc['t2s']
    # index: step -> [transitions]; transition -> [steps]
    step_outs = {}
    for s, t in s2t:
        step_outs.setdefault(s, []).append(t)
    trans_outs = {}
    for t, s in t2s:
        trans_outs.setdefault(t, []).append(s)

    # order: start from initial step(s), walk breadth-first
    order = []
    seen = set()
    initials = [n for n, s in steps.items() if s.get('initial')]
    # 'START' is a pseudo-step referenced in edges but not a real step
    frontier = initials or list(steps.keys())[:1]
    # include START pseudo if present in edges
    if any(s == 'START' for s, _ in s2t):
        frontier = ['START'] + frontier
    while frontier:
        nxt = []
        for s in frontier:
            if s in seen:
                continue
            seen.add(s)
            order.append(s)
            for t in step_outs.get(s, []):
                for ns in trans_outs.get(t, []):
                    if ns not in seen:
                        nxt.append(ns)
        frontier = nxt
    # append any steps not reached
    for n in steps:
        if n not in seen:
            order.append(n)

    rows = ['<div class="rflow">']
    for sname in order:
        if sname == 'START':
            rows.append('<div class="rf-step rf-start">START</div>')
        else:
            s = steps.get(sname)
            if not s:
                continue
            label = html.escape(sname)
            defn = html.escape(s['definition'])
            npar = len(s.get('params', []))
            ndef = len(s.get('deferred', []))
            ualias = s.get('unit_alias', '')
            init = ' <span class="rf-init">initial</span>' if s.get('initial') else ''
            alias_tag = (' <span class="rf-alias">unit: ' + html.escape(ualias) + '</span>') if ualias else ''
            # if the definition matches another recipe object, make it a drill-down link
            base_def = re.sub(r':\d+$', '', s['definition'])
            if base_def in known_recipes:
                defn_html = ('<span class="rf-drill" data-recipe="' + html.escape(base_def, quote=True)
                             + '"><code>' + defn + '</code> \u2197</span>')
            else:
                defn_html = '<code>' + defn + '</code>'
            rows.append('<div class="rf-step"><div class="rf-name">' + label + init + alias_tag
                        + '</div><div class="rf-def">' + _layer_label(s['definition'])
                        + ': ' + defn_html
                        + (' \u00b7 ' + str(npar) + ' parameters' if npar else '')
                        + (' \u00b7 <span class="rf-defcount">' + str(ndef) + ' deferred</span>' if ndef else '')
                        + '</div>')
            # deferred parameters (the values passed down to the next layer)
            if s.get('deferred'):
                rows.append('<div class="rf-defers"><div class="rf-defhdr">Deferred parameters (passed to underlying object)</div>')
                for d in s['deferred']:
                    rows.append('<div class="rf-defrow"><code>' + html.escape(d['name']) + '</code>'
                                + ' \u2192 <code>' + html.escape(d['deferred_to'] or d['name']) + '</code>'
                                + (' <span class="rf-defgrp">' + html.escape(d['group']) + '</span>' if d.get('group') else '')
                                + '</div>')
                rows.append('</div>')
            rows.append('</div>')  # close rf-step
        # outgoing transitions from this step
        for t in step_outs.get(sname, []):
            td = trans.get(t, {})
            expr = td.get('expr', '')
            targets = trans_outs.get(t, [])
            tgt = ', '.join(html.escape(x) for x in targets)
            rows.append('<div class="rf-trans"><span class="rf-tname">\u2500 ' + html.escape(t)
                        + '</span> <span class="rf-tgt">\u2192 ' + (tgt or '?') + '</span>'
                        + ('<div class="rf-expr">' + html.escape(expr) + '</div>' if expr else '')
                        + '</div>')
    rows.append('</div>')
    return '\n'.join(rows)


def _layer_label(definition):
    """Infer the recipe layer of a step's definition from DeltaV naming conventions:
    _UP = unit procedure, _OP = operation, _PH/PHASE = phase. Falls back to a generic
    label so the hierarchy Procedure > Unit Procedure > Operation > Phase reads clearly."""
    d = (definition or '').upper()
    if d.endswith('_UP') or '_UP' in d:
        return 'unit procedure'
    if d.endswith('_OP') or '_OP' in d:
        return 'operation'
    if d.endswith('_PH') or 'PHASE' in d:
        return 'phase'
    return 'step definition'


def _safe_id(s):
    return re.sub(r'[^A-Za-z0-9]', '_', s or 'x')


RECIPE_CSS = """
.rflow{display:flex;flex-direction:column;gap:0;font-size:13px}
.rf-step{border:1px solid var(--border,#e2e8f0);border-radius:9px;padding:9px 12px;background:var(--surface,#fff);margin:3px 0}
.rf-start{background:#0f172a;color:#fff;font-weight:700;text-align:center;max-width:120px}
.rf-name{font-weight:650;color:var(--ink,#16202c)}
.rf-init{font-size:10px;font-weight:700;background:#dcfce7;color:#166534;padding:1px 6px;border-radius:5px;margin-left:6px}
.rf-def{color:var(--ink-3,#64748b);font-size:12px;margin-top:2px}
.rf-trans{padding:3px 0 3px 22px;position:relative;color:#6d28d9;font-size:12px}
.rf-tname{font-weight:600}
.rf-tgt{color:var(--ink-3,#64748b)}
.rf-expr{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#475569;background:#f8fafc;border:1px solid var(--border,#e2e8f0);border-radius:6px;padding:4px 8px;margin:3px 0 3px 0;white-space:pre-wrap;word-break:break-word}
.rp-group{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#64748b;margin:12px 0 6px}
.rf-alias{font-size:10px;font-weight:600;background:#e0f2fe;color:#075985;padding:1px 7px;border-radius:5px;margin-left:6px}
.rf-defcount{color:#b45309;font-weight:600}
.rf-drill{cursor:pointer;color:#7c3aed}
.rf-drill:hover{text-decoration:underline}
.rf-defers{margin:5px 0 2px 14px;padding:7px 10px;background:#fffbeb;border:1px solid #fde68a;border-radius:7px}
.rf-defhdr{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:#b45309;margin-bottom:5px}
.rf-defrow{font-size:12px;color:#475569;padding:1px 0}
.rf-defgrp{font-size:10px;color:#94a3b8;margin-left:5px}
.pfc-wrap{overflow:auto;border:1px solid var(--border,#e2e8f0);border-radius:9px;background:#fff;padding:10px;max-height:520px;cursor:grab;position:relative}
.pfc-wrap.panning{cursor:grabbing}
.pfc-zoomlayer{transform-origin:0 0;transition:transform .05s linear;display:inline-block}
.pfc-toolbar{display:flex;align-items:center;gap:5px;margin-bottom:7px}
.pfc-zbtn{width:26px;height:26px;border:1px solid var(--border,#e2e8f0);background:var(--surface,#fff);border-radius:6px;cursor:pointer;font-size:14px;line-height:1;color:var(--ink,#16202c);display:inline-flex;align-items:center;justify-content:center}
.pfc-zbtn:hover{border-color:var(--accent,#7c3aed);color:var(--accent,#7c3aed)}
.pfc-hint2{font-size:11px;color:var(--ink-3,#94a3b8);margin-left:6px}
.pfc-svg{display:block}
.pfc-step rect{transition:stroke .12s}
.pfc-trans:hover rect{fill:#f5f3ff}
.pfc-panel{margin-top:10px;padding:10px 12px;border:1px solid var(--border,#e2e8f0);border-radius:8px;background:#f8fafc;min-height:24px}
.pfc-hint{color:#94a3b8;font-size:12px}
.pfc-tname{font-weight:700;color:#7c3aed;font-size:12px;margin-bottom:4px}
.pfc-texpr{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#334155;white-space:pre-wrap;word-break:break-word}
"""

