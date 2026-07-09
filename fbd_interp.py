"""FBD interpreter for real-simulation mode (Mode 2).

This module executes a DeltaV Control/Equipment Module's Function Block Diagram
tick-by-tick, so a phase can WAIT for real signals from CM/EM logic instead of
assuming every command is instantly satisfied (the offline "verify steps" mode).

Design (built in verifiable layers):
  Layer 1 (this pass): SignalStore, a small Structured-Text expression evaluator
    (comparisons, boolean ops, IF/assignment), and the primitive logic blocks
    (CND, OR, NOT, BFI, ACT, NDE).
  Layer 2: the DC (Device Control) block modelled as a command->output->feedback
    loop, plus the tick scheduler that propagates wires and closes the I/O loop.
  Layer 3: module wrapper (load from parse_module_fbd), EM command driving, and
    the phase<->CM/EM bridge.

Nothing here touches core/. It consumes fbd_parser.parse_module_fbd() output.

The interpreter is intentionally forgiving: unknown block types evaluate to a
pass-through/neutral value rather than raising, so a partial model still runs and
we can see how far a real EM command gets. Every simplification is logged on the
block so the UI can flag "modelled" vs "assumed".
"""

import re


# ─────────────────────────────────────────────────────────────────────────────
# Signal store
# ─────────────────────────────────────────────────────────────────────────────
class SignalStore:
    """Flat namespace of signal values keyed by dotted/slashed path.

    DeltaV references look like '^/RSP.CV', 'S100/PENDING_CONFIRMS.CV',
    '^/MODE.TARGET'. We normalise the leading '^/' (means "this module") to a
    module-relative key and keep a single dict. Values are Python bool/int/
    float/str. Reads of unknown keys return a configurable default (0) so
    partially-modelled logic still evaluates.
    """

    def __init__(self, module_prefix=''):
        self.vals = {}
        self.module_prefix = module_prefix  # e.g. 'CAS_DRN' for a resolved instance
        self.writes = []  # audit log of (key, value) this tick

    @staticmethod
    def norm(key):
        k = key.strip().strip("'").strip('"')
        # '^/X' -> module-relative 'X'; leading './' or '/' stripped
        if k.startswith('^/'):
            k = k[2:]
        elif k.startswith('/'):
            k = k[1:]
        return k

    def get(self, key, default=0):
        k = self.norm(key)
        if k in self.vals:
            return self.vals[k]
        # bare block-port like 'OR1/OUT_D' may be stored without normalisation
        return self.vals.get(key, default)

    def set(self, key, value):
        k = self.norm(key)
        self.vals[k] = value
        self.writes.append((k, value))

    def clear_writes(self):
        self.writes = []


# ─────────────────────────────────────────────────────────────────────────────
# Structured-Text mini-evaluator
# ─────────────────────────────────────────────────────────────────────────────
# Supports the subset that appears in CND/ACT/transition expressions:
#   - literals: TRUE/FALSE, integers, floats, 'quoted strings', enum tokens (CAS, LO)
#   - references: '^/RSP.CV', 'S100/TIME.CV', bare NAME
#   - comparisons: =  !=  <>  >=  <=  >  <
#   - boolean: AND OR NOT, parentheses
#   - assignment: LHS := RHS ;
#   - IF cond THEN ... [ELSIF ...] [ELSE ...] ENDIF / END_IF
# This is deliberately small; anything unrecognised evaluates to a neutral value
# and is recorded so the UI can mark the block "partially modelled".

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<str>'[^']*'|"[^"]*")
  | (?P<op>:=|<>|!=|>=|<=|=|>|<|\(|\)|;)
  | (?P<num>\d+\.\d+|\d+)
  | (?P<word>[A-Za-z_\^/][A-Za-z0-9_\^/\.]*)
