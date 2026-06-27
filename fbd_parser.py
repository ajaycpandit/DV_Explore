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
    'PID', 'PIDWCALARM', 'AI', 'AIWCALARM', 'AO', 'DI', 'DO', 'AT', 'CND', 'ACT',
    'CALC', 'ALMWCALARM', 'BDE', 'CAV', 'INTEG', 'FILTER', 'LIM', 'SCLR', 'SPLTR',
    'NDE', 'PDE', 'EDC', 'DCC', 'RTLM', 'OR', 'AND', 'NOT', 'XOR', 'RAMP', 'DT',
    'LL', 'RATE', 'SGCR', 'TRIG', 'SEL', 'MULDIV', 'ADD', 'SUB', 'BIASGN', 'CHAR',
    'CTD', 'CTU', 'DCC', 'EDC', 'PDE',
}


# Expression-bearing blocks (ACT/CALC/CND/AT/DCC/...) store their structured-text
# logic in module-scope ATTRIBUTE_INSTANCE objects named "<block>/<attr>" whose
# VALUE holds TYPE=<kind> EXPRESSION="...". The expression string uses FHX quoting:
# embedded double-quotes are doubled ("" -> "). We read it with that rule.
_EXPR_ATTR_HEAD = re.compile(
    r'ATTRIBUTE_INSTANCE\s+NAME="([^"]+)"\s*\{\s*VALUE\s*\{\s*TYPE=(\w+)\s+EXPRESSION="')

# DCC condition groups (Device Control): attr prefix -> human label
_DCC_PREFIX = {'F_': 'Fail', 'I_': 'Interlock', 'P_': 'Permissive'}


def _read_fhx_string(text, pos):
    """Read an FHX double-quoted string whose opening quote has already been
    consumed (pos points at the first char of the content). Returns
    (decoded_string, index_after_closing_quote). A doubled quote ("") is an
    escaped literal quote; a lone quote terminates the string."""
    out = []
    i = pos
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            if i + 1 < n and text[i + 1] == '"':
                out.append('"')
                i += 2
                continue
            return ''.join(out), i + 1
        out.append(ch)
        i += 1
    return ''.join(out), i


def _expr_kind_label(attr, type_kw):
    """Friendly label for an expression attribute (uses DCC F_/I_/P_ grouping
    when present, else the declared TYPE)."""
    for pfx, lab in _DCC_PREFIX.items():
        if attr.startswith(pfx):
            return lab
    return (type_kw or '').replace('_', ' ').title() or 'Expression'


