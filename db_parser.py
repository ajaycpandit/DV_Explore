"""
DeltaV Database Explorer — object-model parser.

Inventories a DeltaV FHX export into a structured catalog of objects and the
references between them, for the navigable explorer. This is the "skeleton" parser:
it identifies every object, its type, category, and class/instance linkage. Detailed
per-object logic parsing (SFC steps, parameters, monitors) is delegated to the
existing validated parsing core (shared with the converter).
"""

import re


def decode_fhx(raw):
    if raw[:2] == b'\xff\xfe':
        return raw.decode('utf-16-le', errors='replace').lstrip('\ufeff')
    if raw[:2] == b'\xfe\xff':
        return raw.decode('utf-16-be', errors='replace').lstrip('\ufeff')
    return raw.decode('utf-8', errors='replace')


def extract_block(text, start):
    """Return the {...} block beginning at/after `start` (balanced braces)."""
    i = text.index('{', start)
    depth = 0
    s = i
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[s:i+1]
        i += 1
    return ''


def _cat_leaf(category):
    """Last segment of a category path, e.g. '.../PCSD_Master_CMs' -> that lib name."""
    return category.rstrip('/').split('/')[-1] if category else ''


def _classify_module_class(name, category, block):
    """Decide whether a MODULE_CLASS is a CM, EM, or Unit class."""
    cat = category.lower()
    if 'equipment module' in cat or name.startswith('EM') or name.startswith('_EM'):
        return 'EM Class'
    if 'unit' in cat or name.startswith('U-') or name.startswith('U_'):
        return 'Unit Class'
    if 'control module' in cat or name.startswith('_'):
        return 'CM Class'
    # fallback by content: units own phases, EMs own state logic
    if 'PHASE' in block[:2000]:
        return 'Unit Class'
    return 'CM Class'


# Standard DeltaV function block types: a curated "what it does" glossary. The
# FHX export carries an authoritative short DESCRIPTION for each; this adds a
# one-line elaboration for the common standard blocks. Falls back to the FHX
# description when a type isn't listed here.
_FB_TYPE_GLOSSARY = {
    'AI': 'Analog Input — reads and scales a measured analog value, with filtering and alarms.',
    'AIWCALARM': 'Analog Input with conditional alarming on the measured value.',
    'AO': 'Analog Output — drives an analog output (e.g. valve position or a downstream setpoint).',
    'DI': 'Discrete Input — reads an on/off field signal.',
    'DO': 'Discrete Output — drives an on/off field output.',
    'PID': 'PID Control — proportional-integral-derivative closed-loop control.',
    'PIDWCALARM': 'PID control with conditional alarming.',
    'CALC': 'Calc/Logic — evaluates a user structured-text expression to compute its outputs.',
    'ACT': 'Action — runs a structured-text action expression (assignments), typically in sequencing logic.',
    'CND': 'Condition — evaluates a structured-text boolean condition expression.',
    'AND': 'Boolean AND gate.',
    'OR': 'Boolean OR gate.',
    'NOT': 'Boolean NOT (inverter).',
    'XOR': 'Boolean exclusive-OR gate.',
    'PDE': 'Positive Edge Trigger — emits a one-shot pulse on a 0→1 (rising) transition.',
    'NDE': 'Negative Edge Trigger — emits a one-shot pulse on a 1→0 (falling) transition.',
    'BDE': 'Edge Trigger — emits a one-shot pulse on an input transition.',
    'AT': 'Analog Tracking — tracks/holds an analog value under condition control.',
    'EDC': 'Enhanced Device Control — commands a discrete device (valve/motor) with confirmed-state feedback and interlocks.',
    'DCC': 'Discrete Control Condition — supplies fail / interlock / permissive conditions to a device control block.',
    'RTLM': 'Rate Limit — limits the rate of change of a signal.',
    'INTEG': 'Integrator.',
    'FILTER': 'Signal filter (smoothing).',
    'LIM': 'Limit — clamps a signal between high/low bounds.',
    'SCLR': 'Scaler — linearly scales a signal.',
    'SEL': 'Selector — chooses among multiple inputs.',
    'MULDIV': 'Multiply/Divide arithmetic.',
    'ADD': 'Addition arithmetic.',
    'SUB': 'Subtraction arithmetic.',
    'CTD': 'Down counter.',
    'CTU': 'Up counter.',
    'CND': 'Condition — evaluates a structured-text boolean condition expression.',
    'ALMWCALARM': 'Alarm block with conditional alarming.',
    'CAV': 'Control Action / value block.',
}


