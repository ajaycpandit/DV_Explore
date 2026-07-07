"""Studio bridge — assembles a single object (phase to start) into a Control
Studio-like multi-panel deep view: the interactive SFC diagram in the main panel
(reusing the existing phase view) plus rich side panels for parameters, phase
attributes and monitors that the browse pane shows only partially.

Additive: core/ untouched; this composes existing parsed data + existing renderers.
"""

import html as _html
import re as _re

import db_parser
import phase_bridge
import em_bridge
import fbd_bridge


# ── #3: S88 path resolution (Plant Area → Process Cell → Unit → EM/CM) ──
# The round-trip export back to DeltaV needs the full equipment path, not just a class
# name. We derive it from the UNIT_MODULE instances: each carries PLANT_AREA="AREA/CELL"
# and its block body lists the equipment/control modules it contains.
_UNIT_CACHE = {}


def _deployed_line_index(text):
    """{ tag: {'cls','area','cell','unit','path'} } parsed from the authoritative
    MODULE_INSTANCE opening line (TAG/PLANT_AREA/MODULE_CLASS all live there)."""
    key = id(text)
    if key in _UNIT_CACHE:
        return _UNIT_CACHE[key]
    idx = {}
    for m in _re.finditer(
            r'MODULE_INSTANCE\s+TAG="([^"]+)"\s+PLANT_AREA="([^"]*)"\s+MODULE_CLASS="([^"]*)"',
            text):
        tag, path, cls = m.group(1), m.group(2), m.group(3)
        parts = path.split('/')
        idx[tag] = {
            'cls': cls, 'path': path,
            'area': parts[0] if parts else '',
            'cell': parts[1] if len(parts) >= 2 else '',
            'unit': parts[2] if len(parts) >= 3 else '',
        }
    _UNIT_CACHE.clear()
    _UNIT_CACHE[key] = idx
    return idx


def resolve_path(text, obj_id):
    """Full S88 breadcrumb for a Studio object id ('phase:X' / 'em:X' / 'cm:X' /
    'dep:TAG'). Returns { 'crumbs': [ {kind,name}... ], 'unit', 'found' }."""
    kind_pref, _, name = (obj_id or '').partition(':')
    kind_label = {'phase': 'Phase', 'em': 'Equipment Module class',
                  'cm': 'Control Module class',
                  'dep': 'Instance'}.get(kind_pref, 'Object')
    idx = _deployed_line_index(text)
    crumbs = []
    unit = ''
    if kind_pref == 'dep' and name in idx:
        info = idx[name]
        unit = info['unit']
        if info['area']:
            crumbs.append({'kind': 'Plant Area', 'name': info['area']})
        if info['cell']:
            crumbs.append({'kind': 'Process Cell', 'name': info['cell']})
        if info['unit']:
            crumbs.append({'kind': 'Unit', 'name': info['unit']})
        crumbs.append({'kind': 'Instance', 'name': name,
                       'sub': 'class ' + info['cls'] if info['cls'] else ''})
        return {'crumbs': crumbs, 'unit': unit, 'found': True,
                'cls': info['cls'], 'path': info['path']}
    # classes/phases: find any deployed instance of this class to borrow the path
    if kind_pref in ('em', 'cm'):
        for tag, info in idx.items():
            if info['cls'] == name:
                if info['area']:
                    crumbs.append({'kind': 'Plant Area', 'name': info['area']})
                if info['cell']:
                    crumbs.append({'kind': 'Process Cell', 'name': info['cell']})
                if info['unit']:
                    crumbs.append({'kind': 'Unit', 'name': info['unit']})
                break
    crumbs.append({'kind': kind_label, 'name': name})
    return {'crumbs': crumbs, 'unit': unit, 'found': bool(crumbs[:-1])}


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


