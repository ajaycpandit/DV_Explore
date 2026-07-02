"""
sim_eval.py  —  SIMULATOR SPIKE (task 2): a minimal evaluator for the DeltaV
structured-text subset used by phase SFC transitions and actions.

This is a spike: it imports nothing from the explorer and touches nothing in it.
Goal: prove the real transition/action expressions from a phase RUN sequence can
be tokenized, parsed, and evaluated against a flat variable store.

Grammar covered (derived from the actual CIP WASH RUN sequence):
  transitions (boolean):
      ref/literal compared with = != <> < > <= >=, combined with AND/OR/NOT,
      parenthesised, plus bare-boolean (truthy) terms.
  actions (statements):
      <ref> := <expr> ;            assignment
      IF (<expr>) THEN <stmts> [ELSE <stmts>] END_IF ;
      ;-separated, multi-line statement sequences.

References resolve to a flat dict by their raw text (quotes stripped); within one
phase the reference strings are internally consistent, so no scope resolution is
needed for the spike. Named-set members ('SET:MEMBER') resolve to their integer
value when SET is known. Unknown variables read as 0 (falsy).
"""

import re


# ───────────────────────────── value model ──────────────────────────────────
class Ref:
    __slots__ = ('key',)

    def __init__(self, key):
        self.key = key

    def __repr__(self):
        return f'Ref({self.key!r})'


def _truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v != ''
    return v is not None


def _num(v):
    """Coerce booleans to 0/1 so 'X = 1' and 'X = TRUE' both work."""
    if isinstance(v, bool):
        return 1 if v else 0
    return v