def parse_database(text):
    """Return a catalog dict describing all objects + relationships in the export."""
    catalog = {
        'areas': [],        # {name, units:[{name,class}]}
        'units': [],        # instances: {name, class, area, category}
        'unit_classes': [], # {name, category, description}
        'em_classes': [],   # {name, category, description}
        'cm_classes': [],   # {name, category, description, control_type}
        'phase_classes': [],# {name, category, description}
        'recipes': [],      # {name, type, category, description}
        'composites': [],   # {name, category, description, anonymous}
        'fb_types': [],     # standard DeltaV block types referenced: {name, description, glossary}
        'modules': [],      # all instances: {name, class, area}
        'index': {},        # name -> object summary (for cross-linking)
    }

    # ── Unit/module INSTANCES: declared as MODULE NAME=.. CLASS=.. with a
    #    PLANT_AREA="Area/ProcessCell" field. Area membership comes from that
    #    field (modules are not physically nested inside the area block). ──────
    area_units = {}   # area name -> [unit dicts]
    for mm in re.finditer(r'MODULE\s+NAME="([^"]+)"\s+CLASS="([^"]+)"', text):
        name, cls = mm.group(1), mm.group(2)
        blk = extract_block(text, mm.end())
        pa = re.search(r'PLANT_AREA="([^"]+)"', blk)
        area_path = pa.group(1) if pa else ''
        area_name = area_path.split('/')[0] if area_path else '(unassigned)'
        desc = re.search(r'DESCRIPTION="([^"]*)"', blk)
        unit = {'name': name, 'class': cls, 'area': area_name,
                'area_path': area_path,
                'description': desc.group(1).strip() if desc else ''}
        catalog['units'].append(unit)
        catalog['modules'].append({'name': name, 'class': cls, 'area': area_name})
        area_units.setdefault(area_name, []).append({'name': name, 'class': cls})

    # register all areas seen (from PLANT_AREA declarations + module references)
    declared = set()
    for am in re.finditer(r'PLANT_AREA\s+NAME="([^"]+)"', text):
        declared.add(am.group(1))
    for aname in sorted(set(list(declared) + list(area_units.keys()))):
        if aname == '(unassigned)' and aname not in area_units:
            continue
        catalog['areas'].append({'name': aname,
                                 'units': area_units.get(aname, [])})

    # ── MODULE_CLASS definitions (CM / EM / Unit classes) ──────────────────
    for mm in re.finditer(r'MODULE_CLASS\s+NAME="([^"]+)"(?:\s+CATEGORY="([^"]*)")?', text):
        name = mm.group(1)
        cat = mm.group(2) or ''
        blk = extract_block(text, mm.end())
        desc = re.search(r'DESCRIPTION="([^"]*)"', blk)
        desc = desc.group(1).strip() if desc else ''
        kind = _classify_module_class(name, cat, blk)
        rec = {'name': name, 'category': cat, 'cat_lib': _cat_leaf(cat),
               'description': desc}
        if kind == 'EM Class':
            catalog['em_classes'].append(rec)
        elif kind == 'Unit Class':
            catalog['unit_classes'].append(rec)
        else:
            # control type hint for CMs
            ct = ''
            for t in ('PID', 'AI', 'AO', 'DI', 'DO', 'CALC', 'CAV'):
                if re.search(r'\b' + t + r'\b', name) or ('/' + t) in blk[:1500]:
                    ct = t; break
            rec['control_type'] = ct
            catalog['cm_classes'].append(rec)

    # ── PHASE_CLASS definitions ────────────────────────────────────────────
    for pm in re.finditer(r'PHASE_CLASS\s+NAME="([^"]+)"(?:\s+CATEGORY="([^"]*)")?', text):
        name = pm.group(1)
        cat = pm.group(2) or ''
        blk = extract_block(text, pm.end())
        desc = re.search(r'DESCRIPTION="([^"]*)"', blk)
        catalog['phase_classes'].append({
            'name': name, 'category': cat, 'cat_lib': _cat_leaf(cat),
            'description': desc.group(1).strip() if desc else ''})

    # ── BATCH_RECIPE (procedures / unit procedures / operations) ───────────
    for rm in re.finditer(r'BATCH_RECIPE\s+NAME="([^"]+)"(?:\s+TYPE=(\w+))?(?:\s+CATEGORY="([^"]*)")?', text):
        name = rm.group(1)
        blk = extract_block(text, rm.end())
        desc = re.search(r'DESCRIPTION="([^"]*)"', blk)
        catalog['recipes'].append({
            'name': name, 'type': rm.group(2) or '', 'category': rm.group(3) or '',
            'description': desc.group(1).strip() if desc else ''})

    # ── Function block types vs composites ─────────────────────────────────
    #   FUNCTION_BLOCK_TEMPLATE  = the standard DeltaV block *types* referenced
    #                              by the modules (ACT, CND, EDC, PID, ...). Not
    #                              composites — these are primitive blocks.
    #   FUNCTION_BLOCK_DEFINITION = the actual composite definitions (user/library
    #                              composites such as C_ARB_MOD_EM_V01, and DeltaV's
    #                              anonymous inline composites named __HEX__).
    #   DeltaV stores a DESCRIPTION on each, which is the authoritative "what it
    #   does"; we capture it (and supplement standard types with a glossary).
    seen_t = set()
    for tm in re.finditer(r'FUNCTION_BLOCK_TEMPLATE\s+NAME="([^"]+)"', text):
        name = tm.group(1)
        if name in seen_t:
            continue
        seen_t.add(name)
        blk = extract_block(text, tm.end())
        desc = re.search(r'DESCRIPTION="([^"]*)"', blk[:300])
        fhx_desc = desc.group(1).strip() if desc else ''
        catalog['fb_types'].append({
            'name': name,
            'description': fhx_desc,
            'glossary': _FB_TYPE_GLOSSARY.get(name, ''),
        })

    seen_comp = set()
    for cm in re.finditer(r'FUNCTION_BLOCK_DEFINITION\s+NAME="([^"]+)"(?:\s+CATEGORY="([^"]*)")?', text):
        name = cm.group(1)
        if name in seen_comp:
            continue
        seen_comp.add(name)
        blk = extract_block(text, cm.end())
        cat = cm.group(2) or ''
        if not cat:
            cm2 = re.search(r'CATEGORY="([^"]*)"', blk[:400])
            cat = cm2.group(1) if cm2 else ''
        desc = re.search(r'DESCRIPTION="([^"]*)"', blk[:600])
        anon = bool(re.match(r'^__[0-9A-Fa-f_]+__$', name))
        # A composite is a reusable *class* when it's a saved/library definition
        # (named, with a category — typically Library/CompositeTemplates/...).
        # The anonymous __HEX__ definitions with no category are *local* inline
        # composites that belong to a single parent object; in a full-database
        # view they shouldn't clutter the top-level Composites section.
        scope = 'class' if (not anon and cat) else 'local'
        catalog['composites'].append({
            'name': name, 'category': cat, 'cat_lib': _cat_leaf(cat),
            'description': desc.group(1).strip() if desc else '',
            'anonymous': anon, 'scope': scope})

    # ── build cross-reference index (class -> instances using it) ──────────
    instances_by_class = {}
    for m in catalog['modules']:
        instances_by_class.setdefault(m['class'], []).append(m['name'])
    catalog['instances_by_class'] = instances_by_class

    # summary index for quick lookup / linking
    def _add(name, otype, **extra):
        catalog['index'][name] = {'name': name, 'type': otype, **extra}
    for u in catalog['units']:        _add(u['name'], 'Unit Instance', cls=u['class'], area=u['area'])
    for c in catalog['unit_classes']: _add(c['name'], 'Unit Class', instances=instances_by_class.get(c['name'], []))
    for c in catalog['em_classes']:   _add(c['name'], 'EM Class')
    for c in catalog['cm_classes']:   _add(c['name'], 'CM Class')
    for p in catalog['phase_classes']:_add(p['name'], 'Phase Class')
    for r in catalog['recipes']:      _add(r['name'], 'Recipe')
    for c in catalog['composites']:   _add(c['name'], 'Composite')
    for t in catalog['fb_types']:     _add(t['name'], 'FB Type', description=t['description'], glossary=t['glossary'])

    # ── real containment references via MODULE_BLOCK ───────────────────────
    #   A module class embeds child modules as:
    #     MODULE_BLOCK NAME="<instance>" MODULE="<referenced class>"
    #   This is the authoritative "class X is used by parent Y as instance Z"
    #   link (e.g. an EM embedding its control-module classes). Works across the
    #   whole database, not just single-object exports.
    class_used_by = {}   # class name -> [{parent, instance}]
    parent_uses = {}     # parent class -> [referenced class names]
    instances = {}       # "parent\u0001tag" -> {tag, cls, parent, desc, ownership}
    parent_instances = {}  # parent -> [instance ids] (in declaration order)
    cat_by_class = {c['name']: c.get('category', '') for c in catalog['cm_classes']}
    cat_by_class.update({c['name']: c.get('category', '') for c in catalog['composites']})
    for mm in re.finditer(r'MODULE_CLASS\s+NAME="([^"]+)"', text):
        parent = mm.group(1)
        blk = extract_block(text, mm.end())
        for mb in re.finditer(r'MODULE_BLOCK\s+NAME="([^"]+)"\s+MODULE="([^"]+)"', blk):
            inst, cls = mb.group(1), mb.group(2)
            class_used_by.setdefault(cls, []).append({'parent': parent, 'instance': inst})
            parent_uses.setdefault(parent, []).append(cls)
            ib = extract_block(blk, mb.end())
            dm = re.search(r'DESCRIPTION="([^"]*)"', ib)
            om = re.search(r'OWNERSHIP=([^\s}]+)', ib)
            iid = parent + '\u0001' + inst
            instances[iid] = {'tag': inst, 'cls': cls, 'parent': parent,
                              'desc': (dm.group(1).strip() if dm else ''),
                              'ownership': (om.group(1) if om else ''),
                              'category': cat_by_class.get(cls, '')}
            parent_instances.setdefault(parent, []).append(iid)
    catalog['class_used_by'] = class_used_by
    catalog['instances'] = instances
    catalog['parent_instances'] = parent_instances

    em_names = {e['name'] for e in catalog['em_classes']}
    cm_names = {c['name'] for c in catalog['cm_classes']}
    # EM class -> the CM classes it embeds (real, from MODULE_BLOCK)
    em_cms = {}
    for parent, used in parent_uses.items():
        if parent in em_names:
            cms = sorted({c for c in used if c in cm_names})
            if cms:
                em_cms[parent] = cms
    catalog['em_cms'] = em_cms

    # ── unit relationships (still heuristic for single-unit class exports) ──
    if len(catalog['unit_classes']) == 1 and catalog['phase_classes']:
        uc = catalog['unit_classes'][0]['name']
        catalog.setdefault('unit_phases', {})[uc] = [p['name'] for p in catalog['phase_classes']]
        if catalog['em_classes']:
            catalog.setdefault('unit_ems', {})[uc] = [e['name'] for e in catalog['em_classes']]
    # Fallback: if no MODULE_BLOCK linkage found but exactly one EM with CMs,
    # associate them (covers exports that don't carry child-module records).
    if not em_cms and len(catalog['em_classes']) == 1 and catalog['cm_classes']:
        em = catalog['em_classes'][0]['name']
        catalog['em_cms'][em] = [c['name'] for c in catalog['cm_classes']]

    _parse_hierarchy(text, catalog)
    return catalog


