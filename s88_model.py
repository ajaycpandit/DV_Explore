"""
ISA-88 / IEC-61512 procedural state model for a *phase* (batch only — EMs do not
use this model). Renders the canonical DeltaV phase state machine as an SVG and
maps the phase's six standard logic blocks onto their acting states.

Per DeltaV, these six logic blocks ALWAYS exist on a phase:
    RUN_LOGIC, HOLD_LOGIC, RESTART_LOGIC, STOP_LOGIC, ABORT_LOGIC, FAIL_MONITOR
"no logic" never means "missing" — it means the block holds a blank step with no
actions, which we surface with a small "blank" tag rather than dimming the state.

States are clickable: clicking an acting state asks the embedded SFC viewer to
switch to that logic block (via window.postMessage; see phase_bridge).
"""

import html

W, H = 150, 46

# name -> (x, y, logic-block-or-None, terminal?)
STATES = {
    'Fault monitor': (34, 34, 'FAIL_MONITOR', False),
    'Aborted':    (392, 34, None, True),
    'Aborting':   (650, 34, 'ABORT_LOGIC', False),
    'Holding':    (210, 196, 'HOLD_LOGIC', False),
    'Held':       (430, 196, None, False),
    'Restarting': (650, 196, 'RESTART_LOGIC', False),
    'Idle':       (34, 344, None, False),
    'Running':    (282, 344, 'RUN_LOGIC', False),
    'Stopping':   (530, 344, 'STOP_LOGIC', False),
    'Complete':   (210, 474, None, True),
    'Stopped':    (530, 474, None, True),
}


def _cx(n): return STATES[n][0] + W / 2
def _cy(n): return STATES[n][1] + H / 2
def _L(n): return STATES[n][0]
def _R(n): return STATES[n][0] + W
def _T(n): return STATES[n][1]
def _B(n): return STATES[n][1] + H


