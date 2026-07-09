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


def _class_io_html(text, cls_name):
    """Parameter / I/O connection list for a MODULE_CLASS (EM or CM), for the Studio
    side pane (#4). Reads ATTRIBUTE definitions: name, connection direction, type,
    description. Gives the right pane real content instead of blank."""
    m = _re.search(r'MODULE_CLASS\s+NAME="' + _re.escape(cls_name) + r'"', text)
    if not m:
        return '<div class="stu-empty">Class definition not found.</div>'
    try:
        blk = db_parser.extract_block(text, text.index('{', m.start()))
    except Exception:
        return '<div class="stu-empty">Could not read class definition.</div>'
    rows = []
    for am in _re.finditer(r'ATTRIBUTE\s+NAME="([^"]+)"([^{]*)\{', blk):
        name = am.group(1)
        inline = am.group(2)  # CONNECTION/TYPE often sit here, before the brace body
        try:
            abody = db_parser.extract_block(blk, am.end() - 1)
        except Exception:
            abody = ''
        scope = inline + abody
        conn = _re.search(r'CONNECTION=(\w+)', scope)
        typ = _re.search(r'TYPE=(\w+)', scope)
        desc = _re.search(r'DESCRIPTION="([^"]*)"', scope)
        # skip pure-graphics/version pseudo-attributes with no connection & no desc
        if not conn and not (desc and desc.group(1)) and name in (
                'VERSION_CLASS', 'VERSION', 'FRAME'):
            continue
        direction = conn.group(1).title() if conn else ''
        arrow = {'Input': '\u2190 read', 'Output': '\u2192 write'}.get(direction, '')
        rows.append((name, direction, arrow, typ.group(1) if typ else '',
                     desc.group(1) if desc else ''))
    if not rows:
        return '<div class="stu-empty">No parameters or I/O connections defined on this class.</div>'
    h = ['<table class="stu-grid"><thead><tr><th>Parameter</th><th>Direction</th>'
         '<th>Type</th><th>Description</th></tr></thead><tbody>']
    for name, direction, arrow, typ, desc in rows:
        dcell = (f'<span class="stu-io stu-io-{direction.lower()}">{_html.escape(arrow)}</span>'
                 if arrow else _html.escape(direction))
        h.append('<tr><td><code>' + _html.escape(name) + '</code></td>'
                 '<td>' + dcell + '</td>'
                 '<td>' + _html.escape(typ) + '</td>'
                 '<td class="stu-desc">' + _html.escape(desc) + '</td></tr>')
    h.append('</tbody></table>')
    return ''.join(h)


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
        insts = _deployed_instances(text, catalog)
    except Exception:
        insts = {}
    if insts:
        for unit in sorted(insts.keys()):
            items = [{'id': it['id'], 'name': it['name'], 'cls': it.get('cls', ''),
                      'kind': it.get('kind', '')}
                     for it in sorted(insts[unit], key=lambda x: x['name'])]
            label = ('Instances \u00b7 ' + unit) if unit else 'Instances (unassigned)'
            groups.append({'group': label, 'items': items, 'is_instances': True})
    return groups


def _deployed_instances(text, catalog=None):
    """{ unit_name: [ {id:'dep:TAG', name:TAG, cls, kind} ] } for all MODULE_INSTANCEs,
    grouped by their S88 unit. `kind` is 'em' or 'cm' (#5), resolved via catalog
    membership of the instance's class."""
    idx = _deployed_line_index(text)
    em_names, cm_names = set(), set()
    if catalog is not None:
        em_names = {e['name'] for e in catalog.get('em_classes', [])}
        cm_names = {c['name'] for c in catalog.get('cm_classes', [])}
    out = {}
    for tag, info in idx.items():
        cls = info.get('cls', '')
        kind = 'em' if cls in em_names else ('cm' if cls in cm_names else '')
        out.setdefault(info.get('unit', ''), []).append(
            {'id': 'dep:' + tag, 'name': tag, 'cls': cls, 'kind': kind})
    return out


