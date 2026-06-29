"""
sim_prompts.py — Step A: extract operator-prompt (OAR) metadata from a phase's
RUN sequence so the simulator can HALT at operator prompts and show the right
control, instead of auto-walking past them.

DeltaV models an operator prompt as an OAR (Operator Attention Request). A step
raises one in its on-entry actions:

    '^/P_MSG_TYPE1.CV'            := '_MSG_TYPE:PROMPT'      (vs :INFO)
    '^/FAIL_MONITOR/OAR/TYPE.CV' := '_OAR_TYPE_BOI:YesNo'   (or 'OK Input', ...)
    '^/FAIL_MONITOR/OAR/OAR_STATUS.CV' := '_OAR_STATUS:ACTIVE'

and the operator's answer lands in
    '^/FAIL_MONITOR/OAR/INPUT.CV'

The outgoing transitions already branch on that variable, e.g. for a YesNo prompt:
    INPUT = 0  -> one path        INPUT = 1  -> the other path

Release mechanism (two flavours, detected per step):
  * 'value'   — at least one outgoing transition tests OAR/INPUT.CV = <n>.
                The operator picks a value; we write OAR/INPUT.CV and re-walk.
                (YesNo, and any multi-choice / numeric-entry prompt.)
  * 'ack'     — no outgoing transition tests OAR/INPUT; release is gated on the
                step's PENDING_CONFIRMS clearing. The operator just acknowledges;
                we clear the request (seed PENDING_CONFIRMS = 0) and re-walk.
                ('OK Input' acknowledge-to-proceed prompts.)

This is logic + UI only (no device/process model) and so belongs in T1, not T2.
core/ is untouched; this reads the same parsed actions the engine already uses.
"""
import re

# OAR variable suffixes (the '^/FAIL_MONITOR/OAR/...' path may vary in prefix,
# so match on the OAR/<field> tail).
_RE_MSGTYPE = re.compile(r"P_MSG_TYPE\d?\.CV'\s*:=\s*'_MSG_TYPE:(\w+)'")
_RE_OARTYPE = re.compile(r"OAR/TYPE\.CV'\s*:=\s*'_OAR_TYPE_BOI:([^']+)'")
_RE_OARSTAT = re.compile(r"OAR/OAR_STATUS\.CV'\s*:=\s*'_OAR_STATUS:(\w+)'")
_RE_MSG1 = re.compile(r'P_MSG1\.CV\'\s*:=\s*""([^"]*)""')
_RE_MSG2 = re.compile(r'P_MSG2\.CV\'\s*:=\s*""([^"]*)""')
# an outgoing transition that reads the operator's answer
_RE_INPUT_CMP = re.compile(r"OAR/INPUT\.CV'\s*=\s*(\d+)")


def _scan_actions(action_blocks):
    """action_blocks: list of (qualifier, expr_text) for one step.
    Return {msgtype, oar_type, oar_status, msg1, msg2} (any may be absent)."""
    info = {}
    for _q, e in action_blocks:
        m = _RE_MSGTYPE.search(e)
        if m:
            info['msgtype'] = m.group(1)
        m = _RE_OARTYPE.search(e)
        if m:
            info['oar_type'] = m.group(1).strip()
        m = _RE_OARSTAT.search(e)
        if m:
            info['oar_status'] = m.group(1)
        # first message assignment wins (later ones may append/clear)
        if 'msg1' not in info:
            m = _RE_MSG1.search(e)
            if m:
                info['msg1'] = m.group(1)
        if 'msg2' not in info:
            m = _RE_MSG2.search(e)
            if m:
                info['msg2'] = m.group(1)
    return info


def extract_prompts(order, actions, s2t, t2s, trans):
    """Return {step_name: prompt_descriptor} for every step that raises an
    operator prompt. Descriptor:
        {
          'oar_type': 'YesNo' | 'OK Input' | ...,
          'release':  'value' | 'ack',
          'msg1', 'msg2': str,
          'input_key': '<step>/.../OAR/INPUT.CV'  (for 'value' release; best-effort),
          'choices':  [ {value:int, label:str, trans:str, to:str}, ... ]  (value release),
          'confirm_key': '<step>/PENDING_CONFIRMS.CV'                      (ack release),
        }
    """
    prompts = {}
    for sn in order:
        info = _scan_actions(actions.get(sn, []))
        is_prompt = (info.get('msgtype') == 'PROMPT'
                     or info.get('oar_status') == 'ACTIVE')
        if not is_prompt:
            continue

        # classify release by inspecting outgoing transitions
        choices = []
        input_key = None
        for tn in s2t.get(sn, []):
            expr = trans.get(tn, '')
            m = _RE_INPUT_CMP.search(expr)
            if m:
                val = int(m.group(1))
                tgt = t2s.get(tn)
                tgt = tgt[0] if isinstance(tgt, list) else tgt
                choices.append({'value': val, 'trans': tn, 'to': tgt})
                if input_key is None:
                    km = re.search(r"'([^']*OAR/INPUT\.CV)'", expr)
                    if km:
                        input_key = km.group(1)

        oar_type = info.get('oar_type', '')
        if choices:
            release = 'value'
            # label YesNo choices conventionally (INPUT 1 = Yes, 0 = No in DeltaV BOI)
            if oar_type.lower().replace(' ', '') == 'yesno':
                for c in choices:
                    c['label'] = 'Yes' if c['value'] == 1 else 'No'
            else:
                for c in choices:
                    c['label'] = str(c['value'])
            choices.sort(key=lambda c: c['value'])
        else:
            release = 'ack'

        prompts[sn] = {
            'oar_type': oar_type,
            'release': release,
            'msg1': info.get('msg1', ''),
            'msg2': info.get('msg2', ''),
            'input_key': input_key,
            'choices': choices,
            'confirm_key': sn + '/PENDING_CONFIRMS.CV',
        }
    return prompts
