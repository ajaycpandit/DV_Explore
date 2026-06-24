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


def build_fbd_views(text):
    """Return {object_name: fbd_view_html} for every module/composite/composite-
    definition in the export that contains a function block diagram. This
    includes nested composite definitions (e.g. C_C_ML_V01) so the explorer can
    drill from a CM into its composite blocks."""
    views = {}
    objs = fbd_parser.list_fbd_objects(text)
    for o in objs:
        name = o['name']
        fbd = fbd_parser.parse_module_fbd(text, name)
        if not fbd or not fbd['blocks']:
            continue
        views[name] = build_fbd_view_html(fbd)
    return views


def build_fbd_view_html(fbd):
    """Compose the FBD leaf view: diagram + composite list + interface +
    connection table. Sectioned so the explorer can show it inline."""
    svg = fbd_render.render_fbd_svg(fbd)

    parts = []
    parts.append('<div class="fbd-wrap">')

    # diagram
    parts.append('<div class="fbd-diagram-card">')
    parts.append(f'<div class="fbd-head">Function Block Diagram — {html.escape(fbd["name"])}'
                 f'<span class="fbd-sub"> · {len(fbd["blocks"])} blocks · '
                 f'{len(fbd["wires"])} wires · Algorithm: FBD</span></div>')
    parts.append(f'<div class="fbd-svg-holder">{svg}</div>')
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


def fbd_block_table(fbd):
    """Block inventory rows (name, type, composite?) — used by the doc table."""
    return [{'name': b['name'], 'type': b['definition'],
             'composite': b['is_composite'], 'desc': b.get('description', '')}
            for b in fbd['blocks']]


def fbd_connection_table(fbd):
    """Wire/connection rows (source -> destination)."""
    return [{'source': w['source'], 'destination': w['destination']}
            for w in fbd['wires']]
