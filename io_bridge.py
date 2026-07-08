"""I/O bridge — extracts the physical field I/O each control module wires to, so the
Control Network can show controller -> CM -> the I/O signals it uses (DeltaV's real
structure), while the CMs themselves live under Control Strategies.

A deployed MODULE_INSTANCE binds its I/O through ATTRIBUTE_INSTANCE entries named
like 'DC1$IO_IN_1' / 'AI1$IO_OUT_1' whose VALUE carries REF="//<signal>/<field>"
and CLASS=<DISCRETE_INPUT|DISCRETE_OUTPUT|ANALOG_INPUT|ANALOG_OUTPUT|...>. This maps
the module to the field devices/cards it reads and writes.

Additive: core/ untouched.
"""

import re

import db_parser

_CLASS_LABEL = {
    'DISCRETE_INPUT': 'DI', 'DISCRETE_OUTPUT': 'DO',
    'ANALOG_INPUT': 'AI', 'ANALOG_OUTPUT': 'AO',
    'PULSE_INPUT': 'PI', 'PULSE_COUNT_INPUT': 'PCI',
}


def _io_for_block(blk):
    io = []
    seen = set()
    for am in re.finditer(
            r'ATTRIBUTE_INSTANCE\s+NAME="([^"]*IO_(?:IN|OUT)[^"]*)"\s*\{\s*VALUE\s*\{([^}]*)\}', blk):
        name, body = am.group(1), am.group(2)
        ref = re.search(r'REF="([^"]*)"', body)
        cls = re.search(r'CLASS=(\w+)', body)
        if not ref or not ref.group(1).strip():
            continue
        signal = ref.group(1).strip().lstrip('/')
        # signal looks like 'FP005-ZSC-001/FIELD_VAL_D' — the tag is the first segment
        sig_tag = signal.split('/')[0]
        port = name.split('$')[-1]
        direction = 'in' if 'IO_IN' in name else 'out'
        klass = cls.group(1) if cls else ''
        key = (port, signal)
        if key in seen:
            continue
        seen.add(key)
        io.append({
            'port': port, 'signal': signal, 'signal_tag': sig_tag,
            'direction': direction, 'class': klass,
            'kind': _CLASS_LABEL.get(klass, klass or '?'),
        })
    return io


def io_by_module(text, tags=None):
    """Return {module_tag: [ {port, signal, signal_tag, direction, class, kind} ]}
    for the given tags (or all MODULE_INSTANCE blocks if tags is None)."""
    out = {}
    want = set(tags) if tags is not None else None
    for m in re.finditer(r'MODULE_INSTANCE\s+TAG="([^"]+)"', text):
        tag = m.group(1)
        if want is not None and tag not in want:
            continue
        try:
            blk = db_parser.extract_block(text, text.index('{', m.start()))
        except Exception:
            continue
        io = _io_for_block(blk)
        if io:
            out[tag] = io
    return out


def flat_io_signals(text, controllers=None, module_controller=None):
    """Flat list of every field I/O signal wired by any module, one row per signal:
    [{signal, signal_tag, kind, direction, module, controller}]. This is the flat
    Control Network view (no CM grouping) — each physical signal with the CM that
    uses it as a column, filterable/sortable in the UI."""
    mod_ctrl = dict(module_controller or {})
    if controllers and not mod_ctrl:
        for cn, tags in controllers.items():
            for t in tags:
                mod_ctrl[t] = cn
    io_map = io_by_module(text)
    rows = []
    for mod, io in io_map.items():
        ctrl = mod_ctrl.get(mod, '')
        for pt in io:
            kind = pt['kind']
            if kind == '?' or not kind:
                # no CLASS token — infer coarse direction label from the port name
                kind = 'DO' if pt['direction'] == 'out' else 'DI'
            rows.append({
                'signal': pt['signal'], 'signal_tag': pt['signal_tag'],
                'kind': kind, 'direction': pt['direction'],
                'port': pt['port'], 'module': mod,
                'controller': ctrl or '(unassigned)',
                'class': pt['class'],
            })
    rows.sort(key=lambda r: (r['controller'], r['signal_tag']))
    return rows


