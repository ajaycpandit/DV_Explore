"""
Function Block Diagram (FBD) SVG renderer.

Draws a parsed FBD as an SVG schematic using DeltaV's stored block coordinates.
Blocks are boxes at their X/Y; wires are drawn between blocks (orthogonal-ish
routing from the right edge of the source to the left edge of the destination).
Composite blocks are visually distinct and carry a data attribute so the explorer
can make them clickable for drill-down.
"""

import html


# block-type color accents (basic types vs composites vs I/O)
_TYPE_COLOR = {
    'PID': '#2563eb', 'PIDWCALARM': '#2563eb',
    'AI': '#0891b2', 'AO': '#0891b2', 'DI': '#0891b2', 'DO': '#0891b2',
    'AT': '#7c3aed', 'CND': '#d97706', 'ACT': '#059669',
    'ALMWCALARM': '#dc2626', 'CALC': '#db2777',
}
_COMPOSITE_COLOR = '#475569'


def _color(b):
    if b['is_composite']:
        return _COMPOSITE_COLOR
    return _TYPE_COLOR.get(b['definition'], '#334155')


def render_fbd_svg(fbd, scale=0.5, pad=40):
    """Return an SVG string for the parsed fbd dict, including DeltaV's section
    frames and labels so the layout resembles the Control Studio print."""
    blocks = fbd['blocks']
    wires = fbd['wires']
    frames = fbd.get('frames', [])
    labels = fbd.get('labels', [])
    if not blocks:
        return '<p style="color:#94a3b8">No function blocks to display.</p>'

    # limit to the logic-diagram region: ignore frames/labels far below the
    # lowest block (help text, revision history, module-config notes). Also drop
    # frames that start above but extend far past the block region.
    maxby = max(b['y'] + b['h'] for b in blocks)
    region_cut = maxby + 60
    frames = [f for f in frames if f['y'] < region_cut and (f['y'] + f['h']) < region_cut + 400]
    labels = [l for l in labels if l['y'] < region_cut]

    # bounds (include frames so section boxes aren't clipped)
    allx = [b['x'] for b in blocks] + [f['x'] for f in frames]
    ally = [b['y'] for b in blocks] + [f['y'] for f in frames]
    allx2 = [b['x'] + b['w'] for b in blocks] + [f['x'] + f['w'] for f in frames]
    ally2 = [b['y'] + b['h'] for b in blocks] + [f['y'] + f['h'] for f in frames]
    minx, miny = min(allx), min(ally)
    maxx, maxy = max(allx2), max(ally2)
    term_col_w = 150
    W = (maxx - minx) * scale + pad * 2 + term_col_w * 2
    H = (maxy - miny) * scale + pad * 2

    def sx(x): return (x - minx) * scale + pad + term_col_w
    def sy(y): return (y - miny) * scale + pad

    bmap = {b['name']: b for b in blocks}

    left_terms, right_terms = [], []
    for w in wires:
        if w['src_block'] is None and w['source'] not in left_terms:
            left_terms.append(w['source'])
        if w['dst_block'] is None and w['destination'] not in right_terms:
            right_terms.append(w['destination'])
    term_y = {}
    for i, tname in enumerate(left_terms):
        term_y[('L', tname)] = pad + 30 + i * 34
    for i, tname in enumerate(right_terms):
        term_y[('R', tname)] = pad + 30 + i * 34

    svg = []
    svg.append(f'<svg class="fbd" viewBox="0 0 {W:.0f} {H:.0f}" '
               f'xmlns="http://www.w3.org/2000/svg" '
               f'style="width:100%;height:auto;background:#fcfcfd">')
    svg.append('<defs><marker id="arr" markerWidth="8" markerHeight="8" '
               'refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" '
               'fill="#94a3b8"/></marker></defs>')

    # --- section frames (drawn first, behind everything) ---
    for f in frames:
        x, y = sx(f['x']), sy(f['y'])
        w, h = f['w'] * scale, f['h'] * scale
        svg.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" '
                   f'fill="none" stroke="#dbe3ec" stroke-width="1"/>')
    # --- section labels ---
    for l in labels:
        lx, ly = sx(l['x']), sy(l['y'])
        svg.append(f'<text x="{lx:.0f}" y="{ly:.0f}" font-size="11" '
                   f'fill="#64748b" font-weight="600">{html.escape(l["text"])}</text>')

    # --- wires first (under blocks) ---
    def port_xy(endpoint_block, port, is_source):
        if endpoint_block is None:
            return None  # terminal handled separately
        b = bmap.get(endpoint_block)
        if not b:
            return None
        cx = sx(b['x']) + (b['w'] * scale if is_source else 0)
        cy = sy(b['y']) + b['h'] * scale / 2
        return (cx, cy)

    for w in wires:
        # source point
        if w['src_block'] is None:
            ty = term_y.get(('L', w['source']))
            if ty is None:
                continue
            x1, y1 = pad + 20, ty
        else:
            pt = port_xy(w['src_block'], w['src_port'], True)
            if not pt:
                continue
            x1, y1 = pt
        # destination point
        if w['dst_block'] is None:
            ty = term_y.get(('R', w['destination']))
            if ty is None:
                continue
            x2, y2 = W - pad - 20, ty
        else:
            pt = port_xy(w['dst_block'], w['dst_port'], False)
            if not pt:
                continue
            x2, y2 = pt
        midx = (x1 + x2) / 2
        svg.append(f'<path d="M{x1:.0f},{y1:.0f} H{midx:.0f} V{y2:.0f} H{x2:.0f}" '
                   f'fill="none" stroke="#94a3b8" stroke-width="1.2" marker-end="url(#arr)"/>')

    # --- terminals ---
    def term(x, y, name, anchor):
        svg.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3" fill="#64748b"/>')
        tx = x + (8 if anchor == 'start' else -8)
        svg.append(f'<text x="{tx:.0f}" y="{y+3:.0f}" font-size="10" '
                   f'fill="#475569" text-anchor="{anchor}" font-family="monospace">'
                   f'{html.escape(name)}</text>')
    for tname in left_terms:
        term(pad + 20, term_y[('L', tname)], tname, 'start')
    for tname in right_terms:
        term(W - pad - 20, term_y[('R', tname)], tname, 'end')

    # --- blocks ---
    for b in blocks:
        x, y = sx(b['x']), sy(b['y'])
        w, h = b['w'] * scale, b['h'] * scale
        col = _color(b)
        comp_attr = (f' data-composite="{html.escape(b["definition"])}" '
                     f'style="cursor:pointer"') if b['is_composite'] else ''
        svg.append(f'<g class="fb{ " fb-composite" if b["is_composite"] else "" }"'
                   f' data-name="{html.escape(b["name"])}"{comp_attr}>')
        dash = ' stroke-dasharray="4 2"' if b['is_composite'] else ''
        svg.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" '
                   f'rx="3" fill="#ffffff" stroke="{col}" stroke-width="1.6"{dash}/>')
        svg.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="14" '
                   f'rx="3" fill="{col}"/>')
        svg.append(f'<text x="{x+w/2:.0f}" y="{y+10:.0f}" font-size="9" '
                   f'fill="#ffffff" text-anchor="middle" font-weight="bold">'
                   f'{html.escape(b["definition"])}</text>')
        svg.append(f'<text x="{x+w/2:.0f}" y="{y+h/2+6:.0f}" font-size="10" '
                   f'fill="#0f172a" text-anchor="middle">{html.escape(b["name"])}</text>')
        if b['is_composite']:
            svg.append(f'<text x="{x+w-4:.0f}" y="{y+h-4:.0f}" font-size="8" '
                       f'fill="{col}" text-anchor="end">[+]</text>')
        svg.append('</g>')

    svg.append('</svg>')
    return '\n'.join(svg)
