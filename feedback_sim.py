"""
feedback_sim.py — Stage 2/3 of the device feedback engine.

Given an EM command (or phase) payload, figure out which devices each step drives
and with what command, so the UI can show the involved devices (as animated glyphs)
and, later, close the loop by feeding device feedback back into the sequence.

DeltaV command patterns observed in the FP005 export:
  - 2-state valve:  '^/<ROLE>/RSP.CV' := 'vlvnc-sp:OPEN' | 'vlvnc-sp:CLOSE'
  - mode set:       '^/<ROLE>/MODE.TARGET' := CAS   (mode, not a drive command)
  - motor/pump:     '^/<ROLE>/RSP.CV' := ... or START/STOP style requests

This module is additive and does not touch core/.
"""

import re

import device_sim as ds


# command extraction: role -> command, per step
_VALVE_RSP = re.compile(r"'[\^/]*/?([A-Z0-9_]+)/RSP\.CV'\s*:=\s*'[^:]*:(\w+)'")
_TARGET = re.compile(r"'[\^/]*/?([A-Z0-9_]+)/(?:SP_D|SP|TARGET)\.CV'\s*:=\s*([A-Za-z0-9_:]+)")


def devices_for_step(actions_for_step):
    """From a step's action list [(qual, expr), ...] return the device commands:
    [{'role':..., 'command':..., 'hint':...}] in order, de-duplicated by role.
    'hint' carries the DeltaV enum family (e.g. 'vlvnc') so we can classify the
    device even when the role name isn't descriptive."""
    out = {}
    hints = {}
    order = []
    for _q, expr in actions_for_step:
        # valve RSP with enum family: '<ROLE>/RSP.CV' := 'vlvnc-sp:OPEN'
        for m in re.finditer(r"'[\^/]*/?([A-Z0-9_]+)/RSP\.CV'\s*:=\s*'([a-z0-9_]+)[-:][^:]*:(\w+)'", expr):
            role, fam_hint, val = m.group(1), m.group(2), m.group(3)
            if role not in out:
                order.append(role)
            out[role] = val.upper()
            hints[role] = fam_hint
        for role, val in _TARGET.findall(expr):
            if val.upper() in ('CAS', 'AUTO', 'MAN', 'ROUT', 'RCAS'):
                continue
            if role not in out:
                order.append(role)
            out[role] = val.upper()
    return [{'role': r, 'command': out[r], 'hint': hints.get(r, '')} for r in order]


def build_device_registry(payload, member_map=None, class_map=None):
    """Build the per-step device command plan plus an initial device-state map.

    member_map: role -> deployed tag (from instance resolution), optional.
    class_map:  deployed tag -> sub_type/class (to classify the device family),
                optional; falls back to name-based classification.
    Returns {'steps': {step: [ {role, tag, family, command} ]},
             'devices': {role: initial_state_dict}}.
    """
    member_map = member_map or {}
    class_map = class_map or {}

    per_step = {}
    devices = {}
    for step in payload.get('order', []):
        cmds = devices_for_step(payload.get('actions', {}).get(step, []))
        plan = []
        for c in cmds:
            role = c['role']
            tag = member_map.get(role, role)
            sub = class_map.get(tag, '')
            # classify from (in priority) the class map, the command enum hint
            # (vlvnc/vlv -> valve, mtr -> motor), then the role name.
            hint = c.get('hint', '')
            if 'vlv' in hint or 'vlvnc' in hint:
                fam = ds.VALVE_2STATE
            elif 'mtr' in hint or 'pmp' in hint:
                fam = ds.MOTOR
            else:
                fam = ds.classify(sub or role, role)
            if role not in devices:
                devices[role] = ds.new_state(fam, tag, role)
            plan.append({'role': role, 'tag': tag, 'family': fam, 'command': c['command']})
        per_step[step] = plan
    return {'steps': per_step, 'devices': devices}


def simulate_step(registry, step, dt_total=None):
    """Apply a step's commands to the device states and settle them (for a
    non-interactive check). Returns the glyph states after settling."""
    plan = registry['steps'].get(step, [])
    for c in plan:
        st = registry['devices'].get(c['role'])
        if st:
            ds.command(st, c['command'])
    # settle: advance until all involved devices report their target
    steps_run = 0
    while any(not ds.settled(registry['devices'][c['role']]) for c in plan) and steps_run < 1000:
        for c in plan:
            ds.advance(registry['devices'][c['role']], 0.1)
        steps_run += 1
    return {c['role']: ds.glyph_state(registry['devices'][c['role']]) for c in plan}