def studio_object_list(text, catalog=None):
    """Typed, grouped list of objects openable in the Studio: Phases, EM/CM classes,
    and their deployed instances (#3). Instances carry their resolved S88 path so the
    round-trip export can reference the full equipment hierarchy."""
    groups = []
    try:
        phases = sorted(phase_bridge.parse_phases_from_export(text).keys())
    except Exception:
        phases = []
    if phases:
        groups.append({'group': 'Phases',
                       'items': [{'id': 'phase:' + p, 'name': p} for p in phases]})
    if catalog is not None:
        ems = sorted(e['name'] for e in catalog.get('em_classes', []))
        if ems:
            groups.append({'group': 'Equipment Module classes',
                           'items': [{'id': 'em:' + e, 'name': e} for e in ems]})
        cms = sorted(c['name'] for c in catalog.get('cm_classes', []))
        if cms:
            groups.append({'group': 'Control Module classes',
                           'items': [{'id': 'cm:' + c, 'name': c} for c in cms]})
    # deployed instances (EM + CM) with their unit path, grouped by unit
    try:
        insts = _deployed_instances(text)
    except Exception:
        insts = {}
    if insts:
        for unit in sorted(insts.keys()):
            items = [{'id': it['id'], 'name': it['name'], 'cls': it.get('cls', '')}
                     for it in sorted(insts[unit], key=lambda x: x['name'])]
            label = ('Instances \u00b7 ' + unit) if unit else 'Instances (unassigned)'
            groups.append({'group': label, 'items': items, 'is_instances': True})
    return groups


def _deployed_instances(text):
    """{ unit_name: [ {id:'dep:TAG', name:TAG, cls} ] } for all MODULE_INSTANCEs,
    grouped by their S88 unit (from the authoritative opening line)."""
    idx = _deployed_line_index(text)
    out = {}
    for tag, info in idx.items():
        out.setdefault(info.get('unit', ''), []).append(
            {'id': 'dep:' + tag, 'name': tag, 'cls': info.get('cls', '')})
    return out


def build_em_studio(text, em_name):
    """Studio payload for an EM class: command/state logic diagram in the main panel,
    plus its resolved control modules and members in the side panels."""
    try:
        ev = em_bridge.build_em_views(text, only=em_name).get(em_name, {})
    except Exception as e:
        return {'error': f'Could not build EM view: {e}'}
    cms = ev.get('cms') or []
    members = ev.get('members') or []
    # side: control modules grid
    cm_html = '<div class="stu-empty">No control modules.</div>'
    if cms:
        rows = ''.join(
            '<tr><td><code>' + _html.escape(c.get('name', '')) + '</code></td><td>'
            + _html.escape(str(c.get('n_blocks', ''))) + '</td></tr>' for c in cms)
        cm_html = ('<table class="stu-grid"><thead><tr><th>Control Module</th>'
                   '<th>Blocks</th></tr></thead><tbody>' + rows + '</tbody></table>')
    mem_html = '<div class="stu-empty">No members.</div>'
    if members:
        rows = ''.join(
            '<tr><td><code>' + _html.escape(m.get('name', '')) + '</code></td><td>'
            + _html.escape(m.get('type', '') or m.get('cls', '')) + '</td><td>'
            + _html.escape(m.get('desc', '')) + '</td></tr>' for m in members)
        mem_html = ('<table class="stu-grid"><thead><tr><th>Member</th><th>Type</th>'
                    '<th>Description</th></tr></thead><tbody>' + rows + '</tbody></table>')

    return {
        'name': em_name, 'kind': 'Equipment Module',
        'diagram_url': 'em', 'obj': em_name,  # main loads via /studio_diagram (see note in phase builder)
        'panels': [{'key': 'cms', 'label': 'Control Modules', 'html': cm_html},
                   {'key': 'members', 'label': 'Members', 'html': mem_html}],
        'counts': {'Control modules': len(cms), 'Members': len(members)},
    }


def build_em_diagram_html(text, em_name):
    """Standalone HTML doc (for the Studio iframe) with an EM's state logic + FBD."""
    try:
        ev = em_bridge.build_em_views(text, only=em_name).get(em_name, {})
    except Exception as e:
        ev = {}
    state = ev.get('state') or ''
    fbd = ev.get('fbd') or ''
    body = ''
    if state:
        body += '<div class="stu-embed">' + state + '</div>'
    if fbd:
        body += '<div class="stu-embed">' + fbd + '</div>'
    if not body:
        body = '<p style="padding:20px;color:#64748b">No command logic or diagram for this EM.</p>'
    return _diagram_doc(em_name, body)


