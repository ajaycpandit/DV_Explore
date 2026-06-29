# DeltaV Strategy Workbench — Handoff

This file lets you resume in a fresh chat without re-explaining. **Two parts:**
(A) a short message to paste into the new chat, and (B) full context for reference.

---

## A. PASTE THIS INTO THE NEW CHAT (then upload `deltav_workbench_FULL_backup.zip`)

> I'm continuing work on my **DeltaV Strategy Workbench** — a Flask/Python web app
> that parses DeltaV FHX exports into an interactive explorer, with an embedded FHX
> Converter and a working **phase-simulator spike**. I'm uploading the full code
> backup (`deltav_workbench_FULL_backup.zip`). Please extract it to
> `/home/claude/work/db_explorer` and read `HANDOFF.md` inside the zip (same as this).
>
> Quick orientation: the explorer is solid and feature-complete; I most recently built
> a **phase sequence simulator spike** (`sim_eval.py` + `sim_run.py` + `build_sim_anim.py`)
> that steps a real phase's SFC logic and animates it in the browser. I want to keep
> going from there.
>
> My test FHX is the CIP skid export — if you don't have it, ask me to upload it
> (I'll send `046CIP723DISTR.fhx`). Please re-read the code before changing anything,
> keep `core/` byte-identical (fix via bridge post-processing only), and don't rebuild
> the deploy zip unless I say "package it".
>
> **Next step I want:** [pick one] (1) port the simulator evaluator to JS so the
> browser animation is interactive (edit a variable / hold a device confirm and watch
> the path change live); (2) extend the engine to the full S88 wrapper (RUN/HOLD/
> RESTART/ABORT/STOP handoff); (3) fix the transition-expression truncation bug in the
> explorer's SFC rendering; (4) integrate the I/O / DeviceNet view into the explorer.

---

## B. FULL CONTEXT (reference)

### Who / what
- **Me:** pharma/biotech automation engineer (Emerson DeltaV, 21 CFR Part 11 / GAMP).
  I also run Shvaan Pet Care (separate project — not relevant here).
- **This project:** "DeltaV Strategy Workbench" — parses DeltaV FHX database exports
  into an interactive web explorer. Deployed on Render (free plan). Also runs locally.
- **Style I prefer:** concise answers, tradeoffs up front, mockups before big UI builds,
  tell me when data is missing, targeted fixes over rewrites, honest caveats. Iterative
  test-driven dev validated against real exports.

### Repo / run
- Code lives in the `db_explorer/` folder (in the zip).
- **Run locally (preferred for sensitive data):** unzip → `cd db_explorer` →
  `python -m venv venv` → activate → `pip install -r requirements.txt` →
  `python run_local.py` (binds 127.0.0.1 only, offline-safe, opens browser).
- **Deploy (Render):** push `db_explorer` contents to the repo → Render → Manual Deploy →
  **"Clear build cache & deploy"** (always clear cache — stale builds are a recurring
  problem) → hard-refresh (Ctrl/Cmd+Shift+R).
- **Static preview (no server):** `python make_explorer.py <file.fhx> out.html`.
- Test file: the CIP skid export (`046CIP723DISTR.fhx`), used at `/tmp/cip.fhx`.

### Explorer — current state (solid / feature-complete)
- Workbench shell: dark left rail + top banner; DeltaV-style tree (Library / System
  Configuration) with placeholders for empty sections.
- **Unified converter (done):** the FHX Converter opens **in-page** via the rail/header
  toggle (no page reload, loaded database stays live). Embed mode `/tool/?embed=1` serves
  the converter rail-less. `core/` is untouched — wrapped at serve time in `converter_app.py`.
- Object detail views: Unit / EM / CM / Phase / Composite / FB-type / Named Set, with
  cross-linking, FBD rendering (DeltaV X/Y coords), EM **state tables** (state-driven EMs),
  command SFCs (command-driven EMs), **ISA-88 S88 state model** wired to phase SFCs.
- **Named sets** (ENUMERATION_SET) under Setup, with entries + "used by".
- **Physical Network → Control Network → Controller** (CTRL02_306) with assigned modules;
  controller shown on module detail.
- **CM/EM parameter cards** (just added): every module-level parameter, grouped by
  Operating / Configuration / Tuning / etc. (Unit was already complete at 8/8; EM=66,
  CM=42/12/119 were the gap, now surfaced).
- Per-object + whole-DB export to Excel/Word; converter at `/tool/`.
- **Rail fix (just added):** explorer rail now `background:var(--rail,#10202f)` with a
  hard-coded fallback so it can't render invisible even if the CSS var fails. (The earlier
  "invisible rail on explorer, visible on converter" was a STALE DEPLOY — redeploy latest
  with cleared cache.)

