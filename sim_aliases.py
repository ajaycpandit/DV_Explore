"""
sim_aliases.py — Item 10: resolve DeltaV unit-alias references.

Transition/action expressions reference other modules by ALIAS, written
'//#ALIAS#/<field>' (e.g. '//#COND_ACID#/PV.CV'). An alias is an indirection the
unit resolves to a real module at configuration time. DeltaV declares them as:

    ALIAS_DEFINITION NAME="COND_ACID" { DESCRIPTION="Acid Conductivity" ... }
    ALIAS_RESOLUTION NAME="COND_ACID" { VALUE { DESCRIPTION="Acid Conductivity"
                                                VALUE="046CIP723AI01" IGNORE=F } }

'#THISUNIT#' is the special self-reference (the unit the phase runs on).

This module extracts {alias: {desc, module}} so the simulator can LABEL a
reference like '//#COND_ACID#/PV.CV' as "COND_ACID -> 046CIP723AI01 (Acid
Conductivity)" instead of showing an opaque alias. It does not change evaluation
(the store key stays the alias form, which is what the logic uses); it only adds
human-resolvable metadata for display.
"""
import re
import sys

sys.path.insert(0, 'core')
import db_parser  # noqa: E402

_DEF_RE = re.compile(r'ALIAS_DEFINITION\s+NAME="([^"]+)"\s*\{')
_RES_RE = re.compile(r'ALIAS_RESOLUTION\s+NAME="([^"]+)"\s*\{')
_VALUE_RE = re.compile(r'VALUE="([^"]*)"')
_DESC_RE = re.compile(r'DESCRIPTION="([^"]*)"')


def resolve_aliases(text):
    """Return {alias_name: {'desc': str, 'module': str}} for every alias declared
    in the export. THISUNIT is added as a self-reference marker."""
    out = {}
    for m in _DEF_RE.finditer(text):
        blk = db_parser.extract_block(text, m.end() - 1)
        d = _DESC_RE.search(blk)
        out.setdefault(m.group(1), {})['desc'] = d.group(1) if d else ''
    for m in _RES_RE.finditer(text):
        blk = db_parser.extract_block(text, m.end() - 1)
        v = _VALUE_RE.search(blk)
        d = _DESC_RE.search(blk)
        rec = out.setdefault(m.group(1), {})
        rec['module'] = v.group(1) if v else ''
        if 'desc' not in rec or not rec['desc']:
            rec['desc'] = d.group(1) if d else ''
    # special self-reference
    out.setdefault('THISUNIT', {'desc': 'This unit (self)', 'module': '#THISUNIT#'})
    return out


def aliases_used(order, actions, trans):
    """Set of alias names actually referenced in this phase's logic (so we only
    ship metadata for aliases the operator will see)."""
    used = set()
    pat = re.compile(r'//#([A-Za-z0-9_]+)#/')
    for e in trans.values():
        used |= set(pat.findall(e or ''))
    for sn in order:
        for _q, a in actions.get(sn, []):
            used |= set(pat.findall(a or ''))
    return used
