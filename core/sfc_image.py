"""
SFC IMAGE RENDERER — DeltaV print style.
White step boxes (ID + description), transition = horizontal bar + ID (with
optional description/expression via show_detail), thin black orthogonal
connectors. Primary forward transition sits on the spine under its step;
other forward/loop transitions are placed at their own x; loop-backs (target
above) route out to the side and back.
Uses explicit FHX connections (divergence + loop-backs preserved).
"""

import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

BLACK = '#000000'
WHITE = '#FFFFFF'
BG    = '#FFFFFF'

COL_W = 210
ROW_H = 70
SW, SH = 92, 34


def _snap_to_grid(steps, trans):
    nodes = [(n, d['x'], d['y']) for n, d in steps] + \
            [(n, d['x'], d['y']) for n, d in trans.items()]
    xs = sorted(set(x for _, x, _ in nodes))
    ys = sorted(set(y for _, _, y in nodes))

    def cluster(vals, tol):
        clusters = []
        for v in vals:
            placed = False
            for c in clusters:
                if abs(v - c[0]) <= tol:
                    c.append(v); placed = True; break
            if not placed:
                clusters.append([v])
        idx = {}
        for i, c in enumerate(sorted(clusters, key=lambda g: g[0])):
            for v in c:
                idx[v] = i
        return idx

    col_idx = cluster(xs, 90)
    row_idx = cluster(ys, 30)
    pos = {n: (col_idx[x], row_idx[y]) for n, x, y in nodes}
    return pos, max(col_idx.values()) + 1, max(row_idx.values()) + 1


def _geo_t2s(steps, trans):
    t2s = {}
    sp = {n: (d['x'], d['y']) for n, d in steps}
    for tname, td in trans.items():
        tx, ty = td['x'], td['y']
        best, bd = None, 1e18
        for sn, (sx, sy) in sp.items():
            if sy > ty:
                dd = (sy - ty) + abs(sx - tx) * 0.5
                if dd < bd:
                    bd, best = dd, sn
        if best:
            t2s[tname] = best
    return t2s


def _ortho(ax, x1, y1, x2, y2, arrow=False, loopback=False):
    if loopback:
        side = x1 + 90 if x2 >= x1 else x1 - 90
        ax.add_line(Line2D([x1, side], [y1, y1], color=BLACK, lw=0.7, zorder=1))
        ax.add_line(Line2D([side, side], [y1, y2], color=BLACK, lw=0.7, zorder=1))
        ax.add_line(Line2D([side, x2], [y2, y2], color=BLACK, lw=0.7, zorder=1))
        return
    if abs(x1 - x2) < 1 or abs(y1 - y2) < 1:
        ax.add_line(Line2D([x1, x2], [y1, y2], color=BLACK, lw=0.7, zorder=1))
    else:
        midy = (y1 + y2) / 2
        ax.add_line(Line2D([x1, x1], [y1, midy], color=BLACK, lw=0.7, zorder=1))
        ax.add_line(Line2D([x1, x2], [midy, midy], color=BLACK, lw=0.7, zorder=1))
        ax.add_line(Line2D([x2, x2], [midy, y2], color=BLACK, lw=0.7, zorder=1))


