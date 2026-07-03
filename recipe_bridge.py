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


def parse_recipe(text):
    """Parse a BATCH_RECIPE export into a structured dict, or None if absent."""
    m = re.search(r'BATCH_RECIPE(?:\s+NAME="([^"]+)")?', text)
    if not m:
        return None
    blk = _blk(text, m.start())
    name = m.group(1) or ''

    def _scalar(key):
        mm = re.search(key + r'="([^"]*)"', blk)
        if mm:
            return mm.group(1)
        mm = re.search(key + r'=([^\s{][^\r\n]*)', blk)
        return mm.group(1).strip() if mm else ''

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

    # formula parameters (recipe-level inputs)
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

    # unit aliases (which physical units this procedure can bind)
    aliases = []
    for am in re.finditer(r'UNIT_ALIAS\s+NAME="([^"]+)"\s*\{', blk):
        abody = db_parser.extract_block(blk, am.end() - 1)
        desc = re.search(r'DESCRIPTION="([^"]*)"', abody)
        aliases.append({'name': am.group(1),
                        'desc': desc.group(1) if desc else ''})

    proc = _parse_pfc(blk)

    return {'meta': meta, 'params': params, 'aliases': aliases, 'procedure': proc}


def _parse_pfc(blk):
    """Parse the PFC_ALGORITHM into steps, transitions, and edges."""
    pm = re.search(r'PFC_ALGORITHM\s*\{', blk)
    if not pm:
        return None
    pfc = db_parser.extract_block(blk, pm.end() - 1)

    steps = {}
    # both INITIAL_STEP and STEP
    for sm in re.finditer(r'(INITIAL_)?STEP\s+NAME="([^"]+)"\s+DEFINITION="([^"]+)"\s*\{', pfc):
        sname, sdef = sm.group(2), sm.group(3)
        sbody = db_parser.extract_block(pfc, sm.end() - 1)
        desc = re.search(r'DESCRIPTION="([^"]*)"', sbody)
        # step parameters (grouped)
        sparams = []
        for spm in re.finditer(r'STEP_PARAMETER\s+NAME="([^"]+)"\s*\{', sbody):
            spb = db_parser.extract_block(sbody, spm.end() - 1)
            origin = re.search(r'ORIGIN=(\w+)', spb)
            grp = re.search(r'GROUP="([^"]*)"', spb)
            sparams.append({'name': spm.group(1),
                           'origin': origin.group(1) if origin else '',
                           'group': grp.group(1) if grp else ''})
        steps[sname] = {
            'name': sname, 'definition': sdef,
            'desc': desc.group(1) if desc else '',
            'initial': bool(sm.group(1)),
            'params': sparams,
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

    # edges
    s2t, t2s = [], []
    for cm in re.finditer(r'STEP_TRANSITION_CONNECTION\s+STEP="([^"]+)"\s+TRANSITION="([^"]+)"', pfc):
        s2t.append((cm.group(1), cm.group(2)))
    for cm in re.finditer(r'TRANSITION_STEP_CONNECTION\s+TRANSITION="([^"]+)"\s+STEP="([^"]+)"', pfc):
        t2s.append((cm.group(1), cm.group(2)))

    return {'steps': steps, 'transitions': transitions, 's2t': s2t, 't2s': t2s}


# ───────────────────────── rendering ─────────────────────────

def build_recipe_html(recipe):
    """Render a parsed recipe as an HTML view: metadata + parameters + a
    procedure flow (steps and transitions with expressions)."""
    if not recipe:
        return '<span class="empty">No recipe in this export.</span>'
    meta = recipe['meta']
    h = []

    # procedure flow (the main content) — render as an ordered SFC-like list
    proc = recipe.get('procedure')
    if proc and proc['steps']:
        h.append('<div class="card" style="max-width:none"><h3>Procedure flow ('
                 + str(len(proc['steps'])) + ' steps, '
                 + str(len(proc['transitions'])) + ' transitions)</h3>')
        h.append(_render_flow(proc))
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


def _render_flow(proc):
    """Render the procedure as steps interleaved with their outgoing transitions."""
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
            init = ' <span class="rf-init">initial</span>' if s.get('initial') else ''
            rows.append('<div class="rf-step"><div class="rf-name">' + label + init
                        + '</div><div class="rf-def">unit procedure: <code>' + defn + '</code>'
                        + (' · ' + str(npar) + ' parameters' if npar else '') + '</div></div>')
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
"""
