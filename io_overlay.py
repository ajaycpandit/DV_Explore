"""Physical I/O overlay.

Strategy/phase FHX exports describe control modules and their logic, but not the
physical wiring. A hardware / I/O-reference export carries that: each field device
sits at a hardware path (Controller -> I/O subsystem -> Card -> Port, sometimes ->
Channel) and exposes one or more signals, each tagged with a DEVICE_SIGNAL_TAG.

This module parses that hardware layer and joins it to the control modules:

  parse_io(text)              -> {devices, tree, signals_by_tag, controllers}
  build_tree(devices)         -> nested Controller/Card/Port/Channel hierarchy
  join_to_modules(io, strat)  -> link each signal to the CM that references it
  io_for_module(io, tag)      -> the physical I/O points a given module uses

Device-type coverage: DeviceNet (Westlock-style valve I/O) is fully parsed here.
The parser is structured so other device types (Foundation Fieldbus H1, HART,
CHARM/CIOC, classic DI/DO cards) can be added as additional _parse_* readers that
emit the same normalised device record; the tree builder and module-join work off
that normal form regardless of source type.

The overlay is additive and degrades gracefully: if a loaded export contains no
hardware blocks, parse_io returns empty structures and the rest of the app behaves
exactly as before. Nothing here touches core/.
"""

import re


# ── device-type readers ──────────────────────────────────────────────────────
def _parse_devicenet(text):
    """DeviceNet devices: DEVICENET_DEVICE with a PORT_ASSIGNMENT path + SIGNALs.
    Path form: Controller/IOsubsystem/Card/Port  (e.g. LAFC-CNTL03B/IO1/C01/P01)."""
    devices = []
    dev_re = re.compile(
        r'DEVICENET_DEVICE NAME="([^"]+)"[^{]*?\{(.*?)\n\}', re.DOTALL)
    for m in dev_re.finditer(text):
        name, body = m.group(1), m.group(2)
        desc = _attr(body, 'DESCRIPTION')
        pa = re.search(r'PORT_ASSIGNMENT\s*\{\s*PATH="([^"]+)"\s+ADDRESS=(\d+)', body)
        path = pa.group(1) if pa else ''
        address = int(pa.group(2)) if pa else None
        manuf = _hdr_attr(m.group(0), 'MANUFACTURER')
        dtype = _hdr_attr(m.group(0), 'DEVICENET_DEVICE_TYPE')
        signals = []
        for sm in re.finditer(
                r'SIGNAL NAME="([^"]+)"\s*\{(.*?)(?=\n\s*SIGNAL NAME="|\n\s*\}\s*$)',
                body + '\n}', re.DOTALL):
            sname, sbody = sm.group(1), sm.group(2)
            signals.append({
                'signal': sname,
                'tag': _attr(sbody, 'DEVICE_SIGNAL_TAG'),
                'desc': _attr(sbody, 'DESCRIPTION'),
                'direction': (re.search(r'DIRECTION=(\w+)', sbody) or _N).group(1)
                             if re.search(r'DIRECTION=(\w+)', sbody) else '',
                'byte': _int(sbody, 'BYTE_OFFSET'),
                'bit': _int(sbody, 'BIT_NUMBER'),
            })
        devices.append({
            'device': name,
            'kind': 'DeviceNet',
            'desc': desc,
            'manufacturer': manuf,
            'device_type': dtype,
            'path': path,
            'address': address,
            'levels': _split_path(path),
            'signals': signals,
        })
    return devices


class _N:  # tiny null-match helper
    @staticmethod
    def group(_):
        return ''


def _attr(body, name):
    m = re.search(name + r'="([^"]*)"', body)
    return m.group(1) if m else ''


def _hdr_attr(header, name):
    m = re.search(name + r'="([^"]*)"', header)
    return m.group(1) if m else ''


def _int(body, name):
    m = re.search(name + r'=(\d+)', body)
    return int(m.group(1)) if m else None


def _split_path(path):
    """Break a hardware path into labelled levels. The path depth varies by device
    type (some have a Port, some go straight Card->Channel), so we label by position
    and by recognised prefixes rather than assuming a fixed shape."""
    if not path:
        return []
    parts = [p for p in path.split('/') if p]
    levels = []
    for i, p in enumerate(parts):
        if i == 0:
            role = 'Controller'
        elif re.match(r'^IO\d*$', p, re.I):
            role = 'I/O subsystem'
        elif re.match(r'^C\d+', p, re.I):
            role = 'Card'
        elif re.match(r'^P\d+', p, re.I):
            role = 'Port'
        elif re.match(r'^(CH|CHAN)\d+', p, re.I):
            role = 'Channel'
        else:
            role = 'Node'
        levels.append({'role': role, 'label': p})
    return levels


# ── top-level parse ───────────────────────────────────────────────────────────
def has_io(text):
    """Cheap check: does this export contain a physical-I/O hardware layer?"""
    return ('DEVICENET_DEVICE ' in text or 'PORT_ASSIGNMENT' in text)


