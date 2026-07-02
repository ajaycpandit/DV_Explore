/* sim_engine.js — JS port of sim_run.py's PhaseSim step engine (Option 1).
 *
 * Drives a phase RUN sequence live in the browser: seed the store, enter steps
 * (firing P/N/blank actions on entry), test outgoing transitions in source order,
 * advance on the first satisfied one. Same logic as the Python PhaseSim, but
 * data-driven from the sim_export.py payload instead of re-parsing FHX.
 *
 * Interactivity: the store is a plain object the UI can mutate between steps
 * (edit a variable, hold a confirm by setting PENDING_CONFIRMS.CV != 0). Calling
 * run() / step() re-walks from the *current* store, so edits change the path live.
 *
 * Depends on SimEval (sim_eval.js).
 */
(function (root) {
  'use strict';

  const SE = (typeof require !== 'undefined') ? require('./sim_eval.js')
            : root.SimEval;

  function _short(s) {
    s = (s || '').replace(/\s+/g, ' ').trim();
    return s.length > 70 ? s.slice(0, 70) + '\u2026' : s;
  }

  function PhaseSim(payload, opts) {
    this.P = payload;
    this.order = payload.order;
    this.steps = payload.steps;
    this.actions = payload.actions;     // {step: [[qual, expr], ...]}
    this.trans = payload.trans;         // {tname: expr}
    this.s2t = payload.s2t;             // {step: [tname,...]}
    this.t2s = payload.t2s;             // {tname: nextStep}
    this.sets = payload.sets || {};
    this.prompts = payload.prompts || {};   // {step: prompt descriptor}
    this.store = {};
    this.log = [];
    this.trace = [];
    this.active = this.order[0];
    this.pausedPrompt = null;           // {step, descriptor} when halted at a prompt
    this._seedFromPayload(opts || {});
  }

  // Seed exactly as Python _seed did, but prefer the payload's seed snapshot so
  // the JS start state is byte-identical to the Python engine's start state.
  PhaseSim.prototype._seedFromPayload = function (opts) {
    const seed = this.P.seed || {};
    this.store = Object.assign({}, seed);
    // operator answers to prompts: { step: {input:<n>}  OR  {ack:true} }
    this.answers = (opts.answers) ? Object.assign({}, opts.answers) : {};
    // allow caller overrides (e.g. operator assigns sync unit)
    if (opts.overrides) Object.assign(this.store, opts.overrides);
    this.active = this.order[0];
    this.log = [];
    this.trace = [];
    this.pausedPrompt = null;
    this._promptEntries = {};   // step -> times entered (for single-use answers)
    this._pendingOarReset = null;
    this._activeActions = {};   // name -> {since} for S/R (Set/Reset) SFC actions
  };

  PhaseSim.prototype.reset = function (opts) {
    this._seedFromPayload(opts || {});
  };

  PhaseSim.prototype.enter = function (step) {
    this.active = step;
    // if we just left a prompt, consume its OAR now (before this step's actions)
    this._applyPendingOarReset();

    // Per-action accounting (item 11): we don't just count blocks that didn't
    // throw — we classify every action by qualifier and record its outcome, so
    // the trace honestly reflects what ran, what stayed active, and what we can't
    // execute yet. Qualifiers:
    //   P (pulse) / N (non-stored) / '' : a structured-text body -> execute now
    //   S (set)   : activate a named SFC action; it stays active until reset
    //   R (reset) : deactivate a previously-set named action
    //   L/D/SD/DS/SL (timed) : time-qualified -> flagged, not yet modeled (T2)
    const acts = this.actions[step] || [];
    const outcomes = [];
    let executed = 0;
    for (let i = 0; i < acts.length; i++) {
      const qual = (acts[i][0] || '').toUpperCase();
      const body = acts[i][1] || '';
      if (qual === 'P' || qual === 'N' || qual === '') {
        const looksLikeStmt = body.indexOf(':=') >= 0 || /\bIF\b/i.test(body);
        if (looksLikeStmt) {
          try {
            SE.runActions(body, this.store, this.sets);
            executed++;
            outcomes.push({ qual: qual || 'N', kind: 'executed', body: _short(body) });
          } catch (ex) {
            outcomes.push({ qual: qual || 'N', kind: 'error', body: _short(body), err: ex.message });
            this.log.push('      ! action error in ' + step + ': ' + ex.message);
          }
        } else {
          // a bare name under P/N (rare) — treat as a named action activation
          this._activeActions[body] = { since: step };
          outcomes.push({ qual: qual || 'N', kind: 'named-run', body: _short(body) });
        }
      } else if (qual === 'S') {
        this._activeActions[body] = { since: step };
        outcomes.push({ qual: 'S', kind: 'activated', body: _short(body) });
        this.log.push('      + action SET: ' + body + ' (active from ' + step + ')');
      } else if (qual === 'R') {
        const was = this._activeActions[body];
        delete this._activeActions[body];
        outcomes.push({ qual: 'R', kind: 'deactivated', body: _short(body),
                        since: was ? was.since : null });
        this.log.push('      - action RESET: ' + body +
                      (was ? ' (was active from ' + was.since + ')' : ''));
      } else {
        // time-qualified or unknown qualifier: record honestly as not-yet-modeled
        outcomes.push({ qual: qual, kind: 'unmodeled', body: _short(body) });
        this.log.push('      ~ action qualifier ' + qual + ' not modeled: ' + _short(body));
      }
    }
    const desc = (this.steps[step] || {}).desc || '';
    this.log.push('  -> STEP ' + step + '  [' + desc + ']  (executed ' + executed + '/' +
                  acts.length + ' action block(s))');
    this.trace.push({ kind: 'enter', step: step, desc: desc,
                      store: Object.assign({}, this.store), nfired: executed,
                      actions: outcomes,
                      active_actions: Object.keys(this._activeActions).slice() });
    return executed;
  };

  // If `active` is an operator prompt, either apply the recorded answer (so the
  // walk can proceed) or return the descriptor to signal a HALT. Returns:
  //   null            -> not a prompt, or already-answered ack; just continue
  //   {halt:descr}    -> unanswered prompt: stop and wait for the operator
  //
  // Answers are SINGLE-USE per entry: a phase can loop back to the same prompt
  // (e.g. add-acid -> recirculate -> re-check conductivity -> prompt again), and
  // a real operator faces the prompt fresh each time. So we record how many times
  // each prompt step has been entered and only apply an answer that was given for
  // the CURRENT entry. A stale answer from a previous loop does not carry forward.
  PhaseSim.prototype._handlePrompt = function (step) {
    const descr = this.prompts[step];
    if (!descr) return null;
    // _notePromptEntry already incremented the counter for THIS entry, so the
    // current entry index is (count - 1).
    const entry = (this._promptEntries[step] || 1) - 1;
    // answers[step] is a map { entryIndex: {input:...} } so that each loop's
    // answer persists and only the matching entry is applied. (Back-compat: a
    // bare {input,_entry} object is also accepted.)
    const rec = this.answers[step];
    let ans = null;
    if (rec) {
      if (rec.byEntry) ans = rec.byEntry[entry];
      else if (rec._entry === entry) ans = rec;        // legacy single-answer form
    }
    if (!ans) return { halt: descr };
    if (descr.release === 'value') {
      if (descr.bool_key) {
        // boolean-prompt dialect: the outgoing transitions test a bool var
        // (e.g. PROMPT_BOOL = TRUE/FALSE). Write the operator's Yes/No as a bool.
        this.store[descr.bool_key] = (ans.input === 1 || ans.input === true);
        this._pendingOarReset = null;
      } else {
        const key = descr.input_key || (step + '/FAIL_MONITOR/OAR/INPUT.CV');
        this.store[key] = ans.input;
        // The outgoing transition reads OAR/INPUT to pick the branch, so we must NOT
        // clear it now. Instead schedule a reset once the walk has LEFT this prompt
        // step, so a later prompt reading the same shared OAR/INPUT can't inherit a
        // stale answer (real DeltaV consumes the OAR input when the request clears).
        this._pendingOarReset = { input_key: key, status_key: descr.status_key || null };
      }
    } else { // 'ack'
      this.store[descr.confirm_key] = 0;
      if (descr.status_key) this._pendingOarReset = { input_key: null, status_key: descr.status_key };
    }
    return null;
  };

  // Reset a consumed OAR (input -> 0, status -> IDLE) after the branch has fired.
  // Called on entry to the step AFTER a prompt, so the transition that reads
  // OAR/INPUT has already been evaluated against the operator's answer.
  PhaseSim.prototype._applyPendingOarReset = function () {
    const r = this._pendingOarReset;
    if (!r) return;
    if (r.input_key) this.store[r.input_key] = 0;
    if (r.status_key) this.store[r.status_key] = '_OAR_STATUS:IDLE';
    this._pendingOarReset = null;
  };

  // Record entry into a prompt step; returns the entry index for that step.
  PhaseSim.prototype._notePromptEntry = function (step) {
    if (!this.prompts[step]) return -1;
    const n = (this._promptEntries[step] || 0);
    this._promptEntries[step] = n + 1;
    return n;
  };

  // Return [transition, nextStep] for the first satisfied outgoing transition.
  PhaseSim.prototype.fireable = function () {
    const outs = this.s2t[this.active] || [];
    for (let i = 0; i < outs.length; i++) {
      const tn = outs[i];
      const expr = this.trans[tn] || '';
      let ok;
      try { ok = SE.evalTransition(expr, this.store, this.sets); }
      catch (ex) { this.log.push('      ! transition error ' + tn + ': ' + ex.message); continue; }
      if (ok) {
        const nxt = this.t2s[tn];
        this.trace.push({ kind: 'fire', t: tn, from: this.active, to: nxt });
        return [tn, nxt];
      }
    }
    return [null, null];
  };

  PhaseSim.prototype.run = function (maxSteps) {
    maxSteps = maxSteps || 80;
    this.pausedPrompt = null;
    this.enter(this.active);
    // a prompt can be raised by the very first step's entry actions
    this._notePromptEntry(this.active);
    let pr = this._handlePrompt(this.active);
    if (pr) { this._haltOnPrompt(this.active, pr.halt); return this.log; }
    for (let k = 0; k < maxSteps; k++) {
      const fr = this.fireable();
      const tn = fr[0], nxt = fr[1];
      if (!tn) {
        this.log.push('      ... waiting at ' + this.active + ' (no outgoing transition satisfied)');
        break;
      }
      this.log.push('      v ' + tn + ' fires -> ' + nxt);
      if (nxt === null || nxt === undefined || !(nxt in this.steps)) {
        this.log.push('      = reached terminal/exit (' + nxt + ')');
        break;
      }
      this.enter(nxt);
      this._notePromptEntry(this.active);
      pr = this._handlePrompt(this.active);
      if (pr) { this._haltOnPrompt(this.active, pr.halt); break; }
    }
    return this.log;
  };

  PhaseSim.prototype._haltOnPrompt = function (step, descr) {
    // entry index this halt corresponds to (we just incremented in _notePromptEntry)
    const entry = (this._promptEntries[step] || 1) - 1;
    this.pausedPrompt = { step: step, descr: descr, entry: entry };
    this.log.push('      ?? operator prompt at ' + step + ' [' + (descr.oar_type || '') +
                  '] entry#' + entry + ' - waiting for operator (' + descr.release + ')');
    this.trace.push({ kind: 'prompt', step: step, descr: descr, entry: entry });
  };

  // Single-step advance for interactive UI: enters next satisfied step, or
  // returns {waiting:true} / {done:true}. Re-evaluates against current store.
  PhaseSim.prototype.stepOnce = function () {
    const fr = this.fireable();
    const tn = fr[0], nxt = fr[1];
    if (!tn) return { waiting: true, at: this.active };
    if (nxt === null || nxt === undefined || !(nxt in this.steps)) return { done: true, to: nxt };
    this.enter(nxt);
    return { advanced: true, to: nxt, trans: tn };
  };

  const API = { PhaseSim: PhaseSim };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  else root.SimEngine = API;
})(typeof window !== 'undefined' ? window : this);