def _as_str(v):
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _numf(v):
    """Numeric coercion for math builtins."""
    v = _num(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _call_builtin(fn, args):
    """DeltaV structured-text builtins (mostly used in message construction).
    Unknown functions pass through their first arg so a message still renders."""
    import math
    if fn == 'round':
        return int(round(_numf(args[0])))
    if fn in ('trunc', 'int'):
        return int(_numf(args[0]))
    if fn == 'abs':
        return abs(_numf(args[0]))
    if fn == 'float':
        return _numf(args[0])
    if fn == 'sqrt':
        return math.sqrt(_numf(args[0]))
    if fn == 'min':
        r = min(_numf(a) for a in args)
        return int(r) if r == int(r) else r
    if fn == 'max':
        r = max(_numf(a) for a in args)
        return int(r) if r == int(r) else r
    if fn in ('time', 'time_to_str'):
        return '<time>'
    if fn == 'date_to_str':
        return '<date>'
    if fn == 'str':
        return _as_str(args[0]) if args else ''
    if fn == 'str_to_int':
        try:
            return int(_as_str(args[0]))
        except (ValueError, TypeError):
            return 0
    if fn == 'str_to_float':
        try:
            return float(_as_str(args[0]))
        except (ValueError, TypeError):
            return 0.0
    if fn == 'len':
        return len(_as_str(args[0])) if args else 0
    return args[0] if args else 0   # unknown fn: pass through


# ───────────────────────────── tokenizer ────────────────────────────────────
_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<ref>'(?:[^']|'')*')                 # 'a/b.CV'  or  'SET:MEMBER'
  | (?P<str>"[^"]*")                         # "text"  (quotes already un-doubled)
  | (?P<denum>\$[A-Za-z_][A-Za-z0-9_]*:[^)'"\s,;]+)   # $time_format:Local
  | (?P<num>\d+\.\d+|\d+)
  | (?P<op>:=|<=|>=|<>|!=|=|<|>|\+|\-|\*|/)
  | (?P<punc>[(),] | ;)
  | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
""", re.VERBOSE)

_KEYWORDS = {'AND', 'OR', 'NOT', 'IF', 'THEN', 'ELSE', 'END_IF', 'ENDIF', 'TRUE', 'FALSE'}


def tokenize(src):
    # strip (* ... *) block comments and `rem ...` line comments, then un-double
    # the FHX-escaped quotes once.
    src = re.sub(r'\(\*.*?\*\)', '', src, flags=re.DOTALL)
    src = re.sub(r'(^|[;\r\n])[ \t]*rem\b[^\r\n]*', r'\1', src, flags=re.IGNORECASE)
    src = src.replace('""', '"')
    toks, i, n = [], 0, len(src)
    while i < n:
        m = _TOKEN_RE.match(src, i)
        if not m:
            raise SyntaxError(f'cannot tokenize at: {src[i:i+30]!r}')
        i = m.end()
        kind = m.lastgroup
        if kind == 'ws':
            continue
        val = m.group()
        if kind == 'ref':
            toks.append(('ref', val[1:-1].replace("''", "'")))
        elif kind == 'str':
            toks.append(('str', val[1:-1]))
        elif kind == 'denum':
            toks.append(('str', val))   # $time_format:Local -> literal string
        elif kind == 'num':
            toks.append(('num', float(val) if '.' in val else int(val)))
        elif kind == 'word':
            up = val.upper()
            toks.append((up if up in _KEYWORDS else 'word', val))
        else:  # op / punc
            toks.append((val.strip(), val.strip()))
    toks.append(('eof', None))
    return toks


# ───────────────────────────── parser ───────────────────────────────────────
class Parser:
    def __init__(self, toks, named_sets=None):
        self.t = toks
        self.p = 0
        self.sets = named_sets or {}

    def _peek(self):
        return self.t[self.p]

    def _next(self):
        tok = self.t[self.p]
        self.p += 1
        return tok

    def _expect(self, kind):
        tok = self._next()
        if tok[0] != kind:
            raise SyntaxError(f'expected {kind}, got {tok}')
        return tok

    # -- expressions --
    def parse_expr(self):
        return self._or()

    def _or(self):
        node = self._and()
        while self._peek()[0] == 'OR':
            self._next()
            node = ('or', node, self._and())
        return node

    def _and(self):
        node = self._not()
        while self._peek()[0] == 'AND':
            self._next()
            node = ('and', node, self._not())
        return node

    def _not(self):
        if self._peek()[0] == 'NOT':
            self._next()
            return ('not', self._not())
        return self._cmp()

    def _cmp(self):
        node = self._add()
        if self._peek()[0] in ('=', '!=', '<>', '<', '>', '<=', '>='):
            op = self._next()[0]
            rhs = self._add()
            return ('cmp', '!=' if op == '<>' else op, node, rhs)
        return node

    def _add(self):
        node = self._mul()
        while self._peek()[0] in ('+', '-'):
            op = self._next()[0]
            node = ('bin', op, node, self._mul())
        return node

    def _mul(self):
        node = self._primary()
        while self._peek()[0] in ('*', '/'):
            op = self._next()[0]
            node = ('bin', op, node, self._primary())
        return node

    def _primary(self):
        kind, val = self._peek()
        if kind == '(':
            self._next()
            node = self.parse_expr()
            self._expect(')')
            return node
        if kind == 'num':
            self._next(); return ('lit', val)
        if kind == 'str':
            self._next(); return ('lit', val)
        if kind == 'TRUE':
            self._next(); return ('lit', True)
        if kind == 'FALSE':
            self._next(); return ('lit', False)
        if kind == 'ref':
            self._next()
            return self._ref_or_member(val)
        if kind == 'word':
            self._next()
            # function call?  word( args )
            if self._peek()[0] == '(':
                self._next()
                args = []
                if self._peek()[0] != ')':
                    args.append(self.parse_expr())
                    while self._peek()[0] == ',':
                        self._next(); args.append(self.parse_expr())
                self._expect(')')
                return ('call', val.lower(), args)
            return ('ref', val)
        raise SyntaxError(f'unexpected token {self._peek()}')

    def _ref_or_member(self, raw):
        # 'SET:MEMBER' with a known set -> integer literal; else a variable ref.
        if ':' in raw:
            setname, _, member = raw.partition(':')
            members = self.sets.get(setname)
            if members is not None:
                return ('lit', members.get(member, raw))
            # unknown set: keep as opaque string literal so comparisons still work
            return ('lit', raw)
        return ('ref', Ref(raw))

    # -- statements --
    def parse_stmts(self):
        stmts = []
        while self._peek()[0] not in ('eof', 'END_IF', 'ENDIF', 'ELSE'):
            if self._peek()[0] == ';':
                self._next(); continue
            stmts.append(self._stmt())
            if self._peek()[0] == ';':
                self._next()
        return ('block', stmts)

    def _stmt(self):
        if self._peek()[0] == 'IF':
            self._next()
            cond = self.parse_expr()
            self._expect('THEN')
            then = self.parse_stmts()
            els = None
            if self._peek()[0] == 'ELSE':
                self._next()
                els = self.parse_stmts()
            if self._peek()[0] in ('END_IF', 'ENDIF'):
                self._next()
            else:
                self._expect('END_IF')
            return ('if', cond, then, els)
        # assignment:  ref := expr  (ref is normally '^/...'; also allow a bare
        # word for DeltaV local/temporary variables like COUNT := 0)
        kind, val = self._next()
        if kind not in ('ref', 'word'):
            raise SyntaxError(f'assignment must start with a ref, got {(kind, val)}')
        self._expect(':=')
        return ('assign', Ref(val), self.parse_expr())


# ───────────────────────────── evaluator ────────────────────────────────────
class Evaluator:
    def __init__(self, store, named_sets=None):
        self.store = store          # flat dict: key -> value
        self.sets = named_sets or {}

    def _read(self, ref):
        return self.store.get(ref.key, 0)

    def eval(self, node):
        op = node[0]
        if op == 'lit':
            return node[1]
        if op == 'ref':
            r = node[1]
            return self._read(r) if isinstance(r, Ref) else self.store.get(r, 0)
        if op == 'not':
            return not _truthy(self.eval(node[1]))
        if op == 'call':
            return _call_builtin(node[1], [self.eval(a) for a in node[2]])
        if op == 'bin':
            _, o, a, b = node
            l, r = self.eval(a), self.eval(b)
            if o == '+':
                if isinstance(l, str) or isinstance(r, str):
                    return _as_str(l) + _as_str(r)        # string concat
                return _num(l) + _num(r)
            if o == '-':
                return _num(l) - _num(r)
            if o == '*':
                return _num(l) * _num(r)
            if o == '/':
                return _num(l) / _num(r) if _num(r) else 0
        if op == 'and':
            return _truthy(self.eval(node[1])) and _truthy(self.eval(node[2]))
        if op == 'or':
            return _truthy(self.eval(node[1])) or _truthy(self.eval(node[2]))
        if op == 'cmp':
            _, c, a, b = node
            l, r = self.eval(a), self.eval(b)
            if isinstance(l, str) or isinstance(r, str):
                ll, rr = l, r          # string compare as-is
            else:
                ll, rr = _num(l), _num(r)
            if c == '=':
                return ll == rr
            if c == '!=':
                return ll != rr
            if c == '<':
                return ll < rr
            if c == '>':
                return ll > rr
            if c == '<=':
                return ll <= rr
            if c == '>=':
                return ll >= rr
        raise ValueError(f'bad expr node {node}')

    def exec(self, node):
        op = node[0]
        if op == 'block':
            for s in node[1]:
                self.exec(s)
        elif op == 'assign':
            self.store[node[1].key] = self.eval(node[2])
        elif op == 'if':
            if _truthy(self.eval(node[1])):
                self.exec(node[2])
            elif node[3] is not None:
                self.exec(node[3])
        else:
            raise ValueError(f'bad stmt node {node}')


# ───────────────────────────── public API ───────────────────────────────────
def eval_transition(expr_src, store, named_sets=None):
    """Evaluate a transition expression -> bool. Trailing ';' is tolerated."""
    src = expr_src.strip().rstrip(';')
    if not src:
        return True
    toks = tokenize(src)
    ast = Parser(toks, named_sets).parse_expr()
    return _truthy(Evaluator(store, named_sets).eval(ast))


def run_actions(action_src, store, named_sets=None):
    """Execute an action body (statement sequence) against the store in place."""
    if not action_src or not action_src.strip():
        return
    toks = tokenize(action_src)
    ast = Parser(toks, named_sets).parse_stmts()
    Evaluator(store, named_sets).exec(ast)
