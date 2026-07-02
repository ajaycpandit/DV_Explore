"""
sim_export.py — SIMULATOR (Option 1): export one phase's RUN-sequence logic as a
JSON payload the in-browser JS engine can step live. No server needed at runtime;
this runs once at build time (or could be wired into the explorer later).

Payload schema (everything the JS engine + renderer need):
  {
    phase, seq_key, order:[step,...],
    steps:   { step: {desc, x, y} },
    actions: { step: [ [qualifier, expr], ... ] },     # source order preserved
    trans:   { tname: expr },                           # quote-aware expressions
    s2t:     { step: [tname,...] },                     # outgoing transitions
    t2s:     { tname: next_step },                      # transition target (single)
    sets:    { setname: { member: int } },              # named sets
    seed:    { key: value },                            # initial store (tie-backs etc.)
  }

The transition expressions use the same quote-aware extraction as sim_run /
sfc_expr_fix, so the JS evaluator sees full conditions (incl. != "").
"""

import json
import sys

sys.path.insert(0, 'core')
import db_parser          # noqa: E402
import sim_run            # noqa: E402
import sim_prompts        # noqa: E402
import sim_aliases        # noqa: E402
import sim_timers         # noqa: E402


def build_payload(text, phase_name):
    sim = sim_run.PhaseSim(text, phase_name)

    steps = {n: {'desc': sim.steps[n].get('description', ''),
                 'x': sim.steps[n]['x'], 'y': sim.steps[n]['y']}
             for n in sim.order}

    actions = {n: [[q, e] for (q, e) in sim.actions.get(n, [])]
               for n in sim.order}

    # t2s: collapse list -> single target (these phases are single-target per trans)
    t2s = {}
    for tn, tgt in sim.t2s.items():
        t2s[tn] = (tgt[0] if isinstance(tgt, list) else tgt)

    prompts = sim_prompts.extract_prompts(
        sim.order, sim.actions, sim.s2t, t2s,
        {tn: sim.trans.get(tn, '') for tn in sim.trans})

    # ── Parameters: split recipe inputs (R_) from internal/computed (P_) ───────
    # R_ params are recipe/configuration values a recipe or operator SETS; they
    # are genuine inputs to the sequence and should be editable, pre-filled with
    # their declared defaults. P_ params are internal CVs the logic COMPUTES or
    # stores during execution; they are read-only state (shown in the watch).
    # We seed each R_ default into the store under its phase-relative key
    # '^/<name>.CV' so transitions that read it (e.g. '^/R_COND_LO_ALM.CV')
    # evaluate against the real value instead of the unknown-ref default of 0.
    raw_params = sim_run_phase_parameters(text, phase_name)
    r_params = []
    for p in raw_params:
        nm = p.get('name', '') or ''
        if not nm.startswith('R_'):
            continue
        key = '^/' + nm + '.CV'
        default = p.get('default', '')
        kind = _param_kind(p.get('type', ''))
        # enum members for a dropdown, if this R_ param is an enumeration
        enum_members = None
        if kind == 'enum':
            enum_members = _enum_for_param(p, sim.sets)
        entry = {
            'name': nm, 'key': key, 'kind': kind,
            'default': _coerce_default(default, kind),
            'units': p.get('units', '') or '',
            'desc': p.get('desc', '') or p.get('description', '') or '',
            'low': p.get('low', ''), 'high': p.get('high', ''),
            'enum': enum_members,
        }
        r_params.append(entry)
        # seed the default so logic referencing this R_ evaluates meaningfully
        if entry['default'] is not None and key not in sim.store:
            sim.store[key] = entry['default']

    # re-snapshot seed AFTER injecting R_ defaults
    seed = {k: _jsonable(v) for k, v in sim.store.items()}

    # Phase (P_) parameters: internal CVs the logic computes/stores during execution.
    # Some are computed by actions (P_TESTS_PASSED, P_MIN_BUFF_VOL, ...); some are read
    # by transitions but never computed (a real process/device value the operator must
    # supply). We surface all of them so the user can SEE computed values and OVERRIDE
    # the ones the sim can't derive. Classify each as 'computed' or 'input'.
    p_params = _phase_params(text, phase_name, sim, raw_params)

    return {
        'phase': phase_name,
        'seq_key': sim.key,
        'order': sim.order,
        'steps': steps,
        'actions': actions,
        'trans': {tn: sim.trans.get(tn, '') for tn in sim.trans},
        's2t': {n: list(sim.s2t.get(n, [])) for n in sim.order},
        't2s': t2s,
        'sets': sim.sets,
        'seed': seed,
        'prompts': prompts,
        'r_params': r_params,
        'p_params': p_params,
        'aliases': _aliases_for(text, sim),
        'timers': sim_timers.detect_timers(
            sim.order, sim.actions,
            {n: list(sim.s2t.get(n, [])) for n in sim.order},
            {tn: sim.trans.get(tn, '') for tn in sim.trans}),
    }


