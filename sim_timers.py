"""
sim_timers.py — Item 9: detect DeltaV timer usage so the simulator can show a
visual countdown that auto-completes.

DeltaV timers (e.g. a UNIT_SUPPORT TMR1 function block) are driven from SFC
actions and gate a transition on completion:

  action  (step S0130):  '.../TMR1/TM_SP.CV'   := '^/R_CHEM_ADD_TM.CV'   (setpoint)
                         '.../TMR1/TM_RESET.CV' := True
                         '.../TMR1/TM_HOLD.CV'  := '_TIMER_HOLD:Run'
  transition (T0140):    ... AND '.../TMR1/TM_COMPLETE.CV' = True

We extract, per step that starts a timer:
  - timer_key  : the TMR path (e.g. '//#UNIT_SUPPORT#/TMR1')
  - sp_ref     : the setpoint source (an R_ param key, so the UI knows the duration)
  - complete_key: '.../TM_COMPLETE.CV' (the flag the outgoing transition waits on)

The simulator uses this to render a countdown from the R_ setpoint value; when it
elapses it sets complete_key := True, releasing the wait. Visual only (auto-
completes) — no real process time, per the agreed scope.
"""
import re

_TM_SP = re.compile(r"'([^']*/TM_SP)\.CV'\s*:=\s*'([^']+)'")
_TM_RESET = re.compile(r"'([^']*)/TM_RESET\.CV'\s*:=\s*True", re.I)
_TM_COMPLETE = re.compile(r"'([^']*/TM_COMPLETE\.CV)'")


def detect_timers(order, actions, s2t, trans):
    """Return {step: timer_descriptor} for steps that start a timer.
    descriptor = {timer_key, sp_ref, complete_key, wait_trans}."""
    out = {}
    for sn in order:
        sp_ref = None
        timer_base = None
        for _q, a in actions.get(sn, []):
            m = _TM_SP.search(a)
            if m:
                # m.group(1) like '//#UNIT_SUPPORT#/TMR1/TM_SP'
                timer_base = m.group(1).rsplit('/TM_SP', 1)[0]
                sp_ref = m.group(2)
                break
        if not timer_base:
            continue
        # find the outgoing transition that waits on this timer's TM_COMPLETE
        complete_key = None
        wait_trans = None
        for tn in s2t.get(sn, []):
            e = trans.get(tn, '')
            cm = _TM_COMPLETE.search(e)
            if cm and timer_base in cm.group(1):
                complete_key = cm.group(1)
                wait_trans = tn
                break
        out[sn] = {
            'timer_key': timer_base,
            'sp_ref': sp_ref,                 # e.g. '^/R_CHEM_ADD_TM.CV'
            'complete_key': complete_key,     # e.g. '//#UNIT_SUPPORT#/TMR1/TM_COMPLETE.CV'
            'wait_trans': wait_trans,
        }
    return out