### Simulator spike — current state (proven, this is the active frontier)
Goal: a logic-level **phase sequence simulator** (design-review / training / logic-checkout —
NOT a validation tool). Tiers: T1 sequence stepper (DONE), T2 full discrete engine (reachable),
T3 process physics, T4 faithful block execution (don't build — that's Emerson's DeltaV Simulate).

**What works now (files in the zip):**
- `sim_eval.py` — DeltaV structured-text evaluator (~250 lines): tokenizer + recursive-descent
  parser + evaluator. Handles refs (`^/`, `//#THISUNIT#/`, `//#EM#/`, step-relative, bare),
  `= != < > <= >=`, `AND/OR/NOT`, parens, bare-boolean transitions, `:=`, `IF…THEN…ELSE…
  END_IF/ENDIF`, string concat `+` and arithmetic, named-set members, `""` escaping, `(* *)` comments.
- `sim_run.py` — loader + step engine. Resolves a phase → its RUN sequence (the **hash-keyed**
  block with the most steps), seeds tie-back confirms to 0, walks the SFC firing real transitions
  and applying real actions. Records a structured trace.
- `build_sim_anim.py` — renders the SFC (real DeltaV coords) and **animates** the walk in the
  browser: active-step highlight, transition firing, operator-message ticker (`P_MSG1`),
  variable watch (incl. EM commands), walk tape, Play/Step/Reset.
- Verified: the WASH phase walks 14 steps / 13 transitions with **zero errors**, executing
  ~52 action blocks. Waits correctly when conditions aren't met.

**Key technical findings (important):**
1. **Phase logic structure:** phases use the S88 framework (RUN/HOLD/RESTART/ABORT/STOP/
   FAIL_MONITOR). The real RUN sequence is a hash-named `FUNCTION_BLOCK_DEFINITION`
   (e.g. `__6568EDA2_91636BEC__`) the phase references; resolve via
   `parse_multiphase_fhx(text)[phase]` and pick the hash-keyed block with the most steps.
2. **Tie-backs are first-class:** `<step>/PENDING_CONFIRMS.CV = 0` is the dominant advance
   condition. Seed to 0 = auto-confirm; hold non-zero = device hasn't reached target.
3. **BUG (still open):** the converter's `parse_sfc` extracts TRANSITION expressions with
   `EXPRESSION="([^"]*)"`, which truncates at the first embedded string quote — so any
   transition comparing to a string (e.g. `!= ""`) is cut off in the explorer's displayed SFC.
   The spike works around it by re-extracting with `EXPRESSION="((?:[^"]|"")*)"`. Should be
   fixed in the explorer too (via a bridge patch, since `core/` stays frozen).

### I/O / DeviceNet
- `io_parser.py` parses DeviceNet hardware exports (DEVICENET_DEVICE) → Controller→Card→Port→
  Device→Signals(DSTs). Resolves CM I/O reference → DST → physical channel. Built + verified on
  `CIP003-HV-010.fhx` (Westlock valve, LAFC-CNTL11B/C04/P01 @ addr 10, DSTs CIP003-ZSC-010 /
  ZSO-010). **Not yet integrated into the explorer** (standalone parser + a one-off view builder).

### Constraints / patterns to honor
- **`core/` must stay byte-identical to the original converter** — never edit it; fix chrome/bugs
  via bridge post-processing (`phase_bridge.py`, `em_bridge.py`, `converter_app.py`).
- Escaping `</script>` as `<\/script>` when embedding HTML-in-JSON-in-HTML.
- Validate generated JS with `node --check` on extracted `<script>` blocks.
- Don't rebuild the deploy zip every turn — only on "package it".

### Open / next-step menu
1. **Interactive JS sim** — port `sim_eval.py` to JS so the browser animation accepts live
   input (edit vars, hold confirms, branch live). ~250 lines, clean port.
2. **Full S88 wrapper** — RUN/HOLD/RESTART/ABORT/STOP handoff in the engine.
3. **Fix transition truncation** in the explorer SFC rendering (bridge patch).
4. **Integrate I/O view** into the explorer (Physical Network → Controller → Card → Port → Device).
5. Polish: relabel hash-named RUN sequences as "RUN Sequence" in the phase view.
