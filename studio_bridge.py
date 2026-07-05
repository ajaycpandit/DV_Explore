"""Studio bridge — assembles a single object (phase to start) into a Control
Studio-like multi-panel deep view: the interactive SFC diagram in the main panel
(reusing the existing phase view) plus rich side panels for parameters, phase
attributes and monitors that the browse pane shows only partially.

Additive: core/ untouched; this composes existing parsed data + existing renderers.
"""

import html as _html

import db_parser
import phase_bridge


def list_studio_phases(text):
    """Phase names available to open in the Studio."""
    try:
        return list(phase_bridge.parse_phases_from_export(text).keys())
    except Exception:
        return []


def _param_grid(params):
    """The phase's recipe/parameter list as a full grid — richer than the browse
    pane: direction, default, range and units side by side."""
    if not params:
        return '<div class="stu-empty">No parameters.</div>'
    h = ['<table class="stu-grid"><thead><tr>'
         '<th>Name</th><th>Class</th><th>Type</th><th>Dir</th><th>Default</th>'
         '<th>Low</th><th>High</th><th>Units</th><th>Group</th><th>Description</th>'
         '</tr></thead><tbody>']
    for p in params:
        h.append('<tr>'
                 '<td><code>' + _html.escape(p.get('name', '')) + '</code></td>'
                 '<td>' + _html.escape(p.get('class', '')) + '</td>'
                 '<td>' + _html.escape(p.get('type', '')) + '</td>'
                 '<td>' + _html.escape(p.get('direction', '')) + '</td>'
                 '<td>' + _html.escape(str(p.get('default', ''))) + '</td>'
                 '<td>' + _html.escape(str(p.get('low', ''))) + '</td>'
                 '<td>' + _html.escape(str(p.get('high', ''))) + '</td>'
                 '<td>' + _html.escape(p.get('units', '')) + '</td>'
                 '<td>' + _html.escape(p.get('group', '')) + '</td>'
                 '<td class="stu-desc">' + _html.escape(p.get('desc', '')) + '</td>'
                 '</tr>')
    h.append('</tbody></table>')
    return ''.join(h)


def _attr_grid(attrs):
    if not attrs:
        return '<div class="stu-empty">No phase attributes.</div>'
    h = ['<table class="stu-grid"><thead><tr>'
         '<th>Name</th><th>Class</th><th>Type</th><th>Group</th><th>Description</th>'
         '</tr></thead><tbody>']
    for a in attrs:
        h.append('<tr>'
                 '<td><code>' + _html.escape(a.get('name', '')) + '</code></td>'
                 '<td>' + _html.escape(a.get('class', '')) + '</td>'
                 '<td>' + _html.escape(a.get('type', '')) + '</td>'
                 '<td>' + _html.escape(a.get('group', '')) + '</td>'
                 '<td class="stu-desc">' + _html.escape(a.get('desc', '')) + '</td>'
                 '</tr>')
    h.append('</tbody></table>')
    return ''.join(h)


def _monitor_grid(mons):
    if not mons:
        return '<div class="stu-empty">No monitors.</div>'
    h = ['<table class="stu-grid"><thead><tr><th>Name</th><th>Detail</th></tr></thead><tbody>']
    for m in mons:
        if isinstance(m, dict):
            nm = m.get('name', '')
            detail = ', '.join(f'{k}={v}' for k, v in m.items() if k != 'name')
        else:
            nm, detail = str(m), ''
        h.append('<tr><td><code>' + _html.escape(nm) + '</code></td><td>'
                 + _html.escape(detail) + '</td></tr>')
    h.append('</tbody></table>')
    return ''.join(h)


def build_phase_studio(text, phase_name):
    """Return the JSON payload the Studio front-end renders into panels:
    {name, kind, diagram(html doc for iframe), params(html), attrs(html),
     monitors(html), counts}. The diagram reuses the interactive phase view so
     the simulator works inside the Studio too."""
    phases = phase_bridge.parse_phases_from_export(text)
    blocks = phases.get(phase_name)
    if blocks is None:
        return {'error': f'Phase "{phase_name}" not found.'}

    params = blocks.get('__parameters__') or []
    attrs = blocks.get('__attributes__') or []
    mons = blocks.get('__monitors__') or []
    n_steps = len([k for k in blocks if not k.startswith('__')])

    # NOTE: the interactive diagram is intentionally NOT embedded here. Serializing a
    # ~400KB HTML document as a JSON string is large and fragile (proxies/timeouts on
    # the deployed stack can truncate it, yielding an HTML error page that fails to
    # parse as JSON). Instead the front-end points an iframe straight at /phase_view,
    # so this payload stays a few KB and the diagram streams as its own HTML response.
    return {
        'name': phase_name,
        'kind': 'Phase (EM class)',
        'params': _param_grid(params),
        'attrs': _attr_grid(attrs),
        'monitors': _monitor_grid(mons),
        'counts': {'params': len(params), 'attrs': len(attrs),
                   'monitors': len(mons), 'steps': n_steps},
    }
