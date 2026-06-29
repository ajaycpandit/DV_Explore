"""
sfc_expr_fix.py — bridge patch (Option 3): repair truncated SFC transition
expressions in the explorer WITHOUT editing core/.

The converter's core parser (core/fhx_app.py parse_sfc) extracts a transition's
EXPRESSION with the regex  EXPRESSION equals "([^ quote ]*)"  which stops at the
FIRST embedded double-quote. DeltaV transition expressions routinely compare
against a string literal (an empty-string comparison, written with FHX-doubled
quotes), so any such transition is truncated at the comparison operator in the
explorer's displayed SFC and detail table.

core/ must stay byte-identical, so we fix this at the data layer: after the core
parser produces the per-phase `blocks`, we re-extract every transition's
EXPRESSION from the raw FHX with a quote-aware regex (FHX doubles a literal " as
""), and overwrite the truncated value on each block's transitions[tn]['expression'].
build_sfc_html then renders the corrected expressions unchanged.

This is the same correct extraction proven in sim_run.fixed_transition_exprs;
centralising it here so both the explorer view and the simulator share one source
of truth.
"""

import re
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.environ.get('FHX_CORE_DIR', os.path.join(_HERE, 'core'))
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

import db_parser  # noqa: E402  (extract_block / block walking)

# Quote-aware EXPRESSION capture: a run of (non-quote | doubled-quote) chars.
# This is the corrected counterpart to core's EXPRESSION="([^"]*)".
_EXPR_RE = re.compile(r'EXPRESSION="((?:[^"]|"")*)"', re.DOTALL)
_TRANS_RE = re.compile(r'TRANSITION\s+NAME="([^"]+)"\s*\{')


def _undouble(s):
    """FHX escapes a literal " inside a quoted string by doubling it (""). The
    core parser never reaches these (it truncates first), so there's no existing
    display convention to match. For the explorer we un-double to the natural
    form — e.g. the doubled empty-string compare becomes  != ""  — which is what
    an engineer reading the SFC expects, and matches how the sim tokenizer
    normalises the same text. Surrounding whitespace is stripped to match core's
    .strip()."""
    return s.replace('""', '"').strip()


def quote_aware_transition_exprs(sfc_block):
    """{transition_name: full_expression} from one SFC block's raw text,
    extracting EXPRESSION with the quote-aware regex."""
    out = {}
    for tm in _TRANS_RE.finditer(sfc_block):
        tb = db_parser.extract_block(sfc_block, tm.end() - 1)
        m = _EXPR_RE.search(tb)
        out[tm.group(1)] = _undouble(m.group(1)) if m else ''
    return out


def _find_block_sfc(text, block_name):
    """Locate a named block in the raw FHX and return its SFC_ALGORITHM body,
    or None if the block has no SFC. Tries FUNCTION_BLOCK_DEFINITION first (the
    common case for RUN/HOLD/etc. sequences), then a generic NAME match."""
    m = re.search(
        r'FUNCTION_BLOCK_DEFINITION\s+NAME="' + re.escape(block_name) + r'"[^{]*\{',
        text)
    if not m:
        m = re.search(r'NAME="' + re.escape(block_name) + r'"[^{]*\{', text)
    if not m:
        return None
    blk = db_parser.extract_block(text, m.end() - 1)
    sm = re.search(r'SFC_ALGORITHM\s*\{', blk)
    if not sm:
        return None
    return db_parser.extract_block(blk, sm.end() - 1)


def repair_phase_blocks(text, blocks):
    """In-place: for every block in `blocks` that carries a 'transitions' dict,
    re-extract its transition expressions quote-aware from the raw FHX `text`
    and overwrite any that the core parser truncated. Returns the same `blocks`
    plus a count of repairs (for logging/verification). Safe no-op if a block's
    SFC can't be located.
    """
    repaired = 0
    for bname, b in blocks.items():
        if not (isinstance(b, dict) and b.get('transitions')):
            continue
        sfc = _find_block_sfc(text, bname)
        if not sfc:
            continue
        fixed = quote_aware_transition_exprs(sfc)
        for tn, td in b['transitions'].items():
            if not isinstance(td, dict):
                continue
            new = fixed.get(tn)
            if new is None:
                continue
            old = (td.get('expression', '') or '').strip()
            if new and new != old:
                td['expression'] = new
                repaired += 1
    return blocks, repaired
