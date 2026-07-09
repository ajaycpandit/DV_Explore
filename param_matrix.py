"""Parameter Matrix — bulk CM/EM parameter export / compare / edit / re-import.

Native DeltaV can import/export module parameters, but comparing the SAME parameter
across every deployed instance of a class (e.g. all 28 two-state valves' trip times,
confirm times, interlock expressions) means opening each module one at a time. This
tool lays every instance of a class out as a grid: rows = parameters, columns =
instances. You can immediately see where one instance deviates from its siblings,
edit values in bulk, and export a minimal-diff FHX to re-import into DeltaV.

Everything here is read-mostly parsing plus a minimal-diff writer; core/ is untouched.

Public API:
  list_classes(text)                 -> [{class, count, kind}]  (classes worth a matrix)
  build_matrix(text, cls)            -> {class, instances[], params[], values{}, ...}
  apply_edits(text, edits)           -> (new_text, applied, skipped)  minimal-diff FHX
"""

import re


_INSTANCE_RE = re.compile(
    r'MODULE_INSTANCE TAG="([^"]+)" PLANT_AREA="([^"]*)" MODULE_CLASS="([^"]+)"',
)


def _iter_instances(text):
    """Yield (tag, area, cls, block_text) for every deployed MODULE_INSTANCE."""
    # split on the instance header; each block runs until the next top-level instance
    matches = list(_INSTANCE_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield m.group(1), m.group(2), m.group(3), text[start:end]


def _attr_values(block):
    """Extract {attr_name: (raw_cv, value_str)} from an instance block.
    Handles ATTRIBUTE_INSTANCE ... { VALUE { CV=... } } and ... { CV=... }."""
    out = {}
    for am in re.finditer(
            r'ATTRIBUTE_INSTANCE NAME="([^"]+)"\s*\{(.*?)\n\s*\}', block, re.DOTALL):
        name, body = am.group(1), am.group(2)
        cv = re.search(r'CV=("(?:[^"\\]|\\.)*"|[^\s}]+)', body)
        if cv:
            raw = cv.group(1)
            val = raw[1:-1] if raw.startswith('"') and raw.endswith('"') else raw
            out[name] = (raw, val)
    return out


def list_classes(text, min_instances=2):
    """Classes with >= min_instances deployed instances — the ones a matrix helps with.
    Returns [{class, count}] sorted by count desc."""
    counts = {}
    for _tag, _area, cls, _blk in _iter_instances(text):
        counts[cls] = counts.get(cls, 0) + 1
    rows = [{'class': c, 'count': n} for c, n in counts.items() if n >= min_instances]
    rows.sort(key=lambda r: (-r['count'], r['class']))
    return rows


def build_matrix(text, cls, param_filter=None):
    """Build the instances x parameters matrix for one class.

    Returns:
      {
        'class': cls,
        'instances': [{tag, area}...],            # columns
        'params': [{name, present, distinct}...], # rows (with how many instances have
                                                  #   it and how many distinct values)
        'values': { param: { tag: value } },      # the grid
        'defaults': { param: most_common_value }, # the modal value (class "norm")
      }
    """
    insts = []
    per = {}   # tag -> {param: value}
    for tag, area, c, blk in _iter_instances(text):
        if c != cls:
            continue
        insts.append({'tag': tag, 'area': area})
        per[tag] = {k: v[1] for k, v in _attr_values(blk).items()}
    insts.sort(key=lambda i: i['tag'])

    # union of all params across these instances
    all_params = set()
    for tag in per:
        all_params.update(per[tag].keys())
    if param_filter:
        pf = param_filter.lower()
        all_params = {p for p in all_params if pf in p.lower()}

    values = {}
    params = []
    defaults = {}
    for p in sorted(all_params):
        col = {}
        present = 0
        seen = {}
        for inst in insts:
            tag = inst['tag']
            if p in per.get(tag, {}):
                v = per[tag][p]
                col[tag] = v
                present += 1
                seen[v] = seen.get(v, 0) + 1
        values[p] = col
        # modal (most common) value = the class "norm"; distinct count flags variance
        modal = max(seen.items(), key=lambda kv: kv[1])[0] if seen else ''
        defaults[p] = modal
        params.append({
            'name': p,
            'present': present,
            'total': len(insts),
            'distinct': len(seen),
            'group': _param_group(p),
        })
    # sort params: most-varying first (those are the interesting ones), then by name
    params.sort(key=lambda r: (-r['distinct'], r['name']))
    return {
        'class': cls,
        'instances': insts,
        'params': params,
        'values': values,
        'defaults': defaults,
    }


def _param_group(name):
    """Bucket a parameter name for grouping in the UI."""
    n = name.upper()
    if n.startswith('ILK') or 'INTERLOCK' in n:
        return 'Interlocks'
    if '$IO_' in n or n.endswith('_IN_1') or n.endswith('_OUT_1'):
        return 'I/O'
    if 'TIME' in n or 'DELAY' in n or 'TRIP' in n:
        return 'Timing'
    if 'DESC' in n:
        return 'Descriptions'
    if 'ALM' in n or 'ALARM' in n or 'MASK' in n:
        return 'Alarms'
    if 'MODE' in n:
        return 'Mode'
    return 'Other'


def apply_edits(text, edits):
    """Apply {tag: {param: new_value}} edits to the FHX, changing ONLY the matching
    CV= tokens (minimal diff, Part 11-friendly). Returns (new_text, applied, skipped).

    We locate each instance block, then within it the specific ATTRIBUTE_INSTANCE's
    VALUE/CV, and replace just that token. Numeric values are written bare; strings
    keep their quoting.
    """
    applied, skipped = [], []
    # work on a mutable copy; edit instance-by-instance using span offsets
    matches = list(_INSTANCE_RE.finditer(text))
    spans = {}
    for i, m in enumerate(matches):
        tag = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spans[tag] = (start, end)

    # build replacements as (abs_start, abs_end, new_str), then apply right-to-left
    repls = []
    for tag, params in edits.items():
        if tag not in spans:
            for p in params:
                skipped.append({'tag': tag, 'param': p, 'reason': 'instance not found'})
            continue
        s, e = spans[tag]
        block = text[s:e]
        for param, new_val in params.items():
            # find this attribute's CV within the block
            am = re.search(
                r'(ATTRIBUTE_INSTANCE NAME="' + re.escape(param) +
                r'"\s*\{.*?CV=)("(?:[^"\\]|\\.)*"|[^\s}]+)', block, re.DOTALL)
            if not am:
                skipped.append({'tag': tag, 'param': param,
                                'reason': 'parameter not present on instance'})
                continue
            old_tok = am.group(2)
            new_tok = _fmt_cv(new_val, old_tok)
            if new_tok == old_tok:
                continue  # no change
            abs_start = s + am.start(2)
            abs_end = s + am.end(2)
            repls.append((abs_start, abs_end, new_tok))
            applied.append({'tag': tag, 'param': param,
                            'old': _unquote(old_tok), 'new': _unquote(new_tok)})
    # apply right-to-left so offsets stay valid
    repls.sort(key=lambda r: -r[0])
    new_text = text
    for start, end, s in repls:
        new_text = new_text[:start] + s + new_text[end:]
    return new_text, applied, skipped


def _fmt_cv(val, old_tok):
    """Format a new CV token, matching the old token's quoting style."""
    s = str(val)
    was_quoted = old_tok.startswith('"')
    if was_quoted:
        return '"' + s.replace('"', '\\"') + '"'
    # bare (numeric/enum) — keep bare if it looks numeric, else quote to be safe
    if re.match(r'^-?\d+(\.\d+)?$', s) or re.match(r'^[A-Za-z0-9_:%\-.]+$', s):
        return s
    return '"' + s.replace('"', '\\"') + '"'


def _unquote(tok):
    return tok[1:-1] if tok.startswith('"') and tok.endswith('"') else tok