def build_em_studio(text, em_name):
    """Studio payload for an EM class: command/state logic diagram in the main panel,
    plus its resolved control modules and members in the side panels.

    Builds directly from command_state_html / build_fbd_views / em_cm_members rather
    than em_bridge.build_em_views, because that path filters through em_modules() which
    misclassifies FBD-only EMs (names not starting with 'EM', no state logic) as CMs and
    returns empty — the cause of blank/missing EM diagrams for classes like
    TOTALIZER_EM_C, CHT_DHT_EM_C, etc."""
    try:
        state = em_bridge.command_state_html(text, em_name) or ''
    except Exception:
        state = ''
    try:
        fbd = fbd_bridge.build_fbd_views(text, only=em_name).get(em_name, '') or ''
    except Exception:
        fbd = ''
    try:
        members = em_bridge.em_cm_members(text, em_name) or []
    except Exception:
        members = []
    if not state and not fbd and not members:
        return {'error': f'No command logic, diagram, or members found for EM "{em_name}".'}
    has_state = bool(state)
    mem_html = '<div class="stu-empty">No control modules resolved for this EM.</div>'
    if members:
        rows = ''.join(
            '<tr><td><code>' + _html.escape(m.get('name', '')) + '</code></td><td>'
            + _html.escape(m.get('type', '') or m.get('cls', '')) + '</td><td>'
            + _html.escape(m.get('desc', '')) + '</td></tr>' for m in members)
        mem_html = ('<table class="stu-grid"><thead><tr><th>Member (CM)</th><th>Type</th>'
                    '<th>Description</th></tr></thead><tbody>' + rows + '</tbody></table>')
    panels = [{'key': 'members', 'label': f'Control Modules ({len(members)})',
               'html': mem_html},
              {'key': 'params', 'label': 'Parameters & I/O',
               'html': _class_io_html(text, em_name)}]
    # Command-driven EMs (with command SFCs) can be run in real-simulation mode.
    can_sim = False
    try:
        import fbd_interp
        _meta = fbd_interp.em_sim_meta(text, em_name)
        can_sim = bool(_meta.get('commands'))
    except Exception:
        can_sim = False
    n_inst = len(_re.findall(
        r'MODULE_INSTANCE TAG="[^"]+" PLANT_AREA="[^"]*" MODULE_CLASS="'
        + _re.escape(em_name) + r'"', text))
    return {
        'name': em_name, 'kind': 'Equipment Module',
        'diagram_url': 'em', 'obj': em_name,
        'has_state': has_state, 'has_fbd': bool(fbd),
        'panels': panels,
        'can_simulate': can_sim,
        'can_matrix': n_inst >= 2, 'matrix_class': em_name, 'instance_count': n_inst,
        'counts': {'Members': len(members),
                   'Logic': 'state+FBD' if (has_state and fbd) else ('state' if has_state else 'FBD')},
    }


def build_em_diagram_html(text, em_name, theme='light'):
    """Standalone HTML doc (for the Studio iframe) with an EM's state logic + FBD.
    Builds directly (see note in build_em_studio) so FBD-only EMs render too."""
    try:
        state = em_bridge.command_state_html(text, em_name) or ''
    except Exception:
        state = ''
    try:
        fbd = fbd_bridge.build_fbd_views(text, only=em_name).get(em_name, '') or ''
    except Exception:
        fbd = ''
    body = ''
    if state:
        body += ('<div class="stu-embed stu-embed-cmd"><div class="stu-embed-h">Command / State logic</div>'
                 '<div class="stu-cmd-host">' + state + '</div></div>')
    if fbd:
        body += ('<div class="stu-embed"><div class="stu-embed-h">Function block diagram</div>'
                 + fbd + '</div>')
    if not body:
        body = '<p style="padding:20px;color:#64748b">No command logic or diagram for this EM.</p>'
    return _diagram_doc(em_name, body, theme=theme)


