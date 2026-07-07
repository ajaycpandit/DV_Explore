"""
em_sim_export.py — build a simulator payload from a command-driven EM command.

A DeltaV command-driven EM exposes one SFC per command (HOLD, OPEN, FILTRATION,
…). Each command has the same structure as a phase SFC — ordered steps with
actions (expression/qualifier/delay/confirm) and transitions with expressions.
So we can reuse the existing phase simulator engine (sim_engine.js / sim_eval)
by emitting the same payload shape that sim_export.build_payload produces.

This module is additive; it does not modify core/.
"""

import re

import db_parser
import sim_export
import em_bridge

try:
    import sim_prompts
except Exception:
    sim_prompts = None
try:
    import sim_aliases
except Exception:
    sim_aliases = None
try:
    import sim_timers
except Exception:
    sim_timers = None


def list_em_commands(text, em_name):
    """Return the command names for a command-driven EM (in order)."""
    core, _ = em_bridge._load_core()
    cmds = core['parse_cdem_fhx'](text)
    seen, out = set(), []
    for c in cmds:
        if (c.get('em_name') or '') != em_name:
            continue
        cn = c.get('command_name', 'CMD')
        if cn in seen:
            continue
        seen.add(cn)
        out.append(cn)
    return out


def build_em_command_payload(text, em_name, command_name, tag=''):
    """Build a sim payload (same shape as sim_export.build_payload) for one command
    of a command-driven EM, so the phase simulator engine can walk it.

    When `tag` (an EM instance tag) is given, aliases resolve to that instance's
    actual wired devices — the point of running simulation on the instance not the
    class (#2)."""
    core, _ = em_bridge._load_core()
    cmds = core['parse_cdem_fhx'](text)
    cmd = None
    for c in cmds:
        if (c.get('em_name') or '') == em_name and c.get('command_name') == command_name:
            cmd = c
            break
    if cmd is None:
        return None

    ordered = cmd.get('ordered_steps', [])  # list of (step_name, {desc, actions, ...})
    order = [sn for sn, _ in ordered]
    steps = {}
    actions = {}
    for sn, sd in ordered:
        steps[sn] = {'desc': sd.get('description', '')}
        acts = []
        for a in sd.get('actions', []):
            qual = a.get('qualifier', 'P') or 'P'
            expr = a.get('expression', '') or ''
            acts.append([qual, expr])
        actions[sn] = acts

    trans = {}
    for tn, td in cmd.get('transitions', {}).items():
        trans[tn] = (td.get('expression', '') or '').strip()

    s2t = {sn: list(ts) for sn, ts in cmd.get('step_to_trans', {}).items()}
    # trans_to_step: DeltaV allows a transition to fan out to multiple steps; the
    # engine expects a single target per transition, so take the first (divergences
    # are rare in command SFCs and the walk still demonstrates the main path).
    t2s = {}
    for tn, tgt in cmd.get('trans_to_step', {}).items():
        if isinstance(tgt, (list, tuple)):
            t2s[tn] = tgt[0] if tgt else ''
        else:
            t2s[tn] = tgt

    # seed store: pull enumeration sets used, and default any referenced params to 0/''
    sets = _collect_sets(text)
    seed = {}

    # prompts: command SFCs can also have operator prompts; reuse the phase detector
    prompts = {}
    if sim_prompts is not None:
        try:
            prompts = sim_prompts.extract_prompts(order, actions, trans, sets) or {}
        except Exception:
            prompts = {}

    aliases = {}
    if sim_aliases is not None:
        try:
            all_al = sim_aliases.resolve_aliases(text)
            used = sim_aliases.aliases_used(order, actions, trans)
            aliases = {a: all_al[a] for a in used if a in all_al}
        except Exception:
            aliases = {}
    # #2: if an instance tag is given, resolve the EM's member roles to THIS instance's
    # actual deployed CM tags, so the walk shows real devices (e.g. BYP_INLET_VLV ->
    # FP005-HV-043) instead of the class role names.
    inst_aliases = _instance_member_aliases(text, em_name, tag) if tag else {}
    if inst_aliases:
        for role, devtag in inst_aliases.items():
            aliases[role] = {'module': devtag, 'desc': 'instance-wired device'}

    timers = {}
    if sim_timers is not None:
        try:
            timers = sim_timers.detect_timers(order, actions, s2t, trans)
        except Exception:
            timers = {}

    # recipe/phase params aren't defined for EM commands; keep empty lists so the
    # simulator's Inputs tab still renders (device levers + aliases remain useful).
    return {
        'phase': f'{em_name} \u00b7 {command_name}',
        'seq_key': command_name,
        'order': order,
        'steps': steps,
        'actions': actions,
        'trans': trans,
        's2t': s2t,
        't2s': t2s,
        'sets': sets,
        'seed': seed,
        'prompts': prompts,
        'r_params': [],
        'p_params': _em_params(actions, trans),
        'aliases': aliases,
        'timers': timers,
    }


def _collect_sets(text):
    """Named enumeration sets from the export (value name lookups for the evaluator)."""
    sets = {}
    try:
        cat = db_parser.parse_database(text)
        for s in cat.get('named_sets', []):
            entries = {}
            for e in s.get('entries', []):
                entries[e['name']] = e['value']
            sets[s['name']] = entries
    except Exception:
        pass
    return sets