def render_sfc_png(label, data, scale=1.0, show_detail=False):
    steps = data['ordered_steps']
    trans = data['transitions']
    s2t   = data.get('step_to_trans', {})
    if not steps:
        return None, 0, 0, {}

    t2s_exp = data.get('trans_to_step', {})
    t2s = {}
    for tn in trans:
        if t2s_exp.get(tn):
            t2s[tn] = list(t2s_exp[tn])
        else:
            g = _geo_t2s(steps, {tn: trans[tn]})
            if g.get(tn):
                t2s[tn] = [g[tn]]

    pos, ncols, nrows = _snap_to_grid(steps, trans)

    def cx(c): return c * COL_W + COL_W / 2
    def cy(r): return (nrows - r) * ROW_H

    span_x = ncols * COL_W + COL_W
    span_y = (nrows + 1) * ROW_H + ROW_H
    dpi = 130
    fig_w = min(max(span_x / 150.0, 6), 26) * scale
    fig_h = min(max(span_y / 150.0, 5), 80) * scale
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)

    # step box widths sized to name; description shown only if it fits
    step_w = {}
    step_desc_fit = {}
    for sn, sd in steps:
        d = (sd.get('description', '') or '').replace('\r', ' ').replace('\n', ' ').strip()
        wn = len(sn) * 4.6 + 16
        w = max(SW, wn)
        step_w[sn] = w
        fit = int((w - 14) / 3.7)
        if d and len(d) <= fit:
            step_desc_fit[sn] = d
        elif d and fit >= 6:
            step_desc_fit[sn] = d[:fit-1] + '\u2026'
        else:
            step_desc_fit[sn] = ''

    row_of = {n: pos[n][1] for n in pos}

    # pull each step's PRIMARY forward transition onto the spine column
    col_override = {}
    for sn, tlist in s2t.items():
        if sn not in pos:
            continue
        s_col, s_row = pos[sn]
        fwd = []
        for tn in tlist:
            if tn not in pos:
                continue
            srows = [row_of[s] for s in t2s.get(tn, []) if s in pos]
            if not (srows and min(srows) <= s_row):
                fwd.append(tn)
        fwd.sort(key=lambda t: pos[t][1])
        if fwd:
            col_override[fwd[0]] = s_col
    for tn, col in col_override.items():
        r = pos[tn][1]; pos[tn] = (col, r)

    init_name = steps[0][0]
    def center(n):
        c, r = pos[n]; return cx(c), cy(r)

    def succ_rows(tn):
        return [row_of[s] for s in t2s.get(tn, []) if s in pos]

    # step -> transitions
    for sn, tlist in s2t.items():
        if sn not in pos:
            continue
        scx, scy = center(sn)
        s_row = row_of[sn]
        fwd, loop = [], []
        for tn in tlist:
            if tn not in pos:
                continue
            srows = succ_rows(tn)
            if srows and min(srows) <= s_row:
                loop.append(tn)
            else:
                fwd.append(tn)
        fwd.sort(key=lambda t: pos[t][1])
        for i, tn in enumerate(fwd):
            tcx, tcy = center(tn)
            if i == 0:
                _ortho(ax, scx, scy - SH/2, scx, tcy + 2)
            else:
                _ortho(ax, scx, scy - SH/2, tcx, tcy + 2)
        for tn in loop:
            tcx, tcy = center(tn)
            _ortho(ax, scx, scy - SH/2, tcx, tcy + 2)

    # transition -> successor step
    for tn, snlist in t2s.items():
        if tn not in pos:
            continue
        tcx, tcy = center(tn)
        for sn in snlist:
            if sn not in pos:
                continue
            scx, scy = center(sn)
            if row_of[sn] <= row_of[tn]:
                _ortho(ax, tcx, tcy - 2, scx, scy, loopback=True)
            else:
                _ortho(ax, tcx, tcy - 2, scx, scy + SH/2)

    # step boxes
    step_px = {}
    for sn, sd in steps:
        ccx, ccy = center(sn)
        w = step_w.get(sn, SW)
        x, y = ccx - w/2, ccy - SH/2
        is_init = (sn == init_name)
        if is_init:
            ax.add_patch(Rectangle((x-3, y-3), w+6, SH+6, facecolor='none',
                         edgecolor=BLACK, lw=0.8, zorder=3))
        ax.add_patch(Rectangle((x, y), w, SH, facecolor=WHITE,
                     edgecolor=BLACK, lw=0.8, zorder=4))
        desc = step_desc_fit.get(sn, '')
        ax.text(ccx, ccy + 6, sn, ha='center', va='center',
                color=BLACK, fontsize=5.2, fontweight='bold', zorder=5)
        if desc:
            ax.text(ccx, ccy - 6, desc, ha='center', va='center',
                    color=BLACK, fontsize=4.4, zorder=5)
        step_px[sn] = (x, y, x + w, y + SH)

    # transitions: bar + ID (+ optional detail)
    for tn, td in trans.items():
        if tn not in pos:
            continue
        ccx, ccy = center(tn)
        is_end = td.get('termination', 'F') == 'T'
        bar_lw = 1.8 if not is_end else 2.6
        ax.add_line(Line2D([ccx-9, ccx+9], [ccy, ccy], color=BLACK,
                    lw=bar_lw, zorder=5, solid_capstyle='butt'))
        ax.text(ccx + 13, ccy, tn, ha='left', va='center',
                color=BLACK, fontsize=5.0, fontweight='bold', zorder=5)
        if show_detail:
            desc = (td.get('description', '') or '').replace('\r', ' ').replace('\n', ' ').strip()
            expr = (td.get('expression', '') or '').replace('\r', ' ').replace('\n', ' ').strip()
            if desc:
                ax.text(ccx + 13, ccy - 5.5, desc, ha='left', va='center',
                        color='#222222', fontsize=3.9, zorder=5)
            if expr:
                yoff = -10.5 if desc else -5.5
                ax.text(ccx + 13, ccy + yoff, expr, ha='left', va='center',
                        color='#555555', fontsize=3.6, style='italic', zorder=5)

    ax.set_xlim(0, span_x)
    ax.set_ylim(-ROW_H/2, span_y)
    ax.set_aspect('equal'); ax.axis('off')
    ax.set_position([0, 0, 1, 1])
    fig.canvas.draw()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor=BG, pad_inches=0.2)
    plt.close(fig); buf.seek(0)
    return buf, int(fig_w*dpi), int(fig_h*dpi), step_px