def _diagram_doc(title, body):
    return ('<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<style>body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
            'background:#fff;color:#16202c}.stu-embed{padding:8px}'
            'table{border-collapse:collapse;font-size:12px}td,th{padding:4px 8px;border:1px solid #e2e8f0}'
            'svg{max-width:100%}</style></head><body>' + body + '</body></html>')


def build_cm_studio(text, cm_name):
    """Studio payload for a CM class: its FBD diagram loads via /studio_diagram in the
    main-panel iframe (kept out of JSON to avoid large-payload truncation)."""
    try:
        fv = fbd_bridge.build_fbd_views(text, only=cm_name)
        diagram = fv.get(cm_name, '')
    except Exception as e:
        return {'error': f'Could not build CM view: {e}'}
    if not diagram:
        return {'error': f'No diagram found for control module "{cm_name}".'}
    return {
        'name': cm_name, 'kind': 'Control Module',
        'diagram_url': 'cm', 'obj': cm_name,
        'panels': [], 'counts': {},
    }


def build_cm_diagram_html(text, cm_name):
    """Standalone HTML doc (for the Studio iframe) with a CM's FBD diagram + info cards."""
    try:
        fv = fbd_bridge.build_fbd_views(text, only=cm_name)
        diagram = fv.get(cm_name, '')
    except Exception:
        diagram = ''
    if not diagram:
        diagram = '<p style="padding:20px;color:#64748b">No diagram for this control module.</p>'
    return _diagram_doc(cm_name, diagram)


def build_studio(text, obj_id, catalog=None):
    """Dispatch a Studio open by object id (phase:X / em:X / cm:X / dep:TAG).
    Always attaches the resolved S88 path breadcrumb (#3)."""
    if obj_id.startswith('phase:'):
        payload = build_phase_studio(text, obj_id.split(':', 1)[1])
    elif obj_id.startswith('em:'):
        payload = build_em_studio(text, obj_id.split(':', 1)[1])
    elif obj_id.startswith('cm:'):
        payload = build_cm_studio(text, obj_id.split(':', 1)[1])
    elif obj_id.startswith('dep:'):
        payload = _build_deployed_studio(text, obj_id.split(':', 1)[1], catalog)
    else:
        payload = build_phase_studio(text, obj_id)
    try:
        payload['path'] = resolve_path(text, obj_id)
    except Exception:
        payload['path'] = {'crumbs': [], 'unit': '', 'found': False}
    return payload


def _build_deployed_studio(text, tag, catalog=None):
    """Studio payload for a deployed MODULE_INSTANCE. Resolves its class from the
    authoritative instance line, then renders the class diagram (EM state/command
    logic or CM FBD) relabelled with the instance identity."""
    idx = _deployed_line_index(text)
    info = idx.get(tag)
    cls = info['cls'] if info else ''
    if not cls:
        return {'name': tag, 'kind': 'Deployed instance',
                'error': f'Could not resolve the class for instance "{tag}".'}
    # decide EM vs CM by catalog membership (robust), falling back to a name heuristic
    is_em = None
    if catalog is not None:
        em_names = {e['name'] for e in catalog.get('em_classes', [])}
        cm_names = {c['name'] for c in catalog.get('cm_classes', [])}
        if cls in em_names:
            is_em = True
        elif cls in cm_names:
            is_em = False
    if is_em is None:
        is_em = bool(_re.search(
            r'MODULE_CLASS\s+NAME="' + _re.escape(cls) + r'"[^{]*\{[^}]*BATCH_EQUIPMENT',
            text))
    try:
        payload = build_em_studio(text, cls) if is_em else build_cm_studio(text, cls)
    except Exception as e:
        return {'name': tag, 'kind': 'Deployed instance',
                'error': f'Could not build view for class "{cls}": {e}'}
    payload['name'] = tag
    payload['kind'] = ('Equipment Module instance' if is_em else 'Control Module instance')
    payload['instance_of'] = cls
    return payload


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
        'diagram_url': True,  # main panel loads /phase_view in an iframe (see note above)
        'panels': [
            {'key': 'params', 'label': 'Parameters', 'html': _param_grid(params)},
            {'key': 'attrs', 'label': 'Attributes', 'html': _attr_grid(attrs)},
            {'key': 'mon', 'label': 'Monitors', 'html': _monitor_grid(mons)},
        ],
        'counts': {'Parameters': len(params), 'Attributes': len(attrs)},
    }
