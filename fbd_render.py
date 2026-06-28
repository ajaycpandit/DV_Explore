"""
Function Block Diagram (FBD) SVG renderer.

Draws a parsed FBD as an SVG schematic using DeltaV's stored block coordinates.
Blocks are boxes at their X/Y. Wires route between block ports; ports are
distributed along each block's edge so multiple connections don't converge on a
single point. Module-level parameters (terminals) are drawn as small labeled
boxes placed right next to the block they connect to — close to how DeltaV's
Control Studio print shows off-page parameter connectors — with a short stub,
instead of long wires to a far-off column. Composite blocks are clickable for
drill-down; expression blocks (ACT/CALC/CND/...) are clickable to pop the logic.
"""

import html
import json


# block-type color accents (basic types vs composites vs I/O)
_TYPE_COLOR = {
    'PID': '#2563eb', 'PIDWCALARM': '#2563eb',
    'AI': '#0891b2', 'AO': '#0891b2', 'DI': '#0891b2', 'DO': '#0891b2',
    'AT': '#7c3aed', 'CND': '#d97706', 'ACT': '#059669',
    'ALMWCALARM': '#dc2626', 'CALC': '#db2777',
}
_COMPOSITE_COLOR = '#475569'

# ── object-type glyphs: marks that mirror DeltaV/ISA control-strategy
# conventions (real gate shapes, condition diamond, instrument bubble, valve),
# so the diagram reads like a control drawing and survives grayscale printing ──
_GLYPH_FOR = {
    'AND': 'and', 'BAND': 'and',
    'OR': 'or', 'BOR': 'or',
    'NOT': 'not',
    'NAND': 'nand', 'NOR': 'nor', 'XOR': 'xor', 'BXOR': 'xor',
    'PDE': 'edge_up', 'BDE': 'edge_up',
    'NDE': 'edge_dn',
    'ODT': 'timer', 'OST': 'timer', 'OSP': 'timer', 'DTON': 'timer', 'DTOF': 'timer',
    'CND': 'cond',
    'CALC': 'calc',
    'ACT': 'action', 'AT': 'action', 'CALCLOGIC': 'calc',
    'PID': 'pid', 'PIDWCALARM': 'pid', 'RATIO': 'pid', 'RTLM': 'pid',
    'AI': 'analog', 'AO': 'analog', 'AIWCALARM': 'analog', 'ALMWCALARM': 'analog',
    'DI': 'disc', 'DO': 'disc',
    'EDC': 'device', 'DCC': 'device', 'DC': 'device', 'MTR': 'device', 'VLV': 'device',
}


