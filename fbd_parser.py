"""
Function Block Diagram (FBD) parser.

Control Modules and composites in DeltaV are function block diagrams: named
function blocks placed at X/Y coordinates, connected by wires (source port ->
destination port). DeltaV stores the full layout, so we render what it laid out
rather than computing a layout ourselves.

Parses a MODULE_CLASS / FUNCTION_BLOCK_TEMPLATE block into:
  - blocks:  name, definition (type), x, y, w, h, description, is_composite
  - wires:   source (block/port or terminal), destination, + parsed endpoints
  - terminals: module-level I/O parameters referenced by wires
"""

import re


def _extract_block(text, start):
    i = text.index('{', start)
    depth = 0
    s = i
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[s:i + 1]
        i += 1
    return ''


# Basic DeltaV function block types (everything else is treated as a composite)
_BASIC_FB = {
    'PID', 'PIDWCALARM', 'AI', 'AO', 'DI', 'DO', 'AT', 'CND', 'ACT', 'CALC',
    'ALMWCALARM', 'BDE', 'CAV', 'INTEG', 'FILTER', 'LIM', 'SCLR', 'SPLTR',
    'NDE', 'OR', 'AND', 'NOT', 'XOR', 'RAMP', 'DT', 'LL', 'RATE', 'SGCR',
    'TRIG', 'SEL', 'MULDIV', 'ADD', 'SUB', 'BIASGN', 'CHAR', 'CTD', 'CTU',
}


def parse_fbd(block_text):
    """Parse one module/composite block's FBD content."""
    blocks = []
    for m in re.finditer(r'FUNCTION_BLOCK\s+NAME="([^"]+)"\s+DEFINITION="([^"]+)"', block_text):
        fb = _extract_block(block_text, m.end())
        rect = re.search(r'RECTANGLE=\s*\{\s*X=(-?\d+)\s+Y=(-?\d+)\s+H=(\d+)\s+W=(\d+)', fb)
        desc = re.search(r'DESCRIPTION="([^"]*)"', fb)
        defn = m.group(2)
        x, y, h, w = (int(rect.group(1)), int(rect.group(2)),
                      int(rect.group(3)), int(rect.group(4))) if rect else (0, 0, 56, 130)
        blocks.append({
            'name': m.group(1),
            'definition': defn,
            'x': x, 'y': y, 'w': w, 'h': h,
            'description': desc.group(1).strip() if desc else '',
            'is_composite': defn not in _BASIC_FB,
        })

    wires = []
    for m in re.finditer(r'WIRE\s+SOURCE="([^"]+)"\s+DESTINATION="([^"]+)"', block_text):
        src, dst = m.group(1), m.group(2)
        wires.append({
            'source': src, 'destination': dst,
            'src_block': src.split('/')[0] if '/' in src else None,
            'src_port': src.split('/')[1] if '/' in src else src,
            'dst_block': dst.split('/')[0] if '/' in dst else None,
            'dst_port': dst.split('/')[1] if '/' in dst else dst,
        })

    # terminals = wire endpoints that are NOT a block (module-level I/O)
    block_names = {b['name'] for b in blocks}
    terminals = set()
    for w in wires:
        if w['src_block'] is None:
            terminals.add(w['source'])
        if w['dst_block'] is None:
            terminals.add(w['destination'])
        # a src/dst that names a non-existent block is also a terminal
        if w['src_block'] and w['src_block'] not in block_names:
            terminals.add(w['src_block'])
        if w['dst_block'] and w['dst_block'] not in block_names:
            terminals.add(w['dst_block'])

    return {'blocks': blocks, 'wires': wires, 'terminals': sorted(terminals)}


def parse_module_fbd(text, module_name=None):
    """Find a MODULE_CLASS or FUNCTION_BLOCK_TEMPLATE by name (or the first one)
    and parse its FBD. Returns the fbd dict plus identity."""
    pat = r'(MODULE_CLASS|FUNCTION_BLOCK_TEMPLATE|FUNCTION_BLOCK_DEFINITION)\s+NAME="([^"]+)"'
    target = None
    if module_name is not None:
        for m in re.finditer(pat, text):
            if m.group(2) == module_name:
                target = m
                break
    else:
        # pick the object with the most function blocks (the real diagram, not a
        # referenced type definition like a bare AI/PID template)
        best = None
        best_n = -1
        for m in re.finditer(pat, text):
            blk = _extract_block(text, m.end())
            n = blk.count('FUNCTION_BLOCK NAME=')
            if n > best_n:
                best_n, best, target = n, blk, m
        if best_n <= 0:
            return None
    if not target:
        return None
    blk = _extract_block(text, target.end())
    fbd = parse_fbd(blk)
    desc = re.search(r'DESCRIPTION="([^"]*)"', blk[:400])
    fbd['name'] = target.group(2)
    fbd['kind'] = target.group(1)
    fbd['description'] = desc.group(1).strip() if desc else ''
    return fbd


def list_fbd_objects(text):
    """Return names of all modules/composites/composite-definitions that contain
    function blocks, so the explorer knows which objects have an FBD view.
    Includes FUNCTION_BLOCK_DEFINITION (nested composites like C_C_ML_V01)."""
    out = []
    seen = set()
    pat = r'(MODULE_CLASS|FUNCTION_BLOCK_TEMPLATE|FUNCTION_BLOCK_DEFINITION)\s+NAME="([^"]+)"'
    for m in re.finditer(pat, text):
        name = m.group(2)
        if name in seen:
            continue
        blk = _extract_block(text, m.end())
        if 'FUNCTION_BLOCK NAME=' in blk:
            seen.add(name)
            out.append({'name': name, 'kind': m.group(1),
                        'n_blocks': blk.count('FUNCTION_BLOCK NAME=')})
    return out