def io_summary_by_controller(text, controllers, module_controller=None):
    """Aggregate I/O per controller: {controller: {'modules': {tag: [io...]},
    'counts': {'AI':n,'DI':n,'AO':n,'DO':n,'other':n,'total':n}}}. Only modules that
    actually wire field I/O are included; a controller with none is still present
    with zero counts so the tree can show it."""
    all_tags = set()
    for cn, tags in controllers.items():
        all_tags.update(tags)
    io_map = io_by_module(text, all_tags)
    out = {}
    for cn, tags in controllers.items():
        mods = {}
        counts = {'AI': 0, 'DI': 0, 'AO': 0, 'AO': 0, 'DO': 0, 'other': 0, 'total': 0}
        for t in tags:
            io = io_map.get(t)
            if not io:
                continue
            mods[t] = io
            for pt in io:
                k = pt['kind']
                if k in ('AI', 'DI', 'AO', 'DO'):
                    counts[k] += 1
                else:
                    counts['other'] += 1
                counts['total'] += 1
        out[cn] = {'modules': mods, 'counts': counts}
    return out


# ── DeviceNet hardware view (integrates the standalone io_parser) ────────────────
def build_devicenet_html(text):
    """Render a DeviceNet hardware download (DEVICENET_DEVICE records) as a
    Controller -> Card -> Port -> Device tree with each device's signals. Returns
    '' when the export carries no DeviceNet data, so callers can gate cleanly.

    The io_parser module has long parsed these records; this bridge finally surfaces
    them in the explorer without touching core.
    """
    import html as _h
    try:
        import io_parser
    except Exception:
        return ''
    if not io_parser.is_io_export(text):
        return ''
    try:
        devices = io_parser.parse_io_devices(text)
    except Exception:
        return ''
    if not devices:
        return ''
    tree = io_parser.io_tree(devices)

    def esc(s):
        return _h.escape(str(s if s is not None else ''))

    total_sig = sum(len(d.get('signals', [])) for d in devices)
    parts = ['<div class="io-dnet">']
    parts.append(
        f'<div class="io-dnet-summary">{len(devices)} DeviceNet device(s) across '
        f'{len(tree)} controller(s), {total_sig} signal(s).</div>')

    for ctrl in sorted(tree):
        cards = tree[ctrl]
        ndev = sum(len(ds) for card in cards.values() for ds in card.values())
        parts.append('<div class="io-info-card io-collapse">')
        parts.append(f'<h4>Controller {esc(ctrl)} '
                     f'<span class="io-sub">{ndev} device(s)</span></h4>')
        for card in sorted(cards):
            ports = cards[card]
            parts.append(f'<div class="io-card-grp"><div class="io-card-h">Card {esc(card)}</div>')
            for port in sorted(ports):
                devs = ports[port]
                parts.append(f'<div class="io-port-grp"><div class="io-port-h">Port {esc(port)} '
                             f'<span class="io-sub">{len(devs)} device(s)</span></div>')
                for d in sorted(devs, key=lambda x: x.get('address', '')):
                    parts.append(_device_block(d, esc))
                parts.append('</div>')
            parts.append('</div>')
        parts.append('</div>')
    parts.append('</div>')
    return ''.join(parts)


def _device_block(d, esc):
    sigs = d.get('signals', [])
    head = (f'<div class="io-dev"><div class="io-dev-h">'
            f'<b>{esc(d.get("name"))}</b> '
            f'<span class="io-dev-addr">node {esc(d.get("address"))}</span> '
            f'<span class="io-sub">{esc(d.get("model") or d.get("device_type"))}</span></div>')
    meta = (f'<div class="io-dev-meta">{esc(d.get("description"))}'
            f'{" · " + esc(d.get("eds_desc")) if d.get("eds_desc") else ""}'
            f' · in {esc(d.get("input_size") or "0")}B / out {esc(d.get("output_size") or "0")}B</div>')
    if sigs:
        rows = ['<table class="io-sig-tbl"><thead><tr>'
                '<th>Signal</th><th>Dir</th><th>Type</th><th>Tag</th>'
                '<th>Byte.Bit</th><th>Description</th></tr></thead><tbody>']
        for s in sigs:
            bb = f'{esc(s.get("byte") or "0")}.{esc(s.get("bit") or "0")}'
            rows.append(
                f'<tr><td>{esc(s.get("name"))}</td><td>{esc(s.get("direction"))}</td>'
                f'<td>{esc(s.get("type"))}</td><td class="io-tag">{esc(s.get("dst"))}</td>'
                f'<td>{bb}</td><td>{esc(s.get("description"))}</td></tr>')
        rows.append('</tbody></table>')
        table = ''.join(rows)
    else:
        table = '<div class="io-sub">No signals.</div>'
    return head + meta + table + '</div>'