def _type_glyph(key, gx, gy, color='#ffffff', s=8.0):
    """SVG glyph for a control-strategy block type, in [gx,gy .. gx+s,gy+s]."""
    sw = f'stroke="{color}" stroke-width="1.1" fill="none" stroke-linejoin="round"'
    fl = f'fill="{color}" stroke="none"'
    bub = (lambda cx, cy: f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{s*0.13:.1f}" {sw}/>')
    if key in ('and', 'nand'):       # AND gate (flat back, round front)
        g = (f'<path d="M{gx},{gy} H{gx+s*0.45:.1f} A{s*0.5:.1f},{s*0.5:.1f} 0 0 1 '
             f'{gx+s*0.45:.1f},{gy+s:.1f} H{gx} Z" {sw}/>')
        return g + (bub(gx + s * 0.98 + 1, gy + s * 0.5) if key == 'nand' else '')
    if key in ('or', 'nor', 'xor'):  # OR gate (curved back, pointed front)
        g = (f'<path d="M{gx},{gy} Q{gx+s*0.55:.1f},{gy:.1f} {gx+s:.1f},{gy+s*0.5:.1f} '
             f'Q{gx+s*0.55:.1f},{gy+s:.1f} {gx},{gy+s:.1f} '
             f'Q{gx+s*0.28:.1f},{gy+s*0.5:.1f} {gx},{gy:.1f} Z" {sw}/>')
        if key == 'xor':
            g += f'<path d="M{gx-s*0.15:.1f},{gy} Q{gx+s*0.13:.1f},{gy+s*0.5:.1f} {gx-s*0.15:.1f},{gy+s:.1f}" {sw}/>'
        return g + (bub(gx + s * 1.05, gy + s * 0.5) if key == 'nor' else '')
    if key == 'not':                 # inverter: triangle + bubble
        return (f'<path d="M{gx},{gy} L{gx},{gy+s:.1f} L{gx+s*0.72:.1f},{gy+s*0.5:.1f} Z" {sw}/>'
                + bub(gx + s * 0.86, gy + s * 0.5))
    if key == 'edge_up':             # rising-edge step
        return f'<path d="M{gx},{gy+s:.1f} H{gx+s*0.45:.1f} V{gy:.1f} H{gx+s:.1f}" {sw}/>'
    if key == 'edge_dn':             # falling-edge step
        return f'<path d="M{gx},{gy:.1f} H{gx+s*0.45:.1f} V{gy+s:.1f} H{gx+s:.1f}" {sw}/>'
    if key == 'timer':               # clock face
        return (f'<circle cx="{gx+s*0.5:.1f}" cy="{gy+s*0.5:.1f}" r="{s*0.48:.1f}" {sw}/>'
                f'<path d="M{gx+s*0.5:.1f},{gy+s*0.5:.1f} V{gy+s*0.2:.1f} M{gx+s*0.5:.1f},{gy+s*0.5:.1f} H{gx+s*0.74:.1f}" {sw}/>')
    if key == 'cond':                # decision diamond
        return (f'<path d="M{gx+s*0.5:.1f},{gy} L{gx+s:.1f},{gy+s*0.5:.1f} '
                f'L{gx+s*0.5:.1f},{gy+s:.1f} L{gx},{gy+s*0.5:.1f} Z" {sw}/>')
    if key == 'calc':                # sigma (summation)
        return f'<path d="M{gx+s:.1f},{gy} H{gx} L{gx+s*0.5:.1f},{gy+s*0.5:.1f} L{gx},{gy+s:.1f} H{gx+s:.1f}" {sw}/>'
    if key == 'action':              # ƒ (function/action)
        return (f'<path d="M{gx+s*0.7:.1f},{gy+s*0.1:.1f} Q{gx+s*0.35:.1f},{gy:.1f} {gx+s*0.38:.1f},{gy+s*0.45:.1f} '
                f'V{gy+s:.1f} M{gx+s*0.15:.1f},{gy+s*0.45:.1f} H{gx+s*0.62:.1f}" {sw}/>')
    if key == 'pid':                 # ISA instrument bubble
        return (f'<circle cx="{gx+s*0.5:.1f}" cy="{gy+s*0.5:.1f}" r="{s*0.48:.1f}" {sw}/>'
                f'<path d="M{gx+s*0.05:.1f},{gy+s*0.5:.1f} H{gx+s*0.95:.1f}" {sw}/>')
    if key == 'analog':              # sine wave
        return (f'<path d="M{gx},{gy+s*0.55:.1f} q{s*0.25:.1f},-{s*0.55:.1f} {s*0.5:.1f},0 '
                f't{s*0.5:.1f},0" {sw}/>')
    if key == 'disc':                # discrete: square wave
        return f'<path d="M{gx},{gy+s:.1f} V{gy+s*0.5:.1f} H{gx+s*0.4:.1f} V{gy:.1f} H{gx+s*0.7:.1f} V{gy+s*0.5:.1f} H{gx+s:.1f}" {sw}/>'
    if key == 'device':              # valve bow-tie
        return (f'<path d="M{gx},{gy} L{gx},{gy+s:.1f} L{gx+s*0.5:.1f},{gy+s*0.5:.1f} Z" {fl}/>'
                f'<path d="M{gx+s:.1f},{gy} L{gx+s:.1f},{gy+s:.1f} L{gx+s*0.5:.1f},{gy+s*0.5:.1f} Z" {fl}/>')
    if key == 'composite':           # nested squares
        return (f'<rect x="{gx:.1f}" y="{gy:.1f}" width="{s*0.66:.1f}" height="{s*0.66:.1f}" {sw}/>'
                f'<rect x="{gx+s*0.34:.1f}" y="{gy+s*0.34:.1f}" width="{s*0.66:.1f}" '
                f'height="{s*0.66:.1f}" {sw}/>')
    return ''


def _glyph_key(deftype):
    return _GLYPH_FOR.get((deftype or '').upper())

# parameter (terminal) box geometry, in screen px
_PBOX_W = 132
_PBOX_H = 20
_PGAP = 16            # gap between block edge and its parameter box
_MARGIN = 185         # horizontal room reserved on each side for parameter boxes


def _color(b):
    if b['is_composite']:
        return _COMPOSITE_COLOR
    return _TYPE_COLOR.get(b['definition'], '#334155')


def _box_w(label, char_w=6.4, padx=16, lo=40, hi=280):
    return max(lo, min(len(label) * char_w + padx, hi))


def _fit_label(name, maxw, char_w=6.4, padx=16):
    w = len(name) * char_w + padx
    if w <= maxw:
        return name, max(40, w)
    keep = int((maxw - padx) / char_w) - 1
    return name[:max(1, keep)] + '\u2026', maxw


def _overlap(a, b, m=2):
    return (a[0] < b[2] + m and a[2] > b[0] - m and
            a[1] < b[3] + m and a[3] > b[1] - m)


_CHROME_LABELS = (
    'REVISION HISTORY', 'MODULE CONFIGURATION', 'User Defined Variables',
    'Tuning Parameters', 'Operating Parameters', 'Calculated Values',
    'Limit Values', 'Description', 'Value', 'Maximum Number',
    'Input Parameters', 'Output Parameters', 'Open', 'Tag of this module',
)


def _is_chrome(text):
    """True for DeltaV print-template boilerplate (parameter-table headers,
    revision/config sections, device-share notes) that isn't part of the FBD
    logic and only clutters a diagram view."""
    t = text.strip()
    if 'SHARED' in t:
        return True
    return any(t == c or t.startswith(c) for c in _CHROME_LABELS)


def _make_axis_remap(occupied, min_gap=90, keep=60):
    """Return a monotonic piecewise-linear map old->new that collapses any empty
    band wider than `min_gap` (in DeltaV units) down to `keep`, leaving occupied
    spans at 1:1 so blocks keep their size and relative order."""
    if not occupied:
        return lambda v: v
    occ = sorted(occupied)
    merged = [list(occ[0])]
    for lo, hi in occ[1:]:
        if lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    pts = [(merged[0][0], merged[0][0])]
    cur = merged[0][0]
    for i, (lo, hi) in enumerate(merged):
        if i > 0:
            gap = lo - merged[i - 1][1]
            cur += keep if gap > min_gap else gap
            pts.append((lo, cur))
        cur += hi - lo
        pts.append((hi, cur))

    def remap(v):
        if v <= pts[0][0]:
            return pts[0][1] + (v - pts[0][0])
        if v >= pts[-1][0]:
            return pts[-1][1] + (v - pts[-1][0])
        for (o0, n0), (o1, n1) in zip(pts, pts[1:]):
            if o0 <= v <= o1:
                return n0 if o1 == o0 else n0 + (v - o0) * (n1 - n0) / (o1 - o0)
        return v
    return remap


def _seg_hits(xa, ya, xb, yb, obstacles):
    """True if an axis-aligned segment crosses any obstacle rect interior."""
    if abs(ya - yb) < 0.5:  # horizontal
        lo, hi = sorted((xa, xb))
        return any(ry0 < ya < ry1 and lo < rx1 and hi > rx0
                   for rx0, ry0, rx1, ry1 in obstacles)
    lo, hi = sorted((ya, yb))  # vertical
    return any(rx0 < xa < rx1 and lo < ry1 and hi > ry0
               for rx0, ry0, rx1, ry1 in obstacles)


def _path_clear(pts, obstacles):
    return not any(_seg_hits(a[0], a[1], b[0], b[1], obstacles)
                   for a, b in zip(pts, pts[1:]))


def _route(x1, y1, x2, y2, obstacles, lane_top, lane_bot, bias=0.0):
    """Return a list of orthogonal waypoints from (x1,y1) to (x2,y2) that avoids
    the obstacle rectangles. Tries straight, then H-V-H through a clear vertical
    channel, then a detour over the top / under the bottom lane."""
    if abs(y1 - y2) < 0.5 and not _seg_hits(x1, y1, x2, y2, obstacles):
        return [(x1, y1), (x2, y2)]
    # candidate vertical-channel x positions, nearest the midpoint first
    edges = sorted({round(o[0]) for o in obstacles} | {round(o[2]) for o in obstacles})
    gaps = [(a + b) / 2 for a, b in zip(edges, edges[1:]) if b - a > 14]
    right_lane = max((o[2] for o in obstacles), default=max(x1, x2)) + 18
    left_lane = min((o[0] for o in obstacles), default=min(x1, x2)) - 18
    cands = [(x1 + x2) / 2 + bias, x1 + 14, x2 - 14, right_lane, left_lane] + gaps
    for cx in sorted(set(cands), key=lambda c: abs(c - (x1 + x2) / 2)):
        pts = [(x1, y1), (cx, y1), (cx, y2), (x2, y2)]
        if _path_clear(pts, obstacles):
            return pts
    # detour over the top or under the bottom
    for lane in (lane_top, lane_bot):
        pts = [(x1, y1), (x1 + 12, y1), (x1 + 12, lane),
               (x2 - 12, lane), (x2 - 12, y2), (x2, y2)]
        if _path_clear(pts, obstacles):
            return pts
    return [(x1, y1), ((x1 + x2) / 2, y1), ((x1 + x2) / 2, y2), (x2, y2)]


def _pts_to_d(pts):
    return 'M' + ' L'.join(f'{x:.0f},{y:.0f}' for x, y in pts)


def _layer_component(comp, succ_all, byname, col_gap, row_pitch):
    """Layered (Sugiyama-lite) layout for one connected component: break cycles,
    longest-path layering, barycenter ordering. Returns {name: (x, y)}."""
    from collections import defaultdict, deque
    cs = set(comp)
    succ = defaultdict(list)
    for u in comp:
        for v in succ_all.get(u, []):
            if v in cs:
                succ[u].append(v)
    color = defaultdict(int)
    back = set()

    def dfs(u):
        color[u] = 1
        for v in succ[u]:
            if color[v] == 1:
                back.add((u, v))
            elif color[v] == 0:
                dfs(v)
        color[u] = 2
    for n in comp:
        if color[n] == 0:
            dfs(n)
    le = [(u, v) for u in comp for v in succ[u] if (u, v) not in back]
    fwd = defaultdict(list); rev = defaultdict(list); indeg = {n: 0 for n in comp}
    for u, v in le:
        fwd[u].append(v); rev[v].append(u); indeg[v] += 1
    q = deque([n for n in comp if indeg[n] == 0])
    topo = []
    while q:
        u = q.popleft(); topo.append(u)
        for v in fwd[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    layer = {n: 0 for n in comp}
    for u in topo:
        for v in fwd[u]:
            layer[v] = max(layer[v], layer[u] + 1)
    cols = defaultdict(list)
    for n in comp:
        cols[layer[n]].append(n)
    L = max(cols) + 1
    order = {l: list(cols[l]) for l in cols}
    pos = {n: i for l in order for i, n in enumerate(order[l])}

    def bary(n, adj):
        ns = adj[n]
        return sum(pos[m] for m in ns) / len(ns) if ns else pos[n]
    for _ in range(6):
        for l in range(1, L):
            order[l].sort(key=lambda n: bary(n, rev))
            for i, n in enumerate(order[l]):
                pos[n] = i
        for l in range(L - 2, -1, -1):
            order[l].sort(key=lambda n: bary(n, fwd))
            for i, n in enumerate(order[l]):
                pos[n] = i
    layer_w = {l: max(byname[n]['w'] for n in order[l]) for l in order}
    xcol = {}
    cx = 0
    for l in range(L):
        xcol[l] = cx
        cx += layer_w.get(l, 90) + col_gap
    out = {}
    for l in range(L):
        col = order[l]
        for i, n in enumerate(col):
            out[n] = (xcol[l], i * row_pitch)
    return out


def auto_layout_coords(blocks, wires, col_gap=150, row_pitch=210, pack_width=2100, gap=120):
    """Reposition blocks purely from connectivity. Each connected component is
    laid out left-to-right by signal flow, then components are shelf-packed into
    a compact grid (so modules whose blocks don't interconnect form a tidy grid
    instead of one tall column). Mutates block x/y in place."""
    from collections import defaultdict
    names = [b['name'] for b in blocks]
    byname = {b['name']: b for b in blocks}
    adj = defaultdict(set); succ = defaultdict(list); eset = set()
    for w in wires:
        s, d = w['src_block'], w['dst_block']
        if s in byname and d in byname and s != d:
            adj[s].add(d); adj[d].add(s)
            if (s, d) not in eset:
                succ[s].append(d); eset.add((s, d))
    seen = set(); comps = []
    for n in names:
        if n in seen:
            continue
        stack = [n]; seen.add(n); comp = []
        while stack:
            u = stack.pop(); comp.append(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v); stack.append(v)
        comps.append(comp)
    laid = []
    for comp in comps:
        p = _layer_component(comp, succ, byname, col_gap, row_pitch)
        x0 = min(p[n][0] for n in comp); y0 = min(p[n][1] for n in comp)
        x1 = max(p[n][0] + byname[n]['w'] for n in comp)
        y1 = max(p[n][1] + byname[n]['h'] for n in comp)
        laid.append((comp, p, x0, y0, x1 - x0, y1 - y0))
    laid.sort(key=lambda t: -t[5])  # tallest shelf first
    cur_x = cur_y = shelf_h = 0
    for comp, p, x0, y0, cw, ch in laid:
        if cur_x > 0 and cur_x + cw > pack_width:
            cur_x = 0; cur_y += shelf_h + gap; shelf_h = 0
        for n in comp:
            px, py = p[n]
            byname[n]['x'] = cur_x + (px - x0)
            byname[n]['y'] = cur_y + (py - y0)
        cur_x += cw + gap
        shelf_h = max(shelf_h, ch)


def type_legend_html():
    """Compact key mapping each control-strategy glyph to its meaning."""
    items = [('and', 'AND'), ('or', 'OR'), ('not', 'NOT'), ('edge_up', 'Edge'),
             ('timer', 'Timer'), ('cond', 'Condition'), ('calc', 'Calc'),
             ('pid', 'PID/loop'), ('analog', 'Analog'), ('device', 'Device'),
             ('composite', 'Composite')]
    out = ['<div class="fbd-legend"><span class="fbd-leg-lbl">Symbols:</span>']
    for k, lbl in items:
        out.append(f'<span class="fbd-leg-item"><svg width="15" height="13" viewBox="0 0 15 13">'
                   f'{_type_glyph(k, 3, 2.5, "#475569", 8)}</svg>{lbl}</span>')
    out.append('</div>')
    return ''.join(out)


def render_fbd_svg(fbd, scale=0.5, pad=40, layout='deltav'):
    """Render the FBD as SVG. Wired input/output pins are drawn on the block
    edges with their names, and connections terminate on those pins — close to
    the DeltaV Control Studio print. Blocks grow vertically when needed so their
    wired pins fit; parameter terminals are text-sized boxes placed next to the
    block and nudged clear of collisions; the viewBox fits the drawn extents."""
    # drop phantom/degenerate blocks: DeltaV stores command & monitor composite
    # references at a sentinel position (-50,-50) with 1x1 size; they are not
    # diagram blocks (that logic lives in the command/state view).
    blocks = [dict(b) for b in fbd['blocks'] if b['w'] > 2 and b['h'] > 2 and b['x'] > -40]
    wires = fbd['wires']
    frames = fbd.get('frames', [])
    labels = fbd.get('labels', [])
    if not blocks:
        return '<p style="color:#94a3b8">No function blocks to display.</p>'

    # keep only frames that actually contain a block (drop empty print-template
    # regions), and labels that sit inside such a frame or next to a block (drop
    # orphaned DeltaV annotation text floating in empty space).
    def _contains(f, b):
        cx, cy = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
        return f['x'] <= cx <= f['x'] + f['w'] and f['y'] <= cy <= f['y'] + f['h']

    frames = [f for f in frames if any(_contains(f, b) for b in blocks)]

    def _label_kept(l):
        for b in blocks:
            # a section header sitting just above a block in the same region
            if (b['y'] + b['h']) >= l['y'] - 4 and (b['y'] - l['y']) <= 250 \
               and b['x'] <= l['x'] + 420 and (b['x'] + b['w']) >= l['x'] - 50:
                return True
            # or a label immediately beside a block (side annotation)
            dx = max(b['x'] - 120 - l['x'], l['x'] - (b['x'] + b['w'] + 120), 0)
            dy = max(b['y'] - 35 - l['y'], l['y'] - (b['y'] + b['h'] + 35), 0)
            if dx == 0 and dy == 0:
                return True
        return False

    labels = [l for l in labels if _label_kept(l) and not _is_chrome(l['text'])]

    if layout == 'auto':
        # connectivity-driven reflow; DeltaV regions/labels don't apply
        auto_layout_coords(blocks, wires)
        frames, labels = [], []
    else:
        # ── whitespace compaction: collapse large empty bands (left over after
        # the print-template chrome is stripped) while keeping block sizes/order ──
        occ_x = [(b['x'], b['x'] + b['w']) for b in blocks]
        occ_y = [(b['y'] - 60, b['y'] + b['h']) for b in blocks]
        rx = _make_axis_remap(occ_x)
        ry = _make_axis_remap(occ_y)
        for b in blocks:
            nx, ny = rx(b['x']), ry(b['y'])
            b['w'] = rx(b['x'] + b['w']) - nx
            b['h'] = ry(b['y'] + b['h']) - ny
            b['x'], b['y'] = nx, ny
        kept_frames = []
        for f in frames:
            nx, ny = rx(f['x']), ry(f['y'])
            f = dict(f, x=nx, y=ny, w=rx(f['x'] + f['w']) - nx, h=ry(f['y'] + f['h']) - ny)
            kept_frames.append(f)
        frames = kept_frames
        labels = [dict(l, x=rx(l['x']), y=ry(l['y'])) for l in labels]

    allx = [b['x'] for b in blocks] + [f['x'] for f in frames]
    ally = [b['y'] for b in blocks] + [f['y'] for f in frames]
    minx, miny = min(allx), min(ally)

    def sx(x): return (x - minx) * scale + pad
    def sy(y): return (y - miny) * scale + pad

    bmap = {b['name']: b for b in blocks}

    # ── wired pins per block ──
    from collections import defaultdict
    in_ports, out_ports = defaultdict(set), defaultdict(set)
    pin_in_net = {}     # (block, in_port) -> driving net (the wire source)
    for w in wires:
        if w['dst_block'] in bmap:
            in_ports[w['dst_block']].add(w['dst_port'])
            pin_in_net[(w['dst_block'], w['dst_port'])] = w['source']
        if w['src_block'] in bmap:
            out_ports[w['src_block']].add(w['src_port'])

    def _net(s):
        return html.escape(s, quote=True)

    PIN_PITCH = 22
    MINW = 70
    HEADER = 14

    # ── block geometry (grow height to fit pins; min width) ──
    geom = {}
    for b in blocks:
        nin = len(in_ports[b['name']])
        nout = len(out_ports[b['name']])
        nmax = max(nin, nout)
        w = max(b['w'] * scale, MINW)
        cy = sy(b['y']) + b['h'] * scale / 2
        need = (nmax - 1) * PIN_PITCH + 38 if nmax > 0 else b['h'] * scale
        h = max(b['h'] * scale, need)
        top = cy - h / 2
        geom[b['name']] = {'x': sx(b['x']), 'top': top, 'w': w, 'h': h, 'cy': cy}

    brects = [(g['x'], g['top'], g['x'] + g['w'], g['top'] + g['h']) for g in geom.values()]

    # ── pin Y positions within each block's body (below header) ──
    port_y_in, port_y_out = {}, {}

    def _assign(ports_by_block, target):
        for blk, ports in ports_by_block.items():
            g = geom[blk]
            uniq = sorted(ports)
            n = len(uniq)
            y0 = g['top'] + 30
            y1 = g['top'] + g['h'] - 6
            if n == 1:
                ys = [(y0 + y1) / 2]
            else:
                ys = [y0 + i * (y1 - y0) / (n - 1) for i in range(n)]
            for p, y in zip(uniq, ys):
                target[(blk, p)] = y

    _assign(in_ports, port_y_in)
    _assign(out_ports, port_y_out)

    def in_xy(blk, port):
        g = geom[blk]
        return g['x'], port_y_in.get((blk, port), g['cy'])

    def out_xy(blk, port):
        g = geom[blk]
        return g['x'] + g['w'], port_y_out.get((blk, port), g['cy'])

    # ── terminal boxes (text-sized + collision-avoid) ──
    placed = list(brects)
    term_items = []
    for w in wires:
        if w['src_block'] is None and w['dst_block'] in bmap:
            side, full = 'in', w['source']
            bx, by = in_xy(w['dst_block'], w['dst_port'])
        elif w['dst_block'] is None and w['src_block'] in bmap:
            side, full = 'out', w['destination']
            bx, by = out_xy(w['src_block'], w['src_port'])
        else:
            continue
        lbl, bw = _fit_label(full, 280)
        ty1, ty2 = by - _PBOX_H / 2, by + _PBOX_H / 2
        if side == 'in':
            right = bx - _PGAP
            rect = (right - bw, ty1, right, ty2)
            guard = 0
            while any(_overlap(rect, o) for o in placed) and guard < 40:
                hit = next(o for o in placed if _overlap(rect, o))
                right = hit[0] - _PGAP
                rect = (right - bw, ty1, right, ty2)
                guard += 1
            stub_from, stub_to = rect[2], bx
        else:
            left = bx + _PGAP
            rect = (left, ty1, left + bw, ty2)
            guard = 0
            while any(_overlap(rect, o) for o in placed) and guard < 40:
                hit = next(o for o in placed if _overlap(rect, o))
                left = hit[2] + _PGAP
                rect = (left, ty1, left + bw, ty2)
                guard += 1
            stub_from, stub_to = bx, rect[0]
        placed.append(rect)
        term_items.append((rect, lbl, full, side, stub_from, stub_to, by, w['source']))

    # ── extents → viewBox ──
    xs, ys = [], []
    for r in brects + [t[0] for t in term_items]:
        xs += [r[0], r[2]]; ys += [r[1], r[3]]
    for f in frames:
        xs += [sx(f['x']), sx(f['x']) + f['w'] * scale]
        ys += [sy(f['y']), sy(f['y']) + f['h'] * scale]
    for l in labels:
        xs += [sx(l['x']), sx(l['x']) + len(l['text']) * 6.2]
        ys += [sy(l['y']) - 10, sy(l['y']) + 4]
    vx0, vy0 = min(xs) - pad, min(ys) - pad
    W, H = max(xs) - vx0 + pad, max(ys) - vy0 + pad

    svg = []
    svg.append(f'<svg class="fbd" viewBox="{vx0:.0f} {vy0:.0f} {W:.0f} {H:.0f}" '
               f'width="{W:.0f}" '
               f'xmlns="http://www.w3.org/2000/svg" '
               f'style="width:{W:.0f}px;max-width:100%;height:auto;background:#fcfcfd">')
    svg.append('<defs><marker id="arr" markerWidth="8" markerHeight="8" '
               'refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" '
               'fill="#94a3b8"/></marker></defs>')

    for f in frames:
        x, y = sx(f['x']), sy(f['y'])
        svg.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{f["w"]*scale:.0f}" '
                   f'height="{f["h"]*scale:.0f}" fill="none" stroke="#dbe3ec" stroke-width="1"/>')
    for l in labels:
        svg.append(f'<text x="{sx(l["x"]):.0f}" y="{sy(l["y"]):.0f}" font-size="11" '
                   f'fill="#64748b" font-weight="600">{html.escape(l["text"])}</text>')

    # block-to-block wires, routed around blocks through clear channels
    block_rect = {n: (g['x'], g['top'], g['x'] + g['w'], g['top'] + g['h'])
                  for n, g in geom.items()}
    lane_top = min(r[1] for r in block_rect.values()) - 14
    lane_bot = max(r[3] for r in block_rect.values()) + 14
    for i, w in enumerate(wires):
        if w['src_block'] is None or w['dst_block'] is None:
            continue
        if w['src_block'] not in bmap or w['dst_block'] not in bmap:
            continue
        x1, y1 = out_xy(w['src_block'], w['src_port'])
        x2, y2 = in_xy(w['dst_block'], w['dst_port'])
        obst = [r for n, r in block_rect.items() if n not in (w['src_block'], w['dst_block'])]
        bias = ((i * 7) % 5 - 2) * 6   # spread parallel runs a little
        pts = _route(x1, y1, x2, y2, obst, lane_top, lane_bot, bias)
        svg.append(f'<path class="fbd-wire" data-net="{_net(w["source"])}" '
                   f'onclick="fbdNet(this)" d="{_pts_to_d(pts)}" fill="none" '
                   f'stroke="#94a3b8" stroke-width="1.2" marker-end="url(#arr)"/>')

    # terminal boxes + stubs
    for rect, lbl, full, side, sfrom, sto, by, net in term_items:
        x, ty = rect[0], rect[1]
        bw = rect[2] - rect[0]
        nid = _net(net)
        svg.append(f'<path class="fbd-wire" data-net="{nid}" d="M{sfrom:.0f},{by:.0f} '
                   f'H{sto:.0f}" fill="none" stroke="#94a3b8" stroke-width="1.2" '
                   f'marker-end="url(#arr)"/>')
        anchor = 'start' if side == 'in' else 'end'
        tx = x + 7 if side == 'in' else x + bw - 7
        svg.append(f'<g class="fb-term" data-net="{nid}" onclick="fbdNet(this)">'
                   f'<title>{html.escape(full)}</title>'
                   f'<rect x="{x:.0f}" y="{ty:.0f}" width="{bw:.0f}" height="{_PBOX_H}" '
                   f'rx="3" fill="#eef2f7" stroke="#94a3b8" stroke-width="1"/>'
                   f'<text x="{tx:.0f}" y="{by+3:.0f}" font-size="10" '
                   f'fill="#334155" text-anchor="{anchor}" font-family="monospace">'
                   f'{html.escape(lbl)}</text></g>')

    # blocks (with named pins on the edges)
    for b in blocks:
        g = geom[b['name']]
        x, y, w, h = g['x'], g['top'], g['w'], g['h']
        col = _color(b)
        cls = 'fb'
        attrs = f' data-name="{html.escape(b["name"])}"'
        if b['is_composite']:
            cls += ' fb-composite'
            attrs += f' data-composite="{html.escape(b["definition"])}" style="cursor:pointer"'
        elif b.get('expressions'):
            cls += ' fb-expr'
            payload = json.dumps([{'a': e['attr'], 'k': e['kind'], 'e': e['expression']}
                                  for e in b['expressions']])
            attrs += (f' data-expr="{html.escape(payload, quote=True)}"'
                      f' onclick="fbdShowExpr(this)" style="cursor:pointer"')
        svg.append(f'<g class="{cls}"{attrs}>')
        dash = ' stroke-dasharray="4 2"' if b['is_composite'] else ''
        svg.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" '
                   f'rx="3" fill="#ffffff" stroke="{col}" stroke-width="1.6"{dash}/>')
        svg.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="14" rx="3" fill="{col}"/>')
        # control-strategy type glyph at header-left
        gk = _glyph_key(b['definition'])
        if gk:
            svg.append(_type_glyph(gk, x + 3, y + 3, '#ffffff', 8))
        # header label: block type, but for composites show a readable label
        # instead of an anonymous hash / overlong class name. Leave room on the
        # right for the [+]/fx marker so they never overlap.
        has_marker = b['is_composite'] or bool(b.get('expressions'))
        type_label = b['definition']
        if b['is_composite'] and type_label.startswith('__') and type_label.endswith('__'):
            type_label = 'COMPOSITE'
        maxc = max(4, int((w - (30 if has_marker else 8)) / 4.7))
        if len(type_label) > maxc:
            type_label = type_label[:maxc - 1] + '\u2026'
        svg.append(f'<text x="{x+w/2:.0f}" y="{y+10:.0f}" font-size="9" '
                   f'fill="#ffffff" text-anchor="middle" font-weight="bold">{html.escape(type_label)}</text>')
        # block name just under the header (keeps it clear of the pins below)
        svg.append(f'<text x="{x+w/2:.0f}" y="{y+HEADER+10:.0f}" font-size="10" '
                   f'fill="#0f172a" text-anchor="middle" font-weight="600">{html.escape(b["name"])}</text>')
        # input pins (left edge); labels truncated to half the block width
        pin_max = max(3, int((w / 2 - 10) / 4.2))

        def _pin(p):
            return p if len(p) <= pin_max else p[:pin_max - 1] + '\u2026'

        for p in sorted(in_ports[b['name']]):
            py = port_y_in[(b['name'], p)]
            net = pin_in_net.get((b['name'], p), '')
            svg.append(f'<circle class="fbd-pin" data-net="{_net(net)}" onclick="fbdNet(this)" '
                       f'cx="{x:.0f}" cy="{py:.0f}" r="2.6" fill="#64748b"/>')
            svg.append(f'<g><title>{html.escape(p)}</title><text x="{x+5:.0f}" y="{py+2.5:.0f}" '
                       f'font-size="7" fill="#64748b" text-anchor="start" '
                       f'font-family="monospace">{html.escape(_pin(p))}</text></g>')
        # output pins (right edge)
        for p in sorted(out_ports[b['name']]):
            py = port_y_out[(b['name'], p)]
            net = f"{b['name']}/{p}"
            svg.append(f'<circle class="fbd-pin" data-net="{_net(net)}" onclick="fbdNet(this)" '
                       f'cx="{x+w:.0f}" cy="{py:.0f}" r="2.6" fill="#64748b"/>')
            svg.append(f'<g><title>{html.escape(p)}</title><text x="{x+w-5:.0f}" y="{py+2.5:.0f}" '
                       f'font-size="7" fill="#64748b" text-anchor="end" '
                       f'font-family="monospace">{html.escape(_pin(p))}</text></g>')
        if b['is_composite']:
            svg.append(f'<text x="{x+w-5:.0f}" y="{y+10:.0f}" font-size="8" '
                       f'fill="#ffffff" text-anchor="end">[+]</text>')
        elif b.get('expressions'):
            svg.append(f'<text x="{x+w-5:.0f}" y="{y+10:.0f}" font-size="8" '
                       f'fill="#ffffff" text-anchor="end" font-style="italic">&#402;x</text>')
        svg.append('</g>')

    svg.append('</svg>')
    return '\n'.join(svg)
