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
        'composites': [],   # {name, category, description}
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

    # ── Composites (FUNCTION_BLOCK_TEMPLATE). The CATEGORY may be on the
    #    declaration line OR inside the block, so check both. ────────────────
    seen_comp = set()
    # names already classified as CM/EM library types (basic control blocks)
    basic_types = {'AI', 'AO', 'DI', 'DO', 'PID', 'CALC'}
    for cm in re.finditer(r'FUNCTION_BLOCK_TEMPLATE\s+NAME="([^"]+)"(?:\s+CATEGORY="([^"]*)")?', text):
        name = cm.group(1)
        if name in seen_comp:
            continue
        seen_comp.add(name)
        blk = extract_block(text, cm.end())
        cat = cm.group(2) or ''
        if not cat:
            cm2 = re.search(r'CATEGORY="([^"]*)"', blk[:400])
            cat = cm2.group(1) if cm2 else ''
        desc = re.search(r'DESCRIPTION="([^"]*)"', blk)
        # treat as composite if category says so, or it's not a basic control block
        is_composite = ('composite' in cat.lower()) or (name not in basic_types)
        if is_composite:
            catalog['composites'].append({
                'name': name, 'category': cat, 'cat_lib': _cat_leaf(cat),
                'description': desc.group(1).strip() if desc else ''})

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

    # ── derive relationships for the tree view ─────────────────────────────
    # When a single Unit Class is the subject of the export, the phase classes
    # exported alongside it are that unit's phases (DeltaV bundles a unit's
    # phases with it). Same heuristic for EM classes co-exported with a unit.
    if len(catalog['unit_classes']) == 1 and catalog['phase_classes']:
        uc = catalog['unit_classes'][0]['name']
        catalog.setdefault('unit_phases', {})[uc] = [p['name'] for p in catalog['phase_classes']]
        if catalog['em_classes']:
            catalog.setdefault('unit_ems', {})[uc] = [e['name'] for e in catalog['em_classes']]
    # When an EM class is the subject, CM classes alongside it are its CMs
    if len(catalog['em_classes']) >= 1 and catalog['cm_classes']:
        # associate all CMs to each EM only when a single EM (unambiguous)
        if len(catalog['em_classes']) == 1:
            em = catalog['em_classes'][0]['name']
            catalog.setdefault('em_cms', {})[em] = [c['name'] for c in catalog['cm_classes']]

    return catalog


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
    }