# (from, to, label, [waypoint list as (x,y)])  — explicit orthogonal routing
def _edges():
    e = []
    # normal start
    e.append(('Idle', 'Running', 'Start & not fail',
              [(_R('Idle'), _cy('Idle')), (_L('Running'), _cy('Running'))]))
    # run -> hold (fault or hold cmd)
    e.append(('Running', 'Holding', 'Fail / Hold',
              [(_cx('Running') - 36, _T('Running')), (_cx('Running') - 36, _B('Holding'))]))
    e.append(('Holding', 'Held', 'Sequence Done',
              [(_R('Holding'), _cy('Holding')), (_L('Held'), _cy('Held'))]))
    e.append(('Held', 'Restarting', 'Restart & not fail',
              [(_R('Held'), _cy('Held')), (_L('Restarting'), _cy('Restarting'))]))
    # restart -> running (loop down-left, above the Running/Stopping row)
    e.append(('Restarting', 'Running', 'Sequence Done',
              [(_cx('Restarting'), _B('Restarting')), (_cx('Restarting'), 312),
               (_cx('Running') + 40, 312), (_cx('Running') + 40, _T('Running'))]))
    # restart -> holding (fail again)
    e.append(('Restarting', 'Holding', 'Fail / Hold',
              [(_cx('Restarting') - 30, _B('Restarting')), (_cx('Restarting') - 30, 288),
               (_cx('Holding') + 38, 288), (_cx('Holding') + 38, _B('Holding'))]))
    # stop paths
    e.append(('Running', 'Stopping', 'Stop',
              [(_R('Running'), _cy('Running')), (_L('Stopping'), _cy('Stopping'))]))
    e.append(('Held', 'Stopping', 'Stop',
              [(_cx('Held'), _B('Held')), (_cx('Held'), 322),
               (_cx('Stopping') - 30, 322), (_cx('Stopping') - 30, _T('Stopping'))]))
    e.append(('Stopping', 'Stopped', 'Sequence Done',
              [(_cx('Stopping'), _B('Stopping')), (_cx('Stopping'), _T('Stopped'))]))
    # complete
    e.append(('Running', 'Complete', 'Sequence Done',
              [(_cx('Running') - 40, _B('Running')), (_cx('Running') - 40, 452),
               (_cx('Complete'), 452), (_cx('Complete'), _T('Complete'))]))
    # aborting -> aborted
    e.append(('Aborting', 'Aborted', 'Sequence Done',
              [(_L('Aborting'), _cy('Aborting')), (_R('Aborted'), _cy('Aborted'))]))
    # ABORT from every active state -> Aborting (the wiring that was missing)
    e.append(('Restarting', 'Aborting', 'Abort',
              [(_cx('Restarting') + 40, _T('Restarting')), (_cx('Restarting') + 40, _B('Aborting'))]))
    e.append(('Held', 'Aborting', 'Abort',
              [(_cx('Held') + 40, _T('Held')), (_cx('Held') + 40, 150),
               (_cx('Aborting') - 36, 150), (_cx('Aborting') - 36, _B('Aborting'))]))
    e.append(('Holding', 'Aborting', 'Abort',
              [(_cx('Holding') + 40, _T('Holding')), (_cx('Holding') + 40, 132),
               (_cx('Aborting'), 132), (_cx('Aborting'), _B('Aborting'))]))
    e.append(('Stopping', 'Aborting', 'Abort',
              [(_R('Stopping'), _cy('Stopping') - 8), (730, _cy('Stopping') - 8),
               (730, 118), (_cx('Aborting') + 40, 118), (_cx('Aborting') + 40, _B('Aborting'))]))
    e.append(('Running', 'Aborting', 'Abort',
              [(_cx('Running') + 52, _T('Running')), (_cx('Running') + 52, 110),
               (_cx('Aborting') - 12, 110), (_cx('Aborting') - 12, _B('Aborting'))]))
    # reset from every terminal -> Idle
    e.append(('Complete', 'Idle', 'Reset',
              [(_L('Complete'), _cy('Complete')), (16, _cy('Complete')),
               (16, _cy('Idle')), (_L('Idle'), _cy('Idle'))], 'reset'))
    e.append(('Stopped', 'Idle', 'Reset',
              [(_cx('Stopped'), _B('Stopped')), (_cx('Stopped'), 548),
               (_cx('Idle'), 548), (_cx('Idle'), _B('Idle'))], 'reset'))
    e.append(('Aborted', 'Idle', 'Reset',
              [(_L('Aborted'), _cy('Aborted')), (16, _cy('Aborted')),
               (16, _cy('Idle') - 18), (_L('Idle'), _cy('Idle') - 18)], 'reset'))
    return e


def _path(pts):
    return 'M' + ' L'.join(f'{x:.0f},{y:.0f}' for x, y in pts)


def _label_pos(pts):
    # place at the midpoint of the longest segment (most room for text)
    best = None
    bl = -1
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        ln = abs(x2 - x1) + abs(y2 - y1)
        if ln > bl:
            bl = ln
            best = ((x1 + x2) / 2, (y1 + y2) / 2)
    return best