def parse_block_expressions(block_text):
    """Return {block_name: [{attr, kind, type, expression}, ...]} for every
    expression-bearing ATTRIBUTE_INSTANCE in the block. Generic across block
    types (ACT, CALC, CND, AT, DCC, ...): keyed off the "<block>/<attr>" name,
    not the block's definition, so new expression blocks need no special-casing."""
    out = {}
    for m in _EXPR_ATTR_HEAD.finditer(block_text):
        full, type_kw = m.group(1), m.group(2)
        block = full.split('/', 1)[0]
        attr = full.split('/', 1)[1] if '/' in full else full
        expr, _ = _read_fhx_string(block_text, m.end())
        expr = expr.strip()
        if not expr:
            continue
        out.setdefault(block, []).append({
            'attr': attr,
            'type': type_kw,
            'kind': _expr_kind_label(attr, type_kw),
            'expression': expr,
        })
    # stable order within a block: by attribute name (T_EXP1, T_EXP2, ...)
    for v in out.values():
        v.sort(key=lambda e: e['attr'])
    return out


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
    seen_wires = set()
    for m in re.finditer(r'WIRE\s+SOURCE="([^"]+)"\s+DESTINATION="([^"]+)"', block_text):
        src, dst = m.group(1), m.group(2)
        if (src, dst) in seen_wires:
            continue  # FHX can list each wire twice; keep one
        seen_wires.add((src, dst))
        wires.append({
            'source': src, 'destination': dst,
            'src_block': src.split('/')[0] if '/' in src else None,
            'src_port': src.split('/')[1] if '/' in src else src,
            'dst_block': dst.split('/')[0] if '/' in dst else None,
            'dst_port': dst.split('/')[1] if '/' in dst else dst,
        })

    # section frames (BOX_GRAPHIC) — the bordered functional regions in DeltaV
    frames = []
    for m in re.finditer(r'BOX_GRAPHIC\s*\{', block_text):
        fb = _extract_block(block_text, m.end() - 1)
        r = re.search(r'RECTANGLE=\s*\{\s*X=(-?\d+)\s+Y=(-?\d+)\s+H=(\d+)\s+W=(\d+)', fb)
        if r:
            frames.append({'x': int(r.group(1)), 'y': int(r.group(2)),
                           'h': int(r.group(3)), 'w': int(r.group(4))})

    # text labels (TEXT_GRAPHIC) — section titles + annotations. Keep concise
    # labels (section headers); skip the long help/revision/copyright text.
    labels = []
    for m in re.finditer(r'TEXT_GRAPHIC\s*\{\s*NAME="[^"]*"\s*ORIGIN=\s*\{\s*X=(-?\d+)\s+Y=(-?\d+)\s*\}\s*(?:END=\s*\{[^}]*\}\s*)?TEXT="([^"]*)"', block_text):
        txt = m.group(3).replace('\\n', ' ').replace('\\t', ' ').strip()
        # keep short, single-line-ish section labels; drop big paragraphs/headers
        if txt and len(txt) <= 28 and '=======' not in txt and '©' not in txt:
            labels.append({'x': int(m.group(1)), 'y': int(m.group(2)), 'text': txt})

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

    # attach structured-text expressions (ACT/CALC/CND/AT/DCC/...) to their blocks
    exprs = parse_block_expressions(block_text)
    for b in blocks:
        b['expressions'] = exprs.get(b['name'], [])

    return {'blocks': blocks, 'wires': wires, 'terminals': sorted(terminals),
            'frames': frames, 'labels': labels, 'expressions': exprs}


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
    fbd['interface'] = parse_module_interface(blk)
    desc = re.search(r'DESCRIPTION="([^"]*)"', blk[:400])
    fbd['name'] = target.group(2)
    fbd['kind'] = target.group(1)
    fbd['description'] = desc.group(1).strip() if desc else ''
    return fbd


def parse_module_interface(block_text):
    """Extract the module's external parameter interface: each module-level
    parameter (ATTRIBUTE) with its connection direction, group, and — where it
    maps to an internal block port — the reference target (from ATTRIBUTE_INSTANCE
    VALUE REF). This is the CM's I/O interface as shown in the DeltaV print."""
    # 1) module-level parameter declarations (ATTRIBUTE at module scope, with a
    #    CONNECTION). We detect these by the CONNECTION= keyword in the block.
    params = {}
    for m in re.finditer(r'ATTRIBUTE\s+NAME="([^"]+)"(?:\s+TYPE=(\w+))?[^\{]*\{', block_text):
        name = m.group(1)
        ptype = m.group(2) or ''
        blk = _extract_block(block_text, m.end() - 1)
        conn = re.search(r'CONNECTION=(\w+)', blk)
        if not conn:
            continue  # not an interface parameter
        grp = re.search(r'GROUP="([^"]*)"', blk)
        params[name] = {
            'name': name,
            'type': ptype.replace('_', ' ').title(),
            'connection': conn.group(1),
            'group': grp.group(1) if grp else '',
            'reference': '',
        }

    # 2) reference targets from ATTRIBUTE_INSTANCE NAME=".." { VALUE { REF=".." } }
    for m in re.finditer(r'ATTRIBUTE_INSTANCE\s+NAME="([^"]+)"\s*\{\s*VALUE\s*\{\s*REF="([^"]+)"', block_text):
        name, ref = m.group(1), m.group(2)
        if name in params:
            params[name]['reference'] = ref

    # order: inputs, outputs, internal, by group then name
    order = {'INPUT': 0, 'OUTPUT': 1, 'INTERNAL_SOURCE': 2, 'INTERNAL': 3}
    out = sorted(params.values(),
                 key=lambda p: (order.get(p['connection'], 9), p['group'], p['name']))
    return out


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