def _em_params(actions, trans):
    """Surface the D_/P_ style parameters an EM command reads/writes so the sim's
    Inputs tab can show and override them (mirrors sim_export._phase_params, but
    from the command's own action/transition text)."""
    written, read = set(), set()
    for sn, acts in actions.items():
        for _q, e in acts:
            for m in re.findall(r"'(\^?/[^']*(?:P_|D_)[A-Z0-9_]+\.CV)'\s*:=", e):
                written.add(m)
    for tn, ex in trans.items():
        for m in re.findall(r"'(\^?/[^']*(?:P_|D_)[A-Z0-9_]+\.CV)'", ex):
            read.add(m)

    def _name(key):
        m = re.search(r'/([A-Za-z0-9_]+)\.CV$', key)
        return m.group(1) if m else key

    out, seen = [], set()
    for key in sorted(read | written):
        nm = _name(key)
        if nm in seen or nm.endswith('PENDING_CONFIRMS') or nm.endswith('FAILED_CONFIRMS'):
            continue
        seen.add(nm)
        out.append({'name': nm, 'key': key, 'value': '',
                    'role': 'computed' if key in written else 'input',
                    'kind': 'text', 'units': '', 'desc': ''})
    out.sort(key=lambda d: (d['role'] != 'input', d['name']))
    return out


def build_em_command_sim_view(text, em_name, command_name, tag=''):
    """Build a single EM command's SFC view with the phase simulator injected,
    so the command can be walked interactively like a phase (#11). When `tag` is a
    deployed EM instance, the sim resolves that instance's actual wired devices (#2)."""
    core, sfc = em_bridge._load_core()
    cmds = core['parse_cdem_fhx'](text)
    cmd = None
    for c in cmds:
        if (c.get('em_name') or '') == em_name and c.get('command_name') == command_name:
            cmd = c
            break
    if cmd is None:
        return None
    block = {
        'instance_name': command_name,
        'description': cmd.get('fb_description', ''),
        'ordered_steps': cmd.get('ordered_steps', []),
        'transitions': cmd.get('transitions', {}),
        'step_to_trans': cmd.get('step_to_trans', {}),
        'trans_to_step': cmd.get('trans_to_step', {}),
    }
    sfc_view = em_bridge._fix_sfc(sfc.build_sfc_html({command_name: block},
                                                     f'{em_name} \u2014 {command_name}'))
    payload = build_em_command_payload(text, em_name, command_name, tag=tag)
    try:
        import sim_overlay
        view = sim_overlay.inject(sfc_view, payload)
    except Exception:
        return sfc_view
    # Stage 3: device feedback panel — show the devices each step drives, animated
    # from command -> feedback via the device models. Reuses instance member
    # resolution so roles map to real deployed tags.
    try:
        import feedback_sim
        import device_panel
        member_map = instance_member_map(text, tag) if tag else {}
        registry = feedback_sim.build_device_registry(payload, member_map=member_map)
        has_devices = any(registry['steps'].get(s) for s in registry['steps'])
        if has_devices:
            with open(_here('device_sim.js'), 'r', encoding='utf-8') as fh:
                dev_js = fh.read()
            panel = device_panel.build_device_panel_html(registry)
            inject_block = ('<style>' + device_panel.DEVICE_CSS + '</style>'
                            '<script>' + dev_js + '</script>' + panel
                            + _DEV_HOOK_JS)
            if '</body>' in view:
                view = view.replace('</body>', inject_block + '</body>', 1)
            else:
                view = view + inject_block
    except Exception:
        pass
    return view


import os as _os


def _here(fname):
    return _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), fname)


# Hook the device panel to the simulator's step/reset so glyphs animate as the
# operator walks the sequence. The sim exposes the current step via the now-line;
# we observe step changes and call __devStep with the active step name.
_DEV_HOOK_JS = """
<script>
(function(){
  function currentStep(){
    var cur=document.querySelector('.sim-tape .row.cur, #tbody tr.cur, .now-line');
    if(!cur) return '';
    var m=(cur.textContent||'').match(/\\b(S\\d{2,4}|[A-Z][A-Z0-9_]{2,})\\b/);
    return m?m[1]:'';
  }
  var last='';
  function tick(){
    var s=currentStep();
    if(s && s!==last){ last=s; if(window.__devStep) window.__devStep(s); }
  }
  // poll for step changes (the sim re-renders the tape on step/play/back)
  setInterval(tick, 250);
  // reset hook
  document.addEventListener('click',function(e){
    var t=e.target;
    if(t && (t.id==='sim-reset' || (t.textContent||'').trim().toLowerCase()==='reset')){
      last=''; if(window.__devReset) window.__devReset();
    }
  });
})();
</script>
"""


def instance_member_map(text, tag, include_ignored=False):
    """Map an EM instance's member roles to their actual deployed CM tags, from the
    instance's MODULE_BLOCK_RESOLUTION blocks. E.g. BYP_INLET_VLV -> FP005-HV-027.
    This is the instance-specific device wiring (#1, #2).

    When include_ignored=True, roles that are intentionally commissioned-out
    (MODULE="" IGNORE=T) are also returned, mapped to the sentinel None, so callers
    can display them as "Ignored" rather than silently dropping them."""
    m = re.search(r'MODULE_INSTANCE\s+TAG="' + re.escape(tag) + r'"', text)
    if not m:
        return {}
    try:
        blk = db_parser.extract_block(text, text.index('{', m.start()))
    except Exception:
        return {}
    out = {}
    for rm in re.finditer(r'MODULE_BLOCK_RESOLUTION\s+NAME="([^"]+)"\s*\{', blk):
        rbody = db_parser.extract_block(blk, rm.end() - 1)
        mod = re.search(r'MODULE="([^"]*)"', rbody)
        modval = mod.group(1) if mod else ''
        if modval:
            out[rm.group(1)] = modval
        elif include_ignored:
            ign = re.search(r'IGNORE=([TF])', rbody)
            if ign and ign.group(1) == 'T':
                out[rm.group(1)] = None  # commissioned-out / ignored member
    return out


def _instance_member_aliases(text, em_name, tag):
    """Alias-style map (role -> device tag) for a specific EM instance."""
    return instance_member_map(text, tag)
