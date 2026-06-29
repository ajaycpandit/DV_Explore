/* sim_eval.js — JS port of sim_eval.py (Option 1).
 *
 * Faithful 1:1 port of the DeltaV structured-text evaluator: tokenizer +
 * recursive-descent parser + tree-walking evaluator. Same grammar, same
 * coercion rules, so a walk driven by this engine reproduces the Python walk.
 *
 * Parity notes (where JS and Python differ, we force Python semantics):
 *  - truthiness: '' / 0 / false / null => falsy; everything else truthy.
 *  - numeric coercion: booleans -> 0/1 for arithmetic & numeric compare.
 *  - '=' is EQUALITY (not assignment) inside expressions; ':=' is assignment.
 *  - string vs number compare: if either side is a string, compare as strings
 *    (matches Python's branch); else compare numerically.
 *  - unknown refs read as 0 (falsy), exactly like store.get(key, 0).
 *
 * Exposed: tokenize, Parser, Evaluator, evalTransition, runActions, makeRef.
 * No DOM, no globals — safe to node --check and unit-test standalone.
 */
(function (root) {
  'use strict';

  // ── value model ──────────────────────────────────────────────────────────
  function Ref(key) { this.key = key; }
  function makeRef(key) { return new Ref(key); }
  function isRef(v) { return v instanceof Ref; }

  function truthy(v) {
    if (typeof v === 'boolean') return v;
    if (typeof v === 'number') return v !== 0;
    if (typeof v === 'string') return v !== '';
    return v !== null && v !== undefined;
  }

  // Coerce booleans to 0/1 so 'X = 1' and 'X = TRUE' both work.
  function num(v) {
    if (typeof v === 'boolean') return v ? 1 : 0;
    return v;
  }

  function asStr(v) {
    if (typeof v === 'boolean') return v ? 'True' : 'False';   // match Python repr
    if (typeof v === 'number' && Number.isInteger(v)) return String(v);
    return String(v);
  }

  // ── tokenizer ────────────────────────────────────────────────────────────
  // Mirrors the Python verbose regex, evaluated left-to-right with sticky flags.
  const KEYWORDS = new Set(
    ['AND', 'OR', 'NOT', 'IF', 'THEN', 'ELSE', 'END_IF', 'ENDIF', 'TRUE', 'FALSE']);

  // Order matters: longer operators before shorter prefixes.
  const SUBPATTERNS = [
    ['ws',   /\s+/y],
    ['ref',  /'(?:[^']|'')*'/y],            // 'a/b.CV' or 'SET:MEMBER'
    ['str',  /"[^"]*"/y],                    // "text"
    ['num',  /\d+\.\d+|\d+/y],
    ['op',   /:=|<=|>=|<>|!=|=|<|>|\+|\-|\*|\//y],
    ['punc', /[()]|;/y],
    ['word', /[A-Za-z_][A-Za-z0-9_]*/y],
  ];

  function tokenize(srcIn) {
    // strip (* ... *) comments, then un-double FHX-escaped quotes once.
    let src = srcIn.replace(/\(\*[\s\S]*?\*\)/g, '');
    src = src.split('""').join('"');
    const toks = [];
    let i = 0;
    const n = src.length;
    while (i < n) {
      let matched = false;
      for (let s = 0; s < SUBPATTERNS.length; s++) {
        const kind = SUBPATTERNS[s][0];
        const re = SUBPATTERNS[s][1];
        re.lastIndex = i;
        const m = re.exec(src);
        if (m && m.index === i) {
          matched = true;
          i = re.lastIndex;
          const val = m[0];
          if (kind === 'ws') { /* skip */ }
          else if (kind === 'ref') {
            toks.push(['ref', val.slice(1, -1).split("''").join("'")]);
          } else if (kind === 'str') {
            toks.push(['str', val.slice(1, -1)]);
          } else if (kind === 'num') {
            toks.push(['num', val.indexOf('.') >= 0 ? parseFloat(val) : parseInt(val, 10)]);
          } else if (kind === 'word') {
            const up = val.toUpperCase();
            toks.push([KEYWORDS.has(up) ? up : 'word', val]);
          } else { // op / punc
            const t = val.trim();
            toks.push([t, t]);
          }
          break;
        }
      }
      if (!matched) {
        throw new SyntaxError('cannot tokenize at: ' + JSON.stringify(src.slice(i, i + 30)));
      }
    }
    toks.push(['eof', null]);
    return toks;
  }

  // ── parser ───────────────────────────────────────────────────────────────
  function Parser(toks, namedSets) {
    this.t = toks;
    this.p = 0;
    this.sets = namedSets || {};
  }
  Parser.prototype._peek = function () { return this.t[this.p]; };
  Parser.prototype._next = function () { return this.t[this.p++]; };
  Parser.prototype._expect = function (kind) {
    const tok = this._next();
    if (tok[0] !== kind) throw new SyntaxError('expected ' + kind + ', got ' + JSON.stringify(tok));
    return tok;
  };

  Parser.prototype.parseExpr = function () { return this._or(); };
  Parser.prototype._or = function () {
    let node = this._and();
    while (this._peek()[0] === 'OR') { this._next(); node = ['or', node, this._and()]; }
    return node;
  };
  Parser.prototype._and = function () {
    let node = this._not();
    while (this._peek()[0] === 'AND') { this._next(); node = ['and', node, this._not()]; }
    return node;
  };
  Parser.prototype._not = function () {
    if (this._peek()[0] === 'NOT') { this._next(); return ['not', this._not()]; }
    return this._cmp();
  };
  Parser.prototype._cmp = function () {
    const node = this._add();
    const k = this._peek()[0];
    if (k === '=' || k === '!=' || k === '<>' || k === '<' || k === '>' || k === '<=' || k === '>=') {
      const op = this._next()[0];
      const rhs = this._add();
      return ['cmp', op === '<>' ? '!=' : op, node, rhs];
    }
    return node;
  };
  Parser.prototype._add = function () {
    let node = this._mul();
    while (this._peek()[0] === '+' || this._peek()[0] === '-') {
      const op = this._next()[0];
      node = ['bin', op, node, this._mul()];
    }
    return node;
  };
  Parser.prototype._mul = function () {
    let node = this._primary();
    while (this._peek()[0] === '*' || this._peek()[0] === '/') {
      const op = this._next()[0];
      node = ['bin', op, node, this._primary()];
    }
    return node;
  };
  Parser.prototype._primary = function () {
    const tok = this._peek();
    const kind = tok[0], val = tok[1];
    if (kind === '(') { this._next(); const node = this.parseExpr(); this._expect(')'); return node; }
    if (kind === 'num') { this._next(); return ['lit', val]; }
    if (kind === 'str') { this._next(); return ['lit', val]; }
    if (kind === 'TRUE') { this._next(); return ['lit', true]; }
    if (kind === 'FALSE') { this._next(); return ['lit', false]; }
    if (kind === 'ref') { this._next(); return this._refOrMember(val); }
    if (kind === 'word') { this._next(); return ['ref', val]; }
    throw new SyntaxError('unexpected token ' + JSON.stringify(this._peek()));
  };
  Parser.prototype._refOrMember = function (raw) {
    if (raw.indexOf(':') >= 0) {
      const idx = raw.indexOf(':');
      const setname = raw.slice(0, idx), member = raw.slice(idx + 1);
      const members = this.sets[setname];
      if (members !== undefined && members !== null) {
        return ['lit', (member in members) ? members[member] : raw];
      }
      return ['lit', raw];
    }
    return ['ref', new Ref(raw)];
  };

  // statements
  Parser.prototype.parseStmts = function () {
    const stmts = [];
    while (true) {
      const k = this._peek()[0];
      if (k === 'eof' || k === 'END_IF' || k === 'ENDIF' || k === 'ELSE') break;
      if (k === ';') { this._next(); continue; }
      stmts.push(this._stmt());
      if (this._peek()[0] === ';') this._next();
    }
    return ['block', stmts];
  };
  Parser.prototype._stmt = function () {
    if (this._peek()[0] === 'IF') {
      this._next();
      const cond = this.parseExpr();
      this._expect('THEN');
      const then = this.parseStmts();
      let els = null;
      if (this._peek()[0] === 'ELSE') { this._next(); els = this.parseStmts(); }
      const k = this._peek()[0];
      if (k === 'END_IF' || k === 'ENDIF') this._next();
      else this._expect('END_IF');
      return ['if', cond, then, els];
    }
    const tok = this._next();
    if (tok[0] !== 'ref') throw new SyntaxError('assignment must start with a ref, got ' + JSON.stringify(tok));
    this._expect(':=');
    return ['assign', new Ref(tok[1]), this.parseExpr()];
  };

  // ── evaluator ──────────────────────────────────────────────────────────────
  function Evaluator(store, namedSets) {
    this.store = store;
    this.sets = namedSets || {};
  }
  Evaluator.prototype._read = function (ref) {
    const v = this.store[ref.key];
    return v === undefined ? 0 : v;
  };
  Evaluator.prototype.eval = function (node) {
    const op = node[0];
    if (op === 'lit') return node[1];
    if (op === 'ref') {
      const r = node[1];
      if (isRef(r)) return this._read(r);
      const v = this.store[r];
      return v === undefined ? 0 : v;
    }
    if (op === 'not') return !truthy(this.eval(node[1]));
    if (op === 'bin') {
      const o = node[1];
      const l = this.eval(node[2]), r = this.eval(node[3]);
      if (o === '+') {
        if (typeof l === 'string' || typeof r === 'string') return asStr(l) + asStr(r);
        return num(l) + num(r);
      }
      if (o === '-') return num(l) - num(r);
      if (o === '*') return num(l) * num(r);
      if (o === '/') return num(r) ? num(l) / num(r) : 0;
    }
    if (op === 'and') return truthy(this.eval(node[1])) && truthy(this.eval(node[2]));
    if (op === 'or') return truthy(this.eval(node[1])) || truthy(this.eval(node[2]));
    if (op === 'cmp') {
      const c = node[1];
      let l = this.eval(node[2]), r = this.eval(node[3]);
      let ll, rr;
      if (typeof l === 'string' || typeof r === 'string') { ll = l; rr = r; }
      else { ll = num(l); rr = num(r); }
      if (c === '=') return ll === rr;
      if (c === '!=') return ll !== rr;
      if (c === '<') return ll < rr;
      if (c === '>') return ll > rr;
      if (c === '<=') return ll <= rr;
      if (c === '>=') return ll >= rr;
    }
    throw new Error('bad expr node ' + JSON.stringify(node));
  };
  Evaluator.prototype.exec = function (node) {
    const op = node[0];
    if (op === 'block') { for (let i = 0; i < node[1].length; i++) this.exec(node[1][i]); }
    else if (op === 'assign') { this.store[node[1].key] = this.eval(node[2]); }
    else if (op === 'if') {
      if (truthy(this.eval(node[1]))) this.exec(node[2]);
      else if (node[3] !== null) this.exec(node[3]);
    } else throw new Error('bad stmt node ' + JSON.stringify(node));
  };

  // ── public API ───────────────────────────────────────────────────────────
  function evalTransition(exprSrc, store, namedSets) {
    let src = (exprSrc || '').trim();
    while (src.endsWith(';')) src = src.slice(0, -1).trim();
    if (!src) return true;
    const toks = tokenize(src);
    const ast = new Parser(toks, namedSets).parseExpr();
    return truthy(new Evaluator(store, namedSets).eval(ast));
  }

  function runActions(actionSrc, store, namedSets) {
    if (!actionSrc || !actionSrc.trim()) return;
    const toks = tokenize(actionSrc);
    const ast = new Parser(toks, namedSets).parseStmts();
    new Evaluator(store, namedSets).exec(ast);
  }

  const API = {
    tokenize: tokenize, Parser: Parser, Evaluator: Evaluator,
    evalTransition: evalTransition, runActions: runActions,
    makeRef: makeRef, Ref: Ref, _truthy: truthy,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  else root.SimEval = API;
})(typeof window !== 'undefined' ? window : this);
