"""Cross-reference bridge — builds a reverse index of where each tag/class is used,
so the UI can answer "where is this module referenced?" without an N×N rescan.

Two kinds of reference are covered:
  1. member-of   : a CM/EM class used as a member inside a parent EM (already available
                   in catalog['class_used_by']; surfaced here uniformly).
  2. logic-ref   : a deployed tag referenced inside another module's expressions/wiring,
                   e.g. '//FP005-HV-001/PV.CV' appearing in FP_CIP_INIT's transition
                   logic. Built with a single pass: find every top-level owning block's
                   extent once, then attribute each //TAG/ reference to the block it
                   falls inside.

Additive: core/ untouched.
"""

import re

# top-level blocks that can *contain* references and that we attribute references to
_OWNER_RE = re.compile(
    r'^(MODULE_INSTANCE|MODULE_CLASS|BATCH_EQUIPMENT_PHASE_CLASS|FUNCTION_BLOCK_DEFINITION)'
    r'\s+(NAME|TAG)="([^"]+)"', re.M)

# a reference to another object's parameter: '//TAG/PATH' (single-quoted in expressions)
_REF_RE = re.compile(r"//([A-Za-z0-9_\-]+)/")


def _owner_spans(text):
    """Return a sorted list of (start, end, kind, name) for each top-level owning block."""
    owners = []
    matches = list(_OWNER_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        kw = m.group(1)
        name = m.group(3)
        kind = {'MODULE_INSTANCE': 'module', 'MODULE_CLASS': 'class',
                'BATCH_EQUIPMENT_PHASE_CLASS': 'phase',
                'FUNCTION_BLOCK_DEFINITION': 'fbdef'}.get(kw, kw.lower())
        owners.append((start, end, kind, name))
    return owners


def build_logic_xref(text):
    """One-pass reverse index of logic references:
    { referenced_tag: [ {owner, kind, count} ] }  (owner = the module/phase that
    references it). Self-references (a module referencing its own tag) are excluded."""
    owners = _owner_spans(text)
    xref = {}
    for (start, end, kind, owner) in owners:
        seg = text[start:end]
        seen = {}
        for rm in _REF_RE.finditer(seg):
            tag = rm.group(1)
            if tag == owner:
                continue  # self-reference
            seen[tag] = seen.get(tag, 0) + 1
        for tag, cnt in seen.items():
            xref.setdefault(tag, []).append({'owner': owner, 'kind': kind, 'count': cnt})
    # sort each list by descending count then name for stable, useful display
    for tag in xref:
        xref[tag].sort(key=lambda r: (-r['count'], r['owner']))
    return xref


# ── exact-use context (lazy; computed on demand for one owner→tag pair) ──
# We attribute each //TAG/ reference to the nearest enclosing *labelled* sub-block so
# the UI can show "block · action · expression". Labels we recognise, innermost-first:
_CTX_LABEL_RE = re.compile(
    r'(STEP|TRANSITION|ACTION|ALGORITHM|ATTRIBUTE_INSTANCE|FUNCTION_BLOCK|'
    r'PARAMETER|WIRE|EXPRESSION_ELEMENT)\s+NAME="([^"]+)"'
)
# the actual line/assignment carrying the reference
_LINE_KEYS = ('EXPRESSION', 'CONFIRM_EXPRESSION', 'REF', 'DESCRIPTION')


def _line_containing(seg, pos):
    """Return the single logical FHX line (a KEY="....") that contains offset `pos`."""
    ls = seg.rfind('\n', 0, pos)
    le = seg.find('\n', pos)
    if ls < 0:
        ls = 0
    if le < 0:
        le = len(seg)
    return seg[ls:le].strip()


def _enclosing_labels(seg, pos):
    """Walk brace depth backwards from `pos` to find the nearest labelled ancestor
    blocks (innermost first). Returns a list of (kind, name)."""
    # Find all label matches before pos with their brace opening, track which are still
    # "open" (their matching close-brace is after pos).
    labels = []
    for m in _CTX_LABEL_RE.finditer(seg, 0, pos):
        # the block body opens at the next '{' after the label
        ob = seg.find('{', m.end())
        if ob < 0 or ob > pos:
            continue
        # is pos inside this block? scan braces from ob
        depth = 0
        close = -1
        i = ob
        n = len(seg)
        while i < n:
            c = seg[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    close = i
                    break
            i += 1
        if close == -1 or close > pos:
            labels.append((m.group(1), m.group(2), ob))
    # innermost = largest opening offset
    labels.sort(key=lambda x: -x[2])
    return [(k, nm) for (k, nm, _ob) in labels]


def reference_uses(text, target_tag, owner_name, logic_xref=None, max_uses=40):
    """For one (owner, target) pair, return the exact use sites:
    [ { context: [ 'ACTION A11', ... ], description, line } ].
    `owner_name` is the module/phase that references `target_tag`. Absolute //TAG/ only."""
    owners = {o[3]: o for o in _owner_spans(text)}
    o = owners.get(owner_name)
    if not o:
        return []
    start, end = o[0], o[1]
    seg = text[start:end]
    ref_pat = re.compile(r'//' + re.escape(target_tag) + r'/')
    uses = []
    seen_lines = set()
    for rm in ref_pat.finditer(seg):
        pos = rm.start()
        line = _line_containing(seg, pos)
        # de-dup identical lines (same assignment repeated is noise)
        if line in seen_lines:
            continue
        seen_lines.add(line)
        labels = _enclosing_labels(seg, pos)
        # a readable description: prefer a DESCRIPTION= sibling of the innermost block
        desc = ''
        if labels:
            # search the innermost block body for a DESCRIPTION
            dm = re.search(r'DESCRIPTION="([^"]*)"',
                           seg[max(0, pos - 400):pos + 400])
            if dm:
                desc = dm.group(1)
        # Pull the tightest meaningful fragment carrying the reference. Prefer an
        # EXPRESSION="..."/CONFIRM_EXPRESSION="..."/REF="..." value on the line.
        key, val = '', line
        found = False
        for k in ('CONFIRM_EXPRESSION', 'EXPRESSION', 'REF'):
            em = re.search(k + r'="([^"]*)"', line)
            if em:
                key, val, found = k, em.group(1).strip(), True
                break
        if not found:
            km = re.match(r'([A-Z_]+)\s*=\s*(.*)$', line)
            if km:
                key, val = km.group(1), km.group(2).strip().strip('"')
        ctx = [f'{k} {nm}' for (k, nm) in labels[:4]]
        uses.append({'context': ctx, 'key': key, 'line': val, 'description': desc})
        if len(uses) >= max_uses:
            break
    return uses


def all_reference_uses(text, target_tag, logic_xref=None, max_per_owner=25):
    """Every logic use-site of `target_tag`, grouped by owner, for the floating
    references window. Returns [ {owner, owner_kind, uses:[...] } ] ordered by
    reference count (heaviest first)."""
    if logic_xref is None:
        logic_xref = build_logic_xref(text)
    refs = logic_xref.get(target_tag, [])
    # figure out each owner's object kind (phase / em / cm / deployed) for navigation
    groups = []
    for r in sorted(refs, key=lambda x: -x.get('count', 0)):
        owner = r.get('owner')
        if not owner:
            continue
        uses = reference_uses(text, target_tag, owner, logic_xref=logic_xref,
                              max_uses=max_per_owner)
        groups.append({'owner': owner, 'count': r.get('count', len(uses)),
                       'kind': r.get('kind', ''), 'uses': uses})
    return groups


def references_for(tag, logic_xref, class_used_by=None):
    """Assemble both reference kinds for one tag/class:
    { 'member_of': [ {parent, instance} ], 'logic_refs': [ {owner, kind, count} ] }."""
    out = {'member_of': [], 'logic_refs': []}
    if class_used_by and tag in class_used_by:
        out['member_of'] = class_used_by[tag]
    if tag in logic_xref:
        out['logic_refs'] = logic_xref[tag]
    return out