def _parse_hierarchy(text, catalog):
    """Parse the real Area / Process Cell / Unit / Module instance hierarchy plus
    unit-class phases, from EQUIPMENT_UNIT_MODULE, MODULE_INSTANCE and PHASE
    records. Populates catalog with unit_instances, deployed_modules,
    unit_modules, unit_class_phases and area_tree."""
    deployed, unit_modules = {}, {}
    for m in re.finditer(r'MODULE_INSTANCE\s+TAG="([^"]+)"\s+PLANT_AREA="([^"]+)"\s+MODULE_CLASS="([^"]*)"', text):
        tag, path, cls = m.group(1), m.group(2), m.group(3)
        parts = path.split('/')
        unit = parts[2] if len(parts) >= 3 else (parts[-1] if parts else '')
        deployed[tag] = {'tag': tag, 'cls': cls, 'path': path, 'unit': unit,
                         'area': parts[0] if parts else '',
                         'cell': parts[1] if len(parts) >= 2 else ''}
        unit_modules.setdefault(unit, []).append(tag)
    catalog['deployed_modules'] = deployed
    catalog['unit_modules'] = unit_modules

    unit_instances = {}
    for m in re.finditer(r'EQUIPMENT_UNIT_MODULE\s+NAME="([^"]+)"\s+CLASS="([^"]+)"', text):
        name, cls = m.group(1), m.group(2)
        blk = extract_block(text, m.end())
        pa = re.search(r'PLANT_AREA="([^"]+)"', blk)
        path = pa.group(1) if pa else ''
        desc = re.search(r'DESCRIPTION="([^"]*)"', blk)
        vals = []
        for vm in re.finditer(r'ATTRIBUTE_INSTANCE\s+NAME="([^"/]+)"\s*\{\s*VALUE\s*\{\s*CV=("[^"]*"|[^}\s]+)', blk):
            vals.append({'name': vm.group(1), 'cv': vm.group(2).strip('"')})
        parts = path.split('/')
        unit_instances[name] = {
            'name': name, 'cls': cls, 'area_path': path,
            'area': parts[0] if parts else '',
            'cell': parts[1] if len(parts) >= 2 else '',
            'description': desc.group(1).strip() if desc else '',
            'values': vals, 'modules': unit_modules.get(name, [])}
    catalog['unit_instances'] = unit_instances

    ucph = {}
    uc_detail = {}
    for uc in catalog['unit_classes']:
        mm = re.search(r'MODULE_CLASS\s+NAME="' + re.escape(uc['name']) + r'"', text)
        if not mm:
            continue
        blk = extract_block(text, mm.end())
        ucph[uc['name']] = [pm.group(1) for pm in re.finditer(r'PHASE\s+CLASS="([^"]+)"', blk)]
        params = [{'name': a.group(1), 'type': a.group(2)}
                  for a in re.finditer(r'ATTRIBUTE\s+NAME="([^"]+)"\s+TYPE=([A-Z_]+)', blk)]
        aliases = []
        for al in re.finditer(r'ALIAS_DEFINITION\s+NAME="([^"]+)"\s*\{([^}]*)\}', blk):
            body = al.group(2)
            desc = re.search(r'DESCRIPTION="([^"]*)"', body)
            purp = re.search(r'PURPOSE=([A-Z_]+)', body)
            aliases.append({'name': al.group(1),
                            'desc': desc.group(1) if desc else '',
                            'purpose': purp.group(1) if purp else ''})
        modmm = re.findall(r'UNIT_MODULE_DEFINITION\s+NAME="([^"]+)"', blk)
        uc_detail[uc['name']] = {'params': params, 'aliases': aliases,
                                 'unit_modules': modmm}
    catalog['unit_class_phases'] = ucph
    catalog['unit_class_detail'] = uc_detail

    area_tree = {}
    for u in unit_instances.values():
        area_tree.setdefault(u['area'] or '(unassigned)', {}).setdefault(u['cell'] or '', []).append(u['name'])
    catalog['area_tree'] = area_tree

    # ── Named Sets (DeltaV "Named Sets", stored as ENUMERATION_SET) ──────────
    named_sets = []
    for nm in re.finditer(r'ENUMERATION_SET\s+NAME="([^"]+)"[^{]*\{', text):
        blk = extract_block(text, nm.end() - 1)
        desc = re.search(r'DESCRIPTION="([^"]*)"', blk)
        cat = re.search(r'CATEGORY="([^"]*)"', blk)
        entries = [{'value': int(e.group(1)), 'name': e.group(2)}
                   for e in re.finditer(r'ENTRY\s+VALUE=(\d+)\s+NAME="([^"]+)"', blk)]
        sname = nm.group(1)
        users = []
        for mc in re.finditer(r'MODULE_CLASS\s+NAME="([^"]+)"', text):
            mcblk = extract_block(text, mc.end())
            if (f'STATE_SET="{sname}"' in mcblk) or (f'SET="{sname}"' in mcblk):
                if mc.group(1) not in users:
                    users.append(mc.group(1))
        named_sets.append({'name': sname,
                           'description': desc.group(1) if desc else '',
                           'category': cat.group(1) if cat else '',
                           'entries': entries,
                           'used_by': users})
    catalog['named_sets'] = named_sets

    em_state_set = {}
    for mc in re.finditer(r'MODULE_CLASS\s+NAME="([^"]+)"', text):
        mcblk = extract_block(text, mc.end())
        ss = re.search(r'STATE_SET="([^"]+)"', mcblk)
        if ss:
            em_state_set[mc.group(1)] = ss.group(1)
    catalog['em_state_set'] = em_state_set

    # ── Physical Network: controller assignment (CONTROLLER="...") ───────────
    controllers = {}
    module_controller = {}
    for m in re.finditer(r'MODULE_INSTANCE\s+TAG="([^"]+)"', text):
        blk = extract_block(text, m.end())
        cm = re.search(r'CONTROLLER="([^"]+)"', blk[:2000])
        if cm:
            controllers.setdefault(cm.group(1), []).append(m.group(1))
            module_controller[m.group(1)] = cm.group(1)
    catalog['controllers'] = controllers
    catalog['module_controller'] = module_controller


def catalog_summary(catalog):
    """Counts for a quick overview."""
    return {
        'areas': len(catalog['areas']),
        'unit_instances': len(catalog['units']),
        'unit_classes': len(catalog['unit_classes']),
        'em_classes': len(catalog['em_classes']),
        'cm_classes': len(catalog['cm_classes']),
        'phase_classes': len(catalog['phase_classes']),
        'recipes': len(catalog['recipes']),
        'composites': len(catalog['composites']),
        'fb_types': len(catalog['fb_types']),
    }
