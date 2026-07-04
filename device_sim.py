"""
device_sim.py — device feedback models for the closed-loop simulator.

In a real plant, DeltaV issues a command to a field device (a valve's SP_D, a
motor's start request, an analog SP) and the device reports feedback (PV_D, RUNNING,
analog PV) after some travel/response time. Phase and EM logic waits on that feedback
to progress. This module models that command -> (delay) -> feedback behaviour so the
sequence simulator can run closed-loop.

Design (deliberately small, per the agreed staging):
  - Each device is a tiny state machine keyed by its DeltaV sub-type family.
  - advance(state, command, dt_seconds) -> new_state, mutating feedback toward the
    commanded target over the device's travel time (mirror-with-delay).
  - No fault injection yet (happy path first); the shape leaves room for it.

The models are pure and framework-free so they can be driven by the phase simulator,
the EM command simulator, or a manual device panel. A JS twin (device_sim.js) mirrors
this for in-browser animation.
"""

# device families we recognise from DeltaV SUB_TYPE / class naming
VALVE_2STATE = 'valve_2state'
VALVE_ANALOG = 'valve_analog'
MOTOR = 'motor'
PUMP = 'pump'
GENERIC = 'generic'


def classify(sub_type, cls=''):
    """Map a DeltaV SUB_TYPE / class name to a device family."""
    s = (sub_type or '').upper() + ' ' + (cls or '').upper()
    if 'VALVE' in s and ('2STATE' in s or '2_STATE' in s or 'DIG' in s):
        return VALVE_2STATE
    if 'VALVE' in s and ('ANLG' in s or 'ANALOG' in s or 'AO' in s or 'POS' in s):
        return VALVE_ANALOG
    if 'MTR' in s or 'MOTOR' in s:
        return MOTOR
    if 'PMP' in s or 'PUMP' in s:
        return PUMP
    if 'VALVE' in s:
        return VALVE_2STATE
    return GENERIC


# default travel/response times (seconds) — overridable per device from CFM timers
DEFAULT_TIMES = {
    VALVE_2STATE: 2.0,
    VALVE_ANALOG: 4.0,
    MOTOR: 3.0,
    PUMP: 3.0,
    GENERIC: 1.0,
}


def new_state(family, tag='', role='', travel=None):
    """Initial device state. Discrete devices start CLOSED/STOPPED; analog at 0."""
    discrete = family in (VALVE_2STATE, MOTOR, PUMP)
    return {
        'tag': tag,
        'role': role,
        'family': family,
        'travel': DEFAULT_TIMES.get(family, 1.0) if travel is None else travel,
        # commanded target and current feedback
        'target': 'CLOSED' if family in (VALVE_2STATE,) else ('STOPPED' if family in (MOTOR, PUMP) else 0.0),
        'pv': 'CLOSED' if family in (VALVE_2STATE,) else ('STOPPED' if family in (MOTOR, PUMP) else 0.0),
        'discrete': discrete,
        'moving': False,
        'elapsed': 0.0,   # time since the current command was issued
    }


# normalise assorted command spellings to the device's canonical target
def _norm_discrete(family, command):
    c = str(command).strip().upper()
    if family == VALVE_2STATE:
        if c in ('OPEN', 'OPENED', 'TRUE', '1', 'ON'):
            return 'OPEN'
        if c in ('CLOSE', 'CLOSED', 'FALSE', '0', 'OFF'):
            return 'CLOSED'
    if family in (MOTOR, PUMP):
        if c in ('START', 'RUN', 'RUNNING', 'ON', 'TRUE', '1'):
            return 'RUNNING'
        if c in ('STOP', 'STOPPED', 'OFF', 'FALSE', '0'):
            return 'STOPPED'
    return None


def command(state, cmd):
    """Issue a new command to the device, arming its feedback transition."""
    if state['discrete']:
        tgt = _norm_discrete(state['family'], cmd)
        if tgt is not None and tgt != state['target']:
            state['target'] = tgt
            state['moving'] = True
            state['elapsed'] = 0.0
    else:
        try:
            tgt = float(cmd)
        except (TypeError, ValueError):
            return state
        if tgt != state['target']:
            state['target'] = tgt
            state['moving'] = True
            state['elapsed'] = 0.0
    return state


def advance(state, dt):
    """Advance the device by dt seconds, moving feedback toward the commanded target."""
    if not state.get('moving'):
        return state
    state['elapsed'] = state.get('elapsed', 0.0) + dt
    travel = max(0.001, state.get('travel', 1.0))
    if state['discrete']:
        # discrete device: PV flips to target once travel time elapses
        if state['elapsed'] >= travel:
            state['pv'] = state['target']
            state['moving'] = False
    else:
        # analog device: PV ramps linearly toward target over travel time
        frac = min(1.0, state['elapsed'] / travel)
        start = state.get('_ramp_start', state['pv'])
        if '_ramp_start' not in state:
            state['_ramp_start'] = state['pv']
            start = state['pv']
        state['pv'] = start + (state['target'] - start) * frac
        if frac >= 1.0:
            state['pv'] = state['target']
            state['moving'] = False
            state.pop('_ramp_start', None)
    return state


def feedback(state):
    """The current feedback value the sequence logic would read (PV)."""
    return state['pv']


def settled(state):
    """True when feedback has reached the commanded target."""
    return not state.get('moving')


def glyph_state(state):
    """A compact descriptor the UI uses to render/animate the device glyph."""
    fam = state['family']
    pv = state['pv']
    if fam == VALVE_2STATE:
        color = 'green' if pv == 'OPEN' else 'gray'
        return {'kind': 'valve', 'open': pv == 'OPEN', 'moving': state['moving'],
                'color': color, 'label': str(pv)}
    if fam in (MOTOR, PUMP):
        running = pv == 'RUNNING'
        return {'kind': fam, 'running': running, 'moving': state['moving'],
                'color': 'green' if running else 'red', 'label': str(pv)}
    if fam == VALVE_ANALOG:
        try:
            pct = float(pv)
        except (TypeError, ValueError):
            pct = 0.0
        return {'kind': 'analog_valve', 'pct': pct, 'moving': state['moving'],
                'color': 'green' if pct > 1 else 'gray', 'label': f'{pct:.0f}%'}
    return {'kind': 'generic', 'label': str(pv), 'color': 'gray', 'moving': False}
