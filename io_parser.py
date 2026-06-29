"""
Parse a DeltaV I/O / DeviceNet hardware download (DEVICENET_DEVICE records) into a
physical-network structure: Controller -> Card -> Port -> Device -> Signals (DSTs).

This is the hardware side that resolves a control module's I/O references: each
SIGNAL carries a DEVICE_SIGNAL_TAG (DST) that strategy logic wires to, plus the
physical channel path and byte/bit offset.
"""

import re
from db_parser import decode_fhx, extract_block


def is_io_export(text):
    return 'DEVICENET_DEVICE ' in text or 'DEVICE_SIGNAL_TAG=' in text


def parse_io_devices(text):
    # device-revision lookup (model / device class / EDS description)
    revs = {}
    for rm in re.finditer(r'DEVICENET_DEVICE_REVISION\s+([^\n]*)', text):
        hdr = rm.group(1)
        if 'MANUFACTURER' not in hdr:
            continue
        bstart = text.find('{', rm.end())
        if bstart < 0:
            continue
        man = re.search(r'MANUFACTURER="([^"]+)"', hdr)
        typ = re.search(r'DEVICENET_DEVICE_TYPE="([^"]+)"', hdr)
        rev = re.search(r'REVISION=(\d+)', hdr)
        blk = extract_block(text, bstart)
        key = (man.group(1) if man else '', typ.group(1) if typ else '', rev.group(1) if rev else '')
        revs[key] = {
            'model': (re.search(r'MODEL="([^"]+)"', blk) or _N()).group(1),
            'device_class': (re.search(r'DEVICE_TYPE="([^"]+)"', blk) or _N()).group(1),
            'eds_desc': (re.search(r'EDS_FILE_DESCRIPTION="([^"]+)"', blk) or _N()).group(1),
        }

    devices = []
    for dm in re.finditer(
            r'DEVICENET_DEVICE\s+NAME="([^"]+)"\s+MANUFACTURER="([^"]+)"'
            r'\s+DEVICENET_DEVICE_TYPE="([^"]+)"\s+REVISION=(\d+)', text):
        name, man, typ, rev = dm.group(1), dm.group(2), dm.group(3), dm.group(4)
        blk = extract_block(text, dm.end())
        desc = (re.search(r'DESCRIPTION="([^"]*)"', blk) or _N()).group(1)
        pa = re.search(r'PORT_ASSIGNMENT\s*\{\s*PATH="([^"]+)"\s*ADDRESS=(\d+)', blk)
        path = pa.group(1) if pa else ''
        addr = pa.group(2) if pa else ''
        parts = path.split('/') if path else []
        controller = parts[0] if len(parts) > 0 else ''
        subsystem = parts[1] if len(parts) > 1 else ''
        card = parts[2] if len(parts) > 2 else ''
        port = parts[3] if len(parts) > 3 else ''
        in_sz = (re.search(r'INPUT_SIZE=(\d+)', blk) or _N('')).group(1)
        out_sz = (re.search(r'OUTPUT_SIZE=(\d+)', blk) or _N('')).group(1)

        signals = []
        for sm in re.finditer(r'SIGNAL\s+NAME="([^"]+)"', blk):
            sb = extract_block(blk, sm.end())
            di = re.search(r'ATTRIBUTE\s+DIRECTION=(\w+)\s+TYPE=(\w+)', sb)
            signals.append({
                'name': sm.group(1),
                'dst': (re.search(r'DEVICE_SIGNAL_TAG="([^"]+)"', sb) or _N()).group(1),
                'description': (re.search(r'DESCRIPTION="([^"]*)"', sb) or _N()).group(1),
                'index': (re.search(r'INDEX=(\d+)', sb) or _N('')).group(1),
                'direction': di.group(1) if di else '',
                'type': (di.group(2) if di else '').replace('DEVICENET_SIGNAL_', ''),
                'byte': (re.search(r'BYTE_OFFSET=(\d+)', sb) or _N('')).group(1),
                'bit': (re.search(r'BIT_NUMBER=(\d+)', sb) or _N('')).group(1),
            })

        r = revs.get((man, typ, rev), {})
        devices.append({
            'name': name, 'manufacturer': man, 'device_type': typ, 'revision': rev,
            'model': r.get('model', ''), 'device_class': r.get('device_class', ''),
            'eds_desc': r.get('eds_desc', ''),
            'description': desc, 'path': path, 'address': addr,
            'controller': controller, 'subsystem': subsystem, 'card': card, 'port': port,
            'input_size': in_sz, 'output_size': out_sz, 'signals': signals,
        })
    return devices


def io_tree(devices):
    """Group devices into Controller -> Card -> Port -> [devices]."""
    tree = {}
    for d in devices:
        (tree.setdefault(d['controller'] or '(no controller)', {})
             .setdefault(d['card'] or '(no card)', {})
             .setdefault(d['port'] or '(no port)', [])
             .append(d))
    return tree


class _N:
    """Tiny stand-in so `(match or _N()).group(1)` is safe when a field is absent."""
    def __init__(self, v=''):
        self._v = v

    def group(self, _):
        return self._v