def _phase_params(text, phase_name, sim, raw_params):
    """Collect phase (P_/D_) parameters relevant to this phase's logic, each with:
      name, key, value (current store value after the initial walk), kind,
      role ('computed' = written by some action; 'input' = read by a transition but
      never written, so the operator must supply it), desc/units from the declaration.
    This lets the UI show computed values AND let the user override inputs the sim
    can't derive (real process/device readings)."""
    import re as _re
    written, read = set(), set()
    for sn in sim.order:
        for _q, e in sim.actions.get(sn, []):
            for m in _re.findall(r"'(\^?/[^']*(?:P_|D_)[A-Z0-9_]+\.CV)'\s*:=", e):
                written.add(m)
    for tn, ex in sim.trans.items():
        for m in _re.findall(r"'(\^?/[^']*(?:P_|D_)[A-Z0-9_]+\.CV)'", ex):
            read.add(m)

    # declaration metadata (desc/units) keyed by name, from the phase's parameter list
    meta = {}
    for p in raw_params:
        nm = (p.get('name') or '')
        if nm:
            meta[nm] = p

    def _name_of(key):
        m = _re.search(r'/([A-Za-z0-9_]+)\.CV$', key)
        return m.group(1) if m else key

    out = []
    seen = set()
    # union of read+written, but only P_/D_ (skip PENDING/FAILED_CONFIRMS bookkeeping)
    for key in sorted(read | written):
        nm = _name_of(key)
        if nm in seen:
            continue
        if nm.endswith('PENDING_CONFIRMS') or nm.endswith('FAILED_CONFIRMS'):
            continue
        seen.add(nm)
        role = 'computed' if key in written else 'input'
        val = sim.store.get(key)
        md = meta.get(nm, {})
        out.append({
            'name': nm, 'key': key,
            'value': _jsonable(val) if val is not None else '',
            'role': role,
            'kind': _param_kind(md.get('type', '')) if md else 'text',
            'units': (md.get('units') or '') if md else '',
            'desc': (md.get('desc') or md.get('description') or '') if md else '',
        })
    # inputs first (they need attention), then computed
    out.sort(key=lambda d: (d['role'] != 'input', d['name']))
    return out


def _aliases_for(text, sim):
    """Resolved alias metadata for aliases used in this phase's logic (item 10)."""
    try:
        all_aliases = sim_aliases.resolve_aliases(text)
        used = sim_aliases.aliases_used(
            sim.order, sim.actions,
            {tn: sim.trans.get(tn, '') for tn in sim.trans})
        return {a: all_aliases[a] for a in used if a in all_aliases}
    except Exception:
        return {}


def _jsonable(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, str)):
        return v
    return str(v)


def sim_run_phase_parameters(text, phase_name):
    """Return the phase's declared __parameters__ list via the core parser."""
    import phase_bridge
    blocks = phase_bridge.parse_phases_from_export(text).get(phase_name, {})
    return blocks.get('__parameters__', []) or []


def _param_kind(type_str):
    """Map a DeltaV parameter TYPE to an input widget kind."""
    t = (type_str or '').lower()
    if 'enum' in t:
        return 'enum'
    if 'bool' in t or 'logical' in t or 'discrete' in t:
        return 'bool'
    if 'int' in t:
        return 'int'
    if 'real' in t or 'float' in t or 'analog' in t:
        return 'real'
    return 'text'


def _coerce_default(default, kind):
    """Coerce a declared default string into the right JS-friendly type."""
    if default is None or default == '':
        if kind in ('int', 'real'):
            return 0
        if kind == 'bool':
            return False
        return ''
    try:
        if kind == 'int':
            return int(float(default))
        if kind == 'real':
            return float(default)
        if kind == 'bool':
            return str(default).strip().lower() in ('true', '1', 'yes')
    except (ValueError, TypeError):
        pass
    return default


def _enum_for_param(p, sets):
    """Best-effort: find the named set whose members this enum param uses.
    The export here has a single set (S_EM-CIP-DISTRIBUTION); if the param's
    type or name doesn't pin a set, fall back to the only/likeliest one."""
    # the parameter dict may name its set; otherwise use the sole set if present
    if len(sets) == 1:
        only = next(iter(sets.values()))
        return [{'label': k, 'value': v} for k, v in only.items()]
    return None


if __name__ == '__main__':
    text = db_parser.decode_fhx(open('/tmp/cip.fhx', 'rb').read())
    phase = sys.argv[1] if len(sys.argv) > 1 else 'CIP-SKD-WASH-PH'
    payload = build_payload(text, phase)
    out = '/tmp/sim_payload.json'
    json.dump(payload, open(out, 'w'))
    print(f'wrote {out}')
    print(f'  phase={payload["phase"]} seq={payload["seq_key"]}')
    print(f'  steps={len(payload["order"])} trans={len(payload["trans"])} '
          f'sets={len(payload["sets"])} seed_keys={len(payload["seed"])}')