def build_s88_svg(blank=None):
    """blank: optional set of logic-block names that hold a blank (no-action) step."""
    blank = blank or set()
    out = ['<svg viewBox="0 0 980 580" width="100%" style="height:auto" class="s88">',
           '<defs><marker id="s88ar" markerWidth="9" markerHeight="9" refX="7.5" refY="3" '
           'orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="var(--edge)"/></marker>'
           '<marker id="s88arr" markerWidth="9" markerHeight="9" refX="7.5" refY="3" '
           'orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="var(--edge-reset)"/></marker></defs>']
    # edges first
    for ed in _edges():
        frm, to, label, pts = ed[0], ed[1], ed[2], ed[3]
        kind = ed[4] if len(ed) > 4 else ''
        col = 'var(--edge-reset)' if kind == 'reset' else 'var(--edge)'
        mk = 's88arr' if kind == 'reset' else 's88ar'
        out.append(f'<path d="{_path(pts)}" fill="none" stroke="{col}" stroke-width="1.5" '
                   f'marker-end="url(#{mk})"/>')
        lx, ly = _label_pos(pts)
        out.append(f'<text x="{lx:.0f}" y="{ly - 5:.0f}" text-anchor="middle" font-size="11" '
                   f'fill="var(--ink-2)" font-family="IBM Plex Sans" '
                   f'style="paint-order:stroke;stroke:var(--surface);stroke-width:3px">{html.escape(label)}</text>')
    # states
    for name, (x, y, logic, term) in STATES.items():
        acting = logic is not None
        is_blank = logic in blank
        fill = ('var(--st-active)' if acting else
                ('var(--st-term)' if term else 'var(--st-quiet)'))
        if logic == 'FAIL_MONITOR':
            fill = 'var(--st-warn)'
        stroke = 'var(--st-active-bd)' if acting else 'var(--st-quiet-bd)'
        if logic == 'FAIL_MONITOR':
            stroke = 'var(--st-warn-bd)'
        ink = '#fff' if acting else 'var(--ink)'
        sub = ''
        if logic:
            tag = logic + ('  · blank' if is_blank else '')
            sub = (f'<text x="{x + W / 2:.0f}" y="{y + 37:.0f}" text-anchor="middle" '
                   f'font-size="10.5" font-family="IBM Plex Mono" fill="#fff" '
                   f'opacity="{0.7 if is_blank else 0.92}">{html.escape(tag)}</text>')
        cls = 's88st acting' if acting else 's88st'
        cur = 'pointer' if acting else 'default'
        out.append(
            f'<g class="{cls}" data-logic="{html.escape(logic or "", quote=True)}" '
            f'data-state="{html.escape(name, quote=True)}" '
            f'onclick="s88Goto(this)" tabindex="{0 if acting else -1}" style="cursor:{cur}">'
            f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="9" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.5"/>'
            f'<text x="{x + W / 2:.0f}" y="{y + (20 if logic else 29):.0f}" text-anchor="middle" '
            f'font-size="14.5" font-weight="600" fill="{ink}" font-family="IBM Plex Sans">'
            f'{html.escape(name)}</text>{sub}</g>')
    out.append('</svg>')
    return ''.join(out)


# CSS + JS injected once into the explorer for the S88 card.
S88_CSS = """
.s88card .s88wrap{display:grid;grid-template-columns:1fr 260px;gap:0}
.s88diagram{padding:16px;overflow:auto}
.s88side{border-left:1px solid var(--border);padding:15px 15px;background:var(--surface-2)}
.s88side h4{margin:0 0 6px;font-size:13px}
.s88side p{margin:0 0 12px;font-size:12.5px;color:var(--ink-2);line-height:1.5}
.s88legend{display:flex;gap:14px;flex-wrap:wrap;padding:10px 16px;border-top:1px solid var(--border);font-size:11.5px;color:var(--ink-2)}
.s88legend i{display:inline-block;width:13px;height:10px;border-radius:3px;margin-right:6px;vertical-align:middle}
.s88st.acting:hover rect{filter:brightness(1.08)}
.s88st.sel rect{stroke-width:3}
.s88 text{user-select:none}
:root{--st-active:#1d4ed8;--st-active-bd:#1e40af;--st-quiet:#ffffff;--st-quiet-bd:#c7d2de;
  --st-term:#eef2f7;--st-warn:#b45309;--st-warn-bd:#92400e;--edge:#7689a0;--edge-reset:#0e7490;}
[data-theme="dark"]{--st-active:#2563eb;--st-active-bd:#60a5fa;--st-quiet:#1b2531;--st-quiet-bd:#3a4856;
  --st-term:#11202e;--st-warn:#b45309;--st-warn-bd:#fbbf24;--edge:#73879b;--edge-reset:#38bdf8;}
"""

S88_JS = """
function s88Goto(g){
  var logic=g.getAttribute('data-logic'); if(!logic) return;
  document.querySelectorAll('.s88st').forEach(function(s){s.classList.remove('sel');});
  g.classList.add('sel');
  var st=g.getAttribute('data-state');
  var sh=document.getElementById('s88h'), sp=document.getElementById('s88p');
  if(sh) sh.textContent=st+(logic==='FAIL_MONITOR'?' monitor':' state');
  if(sp) sp.innerHTML='Runs <b>'+logic+'</b>. Opening it in the phase logic below.';
  var fr=document.getElementById('phaseFrame');
  if(fr&&fr.contentWindow){ try{ fr.contentWindow.postMessage({s88block:logic}, '*'); }catch(e){}
    fr.scrollIntoView({behavior:'smooth',block:'nearest'}); }
}
"""
