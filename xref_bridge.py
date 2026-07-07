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


def references_for(tag, logic_xref, class_used_by=None):
    """Assemble both reference kinds for one tag/class:
    { 'member_of': [ {parent, instance} ], 'logic_refs': [ {owner, kind, count} ] }."""
    out = {'member_of': [], 'logic_refs': []}
    if class_used_by and tag in class_used_by:
        out['member_of'] = class_used_by[tag]
    if tag in logic_xref:
        out['logic_refs'] = logic_xref[tag]
    return out
