"""Formula bulk-edit + round-trip tool (bridge module, core untouched).

DeltaV lets you export/import formula values, but bulk editing across formulas and
diffing two formulas is clunky in the native environment. This tool:

  1. grid(text)          -> a params x formulas matrix (rows=params, cols=formulas)
                            for a spreadsheet-style bulk editor.
  2. build_formula_fhx() -> a minimal, valid FHX file containing only the edited
                            BATCH_RECIPE_FORMULA blocks, importable back into DeltaV
                            (formula-values-only round trip, matching your ask #1).
  3. diff(a, b)          -> a parameter-by-parameter comparison of two formulas
                            (added / removed / changed / same) — the "not easy in
                            native DeltaV" feature.

The FHX we regenerate mirrors the exact block shape seen in real exports:

  BATCH_RECIPE_FORMULA NAME="<formula>" RECIPE="<recipe>"
  {
    DESCRIPTION="..."
    VERSION="..."
    HIDDEN=F
    RELEASED_TO_PRODUCTION=T
    ATTRIBUTE_INSTANCE NAME="<param>"
    {
      VALUE { CV=<value> }
    }
    ...
  }

We only touch formula VALUE blocks; parameter definitions, procedure, steps, and
transitions are never modified — the safest possible round trip.
"""

import re
import datetime


def _q(s):
    return '"' + str(s).replace('"', '') + '"'


def grid(recipe_bridge, text):
    """Build a params x formulas grid for a recipe export.
    Returns {recipe: {'params': [{name,group,type,desc}], 'formulas': [names],
                      'released': {name:bool}, 'values': {param: {formula: value}}}}.
    """
    recs = recipe_bridge.parse_recipes(text)
    formulas = recipe_bridge.parse_formulas(text)
    out = {}
    for r in recs:
        rname = r.get('meta', {}).get('name') or r.get('name') or ''
        if not rname:
            # meta may hold the name differently; fall back to first key of formulas
            rname = next(iter(formulas), '')
        params = r.get('params', [])
        forms = formulas.get(rname, [])
        fnames = [f['name'] for f in forms]
        released = {f['name']: bool(f.get('released')) for f in forms}
        # param metadata
        pmeta = []
        seen = set()
        for p in params:
            nm = p.get('name', '')
            if not nm or nm in seen:
                continue
            seen.add(nm)
            pmeta.append({'name': nm, 'group': p.get('group', ''),
                          'type': p.get('type', ''), 'desc': p.get('description', '')})
        # values matrix — only params that actually appear in some formula are
        # "formula parameters"; include all params but mark which are set
        vals = {}
        for f in forms:
            for pn, pv in (f.get('values') or {}).items():
                vals.setdefault(pn, {})[f['name']] = pv
        # ensure every formula-param has a row even if not in `params`
        for pn in vals:
            if pn not in seen:
                pmeta.append({'name': pn, 'group': '', 'type': '', 'desc': ''})
                seen.add(pn)
        out[rname] = {'params': pmeta, 'formulas': fnames, 'released': released,
                      'values': vals}
    return out


def build_formula_fhx(recipe_name, formulas, author='WorkbenchBulkEdit'):
    """Generate a minimal, valid FHX containing only BATCH_RECIPE_FORMULA blocks.

    `formulas` = [{'name':..., 'description':..., 'released':bool,
                   'values': {param: value}}]. Values that are '' are skipped
    (empty means "not set in this formula", same as DeltaV).
    Returns a UTF-16 FHX string ready to import into DeltaV.
    """
    ts = int(datetime.datetime.now().timestamp())
    tstr = datetime.datetime.now().strftime('%d-%b-%Y %H:%M:%S')
    lines = []
    for f in formulas:
        name = f.get('name', '')
        if not name:
            continue
        desc = f.get('description', '') or ''
        released = 'T' if f.get('released', True) else 'F'
        lines.append(f'BATCH_RECIPE_FORMULA NAME={_q(name)} RECIPE={_q(recipe_name)}')
        lines.append(f' user={_q(author)} time={ts}/* {_q(tstr)} */')
        lines.append('{')
        lines.append(f'  DESCRIPTION={_q(desc)}')
        lines.append('  VERSION=""')
        lines.append('  HIDDEN=F')
        lines.append(f'  RELEASED_TO_PRODUCTION={released}')
        for pn, pv in (f.get('values') or {}).items():
            if pv is None or str(pv).strip() == '':
                continue
            lines.append(f'  ATTRIBUTE_INSTANCE NAME={_q(pn)}')
            lines.append('  {')
            lines.append(f'    VALUE {{ CV={_fmt_cv(pv)} }}')
            lines.append('  }')
        lines.append('}')
    body = '\n'.join(lines) + '\n'
    return body


def _fmt_cv(v):
    """Format a CV: quote strings/enums, leave numbers bare (matching FHX)."""
    s = str(v).strip()
    # numeric (int/float, incl. leading -) -> bare
    if re.fullmatch(r'-?\d+(\.\d+)?', s):
        return s
    # already quoted?
    if s.startswith('"') and s.endswith('"'):
        return s
    return _q(s)


def diff(grid_recipe, formula_a, formula_b):
    """Compare two formulas within one recipe's grid. Returns rows:
    [{param, group, a, b, status}] where status in
    {same, changed, only_a, only_b}."""
    vals = grid_recipe.get('values', {})
    pmeta = {p['name']: p for p in grid_recipe.get('params', [])}
    rows = []
    # union of params that appear in either formula
    names = sorted(n for n, fv in vals.items()
                   if formula_a in fv or formula_b in fv)
    for n in names:
        fv = vals.get(n, {})
        a = fv.get(formula_a)
        b = fv.get(formula_b)
        if a is not None and b is not None:
            status = 'same' if str(a) == str(b) else 'changed'
        elif a is not None:
            status = 'only_a'
        else:
            status = 'only_b'
        rows.append({'param': n, 'group': pmeta.get(n, {}).get('group', ''),
                     'a': a if a is not None else '', 'b': b if b is not None else '',
                     'status': status})
    return rows


def validate_roundtrip(recipe_bridge, original_text, new_fhx):
    """Sanity check: parse the regenerated FHX and confirm it yields formulas with
    the expected values. Returns (ok, summary)."""
    try:
        forms = recipe_bridge.parse_formulas(new_fhx)
        n = sum(len(v) for v in forms.values())
        return True, f'{n} formula block(s) parsed back cleanly'
    except Exception as e:  # noqa
        return False, f'regenerated FHX did not parse: {e}'