""", re.VERBOSE)

_KW = {'IF', 'THEN', 'ELSE', 'ELSIF', 'ENDIF', 'END_IF', 'AND', 'OR', 'NOT',
       'TRUE', 'FALSE'}


def _tokenize(src):
    toks = []
    i = 0
    while i < len(src):
        m = _TOKEN_RE.match(src, i)
        if not m:
            i += 1
            continue
        i = m.end()
        if m.lastgroup == 'ws':
            continue
        toks.append((m.lastgroup, m.group()))
    return toks


def _fmt_val(v):
    """Human-friendly rendering of a signal value for the UI (enum tail, 0/1, dash)."""
    if v is None or v == '':
        return '\u2013'
    if v is True or v == 1:
        return '1'
    if v is False or v == 0:
        return '0'
    s = str(v)
    if ':' in s:
        return s.split(':')[-1]
    return s


def _truthy(v):
    if isinstance(v, str):
        return v.strip().upper() in ('TRUE', '1') or (v.strip() != '' and v.strip() != '0' and v.strip().upper() != 'FALSE')
    return bool(v)


class STEval:
    """Evaluates one CND/ACT/transition expression against a SignalStore.

    eval_condition(expr) -> bool     (for CND / transitions)
    run_action(expr)      -> None    (for ACT: performs := assignments)
    """

    def __init__(self, store, notes=None):
        self.s = store
        self.notes = notes if notes is not None else []

    # -- value resolution ----------------------------------------------------
    def _literal(self, tok_type, tok):
        if tok_type == 'num':
            return float(tok) if '.' in tok else int(tok)
        if tok_type == 'str':
            inner = tok[1:-1]
            # A quoted token that looks like a DeltaV reference ('^/RSP.CV',
            # 'S100/TIME.CV') is a REFERENCE, not a string literal — signal that to
            # the caller by returning None so _resolve handles it. A quoted enum-ish
            # value like 'vlvnc-pv:OPEN' or 'mtr2-sp:START' is a real string literal.
            if inner.startswith('^/') or inner.startswith('/') or re.match(r'^[A-Za-z0-9_]+/', inner):
                return None
            return inner
        up = tok.upper()
        if up == 'TRUE':
            return True
        if up == 'FALSE':
            return False
        return None  # not a literal -> treat as reference/enum

    def _resolve(self, tok):
        """A token that isn't a plain literal: a reference (quoted or bare, with
        / . or ^) -> store lookup; otherwise an enum/mode token (CAS, LO) -> its
        own string."""
        raw = tok
        if (tok.startswith("'") and tok.endswith("'")) or (tok.startswith('"') and tok.endswith('"')):
            raw = tok[1:-1]
        if any(c in raw for c in '^/.') or re.match(r'^[A-Za-z0-9_]+/', raw):
            return self.s.get(raw, 0)
        # bare enum token
        return raw

    # -- expression parser (recursive descent over the token list) ----------
    def eval_condition(self, expr):
        if expr is None:
            return False
        toks = _tokenize(str(expr))
        if not toks:
            return False
        # Fast path: a lone TRUE/FALSE
        if len(toks) == 1:
            v = self._literal(toks[0][0], toks[0][1])
            if v is not None:
                return _truthy(v)
            return _truthy(self._resolve(toks[0][1]))
        self._toks = toks
        self._pos = 0
        try:
            val = self._parse_or()
            return _truthy(val)
        except Exception as e:  # noqa
            self.notes.append(f'condition not fully parsed: {expr!r} ({e})')
            return False

    def _peek(self):
        return self._toks[self._pos] if self._pos < len(self._toks) else (None, None)

    def _next(self):
        t = self._toks[self._pos]
        self._pos += 1
        return t

    def _parse_or(self):
        v = self._parse_and()
        while self._peek()[1] and self._peek()[1].upper() == 'OR':
            self._next()
            r = self._parse_and()
            v = _truthy(v) or _truthy(r)
        return v

    def _parse_and(self):
        v = self._parse_not()
        while self._peek()[1] and self._peek()[1].upper() == 'AND':
            self._next()
            r = self._parse_not()
            v = _truthy(v) and _truthy(r)
        return v

    def _parse_not(self):
        if self._peek()[1] and self._peek()[1].upper() == 'NOT':
            self._next()
            return not _truthy(self._parse_not())
        return self._parse_cmp()

    def _parse_cmp(self):
        left = self._parse_atom()
        op = self._peek()[1]
        if op in ('=', '!=', '<>', '>=', '<=', '>', '<'):
            self._next()
            right = self._parse_atom()
            return self._compare(left, op, right)
        return left

    def _parse_atom(self):
        tt, tok = self._peek()
        if tok == '(':
            self._next()
            v = self._parse_or()
            if self._peek()[1] == ')':
                self._next()
            return v
        self._next()
        lit = self._literal(tt, tok)
        if lit is not None:
            return lit
        return self._resolve(tok)

    @staticmethod
    def _compare(a, op, b):
        # numeric compare when both look numeric; else string compare
        def num(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return None
        na, nb = num(a), num(b)
        if na is not None and nb is not None:
            a, b = na, nb
        else:
            a, b = str(a), str(b)
        if op == '=':
            return a == b
        if op in ('!=', '<>'):
            return a != b
        if op == '>':
            return a > b
        if op == '<':
            return a < b
        if op == '>=':
            return a >= b
        if op == '<=':
            return a <= b
        return False

    # -- action runner (IF/assignments) -------------------------------------
    def run_action(self, expr):
        if not expr:
            return
        self._run_block(str(expr))

    def _run_block(self, src):
        # Split into statements honouring IF...ENDIF nesting.
        # We do a light line-oriented interpreter: assignments and IF blocks.
        stmts = self._split_top(src)
        for st in stmts:
            self._run_stmt(st)

    def _split_top(self, src):
        """Split src into top-level statements: assignments (…;) and IF…ENDIF
        blocks (kept whole)."""
        out = []
        i = 0
        depth = 0
        cur = ''
        # tokenise by words to track IF/ENDIF depth while accumulating raw text
        # simpler: scan word by word
        words = re.split(r'(\bIF\b|\bENDIF\b|\bEND_IF\b|;)', src, flags=re.IGNORECASE)
        for w in words:
            wu = w.strip().upper()
            if wu == 'IF':
                if depth == 0 and cur.strip():
                    out.append(cur); cur = ''
                depth += 1
                cur += w
            elif wu in ('ENDIF', 'END_IF'):
                depth = max(0, depth - 1)
                cur += w
                if depth == 0:
                    out.append(cur); cur = ''
            elif w == ';' and depth == 0:
                cur += w
                if cur.strip():
                    out.append(cur); cur = ''
            else:
                cur += w
        if cur.strip():
            out.append(cur)
        return [s for s in out if s.strip()]

    def _run_stmt(self, st):
        stu = st.strip()
        if re.match(r'^\s*IF\b', stu, re.IGNORECASE):
            self._run_if(stu)
            return
        # assignment: LHS := RHS
        m = re.match(r"^\s*(.+?)\s*:=\s*(.+?)\s*;?\s*$", stu, re.DOTALL)
        if m:
            lhs, rhs = m.group(1), m.group(2)
            val = self._eval_value(rhs)
            self.s.set(lhs, val)

    def _run_if(self, st):
        # IF <cond> THEN <body> [ELSIF <cond> THEN <body>]* [ELSE <body>] ENDIF
        body = re.sub(r'^\s*IF\b', '', st, flags=re.IGNORECASE)
        body = re.sub(r'\b(ENDIF|END_IF)\s*;?\s*$', '', body, flags=re.IGNORECASE)
        # split into branches by ELSIF/ELSE at top level (no nested-IF handling of
        # the same keywords — the valve/motor ACTs don't nest IFs under branches
        # in a way that breaks this; nested IFs are recursed via _run_block)
        parts = re.split(r'\bELSIF\b|\bELSE\b', body, flags=re.IGNORECASE)
        keywords = re.findall(r'\bELSIF\b|\bELSE\b', body, flags=re.IGNORECASE)
        # first part: "<cond> THEN <body>"
        def cond_body(seg):
            mm = re.match(r'^(.*?)\bTHEN\b(.*)$', seg, re.IGNORECASE | re.DOTALL)
            if mm:
                return mm.group(1), mm.group(2)
            return None, seg
        cond, then_body = cond_body(parts[0])
        if self.eval_condition(cond):
            self._run_block(then_body)
            return
        idx = 1
        for kw in keywords:
            seg = parts[idx]
            if kw.upper() == 'ELSIF':
                c, b = cond_body(seg)
                if self.eval_condition(c):
                    self._run_block(b)
                    return
            else:  # ELSE
                self._run_block(seg)
                return
            idx += 1

    def _eval_value(self, rhs):
        rhs = rhs.strip().rstrip(';').strip()
        toks = _tokenize(rhs)
        if len(toks) == 1:
            lit = self._literal(toks[0][0], toks[0][1])
            return lit if lit is not None else self._resolve(toks[0][1])
        # fall back: evaluate as a condition (covers boolean RHS); else raw string
        try:
            return self.eval_condition(rhs)
        except Exception:  # noqa
            return rhs


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — block behaviours, DC device loop, and the tick scheduler
# ─────────────────────────────────────────────────────────────────────────────
# A Block wraps one FUNCTION_BLOCK. evaluate() reads its input ports from the
# store (populated by wires the previous propagate) and writes its output ports.
# Port keys in the store are 'BLOCKNAME/PORT' (e.g. 'OR1/OUT_D', 'DC1/PV_D').

_DIGITAL_OPEN = 1
_DIGITAL_CLOSED = 0


class Block:
    def __init__(self, spec):
        self.name = spec['name']
        self.type = spec.get('definition', '')
        self.exprs = spec.get('expressions', []) or []
        self.notes = []

    def _expr_text(self):
        for e in self.exprs:
            if e.get('expression'):
                return e['expression']
        return None

    def port(self, port):
        return f'{self.name}/{port}'

    def evaluate(self, store, ev):
        t = self.type.upper()
        if t == 'CND':
            # Condition: OUT_D = expression; DISABLE mirrors config (unused here -> 0)
            cond = self._expr_text()
            out = 1 if ev.eval_condition(cond) else 0
            store.set(self.port('OUT_D'), out)
            if self.port('DISABLE') not in store.vals:
                store.set(self.port('DISABLE'), 0)
        elif t == 'ACT':
            # Action: run its ST body only while its IN_D enable is asserted.
            en = store.get(self.port('IN_D'), 0)
            if _truthy(en):
                ev.run_action(self._expr_text())
                store.set(self.port('OUT_D'), 1)
            else:
                store.set(self.port('OUT_D'), 0)
        elif t == 'OR':
            v = 0
            for k, val in store.vals.items():
                if k.startswith(self.name + '/IN_D'):
                    if _truthy(val):
                        v = 1
                        break
            store.set(self.port('OUT_D'), v)
        elif t == 'AND':
            ins = [val for k, val in store.vals.items() if k.startswith(self.name + '/IN_D')]
            v = 1 if ins and all(_truthy(x) for x in ins) else 0
            store.set(self.port('OUT_D'), v)
        elif t == 'NOT':
            store.set(self.port('OUT_D'), 0 if _truthy(store.get(self.port('IN_D'), 0)) else 1)
        elif t == 'BFI':
            # Boolean Fan-In: any asserted input -> OUT_D (interlock active).
            ins = [val for k, val in store.vals.items() if k.startswith(self.name + '/IN_D')]
            v = 1 if any(_truthy(x) for x in ins) else 0
            store.set(self.port('OUT_D'), v)
        elif t == 'NDE':
            # Negative-Detect Edge / pass-through: mirror IN_D to OUT_D (edge timing
            # is not material to the steady-state loop we simulate).
            store.set(self.port('OUT_D'), store.get(self.port('IN_D'), 0))
        elif t == 'DC':
            self._eval_dc(store, ev)
        elif t in ('STROKE_COUNT',):
            pass  # diagnostics only; no effect on the command loop
        else:
            # Unknown block: neutral pass-through, flag it.
            self.notes.append(f'block type {self.type} not modelled (neutral)')


    def _eval_dc(self, store, ev):
        """Device Control: the command/feedback core of a 2-state device.

        Contract (from VALVE_2STATE_C / motor CMs, verified against FP005):
          - The module's RSP.CV holds the request (1 = active/open/run,
            0 = passive/closed/stop). ACT blocks (FORCE_ACTIVE/PASSIVE) write it.
          - INTERLOCK_D (wired from NOT1) must be permissive (1) for the device to
            move; if 0 the device holds.
          - The DC drives a discrete OUTPUT (DO) = requested state when permitted.
          - Feedback (DI) is closed by the I/O sim after a travel delay (see
            IOSim.step); the DC reflects confirmed feedback into PV.CV.

        We store, on the module:
          RSP.CV   request (0/1)                (input, written by ACTs/phase)
          DO       commanded discrete output    (DC output -> I/O sim input)
          DI       feedback discrete input      (I/O sim output -> DC input)
          PV.CV    confirmed process value      (output the phase confirms on)
        """
        req = store.get('RSP.CV', 0)
        try:
            req = int(float(req))
        except (TypeError, ValueError):
            # RSP may be an enum like 'vlvnc-sp:OPEN' -> map by suffix
            r = str(req).upper()
            req = 1 if ('OPEN' in r or 'START' in r or 'RUN' in r or r.endswith(':1')) else 0
        # DC1/INTERLOCK_D is wired from NOT1 (the inverse of the BFI interlock
        # aggregator): 1 = permissive / clear to move, 0 = interlocked / hold. So the
        # device may drive its output when INTERLOCK_D is TRUE.
        interlock_ok = _truthy(store.get(self.port('INTERLOCK_D'), 1))
        if interlock_ok:
            store.set('DO', req)         # command the field output
        # (if interlocked, DO holds its previous value)
        # PV is set from the *feedback* DI, which the I/O sim closes — not from the
        # request. This is the whole point of real-sim: the phase waits for DI.
        di = store.get('DI', None)
        if di is not None:
            store.set('PV.CV', 1 if _truthy(di) else 0)


class IOSim:
    """Closes the output->input loop for digital devices. Each device output DO,
    after `travel_ticks`, drives its paired feedback input DI to the same state.
    This is the simple digital example: valve DO=TRUE -> (travel) -> DI=TRUE.

    Manual overrides (for step-through verification):
      hold=True        -> feedback never arrives (DI frozen), so the device never
                          confirms; used to verify the waiting/timeout path.
      force_di=0/1     -> pin DI to a value regardless of DO (force a feedback).
    """

    def __init__(self, travel_ticks=2):
        self.travel_ticks = travel_ticks
        self.hold = False
        self.force_di = None
        self._pending = {}

    def step(self, store):
        if self.force_di is not None:
            store.set('DI', 1 if _truthy(self.force_di) else 0)
            return
        if self.hold:
            return  # feedback frozen — DI stays where it is
        do = store.get('DO', None)
        if do is None:
            return
        do = 1 if _truthy(do) else 0
        di = store.get('DI', None)
        di = None if di is None else (1 if _truthy(di) else 0)
        if do == di:
            self._pending.pop(id(store), None)
            return
        p = self._pending.get(id(store))
        if not p or p['target'] != do:
            self._pending[id(store)] = {'target': do, 'left': self.travel_ticks}
            return
        p['left'] -= 1
        if p['left'] <= 0:
            store.set('DI', do)
            self._pending.pop(id(store), None)


class ModuleSim:
    """One CM/EM instance: its block graph + a signal store + I/O sim.
    Built from fbd_parser.parse_module_fbd() output."""

    def __init__(self, graph, travel_ticks=2):
        self.graph = graph
        self.name = graph.get('name', '')
        self.store = SignalStore(module_prefix=self.name)
        self.io = IOSim(travel_ticks=travel_ticks)
        self.blocks = [Block(b) for b in graph.get('blocks', [])]
        self.wires = graph.get('wires', [])
        self.notes = []
        self._init_ports()

    def _init_ports(self):
        # seed all wire endpoints to 0 so OR/AND fan-ins have defined inputs
        for w in self.wires:
            for ep in (w.get('source', ''), w.get('destination', '')):
                if '/' in ep and not ep.startswith('^'):
                    self.store.vals.setdefault(ep, 0)

    def _propagate(self):
        """Copy each source port value to its destination port along wires."""
        for w in self.wires:
            src = w.get('source', '')
            dst = w.get('destination', '')
            if not src or not dst:
                continue
            val = self.store.get(src, 0)
            # module-level outputs (no '/') are stored as plain keys
            self.store.vals[dst] = val

    def command(self, active):
        """Set the request the way an EM action would: RSP.CV = 1 (active) / 0."""
        self.store.set('RSP.CV', 1 if active else 0)

    def tick(self, ev=None):
        ev = ev or STEval(self.store, self.notes)
        # 1. evaluate every block (reads inputs, writes outputs)
        for b in self.blocks:
            b.evaluate(self.store, ev)
            self.notes.extend(b.notes); b.notes = []
        # 2. propagate wires (outputs -> connected inputs)
        self._propagate()
        # 3. close the field I/O loop (DO -> travel -> DI)
        self.io.step(self.store)

    def run(self, active, max_ticks=40):
        """Command the device and tick until PV confirms (or timeout).
        Returns (confirmed, ticks_used, trace)."""
        self.command(active)
        target = 1 if active else 0
        trace = []
        for i in range(max_ticks):
            self.tick()
            pv = self.store.get('PV.CV', None)
            trace.append({'tick': i, 'RSP': self.store.get('RSP.CV'),
                          'DO': self.store.get('DO'), 'DI': self.store.get('DI'),
                          'PV': pv})
            if pv is not None and (1 if _truthy(pv) else 0) == target:
                return True, i + 1, trace
        return False, max_ticks, trace


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 — EM SFC executor (drives the real command SFC end-to-end)
# ─────────────────────────────────────────────────────────────────────────────
# The EM has a shared store (its own namespace). Each CM member is a child
# ModuleSim. The EM's action expressions write 'INSTANCE/RSP.CV' as ENUM setpoints
# ('vlvnc-sp:CLOSE', 'mtr2-sp:START'); we translate that to the child's boolean
# request, tick the child (closing DO->DI->PV), then reflect the child's confirmed
# PV back into the EM store as the ENUM PV the confirm expressions expect
# ('vlvnc-pv:CLOSED', 'mtr2-pv:RUNNING'). Transitions advance the SFC.

# enum setpoint/PV vocabulary -> active(True)/passive(False)
_SP_ACTIVE = ('OPEN', 'START', 'RUN', 'ON')
_PV_ACTIVE = ('OPEN', 'RUNNING', 'RUN', 'ON')


def _sp_is_active(val):
    s = str(val).upper()
    return any(tok in s for tok in _SP_ACTIVE)


def _enum_family(val):
    """'vlvnc-sp:CLOSE' -> 'vlvnc'; 'mtr2-sp:START' -> 'mtr2'. Used to build the
    matching PV enum so confirm expressions compare equal."""
    s = str(val)
    if '-' in s:
        return s.split('-', 1)[0]
    if ':' in s:
        return s.split(':', 1)[0]
    return s


def _pv_enum_for(family, active):
    """Build the PV enum a confirm expression expects, e.g. family 'vlvnc' +
    active False -> 'vlvnc-pv:CLOSED'; 'mtr2' + active True -> 'mtr2-pv:RUNNING'."""
    fam = family.lower()
    if active:
        word = 'RUNNING' if fam.startswith('mtr') else 'OPEN'
    else:
        word = 'STOPPED' if fam.startswith('mtr') else 'CLOSED'
    return f'{family}-pv:{word}'


class EMSim:
    """Executes one EM command SFC against real child CM sims."""

    def __init__(self, text, em_name, members, command, travel_ticks=2, travel_map=None,
                 resolution=None, instance_tag=None, overrides=None):
        import fbd_parser
        self.em_name = em_name
        self.instance_tag = instance_tag
        self.command = command
        self.overrides = overrides or {}   # member -> {hold:bool, force_di:0/1, force_do:0/1}
        self.store = SignalStore(module_prefix=em_name)
        self.ev = STEval(self.store)
        self.travel_ticks = travel_ticks
        self.travel_map = travel_map or {}   # member -> travel_ticks override
        self.resolution = resolution or {}   # member -> {'tag':real_tag, 'ignore':bool}
        self.notes = []
        # build a child ModuleSim per CM member
        self.children = {}          # member -> ModuleSim
        self.child_family = {}      # member -> enum family
        self.child_tag = {}         # member -> resolved real CM tag (or member name)
        self.child_ignore = {}      # member -> True if IGNORE'd (unassigned/bypassed)
        for m in members:
            inst = m['name']
            cls = m.get('module', '')
            tt = int(self.travel_map.get(inst, travel_ticks))
            res = self.resolution.get(inst, {})
            self.child_tag[inst] = res.get('tag') or inst
            self.child_ignore[inst] = bool(res.get('ignore', False))
            try:
                g = fbd_parser.parse_module_fbd(text, cls)
                self.children[inst] = ModuleSim(g, travel_ticks=tt)
                self.child_family[inst] = self._family_for_class(cls)
            except Exception as e:  # noqa
                self.notes.append(f'child {inst} ({cls}) could not be modelled: {e}')
        # SFC structure for this command
        self.ordered_steps = command.get('ordered_steps', [])
        self.step_names = [s[0] for s in self.ordered_steps]
        self.steps = {s[0]: s[1] for s in self.ordered_steps}
        self.step_to_trans = command.get('step_to_trans', {})
        self.trans_to_step = command.get('trans_to_step', {})
        self.transitions = command.get('transitions', {})
        self.cur = self.step_names[0] if self.step_names else None
        self.done = False
        self._seed_ignores()

    def _seed_ignores(self):
        # A member that's IGNORE'd in the deployed instance (unassigned) is bypassed:
        # set its '_IGNORE.CV' TRUE so its confirm (which ORs against _IGNORE.CV) passes
        # immediately — exactly how DeltaV treats an unassigned member. Assigned members
        # start FALSE so the real feedback path is what satisfies them.
        for inst in self.children:
            self.store.set(f'{inst}/_IGNORE.CV', bool(self.child_ignore.get(inst, False)))

    # -- action execution ----------------------------------------------------
    def _run_step_actions(self, step, step_name):
        """Run each action's assignment (if its delay gate is open), then translate
        any 'INSTANCE/RSP.CV' enum writes into the child sim's request.

        DeltaV action-state model: an action that isn't gated (or whose gate is
        open) runs and, once its confirm_expression holds, reaches 'Complete',
        published as 'S<step>/A<n>/STATE.CV = $sfc_action_states:Complete'. Later
        actions gate on that (e.g. A3 waits for A2 Complete)."""
        for a in step.get('actions', []):
            an = a.get('action', '')
            state_key = f'{step_name}/{an}/STATE.CV'
            dexpr = a.get('delay_expression', '')
            gate_open = (not dexpr) or self.ev.eval_condition(dexpr)
            if not gate_open:
                continue
            self.ev.run_action(a.get('expression', ''))
            # once this action's confirm holds, mark it Complete so gated peers run
            cexpr = a.get('confirm_expression', '')
            if (not cexpr) or self.ev.eval_condition(cexpr):
                self.store.set(state_key, '$sfc_action_states:Complete')
            else:
                if self.store.get(state_key, '') != '$sfc_action_states:Complete':
                    self.store.set(state_key, '$sfc_action_states:Running')
        self._route_requests_to_children()

    def _route_requests_to_children(self):
        for inst, child in self.children.items():
            rsp = self.store.get(f'{inst}/RSP.CV', None)
            if rsp is None:
                continue
            active = _sp_is_active(rsp)
            fam = _enum_family(rsp)
            if fam and ':' in str(rsp):
                self.child_family[inst] = fam
            child.command(active)

    # -- confirm accounting --------------------------------------------------
    def _pending_confirms(self, step_name, step):
        """Count actions whose confirm_expression is not yet satisfied and publish
        'S<step>/PENDING_CONFIRMS.CV' (the transition reads it)."""
        pending = 0
        for a in step.get('actions', []):
            cexpr = a.get('confirm_expression', '')
            if not cexpr:
                continue
            if not self.ev.eval_condition(cexpr):
                pending += 1
        self.store.set(f'{step_name}/PENDING_CONFIRMS.CV', pending)
        return pending

    def _child_state(self, inst, c):
        """Per-device state for the trace: the command/feedback chain plus interlock
        diagnostics, so the CM window can explain WHY a device is (or isn't) moving."""
        cs = c.store
        ilks = []
        for b in c.blocks:
            if b.type.upper() == 'CND' and b.name.upper().startswith('ILK'):
                asserted = _truthy(cs.get(b.name + '/OUT_D', 0))
                ilks.append({'name': b.name, 'active': asserted,
                             'expr': (b._expr_text() or '')[:80]})
        permissive = _truthy(cs.get('DC1/INTERLOCK_D', 1))
        return {
            'rsp': self.store.get(f'{inst}/RSP.CV'),
            'do': cs.get('DO'), 'di': cs.get('DI'),
            'pv': self.store.get(f'{inst}/PV.CV'),
            'travel': c.io.travel_ticks,
            'permissive': permissive,
            'interlock_active': (not permissive),
            'ilks': ilks,
            'module': c.name,
            'family': self.child_family.get(inst, ''),
            'tag': self.child_tag.get(inst, inst),      # resolved real CM tag
            'ignore': self.child_ignore.get(inst, False),
        }

    def _reflect_children(self):
        """Tick each child and reflect its confirmed PV back to the EM store as the
        enum PV the confirm expressions compare against. Always resolve to an enum
        (family seeded from the device class), so a device at rest reads its passive
        enum (STOPPED/CLOSED) from tick 0 rather than a bare 0."""
        for inst, child in self.children.items():
            ov = self.overrides.get(inst) or {}
            # apply manual overrides to this device's I/O loop before it ticks
            child.io.hold = bool(ov.get('hold'))
            child.io.force_di = ov.get('force_di', None)
            if ov.get('force_do', None) is not None:
                child.store.set('DO', 1 if _truthy(ov['force_do']) else 0)
            child.tick()
            pv = child.store.get('PV.CV', None)
            if pv is None:
                pv = 0  # unmodelled PV -> treat as passive so the enum still resolves
            fam = self.child_family.get(inst)
            if fam and ':' not in str(pv):
                active = _truthy(pv)
                self.store.set(f'{inst}/PV.CV', _pv_enum_for(fam, active))
            else:
                self.store.set(f'{inst}/PV.CV', pv)

    @staticmethod
    def _family_for_class(cls):
        """Map a CM class to its PV/SP enum family so PVs render as the enums the
        confirm expressions expect. FP005 uses 'mtr2-*' for motors and 'vlvnc-*' for
        2-state valves; fall back by keyword."""
        u = (cls or '').upper()
        if 'MTR' in u or 'MOTOR' in u or 'PUMP' in u:
            return 'mtr2'
        if 'VALVE' in u or 'VLV' in u:
            return 'vlvnc'
        return ''


    # -- time model (steps expose S<n>/TIME.CV; transitions may use it) -------
    def _bump_time(self, step_name, dt=1):
        k = f'{step_name}/TIME.CV'
        self.store.set(k, self.store.get(k, 0) + dt)

    def _action_details(self, step, step_name):
        """For the active step, produce a per-action requested-vs-actual breakdown
        so the UI can show what each SFC action asked for against what actually
        happened. For an assignment 'LHS := RHS':
          requested = the target and value written (RHS)
          expected  = the confirm_expression's comparison (what SHOULD become true)
          actual    = the live value of the confirmed signal now
          confirmed = whether the confirm_expression holds this tick
        """
        out = []
        for a in step.get('actions', []):
            an = a.get('action', '')
            expr = (a.get('expression', '') or '').strip()
            cexpr = (a.get('confirm_expression', '') or '').strip()
            # requested: parse first 'LHS := RHS'
            req_target = req_val = ''
            mm = re.search(r"([^\s;]+)\s*:=\s*([^\s;]+)", expr)
            if mm:
                lhs = SignalStore.norm(mm.group(1))
                # the CM instance is the segment before '/RSP' (or the whole LHS root)
                inst_m = re.match(r'([A-Za-z0-9_]+)/', lhs)
                req_target = inst_m.group(1) if inst_m else lhs
                req_val = mm.group(2).strip().strip("'\"")
            # actual: read the confirm target's live value. The confirm usually reads a
            # PV/readback; pull the first reference in the confirm expression.
            actual = ''
            cref = re.search(r"'(\^?/?[A-Za-z0-9_./]+)'", cexpr)
            if cref:
                actual = self.store.get(cref.group(1), '')
            # expected: the literal the confirm compares against (first quoted enum/int)
            expected = ''
            eref = re.findall(r"=\s*'([^']+)'|=\s*(\d+)", cexpr)
            if eref:
                first = eref[0]
                expected = first[0] or first[1]
            confirmed = (not cexpr) or self.ev.eval_condition(cexpr)
            # gate state (Complete/Running/blocked)
            dexpr = a.get('delay_expression', '')
            gate_open = (not dexpr) or self.ev.eval_condition(dexpr)
            out.append({
                'action': an,
                'desc': a.get('description', ''),
                'qualifier': a.get('qualifier', ''),
                'request': (expr.rstrip(';').strip()[:70] if expr else ''),
                'req_target': req_target, 'req_val': req_val,
                'expected': str(expected),
                'actual': _fmt_val(actual),
                'confirmed': bool(confirmed),
                'gated': (not gate_open),
            })
        return out

    # -- one tick of the EM SFC ---------------------------------------------
    def tick(self):
        if self.done or not self.cur:
            return
        step = self.steps[self.cur]
        self._run_step_actions(step, self.cur)   # writes RSP, routes to children
        self._reflect_children()                 # ticks children, updates PV enums
        self._update_action_states(step, self.cur)  # re-check confirms post-feedback
        self._pending_confirms(self.cur, step)
        self._bump_time(self.cur)
        # evaluate the step's outgoing transition(s)
        for tn in self.step_to_trans.get(self.cur, []):
            texpr = self.transitions.get(tn, {}).get('expression', '')
            if self.ev.eval_condition(texpr):
                nxts = self.trans_to_step.get(tn, [])
                if nxts:
                    self.cur = nxts[0]
                else:
                    self.done = True     # terminal transition -> command complete
                return
        # no outgoing transition at all -> terminal step
        if not self.step_to_trans.get(self.cur):
            self.done = True

    def _update_action_states(self, step, step_name):
        """After children have ticked (PVs updated), promote any action whose
        confirm now holds to Complete — this unblocks peers gated on it and lets
        the DO->DI->PV feedback close across ticks."""
        for a in step.get('actions', []):
            an = a.get('action', '')
            state_key = f'{step_name}/{an}/STATE.CV'
            cexpr = a.get('confirm_expression', '')
            if (not cexpr) or self.ev.eval_condition(cexpr):
                self.store.set(state_key, '$sfc_action_states:Complete')

    def run(self, max_ticks=200):
        trace = []
        for i in range(max_ticks):
            prev = self.cur
            prev_desc = self.steps.get(prev, {}).get('description', '') if prev else ''
            prev_step = self.steps.get(prev, {}) if prev else {}
            self.tick()
            trace.append({
                'tick': i, 'step': prev, 'step_desc': prev_desc,
                'pending': self.store.get(f'{prev}/PENDING_CONFIRMS.CV') if prev else None,
                'actions': self._action_details(prev_step, prev) if prev else [],
                'children': {inst: self._child_state(inst, c)
                             for inst, c in self.children.items()},
                'advanced_to': self.cur if self.cur != prev else None,
                'done': self.done,
            })
            if self.done:
                return True, i + 1, trace
        return False, max_ticks, trace

    def layout(self):
        """SFC geometry for the verification view: steps + transitions with their
        stored X/Y, plus which CM instance each action targets (for future
        click-through to the CM status)."""
        steps = []
        for sid, s in self.ordered_steps:
            # map each action to the CM instance it targets (RSP write target)
            acts = []
            for a in s.get('actions', []):
                expr = a.get('expression', '') or ''
                mm = re.search(r"'?\^?/?([A-Za-z0-9_]+)/RSP", expr)
                acts.append({'action': a.get('action', ''),
                             'desc': a.get('description', ''),
                             'target': mm.group(1) if mm else ''})
            steps.append({'id': sid, 'x': s.get('x', 0), 'y': s.get('y', 0),
                          'desc': s.get('description', ''), 'actions': acts,
                          'initial': s.get('initial', False)})
        trans = []
        for tid, td in self.transitions.items():
            trans.append({'id': tid, 'x': td.get('x', 0), 'y': td.get('y', 0),
                          'expr': td.get('expression', '')})
        return {'steps': steps, 'transitions': trans,
                'step_to_trans': self.step_to_trans,
                'trans_to_step': self.trans_to_step}


def resolve_em_instance(text, instance_tag):
    """Read a deployed EM instance's MODULE_BLOCK_RESOLUTION table: how each class
    member (CAS_DRN, RTN_PUMP_E3, ...) maps to a real assigned CM tag (XP070-HV-008)
    and whether it's IGNORE'd (unassigned / bypassed). Returns:
      {'class': em_class, 'members': {member: {'tag':..., 'ignore':bool}}}
    or None if the tag isn't a deployed EM instance.
    """
    m = re.search(r'MODULE_INSTANCE TAG="' + re.escape(instance_tag) +
                  r'" PLANT_AREA="([^"]*)" MODULE_CLASS="([^"]+)"(.*?)'
                  r'(?=\nMODULE_INSTANCE |\Z)', text, re.DOTALL)
    if not m:
        return None
    area, cls, blk = m.group(1), m.group(2), m.group(3)
    members = {}
    for name, mod, ig in re.findall(
            r'MODULE_BLOCK_RESOLUTION NAME="([^"]+)"\s*\{\s*MODULE="([^"]*)"\s*'
            r'IGNORE=([TF])', blk):
        members[name] = {'tag': mod, 'ignore': (ig == 'T' or not mod)}
    return {'class': cls, 'area': area, 'members': members}


def em_instances_for_class(text, em_class):
    """List deployed instance tags for an EM class (for the class-view instance
    picker)."""
    out = []
    for tag, area, cls in re.findall(
            r'MODULE_INSTANCE TAG="([^"]+)" PLANT_AREA="([^"]*)" MODULE_CLASS="([^"]+)"',
            text):
        if cls == em_class:
            out.append({'tag': tag, 'area': area})
    return out


def _em_class_of(text, name):
    """Given a name that may be an EM class OR a deployed instance tag, return
    (em_class, instance_tag_or_None)."""
    res = resolve_em_instance(text, name)
    if res:
        return res['class'], name
    return name, None


def simulate_em_command(text, em_name, command_name, travel_ticks=2, max_ticks=200,
                        travel_map=None, instance_tag=None, overrides=None):
    """Top-level entry: run one EM command SFC end-to-end against real child CMs.
    `em_name` may be an EM class OR a deployed instance tag; if an instance is given
    (or `instance_tag`), members resolve to their real assigned CM tags and IGNORE'd
    members are bypassed. `overrides` (member -> {hold, force_di, force_do}) supports
    manual step-through verification. Returns (completed, ticks, trace, notes, layout)."""
    import em_bridge
    em_class, inst = _em_class_of(text, em_name)
    if instance_tag:
        inst = instance_tag
    resolution = {}
    if inst:
        r = resolve_em_instance(text, inst)
        if r:
            em_class = r['class']
            resolution = r['members']
    core, _sfc = em_bridge._load_core()
    cmds = core['parse_cdem_fhx'](text)
    own = [c for c in cmds if (c.get('em_name') or '') == em_class
           and c.get('command_name') == command_name]
    if not own:
        return False, 0, [], [f'command {command_name!r} not found on EM {em_class!r}'], {}
    members = em_bridge.em_cm_members(text, em_class)
    sim = EMSim(text, em_class, members, own[0], travel_ticks=travel_ticks,
                travel_map=travel_map, resolution=resolution, instance_tag=inst,
                overrides=overrides)
    completed, ticks, trace = sim.run(max_ticks=max_ticks)
    return completed, ticks, trace, sim.notes, sim.layout()


def em_sim_meta(text, em_name):
    """Describe an EM for the real-sim UI: its commands, its CM members (with device
    family, the resolved real CM tag when run on a deployed instance, and whether the
    member is IGNORE'd/unassigned). `em_name` may be a class or an instance tag."""
    import em_bridge, fbd_parser
    core, _sfc = em_bridge._load_core()
    # resolve class vs instance
    em_class, inst = _em_class_of(text, em_name)
    resolution = {}
    if inst:
        r = resolve_em_instance(text, inst)
        if r:
            em_class = r['class']
            resolution = r['members']
    try:
        cmds = core['parse_cdem_fhx'](text)
    except Exception:
        cmds = []
    names = []
    for c in cmds:
        if (c.get('em_name') or '') == em_class:
            cn = c.get('command_name', '')
            if cn and cn not in names:
                names.append(cn)
    members = em_bridge.em_cm_members(text, em_class)
    dev = []
    for m in members:
        member = m['name']
        cls = m.get('module', '')
        fam = 'motor' if ('MTR' in cls.upper() or 'MOTOR' in cls.upper()
                          or 'PUMP' in cls.upper()) else (
              'valve' if ('VALVE' in cls.upper() or 'VLV' in cls.upper()) else 'device')
        modelled = True
        try:
            fbd_parser.parse_module_fbd(text, cls)
        except Exception:
            modelled = False
        default_travel = 20 if fam == 'motor' else (10 if fam == 'valve' else 5)
        res = resolution.get(member, {})
        tag = res.get('tag') or ''
        ignore = bool(res.get('ignore', False)) if resolution else False
        dev.append({'instance': member, 'member': member, 'tag': tag or member,
                    'resolved': bool(tag), 'ignore': ignore,
                    'module': cls, 'family': fam,
                    'modelled': modelled, 'default_travel': default_travel,
                    'desc': m.get('desc', '')})
    return {'em': em_class, 'instance': inst, 'commands': names, 'devices': dev,
            'instances': em_instances_for_class(text, em_class)}