def _diagram_doc(title, body, theme='light'):
    """Wrap Studio diagram fragments (which carry their own <style> blocks) in a doc
    with a layout that gives them room — full width, generous padding, horizontal
    scroll instead of squeezing, and clear separation between stacked sections (state
    logic vs FBD). Honors the parent app's light/dark theme so the diagram pane doesn't
    stay white in dark mode."""
    dark = (theme == 'dark')
    if dark:
        page_bg, card_bg, ink, ink2, border, shadow = (
            '#0f172a', '#1e293b', '#e2e8f0', '#94a3b8', '#334155', 'rgba(0,0,0,.35)')
    else:
        page_bg, card_bg, ink, ink2, border, shadow = (
            '#f8fafc', '#ffffff', '#16202c', '#64748b', '#e2e8f0', 'rgba(15,23,42,.05)')
    return (
        '<!DOCTYPE html><html data-theme="' + theme + '"><head><meta charset="utf-8">'
        '<style>'
        '*{box-sizing:border-box}'
        'html,body{margin:0;padding:0}'
        'body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
        'background:' + page_bg + ';color:' + ink + ';line-height:1.4}'
        '.stu-doc{padding:14px 16px 40px;min-width:0}'
        '.stu-embed{background:' + card_bg + ';border:1px solid ' + border + ';border-radius:10px;'
        'padding:14px 16px;margin:0 0 16px;overflow-x:auto;box-shadow:0 1px 3px ' + shadow + '}'
        '.stu-embed-h{font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;'
        'color:' + ink2 + ';margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid ' + border + '}'
        'table{border-collapse:collapse;font-size:12px}'
        'td,th{padding:4px 8px;border:1px solid ' + border + '}'
        '.fbd-wrap,.fbd-svg-holder{overflow:auto;max-width:100%}'
        # ── Fix the embedded command/state fragment inside the iframe ──
        # The fragment carries its OWN <style> that appears later in the document than
        # this <head> block, so equal-specificity !important rules there would win. We
        # therefore use higher-specificity selectors (html body …) so these overrides
        # beat the fragment regardless of source order.
        # The fragment lays out as a full-height flex column: .main{height:calc(100vh-96px)}
        # with .wrap (SFC, flex:1) over .tablewrap (actions). Inside a short iframe 100vh
        # collapses everything to a sliver — so pin .main to a real height and keep flex.
        'html body .main{height:720px!important;min-height:720px!important;max-height:none!important}'
        # ── #5/#6 fix: the Command/State fragment is a full mini-document (its own
        # <style>+<script>) whose body is `.ctabs` + `#cv`, and it injects each command's
        # SFC into `#cv` as a *nested* <iframe srcdoc=...>. That fragment's CSS sizes
        # `#cv{height:calc(100% - 46px)}` and `html,body{height:100%}` — which only works
        # when it fills a fixed-height host. Embedded in an auto-height `.stu-embed`, the
        # 100% chain resolves against nothing, so `#cv` -> 0 and the nested SFC iframe
        # collapses to a sliver (looks like "EM SFC not rendering"; and the outer app
        # stylesheet can't reach the SFC because it lives in that nested iframe). Give the
        # host and the nested iframe a real, fixed height so the chain resolves.
        'html body .stu-cmd-host{height:760px;min-height:760px;position:relative;overflow:hidden}'
        'html body #cv{height:calc(100% - 46px)!important;min-height:0!important}'
        'html body #cv iframe{width:100%!important;height:100%!important;border:0!important;display:block}'
        'html body .stu-embed-cmd{overflow:visible!important}'
        # ── #6 fix (FBD): the Function-Block-Diagram fragment's chrome (info cards, head
        # bar, actions table, chips, the DeltaV/Auto layout toggle, the legend, wires/pins)
        # is styled by the MAIN explorer stylesheet + fbd_bridge.EXPR_MODAL_CSS, neither of
        # which is present in this standalone Studio iframe. Only the SVG boxes (inline
        # fills) rendered; the surrounding cards showed as raw/unstyled (bare buttons, no
        # borders, wrong table alignment). Re-declare that chrome here, theme-aware, so the
        # FBD looks the same in Studio as inline in the Explorer.
          '.fbd-wrap{display:flex;flex-direction:column;gap:14px}'
          '.fbd-diagram-card{border:1px solid ' + border + ';border-radius:10px;background:' + card_bg + ';overflow:hidden}'
          '.fbd-head{padding:10px 14px;background:' + ('#0b1220' if dark else '#f1f5f9') + ';font-weight:600;font-size:13px;'
          'border-bottom:1px solid ' + border + ';color:' + ink + '}'
          '.fbd-sub{color:' + ink2 + ';font-weight:400;font-size:12px}'
          '.fbd-svg-holder{padding:10px;overflow:auto;max-height:78vh;background:' + card_bg + '}'
          '.fbd-info-card{border:1px solid ' + border + ';border-radius:10px;padding:12px 14px;background:' + card_bg + '}'
          '.fbd-info-card h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:' + ink2 + '}'
          '.fbd-collapse>h4,.fbd-collapse>.fbd-head{cursor:pointer;user-select:none}'
          '.fbd-collapse.collapsed>*:not(h4):not(.fbd-head){display:none!important}'
          '.fbd-comp-link{cursor:pointer}'
          '.fbd-table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px}'
          '.fbd-table th{text-align:left;padding:7px 12px;color:' + ink2 + ';font-size:11px;text-transform:uppercase;'
          'letter-spacing:.04em;border-bottom:1px solid ' + border + ';font-weight:600}'
          '.fbd-table td{padding:7px 12px;border-bottom:1px solid ' + border + ';vertical-align:top;font-size:12px}'
          '.fbd-table tr:last-child td{border-bottom:0}'
          '.chips{display:flex;flex-wrap:wrap;gap:6px}'
          '.chip{padding:4px 10px;border:1px solid ' + border + ';border-radius:8px;font-size:12px;cursor:pointer;'
          'background:' + ('#0b1220' if dark else '#f3f6fa') + ';color:' + ink + '}'
          # layout toggle (DeltaV / Auto-arrange) — was rendering as raw browser buttons
          '.fbd-layout-toggle{display:inline-flex;gap:0;margin:0 0 8px;border:1px solid ' + border + ';'
          'border-radius:7px;overflow:hidden;font-size:12px}'
          '.fbd-layout-toggle .lay-btn{padding:5px 12px;background:' + card_bg + ';border:0;cursor:pointer;'
          'color:' + ink2 + ';font-weight:600}'
          '.fbd-layout-toggle .lay-btn+.lay-btn{border-left:1px solid ' + border + '}'
          '.fbd-layout-toggle .lay-btn.active{background:' + ('#334155' if dark else '#1e293b') + ';color:#fff}'
          '.fbd-net-hint{font-size:11px;color:' + ink2 + ';margin-left:10px}'
          '.fbd-legend{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:2px 0 8px;padding:6px 10px;'
          'background:' + ('#0b1220' if dark else '#f8fafc') + ';border:1px solid ' + border + ';border-radius:7px;'
          'font-size:11px;color:' + ink2 + '}'
          '.fbd-leg-lbl{color:' + ink2 + ';font-weight:600}'
          '.fbd-leg-item{display:inline-flex;align-items:center;gap:4px}.fbd-leg-item svg{flex:0 0 auto}'
          '.fbd-wire{cursor:pointer}.fbd-pin{cursor:pointer}.fb{cursor:default}'
        'html body .wrap{min-height:0!important;overflow:hidden!important}'
        'html body .diagram{min-height:300px!important}'
        'html body .tablewrap{flex:0 0 320px!important;resize:vertical!important;overflow:auto!important}'
        + (
            # ── Dark mode ──
            # The embedded EM/CM command fragment hard-codes light backgrounds on MANY
            # elements — not just .diagram/.tablewrap but the whole command-tab UI:
            # .ctabs/.ctab (command tab bar), .tabs/.tab (sub-tabs), .panel (side panel),
            # .act .expr (action expressions), .special, .sfc-ipanel. A phase view only
            # has the SFC (.diagram/.tablewrap), which is why phases looked fine but EMs/
            # CMs stayed white. Recolor the full surface set, recolor text/borders, and
            # softly invert the SVG diagrams so they read on dark. High specificity
            # (html body …) beats the fragment's own later <style>.
            (
              # surfaces -> dark card
              'html body .diagram,html body .tablewrap,html body .wrap,'
              'html body .panel,html body .tabs,html body .tab,html body .ctab,'
              'html body .sfc-ipanel'
              '{background:' + card_bg + '!important}'
              # tab bars / secondary strips -> slightly deeper
              'html body .ctabs,html body .act .expr'
              '{background:#0b1220!important}'
              # generic text + borders inside the fragment
              'html body .diagram,html body .diagram *,'
              'html body .tablewrap,html body .tablewrap *,'
              'html body .panel,html body .panel *,'
              'html body .tabs,html body .tab,html body .ctab,html body .ctabs'
              '{color:' + ink + '!important;border-color:' + border + '!important}'
              # keep the "active/on" command highlight readable (orange stays, force white text)
              'html body .on{color:#fff!important}'
              # tables inside the fragment
              'html body table td,html body table th{border-color:' + border + '!important}'
              # invert the SVG diagrams (SFC + FBD) so their light palette works on dark
              'html body .diagram svg,html body .wrap svg,html body .fbd-svg-holder svg,'
              'html body .stu-embed svg{filter:invert(.92) hue-rotate(180deg)}'
              'body{color-scheme:dark}'
            )
            if dark else
            'svg{max-width:none;height:auto}'
        ) +
        '</style></head><body><div class="stu-doc">' + body + '</div>'
        # Make the Studio embed section headers (Command/State logic, Function block
        # diagram) collapsible inside the iframe — the parent page's collapse handler
        # can't reach across the iframe boundary, so wire a tiny local one here.
        '<script>(function(){'
        'document.querySelectorAll(".stu-embed-h").forEach(function(h){'
        'h.style.cursor="pointer";h.style.userSelect="none";'
        'var c=document.createElement("span");c.textContent="\\u25be ";c.style.fontSize="10px";'
        'c.style.color="' + ink2 + '";h.insertBefore(c,h.firstChild);'
        'h.addEventListener("click",function(){'
        'var card=h.parentElement,col=card.classList.toggle("stu-collapsed");'
        'c.textContent=col?"\\u25b8 ":"\\u25be ";'
        'Array.prototype.forEach.call(card.children,function(ch){'
        'if(ch!==h) ch.style.display=col?"none":"";});'
        '});});'
        '})();</script>'
        '</body></html>')


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
    # Parameter Matrix is available when this class has >1 deployed instance to compare.
    n_inst = len(_re.findall(
        r'MODULE_INSTANCE TAG="[^"]+" PLANT_AREA="[^"]*" MODULE_CLASS="'
        + _re.escape(cm_name) + r'"', text))
    return {
        'name': cm_name, 'kind': 'Control Module',
        'diagram_url': 'cm', 'obj': cm_name,
        'panels': [{'key': 'params', 'label': 'Parameters & I/O',
                    'html': _class_io_html(text, cm_name)}],
        'can_matrix': n_inst >= 2, 'matrix_class': cm_name, 'instance_count': n_inst,
        'counts': {},
    }


def build_cm_diagram_html(text, cm_name, theme='light'):
    """Standalone HTML doc (for the Studio iframe) with a CM's FBD diagram + info cards."""
    try:
        fv = fbd_bridge.build_fbd_views(text, only=cm_name)
        diagram = fv.get(cm_name, '')
    except Exception:
        diagram = ''
    if not diagram:
        diagram = '<p style="padding:20px;color:#64748b">No diagram for this control module.</p>'
    return _diagram_doc(cm_name, diagram, theme=theme)


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
    # Real-simulation runs on THIS instance (members resolve to real CM tags). Pass the
    # instance tag so the sim resolves member->device and honours IGNORE'd members.
    if is_em and payload.get('can_simulate'):
        payload['sim_instance'] = tag
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
