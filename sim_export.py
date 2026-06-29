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

    # the seed store the Python engine starts from (tie-back confirms etc.)
    seed = {k: _jsonable(v) for k, v in sim.store.items()}

    prompts = sim_prompts.extract_prompts(
        sim.order, sim.actions, sim.s2t, t2s,
        {tn: sim.trans.get(tn, '') for tn in sim.trans})

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
    }


def _jsonable(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, str)):
        return v
    return str(v)


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