def parse_io(text):
    """Parse every hardware device across supported device types into one list, plus
    a signal-tag index and the controller set. Empty if no hardware present."""
    devices = _parse_devicenet(text)
    # (future) devices += _parse_fieldbus(text); _parse_charm(text); ...
    signals_by_tag = {}
    controllers = {}
    for d in devices:
        ctrl = d['levels'][0]['label'] if d['levels'] else ''
        if ctrl:
            controllers.setdefault(ctrl, 0)
            controllers[ctrl] += 1
        for s in d['signals']:
            if s['tag']:
                signals_by_tag[s['tag']] = {
                    'device': d['device'], 'path': d['path'],
                    'signal': s['signal'], 'direction': s['direction'],
                    'desc': s['desc'], 'address': d['address'],
                }
    return {
        'devices': devices,
        'signals_by_tag': signals_by_tag,
        'controllers': sorted(controllers.items()),
        'count': len(devices),
        'signal_count': len(signals_by_tag),
    }


# ── hierarchy tree ────────────────────────────────────────────────────────────
def build_tree(devices):
    """Nest devices into Controller -> I/O -> Card -> Port -> (device -> signals).
    Returns a list of controller nodes with nested children."""
    root = {}
    for d in devices:
        levels = d['levels']
        node = root
        leaf = None
        for lv in levels:
            key = lv['label']
            if key not in node:
                node[key] = {'_role': lv['role'], '_children': {}, '_devices': []}
            leaf = node[key]
            node = leaf['_children']
        if leaf is not None:
            leaf['_devices'].append(d)

    def to_list(d):
        out = []
        for label, sub in sorted(d.items()):
            if label.startswith('_'):
                continue
            node = {
                'label': label,
                'role': sub.get('_role', ''),
                'children': to_list(sub.get('_children', {})),
                'devices': [{'device': x['device'], 'desc': x['desc'],
                             'address': x['address'],
                             'signals': x['signals']}
                            for x in sub.get('_devices', [])],
            }
            out.append(node)
        return out

    return to_list(root)


# ── join to control modules ───────────────────────────────────────────────────
def join_to_modules(io, strat_text):
    """Match each hardware signal tag to the control module that references it in the
    strategy export. Returns {signal_tag: [module_tags...]} and coverage stats."""
    if not strat_text:
        return {'links': {}, 'linked': 0, 'unlinked': 0}
    links = {}
    linked = 0
    for tag in io.get('signals_by_tag', {}):
        # a module references the signal tag directly (in IO_IN/IO_OUT or a param)
        owners = _modules_referencing(strat_text, tag)
        if owners:
            links[tag] = owners
            linked += 1
    return {'links': links, 'linked': linked,
            'unlinked': io.get('signal_count', 0) - linked}


def _modules_referencing(text, tag):
    """Which MODULE_INSTANCE blocks mention this signal tag."""
    owners = []
    # find the tag, then the nearest enclosing MODULE_INSTANCE
    inst_starts = None
    for m in re.finditer(re.escape(tag), text):
        pos = m.start()
        hdr = None
        for im in re.finditer(r'MODULE_INSTANCE TAG="([^"]+)"', text[:pos]):
            hdr = im.group(1)
        if hdr and hdr not in owners:
            owners.append(hdr)
    return owners


def io_for_module(io, strat_text, module_tag):
    """The physical I/O points a given control module uses: for each signal tag the
    module references, the device + full hardware path + signal role."""
    if not strat_text:
        return []
    # find signal tags referenced within this module's block
    blk = _module_block(strat_text, module_tag)
    if not blk:
        return []
    out = []
    for tag, info in io.get('signals_by_tag', {}).items():
        if tag in blk:
            out.append({
                'signal_tag': tag,
                'device': info['device'],
                'path': info['path'],
                'signal': info['signal'],
                'direction': info['direction'],
                'address': info['address'],
                'desc': info['desc'],
                'levels': _split_path(info['path']),
            })
    return out


def _module_block(text, tag):
    m = re.search(r'MODULE_INSTANCE TAG="' + re.escape(tag) + r'"', text)
    if not m:
        return None
    start = m.start()
    nxt = text.find('\nMODULE_INSTANCE ', start + 1)
    return text[start:(nxt if nxt >= 0 else len(text))]


def device_suggestions(io, q, limit=20):
    """Autocomplete device/signal tags for the I/O explorer search."""
    q = (q or '').upper()
    hits = []
    for d in io.get('devices', []):
        if not q or q in d['device'].upper() or q in (d['desc'] or '').upper():
            hits.append(d['device'])
    for tag in io.get('signals_by_tag', {}):
        if q and q in tag.upper():
            hits.append(tag)
    seen = []
    for h in hits:
        if h not in seen:
            seen.append(h)
    return seen[:limit]
