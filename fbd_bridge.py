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
