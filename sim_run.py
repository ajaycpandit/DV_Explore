"""
sim_run.py  —  SIMULATOR SPIKE (task 1+3): load one phase's RUN sequence and step
through it with the sim_eval evaluator. Standalone; imports the converter's
parser only to read the SFC, and re-extracts transition expressions with a
correct ""-aware regex (the converter's parse_sfc truncates transition
expressions at the first embedded string quote).

Run:  PYTHONPATH=$PWD python3 sim_run.py
"""

import re
import sys

sys.path.insert(0, 'core')
import fhx_app                       # converter parser (SFC graph)
import db_parser
import sim_eval


# ── correct, escaping-aware transition-expression extraction ─────────────────
def fixed_transition_exprs(sfc_block):
    out = {}
    for tm in re.finditer(r'TRANSITION\s+NAME="([^"]+)"\s*\{', sfc_block):
        tb = db_parser.extract_block(sfc_block, tm.end() - 1)
        e = re.search(r'EXPRESSION="((?:[^"]|"")*)"', tb, re.DOTALL)
        out[tm.group(1)] = e.group(1) if e else ''
    return out


def load_run_sequence(text, phase_name):
    """Return (steps_dict, order, transitions{name:expr}, step_to_trans, trans_to_step,
    actions{step:[(qual,expr)]}). The RUN sequence is the hash-keyed block with the
    most steps."""
    phase = fhx_app.parse_multiphase_fhx(text)[phase_name]
    seq_key = max((k for k, v in phase.items()
                   if isinstance(v, dict) and v.get('ordered_steps')),
                  key=lambda k: len(phase[k]['ordered_steps']))
    seq = phase[seq_key]
    order = [n for n, _ in seq['ordered_steps']]
    steps = dict(seq['ordered_steps'])
    # re-extract this block's raw SFC to fix transition expressions
    m = re.search(r'FUNCTION_BLOCK_DEFINITION\s+NAME="' + re.escape(seq_key) + r'"[^{]*\{', text)
    blk = db_parser.extract_block(text, m.end() - 1)
    sfc_m = re.search(r'SFC_ALGORITHM\s*\{', blk)
    sfc = db_parser.extract_block(blk, sfc_m.end() - 1)
    trans = fixed_transition_exprs(sfc)
    actions = {sn: [(a.get('qualifier', ''), a.get('expression', ''))
                    for a in steps[sn].get('actions', [])] for sn in order}
    return seq_key, steps, order, trans, seq['step_to_trans'], seq['trans_to_step'], actions


def named_set_map(text):
    cat = db_parser.parse_database(text)
    return {s['name']: {e['name']: e['value'] for e in s['entries']}
            for s in cat['named_sets']}


# ── the step engine ──────────────────────────────────────────────────────────
class PhaseSim:
    def __init__(self, text, phase_name):
        (self.key, self.steps, self.order, self.trans,
         self.s2t, self.t2s, self.actions) = load_run_sequence(text, phase_name)
        self.sets = named_set_map(text)
        self.store = {}
        self.active = self.order[0]
        self.log = []
        self.trace = []          # structured trace for animation
        self._seed()

    def _seed(self):
        # tie-back: every step's confirm counters start satisfied (auto-confirm).
        for sn in self.order:
            self.store[f'{sn}/PENDING_CONFIRMS.CV'] = 0
            self.store[f'{sn}/FAILED_CONFIRMS.CV'] = 0
        # a few phase variables in their power-up state
        self.store['^/P_FIRST_PASS.CV'] = False
        self.store['^/P_TASK_PTR.CV'] = 0
        self.store['//#THISUNIT#/U_CIP_SYNC_UNIT.CV'] = ''

    def enter(self, step):
        """Activate a step and fire its P (pulse-on-entry) actions."""
        self.active = step
        fired = 0
        for qual, expr in self.actions.get(step, []):
            if qual in ('P', '', 'N'):          # spike: treat P/N/blank as run-on-entry
                try:
                    sim_eval.run_actions(expr, self.store, self.sets)
                    fired += 1
                except Exception as ex:
                    self.log.append(f'      ! action error in {step}: {ex}')
        self.log.append(f'  → STEP {step}  [{self.steps[step].get("description","")}]'
                        f'  (ran {fired} action block(s))')
        self.trace.append({'kind': 'enter', 'step': step,
                           'desc': self.steps[step].get('description', ''),
                           'store': dict(self.store)})

    def fireable(self):
        """Return (transition, next_step) for the first satisfied outgoing transition."""
        for tn in self.s2t.get(self.active, []):
            expr = self.trans.get(tn, '')
            try:
                if sim_eval.eval_transition(expr, self.store, self.sets):
                    nxt = self.t2s.get(tn, [None])
                    nxt = nxt[0] if isinstance(nxt, list) else nxt
                    self.trace.append({'kind': 'fire', 't': tn,
                                       'from': self.active, 'to': nxt})
                    return tn, nxt
            except Exception as ex:
                self.log.append(f'      ! transition error {tn}: {ex}')
        return None, None

    def run(self, max_steps=40):
        self.enter(self.active)
        for _ in range(max_steps):
            tn, nxt = self.fireable()
            if not tn:
                self.log.append(f'      … waiting at {self.active} '
                                f'(no outgoing transition satisfied)')
                break
            self.log.append(f'      ✓ {tn} fires → {nxt}')
            if nxt is None or nxt not in self.steps:
                self.log.append(f'      ∎ reached terminal/exit ({nxt})')
                break
            self.enter(nxt)
        return self.log


if __name__ == '__main__':
    text = db_parser.decode_fhx(open('/tmp/cip.fhx', 'rb').read())
    sim = PhaseSim(text, 'CIP-SKD-WASH-PH')
    print(f'RUN sequence {sim.key}: {len(sim.order)} steps, {len(sim.trans)} transitions\n')

    print('── Walk 1: power-up state (sync unit empty) ──')
    for line in sim.run():
        print(line)

    print('\n── Walk 2: operator assigns sync unit, equipment confirms ──')
    sim2 = PhaseSim(text, 'CIP-SKD-WASH-PH')
    sim2.store['//#THISUNIT#/U_CIP_SYNC_UNIT.CV'] = 'CIP_UNIT_01'   # sync unit set
    for line in sim2.run():
        print(line)
