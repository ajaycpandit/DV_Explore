"""
DeltaV Database Explorer — navigable HTML site generator.

Renders the parsed catalog as a single self-contained browsable site:
  - left navigation tree (Areas -> Units -> class; Library -> CM/EM/Phase classes)
  - object detail panel with identity, class<->instance links, and references
  - clickable cross-references (instance -> class, class -> instances)

This is the skeleton (navigation model proven end-to-end). Detailed per-object
views (SFC diagrams, parameters) plug in as "leaf" views in later iterations.
"""

import html
import json

import fbd_bridge  # for the shared expression-popup modal assets
import fonts  # embedded IBM Plex (offline-safe)
import s88_model  # ISA-88 phase state model
try:
    import recipe_bridge
    _RECIPE_CSS = recipe_bridge.RECIPE_CSS
except Exception:
    _RECIPE_CSS = ""


_CSS = """
:root{
  --canvas:#f6f8fb;--surface:#ffffff;--surface-2:#f3f6fa;--border:#dde4ec;--border-strong:#c7d2de;
  --ink:#16202c;--ink-2:#46566b;--ink-3:#7689a0;
  --accent:#1d4ed8;--accent-soft:#e7eefb;--link:#0e7490;
  --ok:#047857;--ok-soft:#e6f4ee;--alarm:#dc2626;--bypass:#b45309;
  --rail:#10202f;--rail-ink:#9fb4c9;--rail-ink-active:#ffffff;
  --mark:#fde68a;--mark-ink:#92400e;
  --shadow:0 1px 2px rgba(16,32,47,.04),0 8px 24px -12px rgba(16,32,47,.16);
  --grid:rgba(29,78,216,.045);
  --b-area:#0284c7;--b-cell:#0891b2;--b-unit:#059669;--b-uclass:#047857;--b-em:#7c3aed;
  --b-cm:#d97706;--b-phase:#db2777;--b-recipe:#dc2626;--b-composite:#475569;--b-fbtype:#0d9488;--b-inst:#7c3aed;--b-nset:#0369a1;--b-ctrl:#3730a3;
}
[data-theme="dark"]{
  --canvas:#0e141b;--surface:#161e27;--surface-2:#1b2531;--border:#28333f;--border-strong:#3a4856;
  --ink:#e6edf3;--ink-2:#a7b6c6;--ink-3:#73879b;
  --accent:#60a5fa;--accent-soft:#16263d;--link:#38bdf8;
  --ok:#34d399;--ok-soft:#10261f;--alarm:#f87171;--bypass:#fbbf24;
  --rail:#0a0f15;--rail-ink:#7f93a8;--rail-ink-active:#ffffff;
  --mark:#7c5e12;--mark-ink:#fde68a;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 12px 30px -14px rgba(0,0,0,.55);
  --grid:rgba(96,165,250,.06);
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;font-family:'IBM Plex Sans',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  color:var(--ink);background:var(--canvas);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.mono,code,.inst-cls,.dt-tag{font-family:'IBM Plex Mono',ui-monospace,Menlo,monospace}
::selection{background:var(--accent-soft)}
button{font-family:inherit}

/* shell */
.app{display:grid;grid-template-columns:60px 1fr;grid-template-rows:56px 1fr;height:100vh}
#view-converter{position:fixed;left:60px;top:0;right:0;bottom:0;display:none;z-index:7;background:var(--canvas)}
#view-studio{position:fixed;left:60px;top:0;right:0;bottom:0;display:none;z-index:7;background:var(--canvas)}
#view-studio.on{display:block}
.stu-shell{display:grid;grid-template-columns:260px 1fr;height:100%;overflow:hidden;transition:grid-template-columns .18s ease}
.stu-shell.side-hidden{grid-template-columns:0 1fr}
.stu-shell.side-hidden .stu-side{opacity:0;pointer-events:none}
.stu-toggle{background:var(--surface-2);border:1px solid var(--border);border-radius:7px;width:30px;height:30px;cursor:pointer;font-size:15px;color:var(--ink-2);display:grid;place-items:center;flex:0 0 auto}
.stu-toggle:hover{background:var(--accent-soft);color:var(--accent)}
.stu-diagram{position:relative}
.stu-diagload{position:absolute;inset:0;display:grid;place-items:center;background:var(--canvas);z-index:2}
.stu-side{border-right:1px solid var(--border);padding:14px 12px;overflow:auto;background:var(--surface)}
.stu-side-h{font-size:15px;font-weight:700;color:var(--ink)}
.stu-side-sub{font-size:11px;color:var(--ink-3);line-height:1.5;margin-top:4px}
.stu-litem{padding:7px 9px;border-radius:7px;cursor:pointer;font-size:12.5px;display:flex;align-items:center;gap:7px}
.stu-litem:hover{background:var(--surface-2)}
.stu-litem.sel{background:var(--accent-soft);color:var(--accent);font-weight:600}
.stu-main{overflow:hidden;display:flex;flex-direction:column;min-height:0;height:100%;position:relative}
.stu-side{border-right:1px solid var(--border);padding:14px 12px;overflow:auto;background:var(--surface);min-height:0}
.stu-welcome{padding:26px}
.stu-head{display:flex;align-items:center;gap:12px;padding:12px 18px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.stu-head h2{margin:0;font-size:17px}
.stu-kind{font-size:11px;font-weight:600;background:var(--accent-soft);color:var(--accent);padding:3px 9px;border-radius:20px}
.stu-instof{font-size:11px;font-weight:600;color:var(--ink-3);font-family:'IBM Plex Mono'}
.stu-simbtn{padding:6px 12px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#fff;font-size:12.5px;font-weight:600;cursor:pointer;margin-right:8px}
.stu-simbtn:hover{filter:brightness(1.06)}
.stu-matrixbtn{padding:6px 12px;border-radius:8px;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);font-size:12.5px;font-weight:600;cursor:pointer;margin-right:8px}
.stu-matrixbtn:hover{background:var(--surface-2)}
/* Parameter Matrix modal */
.pm-ov{position:fixed;inset:0;z-index:10000;pointer-events:none}
.pm-card{position:absolute;top:5vh;left:50%;transform:translateX(-50%);background:var(--surface);border:1px solid var(--border-strong);border-radius:12px;width:min(1240px,96vw);height:84vh;min-width:760px;min-height:440px;max-width:99vw;max-height:95vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.4);pointer-events:auto;resize:both}
.pm-head{display:flex;align-items:center;gap:12px;padding:13px 18px;border-bottom:1px solid var(--border);background:var(--surface-2);cursor:move;user-select:none;flex:0 0 auto}
.pm-head h2{margin:0;font-size:15px;font-weight:650}
.pm-head .sub{font-size:12px;color:var(--ink-3);font-family:'IBM Plex Mono'}
.pm-head .x{margin-left:auto;cursor:pointer;font-size:22px;color:var(--ink-3);line-height:1}
.pm-toolbar{display:flex;align-items:center;gap:9px;padding:10px 18px;border-bottom:1px solid var(--border);flex-wrap:wrap;flex:0 0 auto}
.pm-search{padding:7px 11px;border:1px solid var(--border);border-radius:8px;font-size:13px;min-width:200px;background:var(--surface);color:var(--ink)}
.pm-chip{font-size:11px;padding:5px 11px;border:1px solid var(--border);border-radius:20px;cursor:pointer;background:var(--surface);color:var(--ink-2)}
.pm-chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.pm-vary-toggle{margin-left:auto;font-size:12px;display:flex;align-items:center;gap:6px;color:var(--ink-2)}
.pm-btn{padding:8px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--ink);font-size:12.5px;font-weight:600;cursor:pointer}
.pm-btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.pm-btn:disabled{opacity:.5;cursor:default}
.pm-gridwrap{overflow:auto;flex:1 1 auto;min-height:0}
table.pm-grid{border-collapse:separate;border-spacing:0;font-size:12px;width:max-content}
.pm-grid th,.pm-grid td{border-right:1px solid var(--border);border-bottom:1px solid var(--border);padding:6px 10px;white-space:nowrap}
.pm-grid thead th{position:sticky;top:0;background:var(--surface-2);z-index:3;font-weight:600;text-align:left}
.pm-grid .pm-pname{position:sticky;left:0;background:var(--surface);z-index:2;font-family:'IBM Plex Mono';font-weight:600;min-width:180px;max-width:280px;overflow:hidden;text-overflow:ellipsis}
.pm-grid thead .pm-corner{position:sticky;left:0;z-index:4;background:var(--surface-2)}
.pm-inst{font-family:'IBM Plex Mono';font-size:11px}
.pm-inst small{display:block;color:var(--ink-3);font-weight:400;font-size:9.5px;max-width:150px;overflow:hidden;text-overflow:ellipsis}
.pm-grp td,td.pm-grp{background:var(--surface-2);font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-3);font-weight:700}
.pm-cell{font-family:'IBM Plex Mono';text-align:right}
.pm-cell.vary{background:var(--vary-soft,#fef3c7)}
.pm-cell input{width:100%;min-width:60px;border:0;background:transparent;font:inherit;text-align:right;color:inherit}
.pm-cell input:focus{outline:2px solid var(--accent);border-radius:4px;background:var(--surface)}
.pm-cell.edited{background:var(--ok-soft,#dcfce7)}
.pm-cell.empty{color:var(--ink-3);text-align:center;background:repeating-linear-gradient(45deg,transparent,transparent 5px,rgba(120,137,160,.06) 5px,rgba(120,137,160,.06) 10px)}
.pm-badge{display:inline-block;font-size:9px;padding:1px 6px;border-radius:20px;background:var(--vary-soft,#fef3c7);color:var(--vary,#b45309);font-weight:700;margin-left:6px}
.pm-badge.d{background:var(--accent-soft);color:var(--accent)}
.pm-foot{display:flex;align-items:center;gap:12px;padding:10px 18px;border-top:1px solid var(--border);font-size:12px;color:var(--ink-2);flex:0 0 auto}
.pm-dirty{color:var(--ok,#15803d);font-weight:600}
.pm-empty{padding:40px;text-align:center;color:var(--ink-3)}
/* Real-simulation modal */
.rs-ov{position:fixed;inset:0;z-index:10000;pointer-events:none}
/* floating host */
.rs-ov .rs-card{position:absolute;top:6vh;left:50%;transform:translateX(-50%);height:80vh;width:min(1120px,94vw);min-width:720px;min-height:420px;max-width:99vw;max-height:96vh;resize:both;box-shadow:0 24px 70px rgba(0,0,0,.4);border-radius:14px}
.rs-ov .rs-head{cursor:move}
/* docked host: fills the Studio main area below the head */
.rs-dockhost{position:absolute;inset:0;z-index:60;background:var(--canvas);display:flex}
.rs-dockhost .rs-card{flex:1 1 auto;border-radius:0;box-shadow:none;height:100%;min-width:0}
.rs-dockhost .rs-head{cursor:default}
.rs-card{background:var(--surface);border:1px solid var(--border-strong);overflow:hidden;display:flex;flex-direction:column;pointer-events:auto}
.rs-head{display:flex;align-items:center;gap:12px;padding:11px 16px;border-bottom:1px solid var(--border);background:var(--surface-2);flex:0 0 auto;user-select:none}
.rs-head h2{margin:0;font-size:15px;font-weight:650}
.rs-head .sub{color:var(--ink-3);font-size:12px;font-family:'IBM Plex Mono'}
.rs-head-sp{flex:1}
.rs-hostb{padding:5px 11px;border-radius:7px;border:1px solid var(--border);background:var(--surface);color:var(--ink-2);font-size:12px;font-weight:600;cursor:pointer}
.rs-hostb:hover{background:var(--surface-2)}
.rs-head .x{cursor:pointer;font-size:22px;color:var(--ink-3);line-height:1;margin-left:4px}
.rs-head .x:hover{color:var(--ink)}
.rs-body{display:flex;min-height:0;flex:1 1 auto;overflow:hidden}
.rs-config{width:238px;flex:0 0 238px;border-right:1px solid var(--border);padding:16px;overflow:auto;background:var(--surface)}
.rs-split-v{flex:0 0 6px;cursor:col-resize;background:transparent;position:relative}
.rs-split-v:hover{background:var(--accent-soft)}
.rs-split-v::after{content:'';position:absolute;left:2px;top:0;bottom:0;width:1px;background:var(--border)}
/* run area fills remaining height; SFC + verify each scroll internally (#1,#5) */
.rs-run{flex:1 1 auto;min-width:0;padding:14px 18px;overflow:hidden;display:grid;grid-template-columns:238px 1fr;grid-template-rows:1fr auto;gap:16px;overscroll-behavior:contain}
.rs-lbl{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-3);margin:0 0 8px}
.rs-cmd{width:100%;padding:9px 11px;border:1px solid var(--border);border-radius:9px;font-size:13px;background:var(--surface);color:var(--ink);margin-bottom:18px}
.rs-devrow-cfg{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border)}
.rs-devrow-cfg .nm{flex:1;font-size:12.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rs-fam{font-size:10px;text-transform:uppercase;letter-spacing:.04em;padding:2px 7px;border-radius:20px;background:var(--surface-2);color:var(--ink-2)}
.rs-fam.valve{background:var(--accent-soft);color:var(--accent)}
.rs-fam.motor{background:var(--wait-soft,#fef3c7);color:var(--wait,#b45309)}
.rs-travel{width:52px;padding:5px 7px;border:1px solid var(--border);border-radius:7px;font-size:12px;text-align:right;font-family:'IBM Plex Mono';background:var(--surface);color:var(--ink)}
.rs-travel-u{font-size:10px;color:var(--ink-3)}
.rs-actions{display:flex;gap:8px;margin-top:16px}
.rs-btn{padding:9px 16px;border-radius:9px;border:1px solid var(--border);background:var(--surface);color:var(--ink);font-size:13px;font-weight:600;cursor:pointer}
.rs-btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.rs-btn:disabled{opacity:.5;cursor:default}
.rs-note{margin-top:16px;padding:10px 12px;background:var(--surface-2);border:1px solid var(--border);border-radius:9px;font-size:11.5px;color:var(--ink-2);line-height:1.5}
.rs-status{display:flex;align-items:center;gap:14px;margin-bottom:12px;flex-wrap:wrap}
.rs-clock{font-family:'IBM Plex Mono';font-size:13px;color:var(--ink-2)}
.rs-badge{font-size:11px;padding:3px 10px;border-radius:20px;font-weight:600}
.rs-badge.run{background:var(--wait-soft,#fef3c7);color:var(--wait,#b45309)}
.rs-badge.done{background:var(--ok-soft,#dcfce7);color:var(--ok,#15803d)}
.rs-badge.timeout{background:#fee2e2;color:#b91c1c}
.rs-sfc-col{min-width:0;min-height:0;display:flex;flex-direction:column;height:100%}
.rs-sfc-col .rs-status{flex:0 0 auto}
.rs-sfc-wrap{border:1px solid var(--border);border-radius:11px;background:var(--surface-2);padding:8px;overflow:auto;min-height:0;height:100%}
.sfc-step{cursor:pointer}
.sfc-box{fill:var(--surface);stroke:var(--border-strong);stroke-width:1.5}
.sfc-step.active .sfc-box{fill:var(--accent-soft);stroke:var(--accent);stroke-width:2.5}
.sfc-step.past .sfc-box{fill:var(--ok-soft,#dcfce7);stroke:#a7f3c0}
.sfc-step.sel .sfc-box{stroke:var(--accent);stroke-dasharray:4 3;stroke-width:2.5}
.sfc-sid{font:700 12px 'IBM Plex Mono';fill:var(--ink)}
.sfc-sd{font:11px -apple-system,sans-serif;fill:var(--ink-3)}
.sfc-line{stroke:var(--ink-3);stroke-width:1.5}
.sfc-trans rect{fill:var(--ink)}
.sfc-trans.hot rect{fill:var(--ok,#15803d)}
.sfc-tid{font:700 10px 'IBM Plex Mono';fill:var(--ink-2)}
.rs-verify{overflow:auto;min-height:0;height:100%;overscroll-behavior:contain}
.rs-vhead{font-size:12.5px;font-weight:700;margin:0 0 4px}
.rs-vsub{font-size:11px;color:var(--ink-3);margin:0 0 12px}
.rs-act{border:1px solid var(--border);border-radius:9px;padding:10px 12px;margin-bottom:9px;background:var(--surface);scroll-margin-top:8px}
.rs-act.ok{border-color:#a7f3c0;background:var(--ok-soft,#dcfce7)}
.rs-act.wait{border-color:#fcd989;background:#fffdf5}
/* #4: the currently-resolving action gets focus — accent ring + gentle pulse */
.rs-act.rs-act-live{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft);animation:rsActPulse 1.4s ease-in-out infinite}
@keyframes rsActPulse{0%,100%{box-shadow:0 0 0 2px var(--accent-soft)}50%{box-shadow:0 0 0 4px var(--accent-soft)}}
@media (prefers-reduced-motion: reduce){.rs-act.rs-act-live{animation:none}}
.rs-devopen{cursor:pointer;text-decoration:underline dotted;text-underline-offset:2px}
.rs-devopen:hover{color:var(--accent)}
.rs-actdev.focus{outline:2px solid var(--accent);outline-offset:1px}
.rs-act-h{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.rs-act-id{font:700 11px 'IBM Plex Mono';color:var(--ink-2)}
.rs-act-d{font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rs-act-st{margin-left:auto;font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;white-space:nowrap}
.rs-act-st.ok{background:var(--ok,#15803d);color:#fff}.rs-act-st.wait{background:var(--wait,#b45309);color:#fff}.rs-act-st.gated{background:var(--ink-3);color:#fff}
.rs-io{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11.5px}
.rs-io .k{font-size:9px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink-3);margin-bottom:2px}
.rs-io .v{font-family:'IBM Plex Mono';padding:4px 7px;border-radius:6px;background:var(--surface-2);border:1px solid var(--border);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rs-io .v.exp{color:var(--ink-2)}
.rs-io .v.act.match{background:var(--ok-soft,#dcfce7);color:var(--ok,#15803d);border-color:#a7f3c0}
.rs-io .v.act.miss{background:var(--wait-soft,#fef3c7);color:var(--wait,#b45309);border-color:#fcd989}
.rs-cmlink{margin-top:9px;font-size:11px;color:var(--link);cursor:pointer;display:inline-flex;align-items:center;gap:4px}
.rs-cmlink:hover{text-decoration:underline}
/* inline "actual device being driven" strip inside each action card */
.rs-actdev{display:flex;align-items:center;gap:7px;margin-top:9px;padding:7px 9px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);flex-wrap:wrap}
.rs-actdev.ilk{border-color:#fca5a5;background:#fef2f2}
.rs-actdev-nm{font:700 11px 'IBM Plex Mono';color:var(--ink-2)}
.rs-actdev-pin{font:700 10.5px 'IBM Plex Mono';padding:2px 7px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--ink-3)}
.rs-actdev-pin.hi{background:var(--ok-soft,#dcfce7);color:var(--ok,#15803d);border-color:#a7f3c0}
.rs-actdev-pin.wait{background:var(--wait-soft,#fef3c7);color:var(--wait,#b45309);border-color:#fcd989}
.rs-actdev-ilk{font-size:10px;font-weight:700;color:#b91c1c;text-transform:uppercase;letter-spacing:.03em}
.rs-actdev-open{margin-left:auto;font-size:11px;color:var(--link);cursor:pointer}
.rs-actdev-open:hover{text-decoration:underline}
/* floating CM status window */
.rs-cmwin{position:fixed;top:16vh;right:5vw;z-index:10001;width:360px;background:var(--surface);border:1px solid var(--border-strong);border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,.4);overflow:hidden}
.rs-cmw-head{display:flex;align-items:center;gap:8px;padding:11px 14px;background:var(--surface-2);border-bottom:1px solid var(--border);cursor:move;user-select:none}
.rs-cmw-head b{font-size:13px}
.rs-cmw-cls{font-size:10.5px;color:var(--ink-3);font-family:'IBM Plex Mono'}
.rs-cmw-fam{font-size:9px;text-transform:uppercase;padding:2px 6px;border-radius:20px;background:var(--surface);color:var(--ink-2)}
.rs-cmw-fam.valve{background:var(--accent-soft);color:var(--accent)}.rs-cmw-fam.motor{background:var(--wait-soft,#fef3c7);color:var(--wait,#b45309)}
.rs-cmw-head .x{margin-left:auto;cursor:pointer;font-size:20px;color:var(--ink-3);line-height:1}
.rs-cmw-body{padding:14px}
.rs-cmw-lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-3);margin:0 0 9px}
.rs-perm-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.rs-perm{font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px}
.rs-perm.ok{background:var(--ok-soft,#dcfce7);color:var(--ok,#15803d)}
.rs-perm.blk{background:#fee2e2;color:#b91c1c}
.rs-ilk-hdr{font-size:11px;color:var(--ink-3)}
.rs-ilk-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px}
.rs-ilk{display:flex;align-items:center;gap:6px;padding:4px 8px;border-radius:6px;background:var(--surface-2);border:1px solid var(--border);font-size:10.5px}
.rs-ilk.on{background:#fef2f2;border-color:#fca5a5}
.rs-ilk-dot{width:7px;height:7px;border-radius:50%;background:var(--ink-3);flex:0 0 auto}
.rs-ilk.on .rs-ilk-dot{background:#dc2626}
.rs-ilk-nm{font-family:'IBM Plex Mono';color:var(--ink-2);flex:1}
.rs-ilk-st{font-weight:700;color:var(--ink-3)}
.rs-ilk.on .rs-ilk-st{color:#b91c1c}
.rs-cmw-foot{margin-top:14px;font-size:11px;color:var(--ink-2);line-height:1.5}
.rs-loop{display:flex;align-items:flex-start;flex-wrap:wrap}
.rs-sig{display:flex;flex-direction:column;align-items:center;gap:3px;min-width:56px}
.rs-sig .pin{width:100%;text-align:center;padding:5px 4px;border-radius:7px;font-size:11px;font-weight:700;font-family:'IBM Plex Mono';border:1px solid var(--border);background:var(--surface-2);color:var(--ink-3)}
.rs-sig .pin.hi{background:var(--ok-soft,#dcfce7);color:var(--ok,#15803d);border-color:#a7f3c0}
.rs-sig .pin.wait{background:var(--wait-soft,#fef3c7);color:var(--wait,#b45309);border-color:#fcd989}
.rs-sig .pl{font-size:9px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-3)}
.rs-arrow{color:var(--ink-3);font-size:14px;padding:6px 5px 0;position:relative}
.rs-arrow .tt{position:absolute;top:-9px;left:50%;transform:translateX(-50%);font-size:9px;color:var(--wait,#b45309);white-space:nowrap;font-family:'IBM Plex Mono'}
/* instance picker + resolved-tag member sublabel + ignore badge */
.rs-devrow-cfg.off{opacity:.5}
.rs-devrow-mem{display:block;font-size:9.5px;color:var(--ink-3);font-family:'IBM Plex Mono';font-weight:400}
.rs-ign{font-size:9px;font-weight:700;text-transform:uppercase;padding:2px 6px;border-radius:20px;background:var(--surface-2);color:var(--ink-3)}
/* run-mode toggle */
.rs-mode{display:flex;gap:8px;margin-bottom:16px}
.rs-moderb{flex:1;display:flex;flex-direction:column;font-size:12px;font-weight:600;padding:8px 10px;border:1px solid var(--border);border-radius:8px;cursor:pointer}
.rs-moderb small{font-weight:400;color:var(--ink-3);font-size:10px}
.rs-moderb:has(input:checked){border-color:var(--accent);background:var(--accent-soft)}
.rs-mode{display:flex;flex-direction:column;gap:6px;margin-bottom:16px}
/* device faceplate (floating) */
.rs-face{position:fixed;top:12vh;right:4vw;z-index:10001;width:380px;background:var(--surface);border:1px solid var(--border-strong);border-radius:12px;box-shadow:0 22px 64px rgba(0,0,0,.42);overflow:hidden;max-height:82vh;display:flex;flex-direction:column}
.rs-face-head{display:flex;align-items:center;gap:9px;padding:11px 14px;background:var(--surface-2);border-bottom:1px solid var(--border);cursor:move;user-select:none;flex:0 0 auto}
.rs-face-id{display:flex;flex-direction:column;min-width:0}
.rs-face-id b{font-size:13.5px;font-family:'IBM Plex Mono'}
.rs-face-cls{font-size:10px;color:var(--ink-3);font-family:'IBM Plex Mono';overflow:hidden;text-overflow:ellipsis}
.rs-face-fam{font-size:9px;text-transform:uppercase;padding:2px 7px;border-radius:20px;background:var(--surface);color:var(--ink-2)}
.rs-face-fam.valve{background:var(--accent-soft);color:var(--accent)}.rs-face-fam.motor{background:var(--wait-soft,#fef3c7);color:var(--wait,#b45309)}
.rs-face-head .x{margin-left:auto;cursor:pointer;font-size:20px;color:var(--ink-3);line-height:1}
.rs-face-body{padding:14px;overflow:auto;min-height:0}
.rs-face-status{display:flex;align-items:baseline;gap:10px;padding:12px 14px;border-radius:10px;margin-bottom:14px;background:var(--surface-2);border:1px solid var(--border)}
.rs-face-status.on{background:var(--ok-soft,#dcfce7);border-color:#a7f3c0}
.rs-face-status.move{background:var(--wait-soft,#fef3c7);border-color:#fcd989}
.rs-face-status.ilk{background:#fee2e2;border-color:#fca5a5}
.rs-face-pv{font:700 22px 'IBM Plex Mono';color:var(--ink)}
.rs-face-sw{font-size:12px;font-weight:600;color:var(--ink-2);text-transform:uppercase;letter-spacing:.04em}
.rs-face-drive{margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.rs-face-cmds{display:flex;gap:8px}
.rs-cmdbtn{flex:1;padding:10px;border-radius:9px;border:1px solid var(--border);background:var(--surface);font-size:13px;font-weight:700;cursor:pointer}
.rs-cmdbtn.on{border-color:#a7f3c0;color:var(--ok,#15803d)}
.rs-cmdbtn.on.active{background:var(--ok,#15803d);color:#fff}
.rs-cmdbtn.off{border-color:var(--border-strong);color:var(--ink-2)}
.rs-cmdbtn.off.active{background:var(--ink-2);color:#fff}
.rs-cmdbtn.clr{flex:0 0 auto;font-weight:600;color:var(--ink-3)}
.rs-face-drivenote{font-size:10.5px;color:var(--ink-3);margin:8px 0 0;line-height:1.5}
/* advanced hold/force controls (details/summary) */
.rs-manual{margin-top:14px;padding-top:12px;border-top:1px solid var(--border)}
.rs-manual summary{cursor:pointer;list-style:none;margin-bottom:8px}
.rs-manual summary::-webkit-details-marker{display:none}
.rs-manual summary::before{content:'\\25b8 ';color:var(--ink-3)}
.rs-manual[open] summary::before{content:'\\25be '}
.rs-mctl{display:flex;align-items:center;gap:7px;font-size:12px;margin-bottom:8px;cursor:pointer}
.rs-mctl small{color:var(--ink-3);font-size:10.5px}
.rs-mbtns{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.rs-btn.sm{padding:6px 8px;font-size:11px}
.rs-btn.sm.on{background:var(--accent);border-color:var(--accent);color:#fff}
/* animated device symbol */
.rs-sym{display:inline-flex;align-items:center;justify-content:center}
.rs-sym svg{overflow:visible}
.rs-sym .rs-sym-body{fill:var(--surface-2);stroke:var(--ink-3);stroke-width:1.5}
.rs-sym .rs-sym-rot line{stroke:var(--ink-3);stroke-width:1.6;transform-origin:11px 11px}
.rs-sym-on .rs-sym-body{fill:var(--ok-soft,#dcfce7);stroke:var(--ok,#15803d)}
.rs-sym-on .rs-sym-rot line{stroke:var(--ok,#15803d)}
.rs-sym-off .rs-sym-body{fill:var(--surface-2);stroke:var(--ink-3)}
.rs-sym-move .rs-sym-body{fill:var(--wait-soft,#fef3c7);stroke:var(--wait,#b45309)}
.rs-sym-move .rs-sym-rot line{stroke:var(--wait,#b45309)}
.rs-sym-ilk .rs-sym-body{fill:#fee2e2;stroke:#dc2626}
.rs-sym-move .rs-sym-rot{animation:rsspin 1s linear infinite}
.rs-sym-move .rs-sym-body{animation:rspulse 1.1s ease-in-out infinite}
@keyframes rsspin{to{transform:rotate(360deg)}}
@keyframes rspulse{0%,100%{opacity:1}50%{opacity:.55}}
@media (prefers-reduced-motion: reduce){.rs-sym-move .rs-sym-rot,.rs-sym-move .rs-sym-body{animation:none}}
.rs-scrub{grid-column:1/-1;display:flex;align-items:center;gap:10px;margin-top:4px;padding-top:12px;border-top:1px solid var(--border)}
.rs-scrub input[type=range]{flex:1;accent-color:var(--accent)}
.rs-play{cursor:pointer;font-size:15px;color:var(--accent);background:none;border:0}
.rs-step-now{font-size:13px;font-weight:600}
.rs-empty{color:var(--ink-3);font-size:13px;padding:30px 0;text-align:center}
/* #3: S88 path breadcrumb bar */
.stu-pathbar{display:flex;align-items:center;flex-wrap:wrap;gap:2px;padding:8px 18px;background:var(--surface-2);border-bottom:1px solid var(--border);font-size:12px}
.stu-crumb{display:inline-flex;flex-direction:column;line-height:1.25;padding:3px 9px;border-radius:7px}
.stu-crumb-cur{background:var(--accent-soft)}
.stu-crumb-k{font-size:9.5px;letter-spacing:.03em;text-transform:uppercase;color:var(--ink-3);font-weight:600}
.stu-crumb-n{font-size:12.5px;color:var(--ink);font-weight:600}
.stu-crumb-sub{font-size:10px;color:var(--ink-3);font-family:'IBM Plex Mono'}
.stu-crumb-sep{color:var(--ink-3);margin:0 2px;font-size:15px}
.stu-path-warn{margin-left:8px;font-size:10.5px;color:#9a6700;background:#fdf0d5;border:1px solid #f0d9a8;border-radius:20px;padding:2px 8px}
.stu-browse-btn{width:100%;display:flex;align-items:center;justify-content:center;gap:6px;padding:8px 10px;margin:2px 0 8px;background:var(--accent);color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer}
.stu-browse-btn:hover{filter:brightness(1.06)}
.stu-litem .stu-litem-cls{font-size:10.5px;color:var(--ink-3);font-family:'IBM Plex Mono';margin-left:6px}
.stu-chip{font-size:11px;font-weight:600;background:var(--surface-2);color:var(--ink-2);padding:3px 9px;border-radius:20px}
.stu-body{flex:1 1 auto;display:grid;overflow:hidden;min-height:0}
.stu-body.stu-dock-right{grid-template-columns:1.35fr 5px 1fr;grid-template-rows:minmax(0,1fr)}
.stu-body.stu-dock-left{grid-template-columns:1fr 5px 1.35fr;grid-template-rows:minmax(0,1fr)}
.stu-body.stu-dock-left .stu-pane.stu-diagram{order:3;border-right:0;border-left:1px solid var(--border)}
.stu-body.stu-dock-left .stu-split{order:2}
.stu-body.stu-dock-left .stu-side-panel{order:1}
.stu-body.stu-dock-bottom{grid-template-rows:1.3fr 5px 1fr;grid-template-columns:minmax(0,1fr)}
.stu-pane{overflow:auto;padding:0;min-height:0;min-width:0}
.stu-pane.stu-diagram{border-right:1px solid var(--border);padding:0;background:#fff;overflow:hidden;display:flex;position:relative}
.stu-body.stu-dock-bottom .stu-pane.stu-diagram{border-right:0;border-bottom:1px solid var(--border)}
.stu-diagram iframe{flex:1 1 auto;width:100%;height:100%;border:0;display:block;min-height:0}
.stu-embed-wrap{width:100%;height:100%;overflow:auto;padding:14px}
.stu-side-panel{overflow:auto;min-height:0;min-width:0;display:flex;flex-direction:column}
.stu-split{background:var(--border);cursor:col-resize}
.stu-body.stu-dock-right .stu-split{cursor:col-resize}
.stu-body.stu-dock-bottom .stu-split{cursor:row-resize}
.stu-split:hover{background:var(--accent)}
.stu-dock-btns{margin-left:auto;display:flex;gap:2px;align-items:center;padding-right:6px}
.stu-dockb{background:none;border:1px solid var(--border);border-radius:5px;width:24px;height:22px;cursor:pointer;color:var(--ink-3);font-size:12px;line-height:1}
.stu-dockb:hover{background:var(--accent-soft);color:var(--accent)}
.stu-head-sp{flex:1}
.stu-grp{margin-bottom:10px}
.stu-grp-h{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--ink-3);padding:4px 4px 5px}
.stu-grp-n{color:var(--ink-3);font-weight:500}
.stu-embed{margin-bottom:14px}
.stu-pane.stu-diagram{border-right:1px solid var(--border);padding:0;background:#fff}
.stu-diagram iframe{width:100%;height:100%;border:0;display:block}
.stu-tabs{display:flex;gap:2px;padding:8px 12px 0;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--canvas);z-index:2}
.stu-tab{padding:7px 13px;font-size:12.5px;cursor:pointer;border-radius:7px 7px 0 0;color:var(--ink-2)}
.stu-tab.on{background:var(--accent-soft);color:var(--accent);font-weight:600}
.stu-tabpanel{padding:12px 14px;display:none}
.stu-tabpanel.on{display:block}
.stu-grid{width:100%;border-collapse:collapse;font-size:12px}
.stu-grid th{position:sticky;top:0;background:var(--surface-2);text-align:left;padding:6px 8px;font-weight:600;border-bottom:1px solid var(--border);white-space:nowrap}
.stu-grid td{padding:5px 8px;border-bottom:1px solid var(--border);vertical-align:top}
.stu-grid .stu-desc{color:var(--ink-2);max-width:280px}
.stu-empty{color:var(--ink-3);font-size:12.5px;padding:14px 4px}
.stu-io{font-size:11px;font-weight:600;font-family:'IBM Plex Mono';padding:1px 7px;border-radius:20px;white-space:nowrap}
.stu-io-input{background:#e0f2fe;color:#0369a1}
.stu-io-output{background:#fef3c7;color:#92600a}
.stu-split{cursor:col-resize;width:5px;background:transparent}
@media(max-width:1100px){.stu-body.stu-dock-right{grid-template-columns:minmax(0,1fr);grid-template-rows:1.2fr 5px 1fr}.stu-body.stu-dock-right .stu-pane.stu-diagram{border-right:0;border-bottom:1px solid var(--border)}}
#view-converter.on{display:block}
#convFrame{width:100%;height:100%;border:0;display:block}
#view-recipes{position:fixed;left:60px;top:0;right:0;bottom:0;display:none;z-index:7;background:var(--canvas)}
#view-recipes.on{display:block}
.rec-panes{display:grid;grid-template-columns:340px 1fr;height:100%;overflow:hidden}
.rec-list{overflow:auto;border-right:1px solid var(--border);padding:14px 10px;background:var(--surface)}
.rec-detail{overflow:auto;padding:20px 26px}
.rec-toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.rec-hint{font-size:11px;color:var(--ink-3)}
.rec-cat{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-3);margin:14px 4px 6px}
.rec-item.sel{background:var(--accent-soft)}
.ctx-menu{position:fixed;z-index:60;min-width:210px;background:var(--surface,#fff);border:1px solid var(--border,#e2e8f0);border-radius:9px;box-shadow:0 8px 28px rgba(15,23,42,.18);padding:5px;font-size:13px;user-select:none}
.ctx-it{padding:7px 12px;border-radius:6px;cursor:pointer;color:var(--ink,#16202c);white-space:nowrap}
.ctx-it:hover{background:var(--accent-soft,#f5f3ff);color:var(--accent,#7c3aed)}
.ctx-it.ctx-dis{opacity:.4;cursor:default}
.ctx-it.ctx-dis:hover{background:none;color:var(--ink,#16202c)}
.ctx-it.ctx-danger:hover{background:#fef2f2;color:#dc2626}
.ctx-sep{height:1px;background:var(--border,#e2e8f0);margin:4px 6px}
.ctx-target{outline:2px solid var(--accent,#7c3aed);outline-offset:-2px;border-radius:4px}
/* #1: persistent "currently open object" indicator on nav rows — a soft accent bar +
   tint, nicer than a hard outline, and it moves to whatever object is open. */
.obj-selected{position:relative;background:var(--accent-soft)!important;border-radius:6px}
.obj-selected::before{content:"";position:absolute;left:0;top:3px;bottom:3px;width:3px;border-radius:3px;background:var(--accent)}
.rec-empty{color:var(--ink-3);font-size:13px;padding:16px 8px;line-height:1.6}
.rec-src{font-size:11px;color:var(--ink-3);margin:0 4px 10px;line-height:1.5}
.rec-xl{font-size:11.5px;font-weight:600;margin-left:10px;vertical-align:middle}
.pfc-diagram-btn{margin-left:12px;padding:5px 12px;font-size:12px;font-weight:600;vertical-align:middle;
  border:1px solid var(--accent);background:var(--accent-soft);color:var(--accent);border-radius:7px;cursor:pointer;transition:background .12s}
.pfc-diagram-btn:hover{background:var(--accent);color:#fff}
.rec-dl-group{display:inline-flex;align-items:center;gap:2px;margin-left:14px;padding-left:14px;border-left:1px solid var(--border)}
.rec-imp-opt{font-size:11.5px;color:var(--ink-2);display:inline-flex;align-items:center;gap:5px;margin-left:10px;cursor:pointer}
.rec-imp-opt input{margin:0}
.rec-parent{display:flex;align-items:center;gap:2px}
.rec-parent .tog{cursor:pointer;font-size:10px;color:var(--ink-3);width:14px;flex-shrink:0;text-align:center}
.rec-parent .rec-open{display:flex;align-items:center;gap:6px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
.ip-pop-foot{display:flex;justify-content:flex-end;gap:8px;padding:12px 18px;border-top:1px solid var(--border)}
.exp-btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.exp-btn.primary:hover{filter:brightness(1.05)}
.rec-imp-pop{max-width:460px}
.rec-imp-body{padding:16px 18px}
.rec-imp-q{margin:0 0 12px;font-size:13px;color:var(--ink-2)}
.rec-imp-choice{display:flex;align-items:flex-start;gap:9px;cursor:pointer;padding:9px 11px;border:1px solid var(--border);border-radius:9px;margin-bottom:8px}
.rec-imp-choice span{display:flex;flex-direction:column;line-height:1.3}
.rec-imp-choice span b{font-size:13px}.rec-imp-choice span small{font-size:11px;color:var(--ink-3)}
.rec-imp-choice:has(input:checked){border-color:var(--accent);background:var(--accent-soft)}
.rec-imp-exp{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--ink-2);margin-top:6px;cursor:pointer}
.rail{grid-row:1/3;background:var(--rail,#10202f);display:flex;flex-direction:column;align-items:center;padding:10px 0;gap:4px;z-index:6}
.rail .brand{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;margin-bottom:14px;
  background:linear-gradient(140deg,#2563eb,#0e7490)}
.rail a.rail-btn{width:42px;height:42px;border-radius:11px;color:var(--rail-ink);display:grid;place-items:center;
  position:relative;transition:.15s;text-decoration:none}
.rail a.rail-btn svg{width:21px;height:21px}
.rail a.rail-btn:hover{background:rgba(255,255,255,.07);color:#cfe0f0}
.rail a.rail-btn.active{background:rgba(96,165,250,.16);color:var(--rail-ink-active)}
.rail a.rail-btn.active::before{content:"";position:absolute;left:-10px;top:9px;bottom:9px;width:3px;border-radius:3px;background:#60a5fa}
.rail a.rail-btn .tip{position:absolute;left:50px;white-space:nowrap;background:#10202f;color:#e6edf3;padding:5px 9px;
  border-radius:7px;font-size:12px;opacity:0;pointer-events:none;transform:translateX(-4px);transition:.12s;box-shadow:var(--shadow);z-index:30}
.rail a.rail-btn:hover .tip{opacity:1;transform:translateX(0)}
.rail .spacer{flex:1}

.topbar{grid-column:2;display:flex;align-items:center;gap:14px;padding:0 16px;background:var(--surface);border-bottom:1px solid var(--border);z-index:5}
/* export picker (#7) */
.exp-pick-body{overflow:auto;padding:4px 18px 8px;flex:1}
.exp-search-wrap{padding:10px 18px 4px}
.exp-group{margin-bottom:10px}
.exp-group-h{font-weight:600;font-size:12.5px;padding:5px 0;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--surface);z-index:1}
.exp-cnt{color:var(--ink-3);font-weight:400;font-size:11px}
.exp-items{display:grid;grid-template-columns:1fr 1fr;gap:1px 14px;padding:6px 0 2px 6px}
.exp-ck{display:flex;align-items:center;gap:7px;cursor:pointer}
.exp-item{font-size:12.5px;color:var(--ink-2);padding:2px 0}
.exp-item:hover{color:var(--accent)}
.exp-foot{display:flex;align-items:center;gap:8px;padding:12px 18px;border-top:1px solid var(--border)}
.exp-selcount{font-size:12px;color:var(--ink-3);font-weight:600}
/* append redesign (#6) */
.ap-pop{max-width:500px}
.ap-body{padding:16px 20px 20px}
.ap-lead{margin:0 0 16px;color:var(--ink-2);font-size:13px;line-height:1.55}
.ap-drop{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:26px 18px;border:2px dashed var(--border-strong,#cbd5e1);border-radius:12px;cursor:pointer;transition:all .15s;text-align:center;color:var(--ink-3)}
.ap-drop:hover,.ap-drop.drag{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.ap-drop input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer}
.ap-drop-ico{opacity:.7}
.ap-drop-t{font-size:13px}.ap-drop-t b{color:var(--ink)}
.ap-drop-file{min-height:0}
.ap-chip{display:inline-block;margin-top:4px;background:var(--accent-soft);color:var(--accent);font-weight:600;font-size:12px;padding:3px 10px;border-radius:20px}
.ap-modes{margin-top:16px}
.ap-modes-lbl{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--ink-3);margin-bottom:7px}
.ap-mode{display:inline-flex;align-items:center;gap:8px;cursor:pointer;padding:8px 12px;border:1px solid var(--border);border-radius:9px;margin-right:8px}
.ap-mode span{display:flex;flex-direction:column;line-height:1.2}
.ap-mode span b{font-size:13px}.ap-mode span small{font-size:10.5px;color:var(--ink-3)}
.ap-mode:has(input:checked){border-color:var(--accent);background:var(--accent-soft)}
.ap-recover{margin-top:14px;padding:11px 13px;background:#fff7ed;border:1px solid #fdba74;border-radius:9px}
.ap-recover-t{font-size:12px;color:#9a3412;margin-bottom:8px;line-height:1.5}
.ap-status{font-size:12.5px;color:var(--ink-3);min-height:18px;margin-top:12px}
.ap-foot{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}
.ap-go{background:var(--accent);color:#fff;border:none}
.topbar h1{margin:0;font-size:15px;font-weight:600;letter-spacing:-.01em}
.topbar .sub{color:var(--ink-3);font-size:12px;font-family:'IBM Plex Mono'}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:12px}
/* #1: top-banner command palette (quick name-jump across all objects) */
.cmdp-wrap{flex:1;display:flex;justify-content:center;position:relative;min-width:0}
.cmdp-box{width:min(360px,42vw);display:flex;align-items:center;gap:8px;height:34px;padding:0 10px;background:var(--surface-2);border:1px solid var(--border-strong);border-radius:8px;cursor:text;transition:border-color .12s}
.cmdp-box:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.cmdp-box .cmdp-ico{font-size:14px;color:var(--ink-3);flex:0 0 auto}
.cmdp-box input{flex:1;border:none;background:transparent;outline:none;font-size:13px;color:var(--ink);min-width:0}
.cmdp-box input::placeholder{color:var(--ink-3)}
.cmdp-kbd{font-size:11px;color:var(--ink-3);border:1px solid var(--border);border-radius:5px;padding:1px 6px;font-family:'IBM Plex Mono';flex:0 0 auto}
.cmdp-pop{position:absolute;top:40px;width:min(400px,60vw);max-height:60vh;overflow:auto;background:var(--surface);border:1px solid var(--border-strong);border-radius:10px;box-shadow:0 12px 40px rgba(15,23,42,.28);z-index:60;display:none}
.cmdp-hint{padding:6px 12px;font-size:11px;color:var(--ink-3);border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--surface)}
.cmdp-item{display:flex;align-items:center;gap:10px;padding:8px 12px;cursor:pointer}
.cmdp-item:hover,.cmdp-item.act{background:var(--accent-soft)}
.cmdp-badge{font-size:10px;font-weight:600;color:#fff;border-radius:20px;padding:2px 8px;min-width:38px;text-align:center;flex:0 0 auto}
.cmdp-nm{flex:1;min-width:0;overflow:hidden}
.cmdp-nm .cn{font-size:13px;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cmdp-nm .cs{font-size:11px;color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cmdp-item mark{background:#fde68a;color:#7c4a03;border-radius:2px;padding:0 1px}
.cmdp-enter{font-size:13px;color:var(--accent);flex:0 0 auto;opacity:0}
.cmdp-item.act .cmdp-enter{opacity:1}
.cmdp-empty{padding:14px 12px;font-size:12.5px;color:var(--ink-3)}
.cmdp-action .cn{font-weight:600}
.cmdp-action{border-bottom:1px dashed var(--border)}
.cmdp-refbtn{flex:0 0 auto;font-size:11px;color:var(--ink-3);border:1px solid var(--border);border-radius:6px;padding:1px 6px;margin-right:4px;cursor:pointer}
.cmdp-refbtn:hover{border-color:var(--accent);color:var(--accent)}
@media(max-width:900px){.cmdp-wrap{display:none}}
.hdr-theme{display:flex;align-items:center;gap:7px}
.hdr-theme label{font-size:10.5px;color:var(--ink-3);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.hdr-theme select{background:var(--surface-2);color:var(--ink);border:1px solid var(--border);border-radius:8px;
  padding:6px 9px;font-size:12px;font-weight:600;cursor:pointer;outline:none}
.hdr-theme select:hover{border-color:var(--border-strong)}
.iconbtn{width:36px;height:36px;border-radius:9px;border:1px solid var(--border);background:var(--surface);
  color:var(--ink-2);display:grid;place-items:center;cursor:pointer;transition:.15s}
.iconbtn:hover{border-color:var(--border-strong);color:var(--ink)}
.iconbtn svg{width:18px;height:18px}
.hdr-export{display:flex;gap:8px}
.exp-btn{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:8px;background:var(--surface-2);
  border:1px solid var(--border);color:var(--ink-2);font-size:12px;font-weight:600;text-decoration:none;cursor:pointer}
.exp-btn:hover{border-color:var(--border-strong);color:var(--ink)}

.main{grid-column:2;overflow:hidden;display:flex;flex-direction:column;
  background:linear-gradient(var(--grid) 1px,transparent 1px) 0 0/26px 26px,
    linear-gradient(90deg,var(--grid) 1px,transparent 1px) 0 0/26px 26px,var(--canvas)}
.panes{flex:1;display:grid;grid-template-columns:var(--navw,316px) 10px 1fr;overflow:hidden}
.pane-divider{cursor:col-resize;background:var(--surface-2);position:relative;z-index:6;border-left:1px solid var(--border);border-right:1px solid var(--border)}
.pane-divider:hover,.pane-divider.dragging{background:var(--accent-soft)}
.pane-divider::after{content:'';position:absolute;left:50%;top:0;bottom:0;width:1px;transform:translateX(-50%);background:var(--border)}
.pane-divider:hover::after,.pane-divider.dragging::after{background:var(--accent)}
.pane-divider::before{content:'⋮';position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:14px;line-height:1;color:var(--ink-3);letter-spacing:-1px}
.pane-divider:hover::before{color:var(--accent)}

/* tree */
.nav{overflow:auto;background:color-mix(in srgb,var(--surface) 55%,transparent);padding:6px 8px}
.navsearch{position:sticky;top:0;z-index:5;padding:8px 6px 10px;background:var(--surface);border-bottom:1px solid var(--border);margin:-6px -8px 6px}
.navsearch input{width:100%;padding:9px 11px;border:1px solid var(--border);border-radius:9px;font-size:13px;
  outline:none;background:var(--surface-2);color:var(--ink);font-family:inherit}
.navsearch input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.navres{position:absolute;left:10px;right:10px;top:48px;background:var(--surface);border:1px solid var(--border-strong);
  border-radius:10px;box-shadow:var(--shadow);max-height:60vh;overflow:auto;z-index:20}
.navres-item{padding:8px 11px;cursor:pointer;font-size:13px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)}
.navres-item:last-child{border-bottom:0}
.navres-item.act,.navres-item:hover{background:var(--accent-soft)}
.navres-item .rtype{font-size:10px;color:#fff;border-radius:8px;padding:0 6px;flex:0 0 auto}
.navres-item .rname{font-weight:600;color:var(--ink)}
.navres-empty{padding:10px 11px;color:var(--ink-3);font-size:12px}
.navmode{display:flex;margin-top:6px;border:1px solid var(--border);border-radius:7px;overflow:hidden;width:fit-content}
.navmode .nm-btn{padding:4px 11px;background:var(--surface);border:0;cursor:pointer;font-size:11px;color:var(--ink-3);font-weight:600}
.navmode .nm-btn+.nm-btn{border-left:1px solid var(--border)}
.navmode .nm-btn.active{background:var(--accent);color:#fff}
.navres-item .rsnip{font-family:'IBM Plex Mono';font-size:11px;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.navres-item .rsnip mark,.navres-item .rname mark{background:var(--mark);color:var(--mark-ink);padding:0 1px;border-radius:2px}
.navres-item .rsub{font-size:10px;color:var(--ink-3)}
.navres-item.col{flex-direction:column;align-items:flex-start;gap:2px}
.navsec{padding:11px 10px 4px;font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3)}
.navfolder{display:flex;align-items:center;gap:6px;padding:6px 10px;font-size:12.5px;font-weight:600;
  color:var(--ink-2);cursor:pointer;user-select:none;border-radius:7px}
.navfolder:hover{background:var(--surface-2);color:var(--ink)}
.navfoldbody{margin-left:13px;border-left:1px solid var(--border);padding-left:3px}
.navph{padding:5px 10px 5px 16px;font-size:12.5px;color:var(--ink-3);font-style:italic;opacity:.65;cursor:default}
.navcount{font-family:'IBM Plex Mono';font-size:10.5px;color:var(--ink-3);font-weight:500;
  background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:0 7px;margin-left:2px}
.navsec-tog{cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px}
.navsec-tog:hover{color:var(--ink-2)}
.secarrow{font-size:10px;width:10px;display:inline-block}
.navitem{padding:5px 9px;cursor:pointer;font-size:13px;border-radius:8px;display:flex;align-items:center;gap:8px;color:var(--ink-2);position:relative}
.navitem:hover{background:var(--surface-2)}
.navitem.sel{background:var(--accent-soft);color:var(--ink);font-weight:500}
.navitem.sel::before{content:"";position:absolute;left:-8px;top:6px;bottom:6px;width:3px;border-radius:3px;background:var(--accent)}
.navitem .badge{font-size:10px;padding:0 6px;border-radius:7px;color:#fff;flex:0 0 auto}
.navitem .ic-badge{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;flex:0 0 auto}
.navitem .ic-badge svg{display:block}
.ic-area{color:var(--b-area)}.ic-cell{color:var(--b-cell)}.ic-unit{color:var(--b-unit)}.ic-uclass{color:var(--b-uclass)}
.ic-em{color:var(--b-em)}.ic-cm{color:var(--b-cm)}.ic-phase{color:var(--b-phase)}.ic-recipe{color:var(--b-recipe)}
.ic-inst{color:var(--ink-3)}
/* #5: EM/CM letter badge for Studio instance rows */
.stu-litem .ic-badge .ic-lett{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:4px;font-size:10px;font-weight:800;color:#fff;font-family:'IBM Plex Mono'}
.stu-litem .ic-em .ic-lett{background:var(--b-em)}
.stu-litem .ic-cm .ic-lett{background:var(--b-cm)}
.alias-ignored{font-size:11px;font-weight:600;color:#92600a;background:#fef3c7;padding:1px 8px;border-radius:20px}
.alias-unres{color:#94a3b8}
.alias-row-ign td:first-child code{opacity:.6}
.ic-badge.ic-shared{position:relative;filter:saturate(1.3)}
.ic-badge.ic-shared::after{content:"";position:absolute;right:-2px;bottom:-2px;width:6px;height:6px;border-radius:50%;background:#0891b2;border:1.5px solid var(--surface,#fff)}
.ic-composite{color:var(--b-composite)}.ic-fbtype{color:var(--b-fbtype)}
.navchild{padding-left:34px}
.nav-note{font-size:10.5px;color:var(--ink-3);padding:4px 12px 7px;line-height:1.5;font-style:italic}
.nav-empty{font-size:11px;color:var(--ink-3);padding:5px 12px 7px 34px;font-style:italic}
.io-point{align-items:center;gap:6px;font-size:12px}
.io-point .inst-tag{font-weight:500}
.io-kind{font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:4px;letter-spacing:.03em;flex:0 0 auto}
.io-ai{background:#dbeafe;color:#1e40af}
.io-di{background:#dcfce7;color:#166534}
.io-ao{background:#fef3c7;color:#92400e}
.io-do{background:#fce7f3;color:#9d174d}
.io-arrow{color:var(--ink-3);font-size:11px;flex:0 0 auto}
.io-open{cursor:pointer}
.io-tbl-tools{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.io-tbl-tools select{background:var(--surface-2);border:1px solid var(--border);border-radius:7px;padding:5px 9px;font-size:12.5px}
.io-tbl-count{font-size:12px;color:var(--ink-3)}
.io-tbl td{vertical-align:middle}
.io-dir{font-size:11px;color:var(--ink-3);white-space:nowrap}
.ref-card h4{margin:12px 0 7px;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink-3)}
.ref-chips{display:flex;flex-wrap:wrap;gap:6px}
.ref-chip{display:inline-flex;align-items:center;gap:5px;background:var(--surface-2);border:1px solid var(--border);border-radius:20px;padding:4px 11px;font-size:12.5px;cursor:pointer}
.ref-chip:hover{border-color:var(--accent);color:var(--accent)}
.ref-chip.ref-nolink{cursor:default;opacity:.75}
.ref-chip.ref-nolink:hover{border-color:var(--border);color:inherit}
.ref-role{color:var(--ink-3);font-size:11px}
.ref-cnt{color:var(--ink-3);font-size:11px;font-weight:600}
.navghost{opacity:.55;cursor:pointer;border:1px dashed transparent}
.navghost:hover{opacity:.9;background:var(--surface-2)}
.navghost .inst-cls{font-style:italic}
.navchild2{padding-left:50px}
.navchild3{padding-left:66px}
.navchild4{padding-left:82px}
.navinst{align-items:center}
.navinst .inst-tag{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.navinst .inst-cls{color:var(--ink-3);font-size:10.5px;margin-left:auto;padding-left:8px;white-space:nowrap;flex:0 0 auto}
.own-dot{display:inline-flex;align-items:center;margin-left:5px;flex:0 0 auto}
.own-dot svg{display:block}
.set-row{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:12px 0;border-bottom:1px solid var(--border)}
.set-row:last-of-type{border-bottom:0}
.set-lbl{font-size:13.5px;font-weight:600;color:var(--ink)}
.set-hint{font-size:12px;color:var(--ink-3);margin-top:2px}
.set-row select{background:var(--surface-2);color:var(--ink);border:1px solid var(--border);border-radius:8px;padding:6px 10px;font-size:13px;min-width:170px}
.set-note{margin-top:14px;font-size:11.5px;color:var(--ink-3)}
body[data-density="compact"] .fbd-table td,body[data-density="compact"] .fbd-table th{padding:3px 8px}
body[data-density="compact"] .card{padding:11px 13px;margin-bottom:10px}
body[data-density="compact"] .kv{gap:3px 12px}
.sim-chip{background:var(--accent-soft);border-color:var(--accent)!important;color:var(--accent);font-weight:600}
.sim-chip:hover{background:var(--accent);color:#fff}
.emsim-overlay{position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:9999;display:flex;align-items:center;justify-content:center}
.emsim-modal{background:#fff;border-radius:12px;width:94%;height:90%;max-width:1400px;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.35);overflow:hidden}
.emsim-h{display:flex;justify-content:space-between;align-items:center;padding:12px 18px;border-bottom:1px solid var(--border);flex-shrink:0}
.emsim-x{cursor:pointer;font-size:24px;color:var(--ink-3);line-height:1}
.emsim-x:hover{color:var(--ink)}
.emsim-frame{flex:1;border:none;width:100%}
.bigbtn{margin-top:12px;width:100%;padding:10px 12px;border:0;background:var(--accent);color:#fff;font-weight:600;font-size:13px;border-radius:9px;cursor:pointer;box-shadow:var(--shadow)}
.bigbtn:hover{filter:brightness(1.06)}
.navgroup{position:relative}
.navchildren{position:relative}
.navchildren .navchild{position:relative}
.navchildren .navchild::before{content:"";position:absolute;left:20px;top:0;bottom:50%;border-left:1px dashed var(--border-strong);border-bottom:1px dashed var(--border-strong);width:9px;border-bottom-left-radius:3px}
.navchildren .navchild:not(:last-child)::after{content:"";position:absolute;left:20px;top:50%;bottom:-2px;border-left:1px dashed var(--border-strong)}
.navchildren .navchild2::before{left:34px}
.navchildren .navchild2:not(:last-child)::after{left:34px}
.navchildren .navchild3::before{left:50px}
.navchildren .navchild3:not(:last-child)::after{left:50px}
.navchildren .navchild4::before{left:66px}
.navchildren .navchild4:not(:last-child)::after{left:66px}
.tog{cursor:pointer;user-select:none;color:var(--ink-3);width:12px;display:inline-block;font-size:10px}
.b-area{background:var(--b-area)}.b-unit{background:var(--b-unit)}.b-em{background:var(--b-em)}
.b-cm{background:var(--b-cm)}.b-phase{background:var(--b-phase)}.b-recipe{background:var(--b-recipe)}
.b-composite{background:var(--b-composite)}.b-uclass{background:var(--b-uclass)}.b-fbtype{background:var(--b-fbtype)}.b-nset{background:var(--b-nset)}.b-ctrl{background:var(--b-ctrl)}
.badge.b-inst{background:var(--b-inst)}

/* detail */
.detail{overflow:auto;padding:22px 24px 48px;position:relative}
.obj-export{position:absolute;top:18px;right:24px;display:flex;gap:6px;z-index:3}
.exp-mini{font-size:11.5px;font-weight:600;padding:5px 10px;border:1px solid var(--border);border-radius:7px;
  background:var(--surface);color:var(--ink-2);text-decoration:none;transition:.15s;white-space:nowrap}
.exp-mini:hover{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.exp-mini svg,.hdr-export a svg{width:13px;height:13px;vertical-align:-2px;margin-right:4px}
.metabinder{margin:2px 0 12px}
.metabinder>summary{cursor:pointer;color:var(--ink-3);font-size:12.5px;font-weight:600;list-style:none;
  display:inline-flex;align-items:center;gap:5px;padding:3px 0;user-select:none}
.metabinder>summary::-webkit-details-marker{display:none}
.metabinder>summary::before{content:'\\25b8';font-size:10px;transition:transform .15s}
.metabinder[open]>summary::before{transform:rotate(90deg)}
.metabinder .kv{margin-top:8px}
.ov-badge{display:inline-block;font:600 9px 'IBM Plex Sans';background:#fef3c7;color:#92400e;padding:1px 5px;border-radius:4px;vertical-align:middle;margin-left:5px}
.ip-default{display:inline-block;font:600 10px 'IBM Plex Sans';background:#f1f5f9;color:#94a3b8;padding:1px 7px;border-radius:5px;letter-spacing:.02em}
.ip-enum{font:12px 'IBM Plex Mono';padding:3px 7px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--ink);max-width:260px}
.ip-more{color:var(--accent);cursor:pointer;font-size:11px;font-weight:600;margin-left:4px;user-select:none}
.ip-more:hover{text-decoration:underline}
.ip-pop-overlay{position:fixed;inset:0;background:rgba(15,23,42,.4);z-index:9999;display:flex;align-items:center;justify-content:center}
.ip-pop{background:#fff;border-radius:12px;max-width:640px;width:90%;max-height:70vh;overflow:auto;box-shadow:0 20px 60px rgba(0,0,0,.3);padding:0}
.ip-pop-h{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid var(--border)}
.ip-pop-x{cursor:pointer;font-size:22px;color:var(--ink-3);line-height:1}
.ip-pop-x:hover{color:var(--ink)}
.ip-pop-meta{padding:8px 18px 0;color:var(--ink-3);font-size:12px}
.ip-pop-val{margin:8px 18px 18px;padding:12px;background:#f8fafc;border:1px solid var(--border);border-radius:8px;font:13px 'IBM Plex Mono';white-space:pre-wrap;word-break:break-word;color:#16202c}
/* floating reference-uses card — non-modal, draggable */
.ruse-card{position:fixed;z-index:10000;width:520px;max-width:92vw;max-height:70vh;display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--border-strong);border-radius:12px;box-shadow:0 18px 55px rgba(0,0,0,.32);overflow:hidden}
.ruse-h{display:flex;align-items:center;gap:8px;padding:11px 14px;border-bottom:1px solid var(--border);cursor:move;background:var(--surface-2);user-select:none}
.ruse-h b{font-size:13px;color:var(--ink)}
.ruse-h .ruse-sub{font-size:11.5px;color:var(--ink-3);font-weight:400}
.ruse-x{margin-left:auto;cursor:pointer;font-size:20px;line-height:1;color:var(--ink-3)}
.ruse-x:hover{color:var(--ink)}
.ruse-body{overflow:auto;padding:10px 14px 14px}
.ruse-item{border:1px solid var(--border);border-radius:9px;padding:9px 11px;margin:9px 0;background:var(--canvas)}
.ruse-ctx{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:6px}
.ruse-crumb{font-size:11px;font-weight:600;background:var(--accent-soft);color:var(--accent);padding:2px 8px;border-radius:20px}
.ruse-crumb .rc-kind{opacity:.7;font-weight:500;margin-right:3px}
.ruse-desc{font-size:12px;color:var(--ink-2);margin-bottom:5px;font-style:italic}
.ruse-key{font-size:10.5px;font-weight:700;letter-spacing:.04em;color:var(--ink-3);text-transform:uppercase}
.ruse-expr{font:12.5px 'IBM Plex Mono',monospace;white-space:pre-wrap;word-break:break-word;color:var(--ink);background:var(--surface-2);border:1px solid var(--border);border-radius:6px;padding:7px 9px;margin-top:3px}
.ruse-empty{color:var(--ink-3);font-size:13px;padding:14px 4px}
.ref-uses-btn{margin-left:5px;font-size:11px;color:var(--ink-3);border:1px solid var(--border);border-radius:6px;padding:0 6px;line-height:16px;cursor:pointer}
.ref-uses-btn:hover{border-color:var(--accent);color:var(--accent)}
/* #2: floating references window groups */
.refs-card{width:560px}
.refs-grp{margin:4px 0 12px}
.refs-grp-h{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-3);margin:8px 0 4px}
.refs-owner{display:flex;align-items:center;gap:8px;padding:7px 10px;border:1px solid var(--border);border-radius:8px;margin:5px 0;background:var(--surface-2)}
.refs-owner-hd{background:var(--accent-soft);border-color:var(--border-strong)}
.refs-owner:not(.refs-noopen){cursor:pointer}
.refs-owner:not(.refs-noopen):hover{border-color:var(--accent)}
.refs-oname{font-weight:600;font-size:13px;color:var(--ink)}
.refs-role{font-size:11px;color:var(--ink-3);font-family:'IBM Plex Mono'}
.refs-go{margin-left:auto;font-size:11px;color:var(--accent);font-weight:600}
.refs-noopen .refs-go{display:none}
.refs-use{border-left:2px solid var(--border);margin:6px 0 6px 10px;padding:4px 0 4px 10px}
.cm-group{margin:6px 0}
.cm-group>summary{cursor:pointer;font-size:12.5px;font-weight:600;color:var(--ink-2);padding:6px 0;list-style:none;user-select:none;display:flex;align-items:center;gap:7px}
.cm-group>summary::-webkit-details-marker{display:none}
.cm-group>summary::before{content:'\\25b8';font-size:10px;color:var(--ink-3);transition:transform .15s}
.cm-group[open]>summary::before{transform:rotate(90deg)}
.cm-count{background:var(--accent-soft);color:var(--accent);font-size:11px;font-weight:700;padding:1px 7px;border-radius:9px}
.cm-list{display:flex;flex-wrap:wrap;gap:7px;padding:6px 0 4px 18px}
.cm-chip{display:inline-flex;align-items:center;gap:7px;padding:6px 11px;border:1px solid var(--border);border-radius:8px;background:var(--surface);cursor:pointer;font-size:12px;transition:.15s}
.cm-chip:hover{border-color:var(--accent);background:var(--accent-soft)}
.cm-chip .cm-sub{color:var(--ink-3);font-size:11px}
.cm-ico{width:13px;height:13px;flex-shrink:0;border-radius:50%;position:relative}
.cm-ico-shared{background:#0891b2}
.cm-ico-shared::after{content:'';position:absolute;inset:3px;border:1.5px solid #fff;border-radius:50%;border-right-color:transparent}
.cm-ico-private{background:#6d28d9}
.cm-ico-private::after{content:'';position:absolute;left:4px;top:5px;width:5px;height:4px;border:1.5px solid #fff;border-bottom:none;border-radius:3px 3px 0 0}
.cm-ico-none{background:#cbd5e1}
.alias-filter{width:100%;max-width:420px;margin:0 0 10px;padding:7px 11px;border:1px solid var(--border);border-radius:8px;font-size:13px;background:var(--surface);color:var(--ink);font-family:inherit}
.loading-detail{display:flex;align-items:center;gap:10px;color:var(--ink-2);font-size:14px;margin-top:20px}
.spin{width:15px;height:15px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;display:inline-block;animation:dvspin .7s linear infinite}
@keyframes dvspin{to{transform:rotate(360deg)}}
/* attractive shimmer skeleton for lazy content */
.dv-skel{display:flex;flex-direction:column;gap:9px;margin-top:6px}
.dv-skel .ln{height:12px;border-radius:6px;background:linear-gradient(90deg,var(--surface-2) 25%,var(--border) 37%,var(--surface-2) 63%);background-size:400% 100%;animation:dvsheen 1.3s ease infinite}
.dv-skel .ln.w1{width:70%}.dv-skel .ln.w2{width:90%}.dv-skel .ln.w3{width:55%}
@keyframes dvsheen{0%{background-position:100% 0}100%{background-position:-100% 0}}
.dv-loader{display:inline-flex;align-items:center;gap:9px;color:var(--ink-2);font-size:13px}
.dv-dots{display:inline-flex;gap:3px}
.dv-dots i{width:6px;height:6px;border-radius:50%;background:var(--accent);display:inline-block;animation:dvbounce 1s ease-in-out infinite}
.dv-dots i:nth-child(2){animation-delay:.15s}.dv-dots i:nth-child(3){animation-delay:.3s}
/* selectable loader styles (#4). The active one is chosen by data-loader on <body>;
   the generic .dvload picks up whichever variant is active. */
.dvload{display:inline-flex;align-items:center;gap:7px;color:var(--ink-3);font-size:12px}
.dvload .lv{display:none}
body[data-loader="dots"] .dvload .lv-dots{display:inline-flex;gap:3px}
body[data-loader="dots"] .dvload .lv-dots i{width:6px;height:6px;border-radius:50%;background:var(--accent);animation:dvbounce 1s ease-in-out infinite}
body[data-loader="dots"] .dvload .lv-dots i:nth-child(2){animation-delay:.15s}
body[data-loader="dots"] .dvload .lv-dots i:nth-child(3){animation-delay:.3s}
body[data-loader="ring"] .dvload .lv-ring{display:inline-block;width:15px;height:15px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:dvspin .7s linear infinite}
body[data-loader="bars"] .dvload .lv-bars{display:inline-flex;gap:2px;align-items:flex-end;height:14px}
body[data-loader="bars"] .dvload .lv-bars i{width:3px;background:var(--accent);animation:dvbar 1s ease-in-out infinite}
body[data-loader="bars"] .dvload .lv-bars i:nth-child(1){animation-delay:0s}
body[data-loader="bars"] .dvload .lv-bars i:nth-child(2){animation-delay:.2s}
body[data-loader="bars"] .dvload .lv-bars i:nth-child(3){animation-delay:.4s}
body[data-loader="bars"] .dvload .lv-bars i:nth-child(4){animation-delay:.6s}
body[data-loader="pulse"] .dvload .lv-pulse{display:inline-block;width:13px;height:13px;border-radius:50%;background:var(--accent);animation:dvpulse 1s ease-in-out infinite}
body[data-loader="orbit"] .dvload .lv-orbit{display:inline-block;position:relative;width:16px;height:16px}
body[data-loader="orbit"] .dvload .lv-orbit::before{content:"";position:absolute;inset:0;border-radius:50%;border:2px solid var(--border)}
body[data-loader="orbit"] .dvload .lv-orbit::after{content:"";position:absolute;width:5px;height:5px;border-radius:50%;background:var(--accent);top:-1px;left:5px;transform-origin:3px 9px;animation:dvspin .9s linear infinite}
body[data-loader="rainbow"] .dvload .lv-rainbow{display:inline-block;width:15px;height:15px;border-radius:50%;border:2px solid transparent;background:conic-gradient(from 0deg,#ef4444,#f59e0b,#eab308,#22c55e,#3b82f6,#8b5cf6,#ef4444) border-box;-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 3px),#000 0);mask:radial-gradient(farthest-side,transparent calc(100% - 3px),#000 0);animation:dvspin .8s linear infinite}
body[data-loader="dotwave"] .dvload .lv-dotwave{display:inline-flex;gap:3px}
body[data-loader="dotwave"] .dvload .lv-dotwave i{width:7px;height:7px;border-radius:50%;animation:dvbounce 1s ease-in-out infinite}
body[data-loader="dotwave"] .dvload .lv-dotwave i:nth-child(1){background:#ef4444}
body[data-loader="dotwave"] .dvload .lv-dotwave i:nth-child(2){background:#3b82f6;animation-delay:.15s}
body[data-loader="dotwave"] .dvload .lv-dotwave i:nth-child(3){background:#22c55e;animation-delay:.3s}
body[data-loader="dotwave"] .dvload .lv-dotwave i:nth-child(4){background:#f59e0b;animation-delay:.45s}
body[data-loader="comet"] .dvload .lv-comet{display:inline-block;width:15px;height:15px;border-radius:50%;background:conic-gradient(from 0deg,transparent 0deg,var(--accent) 300deg,transparent 360deg);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 3px),#000 0);mask:radial-gradient(farthest-side,transparent calc(100% - 3px),#000 0);animation:dvspin .7s linear infinite}
body:not([data-loader]) .dvload .lv-dots,body[data-loader=""] .dvload .lv-dots{display:inline-flex;gap:3px}
body:not([data-loader]) .dvload .lv-dots i,body[data-loader=""] .dvload .lv-dots i{width:6px;height:6px;border-radius:50%;background:var(--accent);animation:dvbounce 1s ease-in-out infinite}
@keyframes dvspin{to{transform:rotate(360deg)}}
@keyframes dvbar{0%,100%{height:5px}50%{height:14px}}
@keyframes dvpulse{0%,100%{transform:scale(.5);opacity:.5}50%{transform:scale(1);opacity:1}}
@keyframes dvbounce{0%,80%,100%{transform:translateY(0);opacity:.4}40%{transform:translateY(-5px);opacity:1}}
h2.dt{margin:0;font-size:21px;font-weight:600;letter-spacing:-.01em;font-family:'IBM Plex Mono'}
.dt-type{display:inline-block;font-size:11px;color:#fff;padding:3px 10px;border-radius:8px;margin:8px 0 14px;font-weight:600;letter-spacing:.02em}
.dt-desc{color:var(--ink-2);margin:0 0 18px;font-size:13.5px}
.kv{display:grid;grid-template-columns:170px 1fr;gap:5px 16px;font-size:13px;margin-bottom:6px;max-width:760px}
.kv .k{color:var(--ink-3)}
.card{border:1px solid var(--border);border-radius:12px;padding:15px 16px;margin-bottom:14px;background:var(--surface);max-width:920px;box-shadow:var(--shadow)}
.card > h3{cursor:pointer;user-select:none;display:flex;align-items:center;gap:8px;margin:-4px -6px 8px;padding:4px 6px;border-radius:7px;transition:background .12s}
.card > h3:hover{background:var(--surface-2)}
.card > h3::before{content:'\\25be';font-size:11px;color:var(--accent);transition:transform .15s;flex-shrink:0}
.card.collapsed>h3{margin-bottom:-4px}
.card.collapsed>h3::before{transform:rotate(-90deg)}
.card.collapsed>*:not(h3){display:none!important}
.card.collapsed{padding-bottom:11px}
.subcard{border:1px solid var(--border);border-radius:9px;padding:11px 12px;margin:10px 0;background:var(--surface)}
.card > h4, .subcard > h4, .subcard > h3{cursor:pointer;user-select:none;display:flex;align-items:center;gap:7px;margin:0 0 7px;padding:2px 4px;border-radius:6px;transition:background .12s;font-size:12.5px}
.card > h4:hover, .subcard > h4:hover, .subcard > h3:hover{background:var(--surface-2)}
.card > h4::before, .subcard > h4::before, .subcard > h3::before{content:'\\25be';font-size:10px;color:var(--accent);transition:transform .15s;flex-shrink:0}
.card.collapsed>h4::before, .subcard.collapsed>h4::before, .subcard.collapsed>h3::before{transform:rotate(-90deg)}
.subcard.collapsed>*:not(h4):not(h3){display:none!important}
.card h3{margin:0 0 11px;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-3);font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:4px 10px;border:1px solid var(--border);border-radius:8px;font-size:12px;cursor:pointer;background:var(--surface-2);color:var(--ink-2);font-family:'IBM Plex Mono'}
.chip:hover{border-color:var(--accent);color:var(--ink)}
.link{color:var(--link);cursor:pointer;text-decoration:none;border-bottom:1px solid color-mix(in srgb,var(--link) 35%,transparent)}
.link:hover{border-bottom-color:var(--link)}
.empty{color:var(--ink-3);font-style:italic}
.welcome{color:var(--ink-2);max-width:680px}
.welcome h2{font-size:18px;color:var(--ink)}
.dtree{margin:6px 0 0 4px}
.dtree .tnode{position:relative;padding:3px 0 3px 22px;font-size:13px}
.dtree .tnode::before{content:"";position:absolute;left:6px;top:0;height:14px;width:12px;border-left:1px dashed var(--border-strong);border-bottom:1px dashed var(--border-strong);border-bottom-left-radius:3px}
.dtree .tnode:not(:last-child)::after{content:"";position:absolute;left:6px;top:14px;bottom:-3px;border-left:1px dashed var(--border-strong)}
.dtree .troot{font-weight:600;padding:2px 0}
.tnode .link{font-size:13px}
.phaseframe{width:100%;height:88vh;border:1px solid var(--border);border-radius:10px;background:#fff}
.frame-wrap{position:relative}
.frame-load{position:absolute;top:0;left:0;right:0;height:120px;display:flex;align-items:center;justify-content:center;gap:10px;color:var(--ink-2);font-size:14px;background:var(--surface);border:1px solid var(--border);border-radius:10px;z-index:2}
.emtabs{display:flex;gap:6px;margin-bottom:12px}
.pgrp{margin:6px 0 14px}.pgrp-h{font-size:12px;font-weight:600;color:var(--ink-2);text-transform:uppercase;letter-spacing:.04em;margin:10px 0 6px;display:flex;align-items:center;gap:8px}
.ptype{font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--ink-3);white-space:nowrap}.pdesc{color:var(--ink-2);font-size:12.5px}
.emtab{padding:7px 15px;border:1px solid var(--border);border-radius:9px;background:var(--surface);cursor:pointer;font-size:13px;font-weight:600;color:var(--ink-2)}
.emtab.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.empanel{display:none}.empanel.on{display:block}
.fbd-wrap{display:flex;flex-direction:column;gap:14px}
.fbd-diagram-card{border:1px solid var(--border);border-radius:10px;background:var(--surface);overflow:hidden}
.fbd-head{padding:10px 14px;background:var(--surface-2);font-weight:600;font-size:13px;border-bottom:1px solid var(--border);color:var(--ink)}
.fbd-sub{color:var(--ink-3);font-weight:400;font-size:12px}
.fbd-svg-holder{padding:10px;overflow:auto;max-height:78vh;background:var(--surface)}
/* The FBD SVG is drawn with a fixed light palette (white block fills, dark text).
   In dark mode, recolor the holder and softly invert the SVG so it reads correctly
   on a dark surface without rewriting the shared fbd_bridge renderer. */
[data-theme="dark"] .fbd-diagram-card,[data-theme="dark"] .fbd-svg-holder{background:#0f1722}
[data-theme="dark"] .fbd-svg-holder svg{filter:invert(0.92) hue-rotate(180deg)}
.io-dnet{display:flex;flex-direction:column;gap:12px}
.io-dnet-summary{color:var(--ink-3);font-size:12.5px}
.io-info-card{border:1px solid var(--border);border-radius:10px;padding:12px 14px;background:var(--surface)}
.io-info-card>h4{margin:0 0 10px;font-size:13px;color:var(--ink);cursor:pointer;user-select:none}
.io-info-card>h4::before{content:"\\25be";display:inline-block;margin-right:6px;font-size:10px;color:var(--ink-3);transition:transform .12s}
.io-info-card.collapsed>h4::before{transform:rotate(-90deg)}
.io-info-card.collapsed>*:not(h4){display:none!important}
.io-sub{color:var(--ink-3);font-weight:400;font-size:11.5px}
.io-card-grp{margin:8px 0 8px 6px;padding-left:10px;border-left:2px solid var(--border)}
.io-card-h{font-weight:600;font-size:12.5px;color:var(--ink-2);margin-bottom:5px}
.io-port-grp{margin:6px 0 6px 8px}
.io-port-h{font-size:12px;color:var(--ink-3);margin-bottom:5px}
.io-dev{border:1px solid var(--border);border-radius:8px;padding:9px 11px;margin:6px 0;background:var(--surface-2)}
.io-dev-h{font-size:13px;margin-bottom:3px}
.io-dev-addr{color:#0891b2;font-family:'IBM Plex Mono';font-size:11.5px;margin:0 6px}
.io-dev-meta{color:var(--ink-3);font-size:11.5px;margin-bottom:7px}
.io-sig-tbl{width:100%;border-collapse:collapse;font-size:11.5px;font-family:'IBM Plex Mono'}
.io-sig-tbl th{text-align:left;padding:4px 8px;color:var(--ink-3);font-family:'IBM Plex Sans';font-size:10.5px;text-transform:uppercase;letter-spacing:.03em;border-bottom:1px solid var(--border)}
.io-sig-tbl td{padding:4px 8px;border-bottom:1px solid var(--border);vertical-align:top}
.io-sig-tbl tr:last-child td{border-bottom:0}
.io-tag{color:#0369a1}
.av-report{display:flex;flex-direction:column;gap:12px}
.av-summary{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:4px}
.av-chip{font-size:12px;padding:4px 10px;border-radius:20px;background:var(--surface-2);border:1px solid var(--border);color:var(--ink-2)}
.av-err-c{background:#fef2f2;border-color:#fecaca;color:#b91c1c}
.av-warn-c{background:#fffbeb;border-color:#fde68a;color:#b45309}
.av-info-c{background:#eff6ff;border-color:#bfdbfe;color:#1d4ed8}
[data-theme="dark"] .av-err-c{background:#3b1a1a;border-color:#7f1d1d;color:#fca5a5}
[data-theme="dark"] .av-warn-c{background:#3a2f15;border-color:#78511a;color:#fcd34d}
[data-theme="dark"] .av-info-c{background:#1e293b;border-color:#334155;color:#93c5fd}
.av-unit{border:1px solid var(--border);border-radius:10px;padding:12px 14px;background:var(--surface)}
.av-unit>h4{margin:0 0 10px;font-size:13px;color:var(--ink);cursor:pointer;user-select:none;display:flex;align-items:center;gap:8px}
.av-unit>h4::after{content:"\\25be";margin-left:auto;font-size:10px;color:var(--ink-3);transition:transform .12s}
.av-unit.collapsed>h4::after{transform:rotate(-90deg)}
.av-unit.collapsed>*:not(h4){display:none!important}
.av-dot{width:9px;height:9px;border-radius:50%;flex-shrink:0}
.av-dot-err{background:#dc2626}.av-dot-warn{background:#d97706}.av-dot-ok{background:#16a34a}
.av-sub{color:var(--ink-3);font-weight:400;font-size:11.5px}
.av-unit-counts{color:var(--ink-3);font-family:'IBM Plex Mono';font-size:11px}
.av-tbl{width:100%;border-collapse:collapse;font-size:12px}
.av-tbl th{text-align:left;padding:5px 9px;color:var(--ink-3);font-size:10.5px;text-transform:uppercase;letter-spacing:.03em;border-bottom:1px solid var(--border)}
.av-tbl td{padding:5px 9px;border-bottom:1px solid var(--border);vertical-align:top}
.av-tbl tr:last-child td{border-bottom:0}
.av-alias{font-family:'IBM Plex Mono';color:#7c3aed}
.av-detail{color:var(--ink-2)}
.av-sev{font-size:10px;font-weight:700;padding:1px 7px;border-radius:4px;letter-spacing:.04em}
.av-err{background:#fee2e2;color:#b91c1c}.av-warn{background:#fef3c7;color:#b45309}.av-info{background:#dbeafe;color:#1d4ed8}
[data-theme="dark"] .av-err{background:#7f1d1d;color:#fecaca}
[data-theme="dark"] .av-warn{background:#78511a;color:#fde68a}
[data-theme="dark"] .av-info{background:#1e3a5f;color:#bfdbfe}
.av-clean{color:#16a34a;font-size:12.5px}
.fbd-info-card{border:1px solid var(--border);border-radius:10px;padding:12px 14px;background:var(--surface)}
.fbd-info-card h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:var(--ink-3)}
.fbd-collapse>h4,.fbd-collapse>.fbd-head{cursor:pointer;user-select:none}
.fbd-collapse>h4::before,.fbd-collapse>.fbd-head::before{content:"\\25be";display:inline-block;margin-right:6px;font-size:10px;transition:transform .12s;color:var(--ink-3)}
.fbd-collapse.collapsed>h4::before,.fbd-collapse.collapsed>.fbd-head::before{transform:rotate(-90deg)}
.fbd-info-card.fbd-collapse.collapsed>*:not(h4){display:none!important}
.fbd-diagram-card.fbd-collapse.collapsed>*:not(.fbd-head){display:none!important}
.fbd-comp-link{border-color:var(--border-strong)}
.fbd-table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px}
.fbd-table th{text-align:left;padding:7px 12px;color:var(--ink-3);font-size:11px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--border);font-weight:600}
.fbd-table td{padding:7px 12px;border-bottom:1px solid var(--border);vertical-align:top;font-family:'IBM Plex Mono';font-size:12px}
.fbd-table td.p,.fbd-table th{font-family:'IBM Plex Sans'}
.fbd-table tr:last-child td{border-bottom:0}
.fbd-table code{font-size:11px;background:var(--surface-2);padding:1px 5px;border-radius:4px}
.fb-composite rect:first-of-type{transition:fill .15s}
.fb{cursor:default}
.stat{display:inline-block;margin:0 20px 12px 0}
.stat b{font-size:24px;display:block;font-family:'IBM Plex Mono'}
.stat span{font-size:12px;color:var(--ink-3)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""


def _badge(otype):
    m = {'Area': 'b-area', 'Unit Instance': 'b-unit', 'EM Class': 'b-em',
         'CM Class': 'b-cm', 'Phase Class': 'b-phase', 'Recipe': 'b-recipe',
         'Composite': 'b-composite', 'Unit Class': 'b-uclass'}
    return m.get(otype, 'b-composite')


_NAV_BADGE_CLS = {'area': 'ic-area', 'unit': 'ic-unit', 'em': 'ic-em', 'cm': 'ic-cm',
                  'inst': 'ic-cm', 'phase': 'ic-phase', 'recipe': 'ic-recipe',
                  'composite': 'ic-composite', 'uclass': 'ic-uclass', 'fbtype': 'ic-fbtype',
                  'cell': 'ic-cell'}
_NAV_TITLE = {'area': 'Area', 'unit': 'Unit', 'em': 'Equipment Module',
              'cm': 'Control Module', 'inst': 'Control Module', 'phase': 'Phase',
              'recipe': 'Recipe', 'composite': 'Composite', 'uclass': 'Unit Class',
              'fbtype': 'Function Block Type', 'cell': 'Process Cell'}
# Line/outline icons (stroke = currentColor); Control Module is a filled valve bow-tie.
_O = 'fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"'
_F = 'fill="currentColor" stroke="none"'
_NAV_ICON = {
    'area': f'<rect x="2" y="3" width="11" height="2.4" rx="1" {_O}/><rect x="2" y="6.3" width="11" height="2.4" rx="1" {_O}/><rect x="2" y="9.6" width="11" height="2.4" rx="1" {_O}/>',
    'cell': f'<rect x="2" y="2.5" width="11" height="10" rx="1.4" {_O} stroke-dasharray="2.3 1.5"/><rect x="4" y="5.4" width="3" height="4.2" rx="0.6" {_O}/><rect x="8" y="5.4" width="3" height="4.2" rx="0.6" {_O}/>',
    'unit': f'<ellipse cx="7.5" cy="4" rx="3.6" ry="1.4" {_O}/><path d="M3.9 4v6.8a3.6 1.4 0 0 0 7.2 0V4" {_O}/>',
    'uclass': f'<ellipse cx="7.5" cy="4" rx="3.6" ry="1.4" {_O} stroke-dasharray="2 1.3"/><path d="M3.9 4v6.8a3.6 1.4 0 0 0 7.2 0V4" {_O} stroke-dasharray="2 1.3"/>',
    'em': f'<path d="M7.5 2l4.7 2.75v5.5L7.5 13l-4.7-2.75v-5.5z" {_O}/>',
    'cm': f'<path d="M2.5 4 7.5 7.5 2.5 11Z" {_F}/><path d="M12.5 4 7.5 7.5 12.5 11Z" {_F}/>',
    'phase': f'<rect x="3" y="4" width="9" height="7" rx="1.2" {_O}/><path d="M7.5 2v2M7.5 11v2" {_O}/>',
    'recipe': f'<path d="M4 2.4h4.6l2.6 2.6v7.6h-7.2z" {_O}/><path d="M8.4 2.4v2.8h2.8M5.5 8h4M5.5 10h3" {_O}/>',
    'composite': f'<rect x="2.4" y="2.4" width="7" height="7" rx="1.1" {_O}/><rect x="5.6" y="5.6" width="7" height="7" rx="1.1" {_O}/>',
    'fbtype': f'<rect x="3.6" y="3.6" width="7.8" height="7.8" rx="1.1" {_O}/><path d="M1.9 6h1.7M1.9 9h1.7M11.4 6h1.7M11.4 9h1.7" {_O}/>',
}
_NAV_ICON['inst'] = _NAV_ICON['cm']

# ── switchable icon themes (re-skinnable live in the browser) ──
# Each theme provides an SVG glyph per type, all using currentColor so the JS
# switcher only has to swap markup + set the element colour.
_TYPE_KEYS = ['area', 'cell', 'unit', 'uclass', 'em', 'cm', 'inst', 'phase',
              'recipe', 'composite', 'fbtype']


def _isa(code, fs):
    return (f'<circle cx="7.5" cy="7.5" r="6" fill="#fff" stroke="currentColor" stroke-width="1.4"/>'
            f'<text x="7.5" y="{7.5 + fs * 0.36:.1f}" font-size="{fs}" fill="currentColor" '
            f'text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700">{code}</text>')


_ICON_THEMES = {
    'outline': dict(_NAV_ICON),
    'deltav': {
        'area': f'<rect x="2.4" y="9" width="9" height="2.7" rx="0.7" {_F}/><rect x="3" y="6.1" width="9" height="2.7" rx="0.7" {_F} opacity="0.82"/><rect x="3.6" y="3.2" width="9" height="2.7" rx="0.7" {_F} opacity="0.64"/>',
        'cell': f'<path d="M7.5 2l1.7 1.7L7.5 5.4 5.8 3.7Z" {_F}/><path d="M4.2 6.3l1.7 1.7L4.2 9.7 2.5 8Z" {_F}/><path d="M10.8 6.3l1.7 1.7-1.7 1.7L9.1 8Z" {_F}/><path d="M7.5 9.6l1.7 1.7-1.7 1.7-1.7-1.7Z" {_F}/>',
        'unit': f'<ellipse cx="7.5" cy="3.9" rx="4" ry="1.5" {_F}/><path d="M3.5 3.9v6.8a4 1.5 0 0 0 8 0V3.9" {_O}/>',
        'uclass': f'<ellipse cx="7.5" cy="3.9" rx="4" ry="1.5" {_O}/><path d="M3.5 3.9v6.8a4 1.5 0 0 0 8 0V3.9" {_O}/>',
        'em': f'<rect x="2.4" y="2.4" width="4.3" height="4.3" rx="0.8" {_F}/><rect x="8.3" y="2.4" width="4.3" height="4.3" rx="0.8" {_F} opacity="0.8"/><rect x="2.4" y="8.3" width="4.3" height="4.3" rx="0.8" {_F} opacity="0.8"/><rect x="8.3" y="8.3" width="4.3" height="4.3" rx="0.8" {_F}/>',
        'cm': f'<path d="M2.5 4 7.5 7.5 2.5 11Z" {_F}/><path d="M12.5 4 7.5 7.5 12.5 11Z" {_F}/>',
        'inst': f'<circle cx="7.5" cy="4.4" r="2" {_F}/><circle cx="4.4" cy="7.5" r="2" {_F}/><circle cx="10.6" cy="7.5" r="2" {_F}/><circle cx="7.5" cy="10.6" r="2" {_F}/>',
        'phase': f'<path d="M7.5 1.8V3.8M7.5 11.2V13.2" {_O}/><rect x="3" y="3.8" width="9" height="7.4" rx="1" {_O}/><rect x="3" y="3.8" width="2" height="7.4" {_F}/>',
        'recipe': f'<path d="M2 4.5a1 1 0 0 1 1-1h3l1.2 1.3H12a1 1 0 0 1 1 1v5.4a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1Z" {_F}/>',
        'composite': f'<rect x="2.6" y="2.6" width="6.3" height="6.3" rx="1" {_O}/><rect x="6.1" y="6.1" width="6.3" height="6.3" rx="1" {_F}/>',
        'fbtype': f'<rect x="3.6" y="3.6" width="7.8" height="7.8" rx="1.1" {_O}/><path d="M1.9 6h1.7M1.9 9h1.7M11.4 6h1.7M11.4 9h1.7" {_O}/>',
    },
    'geometric': {
        'area': f'<rect x="2" y="2" width="11" height="11" rx="2.4" {_F}/>',
        'cell': f'<rect x="2" y="2" width="11" height="11" rx="2.4" {_O}/>',
        'unit': f'<circle cx="7.5" cy="7.5" r="5.6" {_F}/>',
        'uclass': f'<circle cx="7.5" cy="7.5" r="5.4" {_O}/>',
        'em': f'<path d="M7.5 1.6l5.1 2.95v5.9L7.5 13.4l-5.1-2.95v-5.9z" {_F}/>',
        'cm': f'<path d="M7.5 2 13 12.5 2 12.5z" {_F}/>',
        'inst': f'<path d="M7.5 3 11.6 11 3.4 11z" {_F}/>',
        'phase': f'<path d="M7.5 1.8 13.2 7.5 7.5 13.2 1.8 7.5z" {_F}/>',
        'recipe': f'<path d="M7.5 1.8l5.4 3.9-2.06 6.35h-6.68L2.1 5.7z" {_F}/>',
        'composite': f'<rect x="2.4" y="2.4" width="7" height="7" rx="1.1" {_O}/><rect x="5.6" y="5.6" width="7" height="7" rx="1.1" {_F}/>',
        'fbtype': f'<rect x="2.4" y="2.4" width="10.2" height="10.2" rx="2" {_F}/>',
    },
    'isa': {
        'area': _isa('A', 7), 'cell': _isa('PC', 5.2), 'unit': _isa('U', 7),
        'uclass': _isa('UC', 5.2), 'em': _isa('EM', 5.2), 'cm': _isa('CM', 5.2),
        'inst': _isa('CM', 5.2), 'phase': _isa('PH', 5.2), 'recipe': _isa('R', 7),
        'composite': _isa('CX', 5.2), 'fbtype': _isa('FB', 5.2),
    },
}

_COL_OUTLINE = {'area': '#0284c7', 'cell': '#0891b2', 'unit': '#059669', 'uclass': '#047857',
                'em': '#7c3aed', 'cm': '#d97706', 'inst': '#d97706', 'phase': '#db2777',
                'recipe': '#dc2626', 'composite': '#475569', 'fbtype': '#0d9488'}
_COL_DELTAV = {'area': '#a9772b', 'cell': '#7e3ff2', 'unit': '#1f6fb2', 'uclass': '#1f6fb2',
               'em': '#e08a00', 'cm': '#9b2c2c', 'inst': '#cf3d9e', 'phase': '#d6409f',
               'recipe': '#b8860b', 'composite': '#475569', 'fbtype': '#0d9488'}
_THEME_COLORS = {'outline': _COL_OUTLINE, 'deltav': _COL_DELTAV,
                 'geometric': _COL_OUTLINE, 'isa': _COL_OUTLINE}
_THEME_LABELS = [('outline', 'Line / outline'), ('deltav', 'DeltaV-matched'),
                 ('block', 'Module-block'), ('pid', 'P&ID physical'),
                 ('geometric', 'Geometric'), ('pill', 'Filled pill'),
                 ('duotone', 'Duotone'), ('mono', 'Monogram'), ('isa', 'ISA balloon')]

_CODES = {'area': 'A', 'cell': 'PC', 'unit': 'U', 'uclass': 'UC', 'em': 'EM',
          'cm': 'CM', 'inst': 'CM', 'phase': 'PH', 'recipe': 'R', 'composite': 'CX',
          'fbtype': 'FB'}
_WHF = 'fill="#ffffff" stroke="none"'
_WHO = 'fill="none" stroke="#ffffff" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"'

# Module-block theme (DeltaV Control Studio block-with-header motif)
_ICON_THEMES['block'] = {
    'area': f'<rect x="2" y="3" width="11" height="9.2" rx="1.3" {_O}/><rect x="2" y="3" width="11" height="2.7" rx="1.2" {_F}/><path d="M4 8h7M4 10h5" {_O}/>',
    'cell': f'<rect x="2" y="2.5" width="11" height="10" rx="1.4" {_O} stroke-dasharray="2.3 1.5"/><rect x="4" y="5.4" width="3" height="4.2" rx="0.6" {_F}/><rect x="8" y="5.4" width="3" height="4.2" rx="0.6" {_F}/>',
    'unit': f'<rect x="2.3" y="3" width="10.4" height="9" rx="1.2" {_O}/><rect x="2.3" y="3" width="10.4" height="2.7" rx="1.2" {_F}/><path d="M6 7.2a1.5 1 0 0 1 3 0v2a1.5 1 0 0 1-3 0Z" {_F}/>',
    'uclass': f'<rect x="2.3" y="3" width="10.4" height="9" rx="1.2" {_O} stroke-dasharray="2 1.3"/><rect x="2.3" y="3" width="10.4" height="2.7" rx="1.2" {_F}/>',
    'em': f'<rect x="2" y="3" width="11" height="9" rx="1.1" {_O}/><rect x="2" y="3" width="11" height="2.4" {_F}/><rect x="3.6" y="6.4" width="3" height="3.5" rx="0.5" {_F}/><rect x="8.4" y="6.4" width="3" height="3.5" rx="0.5" {_F}/>',
    'cm': f'<rect x="2.5" y="3.8" width="10" height="7.4" rx="1.1" {_F}/><rect x="2.5" y="3.8" width="10" height="2.4" rx="1.1" fill="#fff" opacity="0.55"/>',
    'inst': f'<rect x="3" y="3.8" width="9" height="7.4" rx="1.1" {_F}/><rect x="3" y="3.8" width="9" height="2.3" rx="1.1" fill="#fff" opacity="0.55"/>',
    'phase': f'<path d="M7.5 1.8V3.8M7.5 11.2V13.2" {_O}/><rect x="3" y="3.8" width="9" height="7.4" rx="1" {_O}/><rect x="3" y="3.8" width="2" height="7.4" {_F}/>',
    'recipe': f'<rect x="5" y="2" width="5" height="2.6" rx="0.6" {_F}/><rect x="5" y="6.2" width="5" height="2.6" rx="0.6" {_F}/><rect x="5" y="10.4" width="5" height="2.6" rx="0.6" {_F}/><path d="M7.5 4.6v1.6M7.5 8.8v1.6" {_O}/>',
    'composite': f'<rect x="2.4" y="2.4" width="7" height="7" rx="1.1" {_O}/><rect x="5.6" y="5.6" width="7" height="7" rx="1.1" {_F}/>',
    'fbtype': f'<rect x="3.6" y="3.6" width="7.8" height="7.8" rx="1.1" {_O}/><path d="M1.9 6h1.7M1.9 9h1.7M11.4 6h1.7M11.4 9h1.7" {_O}/>',
}
# P&ID physical theme (plant, vessels, valves, flask)
_ICON_THEMES['pid'] = {
    'area': f'<path d="M2 13V7.5l2.4 1.2V7.5l2.4 1.2V7.5l2.4 1.2V6l1.8 1V13Z" {_F}/>',
    'cell': f'<rect x="2.4" y="2.4" width="4.4" height="4.4" rx="1" {_F}/><rect x="8.2" y="2.4" width="4.4" height="4.4" rx="1" {_F}/><rect x="2.4" y="8.2" width="4.4" height="4.4" rx="1" {_F}/><rect x="8.2" y="8.2" width="4.4" height="4.4" rx="1" {_F}/>',
    'unit': f'<path d="M4 4.2a3.5 1.4 0 0 1 7 0v6.6a3.5 1.4 0 0 1-7 0Z" {_F}/>',
    'uclass': f'<path d="M4 4.2a3.5 1.4 0 0 1 7 0v6.6a3.5 1.4 0 0 1-7 0Z" {_O}/>',
    'em': f'<rect x="2" y="4" width="11" height="7" rx="0.8" {_O}/><path d="M4.5 4v7M8 4v7M11 4v7" {_O}/>',
    'cm': f'<path d="M2.5 4 7.5 7.5 2.5 11Z" {_F}/><path d="M12.5 4 7.5 7.5 12.5 11Z" {_F}/>',
    'inst': f'<path d="M2.5 4 7.5 7.5 2.5 11Z" {_F}/><path d="M12.5 4 7.5 7.5 12.5 11Z" {_F}/>',
    'phase': f'<path d="M7.5 1.8V3.8M7.5 11.2V13.2" {_O}/><rect x="3" y="3.8" width="9" height="7.4" rx="1" {_O}/><rect x="3" y="3.8" width="2" height="7.4" {_F}/>',
    'recipe': f'<path d="M6.2 2v3.4L3.3 11a1.1 1.1 0 0 0 1 1.7h6.4a1.1 1.1 0 0 0 1-1.7L8.8 5.4V2Z" {_O}/><path d="M5.5 2h4M5.2 8.7h4.6" {_O}/>',
    'composite': f'<rect x="2.4" y="2.4" width="7" height="7" rx="1.1" {_O}/><rect x="5.6" y="5.6" width="7" height="7" rx="1.1" {_O}/>',
    'fbtype': f'<rect x="3.6" y="3.6" width="7.8" height="7.8" rx="1.1" {_O}/><path d="M1.9 6h1.7M1.9 9h1.7M11.4 6h1.7M11.4 9h1.7" {_O}/>',
}


def _pillify(inner):
    return ('<rect x="0.5" y="0.5" width="14" height="14" rx="4" fill="currentColor"/>'
            + inner.replace('currentColor', '#ffffff'))


def _duotone(inner):
    return ('<rect x="0.5" y="0.5" width="14" height="14" rx="4" fill="currentColor" opacity="0.16"/>'
            + inner)


def _mono(code):
    fs = 7 if len(code) == 1 else 5.4
    return ('<rect x="0.5" y="0.5" width="14" height="14" rx="4" fill="currentColor" opacity="0.16"/>'
            f'<text x="7.5" y="{7.5 + fs * 0.36:.1f}" font-size="{fs}" fill="currentColor" '
            f'text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700">{code}</text>')


_ICON_THEMES['pill'] = {t: _pillify(_ICON_THEMES['outline'][t]) for t in _TYPE_KEYS}
_ICON_THEMES['pill']['inst'] = _pillify(_ICON_THEMES['outline']['inst'])
_ICON_THEMES['duotone'] = {t: _duotone(_ICON_THEMES['geometric'][t]) for t in _TYPE_KEYS}
_ICON_THEMES['duotone']['inst'] = _duotone(_ICON_THEMES['geometric']['inst'])
_ICON_THEMES['mono'] = {t: _mono(_CODES[t]) for t in _TYPE_KEYS}
_ICON_THEMES['mono']['inst'] = _mono(_CODES['inst'])

for _t in ('block', 'geometric', 'pill', 'duotone', 'mono'):
    _THEME_COLORS[_t] = _COL_OUTLINE
_THEME_COLORS['pid'] = _COL_DELTAV



def _ownership_nav_ico(own):
    """Small inline indicator for shared/private CM ownership in the nav tree (#4)."""
    if own == 'SHARED':
        return ('<span class="own-dot own-shared" title="Shared — usable by multiple EMs">'
                '<svg width="11" height="11" viewBox="0 0 11 11"><circle cx="5.5" cy="5.5" r="4.2" '
                'fill="none" stroke="#0891b2" stroke-width="1.4" stroke-dasharray="3 2"/></svg></span>')
    if own == 'PRIVATE':
        return ('<span class="own-dot own-private" title="Private — owned by this EM">'
                '<svg width="11" height="11" viewBox="0 0 11 11"><rect x="2.4" y="4.6" width="6.2" height="4.4" '
                'rx="1" fill="#6d28d9"/><path d="M3.7 4.6V3.5a1.8 1.8 0 0 1 3.6 0v1.1" fill="none" '
                'stroke="#6d28d9" stroke-width="1.2"/></svg></span>')
    return ''


def _nav_badge(key, own=None):
    if key == 'nset':
        return ('<span class="ic-badge b-nset" title="Named Set">'
                '<svg viewBox="0 0 15 15" width="15" height="15" aria-hidden="true">'
                '<rect x="2.4" y="2.4" width="10.2" height="10.2" rx="2.2" fill="none" stroke="#fff" stroke-width="1.3"/>'
                '<path d="M5 5.4h5M5 7.5h5M5 9.6h3" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/></svg></span>')
    if key == 'ctrl':
        return ('<span class="ic-badge b-ctrl" title="Controller">'
                '<svg viewBox="0 0 15 15" width="15" height="15" aria-hidden="true">'
                '<rect x="3" y="2.6" width="9" height="9.8" rx="1.4" fill="none" stroke="#fff" stroke-width="1.3"/>'
                '<rect x="5.4" y="5" width="4.2" height="4.2" rx="0.6" fill="#fff"/>'
                '<path d="M5.4 2.6V1.4M9.6 2.6V1.4M5.4 13.6v-1.2M9.6 13.6v-1.2M3 5.6H1.6M3 9.4H1.6M13.4 5.6H12M13.4 9.4H12" stroke="#fff" stroke-width="1.1" stroke-linecap="round"/></svg></span>')
    cls = _NAV_BADGE_CLS.get(key, 'b-composite')
    title = _NAV_TITLE.get(key, key)
    # #1: a CM that's a SHARED EM member gets a visually distinct badge (dashed ring
    # overlay + shared tint) so shared CMs read differently from private/standalone CMs.
    own_cls = ''
    own_extra = ''
    if key in ('cm', 'inst') and (own or '').upper() == 'SHARED':
        own_cls = ' ic-shared'
        title = 'Shared control module'
        own_extra = ('<circle cx="7.5" cy="7.5" r="6.4" fill="none" stroke="#fff" '
                     'stroke-width="1.1" stroke-dasharray="2.6 2" opacity="0.9"/>')
    return (f'<span class="ic-badge {cls}{own_cls}" data-ic="{key}" title="{title}">'
            f'<svg viewBox="0 0 15 15" width="15" height="15" aria-hidden="true">'
            f'{_NAV_ICON.get(key, "")}{own_extra}</svg></span>')


_EXCEL_ICON = '<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="1.5" y="2" width="13" height="12" rx="1.5" fill="#107C41"/><path d="M5.2 5L8 8 5.2 11M10.8 5L8 8l2.8 3" stroke="#fff" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>'
_WORD_ICON = '<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="1.5" y="2" width="13" height="12" rx="1.5" fill="#185ABD"/><path d="M4 5l1.2 6L6.6 6.5 8 11l1.4-4.5L10.6 11 12 5" stroke="#fff" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>'
# neutral "export/download" glyph — the banner action exports to BOTH Excel and Word,
# so a format-specific (green Excel) icon there was misleading. Uses currentColor so it
# themes correctly (light/dark) and reads as a generic download/share action.
_EXPORT_ICON = ('<svg viewBox="0 0 16 16" width="14" height="14" fill="none" '
                'style="vertical-align:-2px;margin-right:5px" xmlns="http://www.w3.org/2000/svg">'
                '<path d="M8 2v8m0 0L5.2 7.2M8 10l2.8-2.8" stroke="currentColor" stroke-width="1.4" '
                'stroke-linecap="round" stroke-linejoin="round"/>'
                '<path d="M2.8 10.5v1.7A1.3 1.3 0 004.1 13.5h7.8a1.3 1.3 0 001.3-1.3v-1.7" '
                'stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>')
_BUILD_ID = "20260709-1554"


def build_explorer_html(catalog, fname, phase_views=None, phase_names=None, fbd_views=None,
                        fbd_names=None, em_views=None, em_names=None,
                        param_index=None, expr_index=None, export_token=None,
                        recipe_views=None, recipe_step_views=None):
    """phase_names/fbd_names/em_names: lists of objects available for lazy drill-down
    (built on click via /phase_view, /fbd_view, /em_view). The *_views maps are the
    legacy eager form, still accepted as a fallback."""
    recipe_views = recipe_views or {}
    phase_views = phase_views or {}
    phase_names = phase_names or list(phase_views.keys())
    fbd_views = fbd_views or {}
    fbd_names = fbd_names or list(fbd_views.keys())
    em_views = em_views or {}
    em_names = em_names or list(em_views.keys())
    em_views = em_views or {}
    summary = {
        'Areas': len(catalog['areas']),
        'Unit instances': len(catalog['units']),
        'Unit classes': len(catalog['unit_classes']),
        'EM classes': len(catalog['em_classes']),
        'CM classes': len(catalog['cm_classes']),
        'Phase classes': len(catalog['phase_classes']),
        'Recipes': len(catalog['recipes']),
        'Composite classes': len([c for c in catalog['composites'] if c.get('scope') == 'class']),
        'FB types': len(catalog['fb_types']),
    }

    # build a flat object dict for JS: id -> full record
    objs = {}

    def put(oid, otype, rec):
        objs[oid] = dict(rec, _id=oid, _type=otype)

    for a in catalog['areas']:
        put('area:' + a['name'], 'Area', a)
    for u in catalog['units']:
        put('unit:' + u['name'], 'Unit Instance', u)
    for c in catalog['unit_classes']:
        put('uclass:' + c['name'], 'Unit Class',
            dict(c, instances=catalog['instances_by_class'].get(c['name'], [])))
    for c in catalog['em_classes']:
        put('em:' + c['name'], 'EM Class', c)
    for c in catalog['cm_classes']:
        put('cm:' + c['name'], 'CM Class', c)
    for p in catalog['phase_classes']:
        put('phase:' + p['name'], 'Phase Class', p)
    for r in catalog['recipes']:
        put('recipe:' + r['name'], 'Recipe', r)
    for c in catalog['composites']:
        disp = c.get('description') if c.get('anonymous') and c.get('description') else c['name']
        put('composite:' + c['name'], 'Composite', dict(c, _disp=disp))
    for t in catalog['fb_types']:
        put('fbtype:' + t['name'], 'FB Type', t)
    for s in catalog.get('named_sets', []):
        put('nset:' + s['name'], 'Named Set', s)

    data_json = json.dumps({'objs': objs, 'summary': summary,
                            'unit_phases': catalog.get('unit_phases', {}),
                            'unit_ems': catalog.get('unit_ems', {}),
                            'em_cms': catalog.get('em_cms', {}),
                            'used_by': catalog.get('class_used_by', {}),
                            'logic_xref': catalog.get('logic_xref', {}),
                            'io_flat': catalog.get('io_flat', []),
                            'instances': catalog.get('instances', {}),
                            'parent_instances': catalog.get('parent_instances', {}),
                            'unit_instances': catalog.get('unit_instances', {}),
                            'deployed_modules': catalog.get('deployed_modules', {}),
                            'unit_modules': catalog.get('unit_modules', {}),
                            'unit_class_phases': catalog.get('unit_class_phases', {}),
                            'unit_class_detail': catalog.get('unit_class_detail', {}),
                            'named_sets': {s['name']: s for s in catalog.get('named_sets', [])},
                            'em_state_set': catalog.get('em_state_set', {}),
                            'controllers': catalog.get('controllers', {}),
                            'has_devicenet': catalog.get('has_devicenet', False),
                            'module_controller': catalog.get('module_controller', {}),
                            'module_params': catalog.get('module_params', {}),
                            'area_tree': catalog.get('area_tree', {})})
    phase_views_json = json.dumps(phase_views)
    phase_names_json = json.dumps(phase_names)
    s88_svg_json = json.dumps(s88_model.build_s88_svg())
    fbd_views_json = json.dumps(fbd_views)
    fbd_names_json = json.dumps(fbd_names)
    em_names_json = json.dumps(em_names)
    em_views_json = json.dumps(em_views)
    recipe_views_json = json.dumps(recipe_views)
    param_index_json = json.dumps(param_index or {})
    expr_index_json = json.dumps(expr_index or [])

    js = """
const DB = __DATA__;
const PHASE_VIEWS = __PHASE_VIEWS__;
const PHASE_NAMES = __PHASE_NAMES__;
const FBD_VIEWS = __FBD_VIEWS__;
const FBD_NAMES = __FBD_NAMES__;
const EM_NAMES = __EM_NAMES__;
const EM_VIEWS = __EM_VIEWS__;
const RECIPE_VIEWS = __RECIPE_VIEWS__;
const RECIPE_STEP_VIEWS = __RECIPE_STEP_VIEWS__;
let PARAM_INDEX = __PARAM_INDEX__;
let EXPR_INDEX = __EXPR_INDEX__;
var SEARCH_IDX_LOADED = (Object.keys(PARAM_INDEX).length>0 || EXPR_INDEX.length>0);
var SEARCH_IDX_LOADING = false;
function ensureSearchIndex(cb){
  // The params/expressions search index is built lazily on first use so opening a
  // large export stays fast. Names search works immediately (from DB.objs).
  if(SEARCH_IDX_LOADED || SEARCH_IDX_LOADING){ if(cb)cb(); return; }
  if(typeof EXPORT_TOKEN==='undefined' || !EXPORT_TOKEN){ if(cb)cb(); return; }
  SEARCH_IDX_LOADING=true;
  fetch('/search_index?t='+encodeURIComponent(EXPORT_TOKEN))
    .then(function(r){return r.json();})
    .then(function(x){
      PARAM_INDEX = x.params||{}; EXPR_INDEX = x.exprs||[];
      SEARCH_IDX_LOADED=true; SEARCH_IDX_LOADING=false; SIDX=null;  // rebuild names+params
      if(cb)cb();
    })
    .catch(function(){ SEARCH_IDX_LOADING=false; if(cb)cb(); });
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
// escape a value for embedding inside a single-quoted JS string in an inline handler
function jsq(s){return (s||'').replace(/\\\\/g,'\\\\\\\\').replace(/'/g,"\\\\'");}
function badge(t){const m={'Area':'b-area','Unit Instance':'b-unit','EM Class':'b-em','CM Class':'b-cm','Phase Class':'b-phase','Recipe':'b-recipe','Composite':'b-composite','Unit Class':'b-uclass','FB Type':'b-fbtype','Named Set':'b-nset'};return m[t]||'b-composite';}
function badgeColor(t){const m={'b-area':'#0ea5e9','b-unit':'#6366f1','b-em':'#0f766e','b-cm':'#7c3aed','b-phase':'#b45309','b-recipe':'#be123c','b-composite':'#475569','b-uclass':'#2563eb','b-fbtype':'#334155'};if(t==='Parameter')return '#0891b2';if(t==='Instance')return '#6d28d9';if(t==='EM instance')return '#0f766e';if(t==='CM instance')return '#6d28d9';return m[badge(t)]||'#475569';}

// ── global search: Names | Expressions | Values ──
var SIDX=null, SRES=[], SSEL=-1, SMODE='names';
function searchIndex(){
  if(SIDX)return SIDX;
  SIDX=[];
  for(var id in DB.objs){var o=DB.objs[id];SIDX.push({id:id,name:o.name||'',type:o._type||'',desc:o.description||''});}
  for(var pn in PARAM_INDEX){SIDX.push({id:'param:'+pn,name:pn,type:'Parameter',desc:''});}
  for(var iid in (DB.instances||{})){var ins=DB.instances[iid];SIDX.push({id:'inst:'+iid,name:ins.tag,type:'Instance',desc:ins.cls});}
  // deployed module tags (e.g. FP005-HV-001) — the actual objects opened via
  // showDeployed(); previously unsearchable. id uses the dep: scheme handled by show().
  for(var dt in (DB.deployed_modules||{})){
    var dm=DB.deployed_modules[dt];
    var dtype=(DB.objs['em:'+(dm.cls||'')])?'EM instance':'CM instance';
    SIDX.push({id:'dep:'+dt,name:dt,type:dtype,desc:(dm.cls||'')});
  }
  SIDX.sort(function(a,b){return a.name.localeCompare(b.name);});
  return SIDX;
}
function escRe(s){return s.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');}
function hiQ(t,q){if(!q)return esc(t);try{return esc(t).replace(new RegExp('('+escRe(q)+')','ig'),'<mark>$1</mark>');}catch(e){return esc(t);}}
function navMode(btn,m){
  SMODE=m;
  document.querySelectorAll('.navmode .nm-btn').forEach(b=>b.classList.toggle('active',b===btn));
  var q=document.getElementById('navq');
  q.placeholder=(m==='expr'?'Search expression logic…':m==='values'?'Search configured values…':'Search names, logic, values…');
  navSearch(q.value); q.focus();
}
function navSearch(q){
  var box=document.getElementById('navres');
  q=(q||'').trim();
  if(!q){box.style.display='none';box.innerHTML='';SRES=[];SSEL=-1;return;}
  // expr/values search needs the lazily-built index; fetch then re-run once.
  if((SMODE==='expr'||SMODE==='values') && !SEARCH_IDX_LOADED){
    box.style.display='block';
    box.innerHTML='<div class="navres-empty">Building search index…</div>';
    ensureSearchIndex(function(){ navSearch(q); });
    return;
  }
  var ql=q.toLowerCase(), out=[], h='';
  if(SMODE==='expr'){
    for(var i=0;i<EXPR_INDEX.length && out.length<60;i++){
      var pos=(EXPR_INDEX[i].e||'').toLowerCase().indexOf(ql);
      if(pos>=0) out.push({i:i,pos:pos});
    }
    SRES=out;SSEL=out.length?0:-1;
    if(!out.length){box.innerHTML='<div class="navres-empty">No expression contains "'+esc(q)+'"</div>';box.style.display='block';return;}
    out.forEach(function(r,k){
      var e=EXPR_INDEX[r.i], st=Math.max(0,r.pos-22);
      var snip=(st>0?'…':'')+e.e.slice(st,r.pos+q.length+44).replace(/\\s+/g,' ');
      h+='<div class="navres-item col'+(k===0?' act':'')+'" data-i="'+r.i+'" onmousedown="openExpr(this.dataset.i)">'+
         '<span class="rsub"><span class="rtype" style="background:#7c3aed">'+esc(e.m)+'</span> '+esc(e.blk)+' · '+esc(e.attr)+'</span>'+
         '<span class="rsnip">'+hiQ(snip,q)+'</span></div>';
    });
  } else if(SMODE==='values'){
    for(var pn in PARAM_INDEX){
      var vals=PARAM_INDEX[pn].vals||[];
      for(var j=0;j<vals.length;j++){
        if(String(vals[j].cv).toLowerCase().indexOf(ql)>=0){ out.push({name:pn,cv:vals[j].cv,m:vals[j].m}); break; }
      }
      if(out.length>=60)break;
    }
    SRES=out;SSEL=out.length?0:-1;
    if(!out.length){box.innerHTML='<div class="navres-empty">No configured value matches "'+esc(q)+'"</div>';box.style.display='block';return;}
    out.forEach(function(r,k){
      h+='<div class="navres-item'+(k===0?' act':'')+'" data-id="param:'+esc(r.name)+'" onmousedown="navPick(this.dataset.id)">'+
         '<span class="rtype" style="background:#0891b2">Value</span>'+
         '<span class="rname">'+esc(r.name)+' = '+hiQ(String(r.cv),q)+'</span>'+
         '<span class="rsub" style="margin-left:6px">'+esc(r.m)+'</span></div>';
    });
  } else {
    var idx=searchIndex();
    for(var i=0;i<idx.length && out.length<40;i++){
      var e=idx[i];
      if(e.name.toLowerCase().indexOf(ql)>=0 || e.type.toLowerCase().indexOf(ql)>=0) out.push(e);
    }
    SRES=out;SSEL=out.length?0:-1;
    if(!out.length){box.innerHTML='<div class="navres-empty">No matches for "'+esc(q)+'"</div>';box.style.display='block';return;}
    out.forEach(function(e,k){
      h+='<div class="navres-item'+(k===0?' act':'')+'" data-id="'+esc(e.id)+'" onmousedown="navPick(this.dataset.id)">'+
         '<span class="rtype" style="background:'+badgeColor(e.type)+'">'+esc(e.type)+'</span>'+
         '<span class="rname">'+hiQ(e.name,q)+'</span></div>';
    });
  }
  box.innerHTML=h;box.style.display='block';
}
// ── #1: top-banner command palette — fast name-jump across every object type ──
var CMDP_RES=[], CMDP_SEL=-1;
function cmdpClose(){ var p=document.getElementById('cmdpPop'); if(p)p.style.display='none'; CMDP_RES=[]; CMDP_SEL=-1; }
function cmdpSubtitle(e){
  // a short context line: description if present, else type-specific hint
  if(e.type==='Instance') return 'instance'+(e.desc?' of '+e.desc:'');
  if(e.desc) return e.desc;
  return e.type||'';
}
function _cmdpRefCount(name){
  var n=0;
  if(DB.logic_xref&&DB.logic_xref[name]) DB.logic_xref[name].forEach(function(r){ n+=(r.count||1); });
  if(DB.used_by&&DB.used_by[name]) n+=DB.used_by[name].length;
  return n;
}
function cmdpSearch(q){
  var pop=document.getElementById('cmdpPop'); if(!pop) return;
  q=(q||'').trim();
  if(!q){ cmdpClose(); return; }
  var ql=q.toLowerCase(), idx=searchIndex(), out=[];
  // rank: name-prefix first, then name-substring, then type match
  var pre=[], sub=[], typ=[];
  for(var i=0;i<idx.length;i++){
    var e=idx[i], nl=e.name.toLowerCase();
    var p=nl.indexOf(ql);
    if(p===0) pre.push(e);
    else if(p>0) sub.push(e);
    else if((e.type||'').toLowerCase().indexOf(ql)>=0) typ.push(e);
    if(pre.length>=40) break;
  }
  var objs=pre.concat(sub).concat(typ).slice(0,30);
  // #8: turn object hits into rows; annotate each with its reference count so the user
  // can jump straight into "what references this". Also add explicit action rows:
  //  - "Find references to <exact match>"  (opens the floating references window)
  //  - "Search logic/expressions for <q>"  (deep expression search in the rail)
  out=objs.map(function(e){ return {kind:'obj', e:e, refs:_cmdpRefCount(e.name)}; });
  // exact (case-insensitive) name match → offer a dedicated references action at the top
  var exact=objs.filter(function(e){ return e.name.toLowerCase()===ql; })[0]
          || (objs[0] && objs[0].name.toLowerCase().indexOf(ql)===0 ? objs[0] : null);
  var actions=[];
  if(exact && _cmdpRefCount(exact.name)>0){
    actions.push({kind:'refs', name:exact.name, refs:_cmdpRefCount(exact.name)});
  }
  actions.push({kind:'expr', q:q});
  out=actions.concat(out).slice(0,40);
  CMDP_RES=out; CMDP_SEL=out.length?0:-1;
  if(!out.length){ pop.innerHTML='<div class="cmdp-empty">No object matches \\u201c'+esc(q)+'\\u201d</div>'; pop.style.display='block'; return; }
  var nobj=out.filter(function(r){return r.kind==='obj';}).length;
  var h='<div class="cmdp-hint">'+nobj+(nobj>=30?'+':'')+' object'+(nobj===1?'':'s')+' \\u2014 \\u2191\\u2193 move, \\u21b5 open, esc close</div>';
  out.forEach(function(r,k){
    var act=(k===CMDP_SEL?' act':'');
    if(r.kind==='refs'){
      h+='<div class="cmdp-item cmdp-action'+act+'" data-i="'+k+'" onmousedown="cmdpPick('+k+')">'
        +'<span class="cmdp-badge" style="background:#0891b2">REFS</span>'
        +'<span class="cmdp-nm"><span class="cn">Find references to '+esc(r.name)+'</span>'
        +'<span class="cs">'+r.refs+' reference'+(r.refs===1?'':'s')+' across logic & members</span></span>'
        +'<span class="cmdp-enter">\\u21b5</span></div>';
    } else if(r.kind==='expr'){
      h+='<div class="cmdp-item cmdp-action'+act+'" data-i="'+k+'" onmousedown="cmdpPick('+k+')">'
        +'<span class="cmdp-badge" style="background:#7c3aed">LOGIC</span>'
        +'<span class="cmdp-nm"><span class="cn">Search logic & values for \\u201c'+esc(r.q)+'\\u201d</span>'
        +'<span class="cs">deep search across expressions and configured values</span></span>'
        +'<span class="cmdp-enter">\\u21b5</span></div>';
    } else {
      var e=r.e, col=badgeColor(e.type);
      var bl=(e.type||'').toUpperCase();
      if(bl==='EM INSTANCE')bl='EM'; else if(bl==='CM INSTANCE')bl='CM'; else if(bl==='UNIT INSTANCE')bl='UNIT';
      else if(bl==='PARAMETER')bl='PARAM'; else if(bl==='EM CLASS')bl='EM'; else if(bl==='CM CLASS')bl='CM';
      else if(bl==='PHASE CLASS')bl='PHASE'; else if(bl==='NAMED SET')bl='SET';
      var refBtn=r.refs>0 ? '<span class="cmdp-refbtn" title="'+r.refs+' reference(s) \\u2014 open references window" onmousedown="event.stopPropagation();event.preventDefault();cmdpOpenRefs(\\''+esc(e.name).replace(/'/g,"\\\\'")+'\\')">\\u2922 '+r.refs+'</span>' : '';
      h+='<div class="cmdp-item'+act+'" data-i="'+k+'" onmousedown="cmdpPick('+k+')">'
        +'<span class="cmdp-badge" style="background:'+col+'">'+esc(bl)+'</span>'
        +'<span class="cmdp-nm"><span class="cn">'+hiQ(e.name,q)+'</span>'
        +'<span class="cs">'+esc(cmdpSubtitle(e))+'</span></span>'
        +refBtn
        +'<span class="cmdp-enter">\\u21b5</span></div>';
    }
  });
  pop.innerHTML=h; pop.style.display='block';
}
function cmdpOpenRefs(name){
  var inp=document.getElementById('cmdpInput'); if(inp){ inp.blur(); }
  cmdpClose();
  showReferencesFloat(name);
}
function cmdpPick(k){
  var r=CMDP_RES[k]; if(!r) return;
  var inp=document.getElementById('cmdpInput'); if(inp){ inp.value=''; inp.blur(); }
  cmdpClose();
  if(r.kind==='refs'){ showReferencesFloat(r.name); return; }
  if(r.kind==='expr'){ cmdpDeepSearch(r.q); return; }
  show(r.e.id);
}
function cmdpDeepSearch(q){
  // route into the rail's expression/value search
  switchView('explorer');
  var exprBtn=document.querySelector('.navmode .nm-btn:nth-child(2)');
  if(exprBtn && typeof navMode==='function'){ try{ navMode(exprBtn,'expr'); }catch(_e){} }
  var nq=document.getElementById('navq');
  if(nq){ nq.value=q; nq.focus(); try{ navSearch(nq.value); }catch(_e){} }
}
function cmdpKey(ev){
  if(ev.key==='Escape'){ cmdpClose(); ev.target.value=''; ev.target.blur(); return; }
  if(!CMDP_RES.length) return;
  if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){
    ev.preventDefault();
    CMDP_SEL+=(ev.key==='ArrowDown'?1:-1);
    if(CMDP_SEL<0)CMDP_SEL=CMDP_RES.length-1; if(CMDP_SEL>=CMDP_RES.length)CMDP_SEL=0;
    var items=document.querySelectorAll('#cmdpPop .cmdp-item');
    items.forEach(function(it,i){ it.classList.toggle('act',i===CMDP_SEL); });
    if(items[CMDP_SEL]) items[CMDP_SEL].scrollIntoView({block:'nearest'});
  } else if(ev.key==='Enter' && CMDP_SEL>=0){
    ev.preventDefault(); cmdpPick(CMDP_SEL);
  }
}
function openExpr(i){
  var e=EXPR_INDEX[i]; if(!e)return;
  document.getElementById('navres').style.display='none';
  fbdEnsureModal();
  document.getElementById('fbdExprTitle').textContent=e.blk+' · '+e.attr;
  document.getElementById('fbdExprSub').textContent=e.m+(e.kind?' ('+e.kind+')':'');
  document.getElementById('fbdExprBody').innerHTML='<pre>'+fbdHL(e.e)+'</pre>';
  document.getElementById('fbdExprModal').style.display='flex';
}
function navPick(id){
  document.getElementById('navres').style.display='none';
  document.getElementById('navq').value='';
  SRES=[];SSEL=-1;
  show(id);
}
function navSearchKey(ev){
  var box=document.getElementById('navres');
  if(ev.key==='Escape'){box.style.display='none';ev.target.value='';SRES=[];return;}
  if(!SRES.length)return;
  if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){
    ev.preventDefault();
    SSEL+=(ev.key==='ArrowDown'?1:-1);
    if(SSEL<0)SSEL=SRES.length-1; if(SSEL>=SRES.length)SSEL=0;
    var items=box.querySelectorAll('.navres-item');
    items.forEach(function(it,i){it.classList.toggle('act',i===SSEL);});
    if(items[SSEL])items[SSEL].scrollIntoView({block:'nearest'});
  } else if(ev.key==='Enter' && SSEL>=0){
    ev.preventDefault();
    var r=SRES[SSEL];
    if(SMODE==='expr') openExpr(r.i);
    else if(SMODE==='values') navPick('param:'+r.name);
    else navPick(r.id);
  }
}
// ── resizable left nav pane (drag the divider) — fully delegated so it works
// regardless of when the divider element is added to the DOM ──
(function(){
  function panesEl(){ return document.querySelector('.panes'); }
  function setW(px){ var p=panesEl(); if(!p) return; px=Math.max(180,Math.min(720,px)); p.style.setProperty('--navw', px+'px'); }
  var dragging=false;
  document.addEventListener('mousedown',function(e){
    var div=e.target.closest && e.target.closest('#paneDivider, .pane-divider');
    if(!div) return;
    dragging=true; div.classList.add('dragging');
    document.body.style.userSelect='none'; document.body.style.cursor='col-resize'; e.preventDefault();
  });
  document.addEventListener('mousemove',function(e){
    if(!dragging) return;
    var p=panesEl(); if(!p) return;
    setW(e.clientX - p.getBoundingClientRect().left);
  });
  document.addEventListener('mouseup',function(){
    if(!dragging) return; dragging=false;
    document.querySelectorAll('.pane-divider.dragging').forEach(function(d){d.classList.remove('dragging');});
    document.body.style.userSelect=''; document.body.style.cursor='';
  });
  document.addEventListener('dblclick',function(e){
    if(e.target.closest && e.target.closest('#paneDivider, .pane-divider')){ var p=panesEl(); if(p) p.style.setProperty('--navw','316px'); }
  });
})();
document.addEventListener('keydown',function(e){
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();var cq=document.getElementById('cmdpInput');if(cq){cq.focus();cq.select();}else{var q=document.getElementById('navq');if(q){q.focus();q.select();}}}
});
document.addEventListener('click',function(e){
  var s=document.querySelector('.navsearch');
  if(s&&!s.contains(e.target)){var b=document.getElementById('navres');if(b)b.style.display='none';}
});

function paramsCard(name){
  var ps=(DB.module_params&&DB.module_params[name])||[];
  if(!ps.length) return '';
  var order=['Operating','Configuration','Configure','Tuning','Calculated','Batch','Alarm'];
  var groups={};
  ps.forEach(function(p){(groups[p.group||'Other']=groups[p.group||'Other']||[]).push(p);});
  var keys=Object.keys(groups).sort(function(a,b){var ia=order.indexOf(a),ib=order.indexOf(b);return (ia<0?99:ia)-(ib<0?99:ib);});
  var h='<div class="card" style="max-width:none"><h3>Parameters ('+ps.length+')</h3>';
  keys.forEach(function(g){
    var rows=groups[g];
    h+='<div class="pgrp"><div class="pgrp-h">'+esc(g)+'<span class="navcount">'+rows.length+'</span></div>';
    h+='<table class="fbd-table"><thead><tr><th>Name</th><th>Type</th><th>Description</th></tr></thead><tbody>';
    rows.forEach(function(p){
      h+='<tr><td><code>'+esc(p.name)+'</code></td><td class="ptype">'+esc(p.type)+'</td><td class="pdesc">'+esc(p.description||'')+'</td></tr>';
    });
    h+='</tbody></table></div>';
  });
  return h+'</div>';
}
// ── app settings (in-memory; applied live) ──
var APP_SETTINGS={ cardsDefault:'expanded', sfcWheel:'zoom', density:'comfortable', transExpr:'inline', loader:'dots' };
// emits a loader that renders whichever style is active (data-loader on <body>).
// All variants are present; CSS shows only the selected one.
function dvLoader(label){
  return '<span class="dvload"><span class="lv lv-dots"><i></i><i></i><i></i></span>'
    +'<span class="lv lv-ring"></span>'
    +'<span class="lv lv-bars"><i></i><i></i><i></i><i></i></span>'
    +'<span class="lv lv-pulse"></span>'
    +'<span class="lv lv-orbit"></span>'
    +'<span class="lv lv-rainbow"></span>'
    +'<span class="lv lv-dotwave"><i></i><i></i><i></i><i></i></span>'
    +'<span class="lv lv-comet"></span>'
    +(label?('<span>'+label+'</span>'):'')+'</span>';
}
function applySettings(){
  document.body.setAttribute('data-density', APP_SETTINGS.density);
  document.body.setAttribute('data-sfcwheel', APP_SETTINGS.sfcWheel);
  document.body.setAttribute('data-loader', APP_SETTINGS.loader||'dots');
  // default-collapse all current cards if requested
  if(APP_SETTINGS.cardsDefault==='collapsed'){
    document.querySelectorAll('#detail .card').forEach(function(c){ c.classList.add('collapsed'); });
  }
}
function openSettings(){
  var ov=document.getElementById('settingsOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='settingsOverlay'; ov.className='ip-pop-overlay'; document.body.appendChild(ov); }
  ov.onclick=function(e){ if(e.target===ov) ov.remove(); };
  function row(label,hint,id,opts,cur){
    var o=opts.map(function(x){return '<option value="'+x[0]+'"'+(x[0]===cur?' selected':'')+'>'+x[1]+'</option>';}).join('');
    return '<div class="set-row"><div><div class="set-lbl">'+label+'</div><div class="set-hint">'+hint+'</div></div>'
      +'<select id="'+id+'">'+o+'</select></div>';
  }
  ov.innerHTML='<div class="ip-pop" style="max-width:560px"><div class="ip-pop-h"><b>&#9881; Settings</b>'
    +'<span class="ip-pop-x" onclick="var o=document.getElementById(\\'settingsOverlay\\');if(o)o.remove();">\\u00d7</span></div>'
    +'<div style="padding:8px 18px 18px">'
    +row('Cards default state','How cards appear when you open an object','set-cards',[['expanded','Expanded'],['collapsed','Collapsed']],APP_SETTINGS.cardsDefault)
    +row('SFC mouse wheel','What the wheel does over an SFC diagram','set-sfcwheel',[['zoom','Zoom the diagram'],['pan','Scroll the diagram'],['page','Scroll the page']],APP_SETTINGS.sfcWheel)
    +row('Transitions in tables','Show transitions after each step, or grouped','set-transexpr',[['inline','After each step'],['grouped','Grouped at bottom']],APP_SETTINGS.transExpr)
    +row('Density','Spacing of lists and tables','set-density',[['comfortable','Comfortable'],['compact','Compact']],APP_SETTINGS.density)
    +'<div class="set-row"><div><div class="set-lbl">Icon theme</div><div class="set-hint">Style of the icons in the navigation tree</div></div>'
    +'<select id="set-icontheme" onchange="skinTree(this.value)">'
    + _ICON_THEME_OPTS
    +'</select></div>'
    +'<div class="set-row"><div><div class="set-lbl">Loading animation</div><div class="set-hint">Shown while diagrams and data load</div></div>'
    +'<div style="display:flex;align-items:center;gap:12px">'
    +'<span id="loaderPreview" style="min-width:70px">'+dvLoader('')+'</span>'
    +'<select id="set-loader" onchange="document.body.setAttribute(\\'data-loader\\',this.value)">'
    +['dots','ring','bars','pulse','orbit','rainbow','dotwave','comet'].map(function(x){return '<option value="'+x+'"'+(x===APP_SETTINGS.loader?' selected':'')+'>'+x.charAt(0).toUpperCase()+x.slice(1)+(['rainbow','dotwave','comet'].indexOf(x)>=0?' \\u2728':'')+'</option>';}).join('')
    +'</select></div></div>'
    +'<div style="display:flex;gap:8px;margin-top:16px">'
    +'<button class="exp-btn" style="background:var(--accent);color:#fff;border:none" onclick="saveSettings()">Apply</button>'
    +'<button class="exp-btn" onclick="var o=document.getElementById(\\'settingsOverlay\\');if(o)o.remove();">Cancel</button>'
    +'</div>'
    +'<div class="set-note">Settings apply to this session. (Persistent storage isn\\'t available in this environment.)</div>'
    +'</div></div>';
}
function saveSettings(){
  APP_SETTINGS.cardsDefault=(document.getElementById('set-cards')||{}).value||'expanded';
  APP_SETTINGS.sfcWheel=(document.getElementById('set-sfcwheel')||{}).value||'zoom';
  APP_SETTINGS.transExpr=(document.getElementById('set-transexpr')||{}).value||'inline';
  APP_SETTINGS.density=(document.getElementById('set-density')||{}).value||'comfortable';
  APP_SETTINGS.loader=(document.getElementById('set-loader')||{}).value||'dots';
  applySettings();
  var o=document.getElementById('settingsOverlay'); if(o) o.remove();
}
// #7: multi-object export picker — pick any set of objects and export them together
// to one Excel or Word file, instead of the old whole-database dump.
function openExportPicker(){
  if(typeof EXPORT_TOKEN==='undefined' || !EXPORT_TOKEN) return;
  var ov=document.getElementById('expPickOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='expPickOverlay'; ov.className='ip-pop-overlay'; document.body.appendChild(ov); }
  ov.onclick=function(e){ if(e.target===ov) ov.remove(); };
  // group selectable objects by type
  var groups={}, labels={phase:'Phases',em:'Equipment Modules',cm:'Control Module Classes',
    recipe:'Recipes',uclass:'Unit Classes',fbtype:'Function Block Types'};
  for(var id in DB.objs){
    var t=id.slice(0,id.indexOf(':')); var o=DB.objs[id];
    if(!labels[t]) continue;
    (groups[t]=groups[t]||[]).push({id:id,name:o.name||id});
  }
  var body='';
  Object.keys(labels).forEach(function(t){
    var list=(groups[t]||[]).sort(function(a,b){return a.name<b.name?-1:1;});
    if(!list.length) return;
    body+='<div class="exp-group"><div class="exp-group-h">'
      +'<label class="exp-ck"><input type="checkbox" onchange="expToggleGroup(this,\\''+t+'\\')"> '
      +esc(labels[t])+' <span class="exp-cnt">'+list.length+'</span></label></div>'
      +'<div class="exp-items" data-group="'+t+'">';
    list.forEach(function(it){
      body+='<label class="exp-ck exp-item"><input type="checkbox" class="exp-obj" value="'+esc(it.id)+'" onchange="expUpdateCount()"> '+esc(it.name)+'</label>';
    });
    body+='</div></div>';
  });
  if(!body) body='<div class="set-note">No exportable objects in this import.</div>';
  ov.innerHTML='<div class="ip-pop" style="max-width:640px;max-height:86vh;display:flex;flex-direction:column">'
    +'<div class="ip-pop-h"><b>'+_EXCEL_ICON_RAW+' Export objects</b>'
    +'<span class="ip-pop-x" onclick="var o=document.getElementById(\\'expPickOverlay\\');if(o)o.remove();">\\u00d7</span></div>'
    +'<div class="exp-search-wrap"><input class="alias-filter" id="expSearch" placeholder="Filter objects\\u2026" oninput="expFilter(this)"></div>'
    +'<div class="exp-pick-body">'+body+'</div>'
    +'<div class="exp-foot">'
    +'<span class="exp-selcount" id="expSelCount">0 selected</span>'
    +'<div style="flex:1"></div>'
    +'<button class="exp-btn" onclick="expClear()">Clear</button>'
    +'<button class="exp-btn" id="expWordBtn" style="opacity:.5;pointer-events:none" onclick="expDoExport(\\'word\\')">'+_WORD_ICON_RAW+' Word</button>'
    +'<button class="exp-btn" id="expExcelBtn" style="opacity:.5;pointer-events:none;background:var(--accent);color:#fff;border:none" onclick="expDoExport(\\'excel\\')">'+_EXCEL_ICON_RAW+' Excel</button>'
    +'</div></div>';
}
function expToggleGroup(ck,t){
  document.querySelectorAll('.exp-items[data-group="'+t+'"] .exp-obj').forEach(function(c){
    if(c.closest('.exp-item').style.display!=='none') c.checked=ck.checked;
  });
  expUpdateCount();
}
function expFilter(inp){
  var q=(inp.value||'').toLowerCase();
  document.querySelectorAll('#expPickOverlay .exp-item').forEach(function(it){
    it.style.display=(!q || it.textContent.toLowerCase().indexOf(q)>=0)?'':'none';
  });
}
function expUpdateCount(){
  var n=document.querySelectorAll('#expPickOverlay .exp-obj:checked').length;
  document.getElementById('expSelCount').textContent=n+' selected';
  ['expExcelBtn','expWordBtn'].forEach(function(id){
    var b=document.getElementById(id); if(!b) return;
    b.style.opacity=n?'1':'.5'; b.style.pointerEvents=n?'auto':'none';
  });
}
function expClear(){
  document.querySelectorAll('#expPickOverlay input[type=checkbox]').forEach(function(c){c.checked=false;});
  expUpdateCount();
}
function expDoExport(fmt){
  var objs=Array.from(document.querySelectorAll('#expPickOverlay .exp-obj:checked')).map(function(c){return c.value;});
  if(!objs.length) return;
  var url='/export_multi?token='+encodeURIComponent(EXPORT_TOKEN)+'&fmt='+fmt+'&name=selected_export&objs='+encodeURIComponent(objs.join(','));
  window.location.href=url;
  var o=document.getElementById('expPickOverlay'); if(o) o.remove();
}
// #4/#6: append another FHX (recipe, another unit, etc.) onto the current import,
// redesigned as a polished drag-and-drop card.
function openAppend(){
  var tok=(typeof EXPORT_TOKEN!=='undefined')?EXPORT_TOKEN:'';
  if(!tok){ alert('Append needs the current import token, which is unavailable. Re-import the base file and try again.'); return; }
  var ov=document.getElementById('appendOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='appendOverlay'; ov.className='ip-pop-overlay'; document.body.appendChild(ov); }
  ov.onclick=function(e){ if(e.target===ov) ov.remove(); };
  ov.innerHTML='<div class="ip-pop ap-pop"><div class="ip-pop-h"><b>'
    +'<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" style="vertical-align:-3px;margin-right:5px"><path d="M12 5v14M5 12h14"/></svg>'
    +'Append another FHX</b>'
    +'<span class="ip-pop-x" onclick="var o=document.getElementById(\\'appendOverlay\\');if(o)o.remove();">\\u00d7</span></div>'
    +'<div class="ap-body">'
    +'<p class="ap-lead">Merge a second export \\u2014 a recipe, another unit, anything \\u2014 into this session. Your current import is kept; the new objects are added on top.</p>'
    +'<label class="ap-drop" id="apDrop">'
    +'<input type="file" id="appendFile" accept=".fhx" onchange="apPicked(this)">'
    +'<svg class="ap-drop-ico" viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>'
    +'<div class="ap-drop-t"><b>Choose an FHX file</b> or drop it here</div>'
    +'<div class="ap-drop-file" id="apDropFile"></div>'
    +'</label>'
    +'<div class="ap-modes">'
    +'<div class="ap-modes-lbl">If an object already exists</div>'
    +'<label class="ap-mode"><input type="radio" name="appendMode" value="skip" checked><span><b>Skip</b><small>keep the original</small></span></label>'
    +'<label class="ap-mode"><input type="radio" name="appendMode" value="overwrite"><span><b>Overwrite</b><small>the new one wins</small></span></label>'
    +'</div>'
    +'<div id="appendBaseWrap" class="ap-recover" style="display:none">'
    +'<div class="ap-recover-t">The original import isn\\'t on the server anymore (the free host may have restarted). Re-select the <b>base</b> FHX so the merge can proceed \\u2014 nothing is lost.</div>'
    +'<input type="file" id="appendBaseFile" accept=".fhx"></div>'
    +'<div id="appendStatus" class="ap-status"></div>'
    +'<div class="ap-foot">'
    +'<button class="exp-btn" onclick="var o=document.getElementById(\\'appendOverlay\\');if(o)o.remove();">Cancel</button>'
    +'<button class="exp-btn ap-go" onclick="doAppend()">Merge &amp; reload</button>'
    +'</div>'
    +'</div></div>';
  var drop=document.getElementById('apDrop');
  ['dragenter','dragover'].forEach(function(ev){ drop.addEventListener(ev,function(e){e.preventDefault();drop.classList.add('drag');}); });
  ['dragleave','drop'].forEach(function(ev){ drop.addEventListener(ev,function(e){e.preventDefault();drop.classList.remove('drag');}); });
  drop.addEventListener('drop',function(e){ var f=e.dataTransfer.files; if(f&&f.length){ document.getElementById('appendFile').files=f; apPicked(document.getElementById('appendFile')); } });
}
function apPicked(inp){
  var el=document.getElementById('apDropFile');
  if(inp.files&&inp.files.length){ el.innerHTML='<span class="ap-chip">\\u2713 '+esc(inp.files[0].name)+'</span>'; }
  else el.textContent='';
}
function doAppend(){
  var fi=document.getElementById('appendFile');
  var st=document.getElementById('appendStatus');
  if(!fi.files || !fi.files.length){ st.textContent='Please choose an FHX file to append first.'; return; }
  var mode=(document.querySelector('input[name=appendMode]:checked')||{}).value||'skip';
  var fd=new FormData();
  fd.append('token', (typeof EXPORT_TOKEN!=='undefined'?EXPORT_TOKEN:''));
  fd.append('mode', mode);
  fd.append('file', fi.files[0]);
  var baseFi=document.getElementById('appendBaseFile');
  if(baseFi && baseFi.files && baseFi.files.length){ fd.append('base', baseFi.files[0]); }
  st.textContent='Merging\\u2026';
  fetch('/append',{method:'POST',body:fd})
    .then(function(r){ return r.text().then(function(t){ return {ok:r.ok,status:r.status,t:t}; }); })
    .then(function(res){
      if(!res.ok){
        // stash expired -> reveal the base-file picker so the user can recover
        if(res.status===409 || res.t.indexOf('reimport')>=0 || res.t.indexOf('not found')>=0){
          var w=document.getElementById('appendBaseWrap'); if(w) w.style.display='block';
          st.textContent='Select the base FHX above, then click Merge again.';
        } else {
          st.textContent='Merge failed: '+res.t.slice(0,200);
        }
        return;
      }
      // success: server returns {token,name}. Navigate to a normal GET render so the
      // merged explorer loads exactly like a fresh page (no document.write quirks).
      var j={}; try{ j=JSON.parse(res.t); }catch(e){}
      if(j && j.token){
        window.location.href='/explore_stashed?t='+encodeURIComponent(j.token)+'&name='+encodeURIComponent(j.name||'merged');
      } else {
        // fallback for older server: write the returned HTML
        document.open(); document.write(res.t); document.close();
      }
    })
    .catch(function(e){ st.textContent='Merge error: '+e.message; });
}
function switchView(v){
  var conv=document.getElementById('view-converter'), recs=document.getElementById('view-recipes'), stu=document.getElementById('view-studio');
  var re=document.getElementById('rb-explorer'), rc=document.getElementById('rb-converter'), rr=document.getElementById('rb-recipes'), rs=document.getElementById('rb-studio');
  conv.classList.remove('on'); if(recs) recs.classList.remove('on'); if(stu) stu.classList.remove('on');
  re.classList.remove('active'); rc.classList.remove('active'); if(rr) rr.classList.remove('active'); if(rs) rs.classList.remove('active');
  if(v==='converter'){
    var fr=document.getElementById('convFrame');
    if(!fr.getAttribute('src')) fr.setAttribute('src','/tool/?embed=1');
    conv.classList.add('on'); rc.classList.add('active');
  } else if(v==='recipes'){
    if(recs) recs.classList.add('on'); if(rr) rr.classList.add('active');
  } else if(v==='studio'){
    if(stu) stu.classList.add('on'); if(rs) rs.classList.add('active');
    stuBuildList();
  } else {
    re.classList.add('active');
  }
}
// ── Studio: single-object deep view ──────────────────────────────────────────
// ── Studio: multi-object deep view (phases, EMs, CMs) ──
var STU={open:null, dock:'right'};  // dock: right | bottom | float
function stuBuildList(){
  var box=document.getElementById('stuList'); if(!box || box._built) return;
  box.innerHTML='<div class="stu-empty">'+dvLoader('Loading objects\u2026')+'</div>';
  fetch('/studio_list?t='+encodeURIComponent(EXPORT_TOKEN))
    .then(function(r){return r.json();})
    .then(function(d){
      var groups=d.groups||[];
      if(!groups.length){ box.innerHTML='<div class="stu-empty">No objects in this import.</div>'; return; }
      var icons={Phases:'ic-phase','Equipment Module classes':'ic-em','Control Module classes':'ic-cm'};
      var h='';
      // #5: render the SAME themed icon the Explorer tree uses, and differentiate a
      // class (em/cm/phase glyph) from an instance (the 'inst' glyph) — while tinting
      // an instance by whether its class is an EM or CM.
      function _activeIconTheme(){
        try{ var t=localStorage.getItem('dvexp_icontheme'); if(t&&ICON_THEMES[t]) return t; }catch(e){}
        return 'outline';
      }
      function _studioIconSvg(iconKey, colorKey){
        var thm=_activeIconTheme();
        var set=ICON_THEMES[thm]||ICON_THEMES.outline;
        var cols=THEME_COLORS[thm]||{};
        var glyph=set[iconKey]!==undefined?set[iconKey]:'';
        var col=cols[colorKey]||'';
        return '<span class="ic-badge" data-ic="'+iconKey+'" style="'+(col?('color:'+col):'')+'">'
          +'<svg viewBox="0 0 15 15" width="15" height="15" aria-hidden="true">'+glyph+'</svg></span>';
      }
      groups.forEach(function(g){
        var gi=icons[g.group]|| (g.is_instances?'ic-inst':'');
        h+='<div class="stu-grp"><div class="stu-grp-h">'+esc(g.group)+' <span class="stu-grp-n">'+g.items.length+'</span></div>';
        g.items.forEach(function(it){
          var iconHtml;
          if(g.is_instances){
            // instance: use the 'inst' glyph, tinted by its EM/CM class kind
            iconHtml=_studioIconSvg('inst', it.kind==='em'?'em':(it.kind==='cm'?'cm':'inst'));
          } else if(g.group==='Phases'){
            iconHtml=_studioIconSvg('phase','phase');
          } else if(g.group==='Equipment Module classes'){
            iconHtml=_studioIconSvg('em','em');
          } else if(g.group==='Control Module classes'){
            iconHtml=_studioIconSvg('cm','cm');
          } else {
            iconHtml=_studioIconSvg('inst','inst');
          }
          h+='<div class="stu-litem" data-id="'+esc(it.id)+'" onclick="stuOpen(\\''+esc(it.id).replace(/'/g,"\\\\'")+'\\')">'
            +iconHtml
            +esc(it.name)
            +(it.cls?'<span class="stu-litem-cls">'+esc(it.cls)+'</span>':'')+'</div>';
        });
        h+='</div>';
      });
      box.innerHTML=h; box._built=1;
      if(STU.open){ document.querySelectorAll('#stuList .stu-litem').forEach(function(it){ it.classList.toggle('sel', it.dataset.id===STU.open); }); }
    })
    .catch(function(e){ box.innerHTML='<div class="stu-empty">Could not load: '+esc(e.message)+'</div>'; });
}
function stuFilterList(inp){
  var q=(inp.value||'').toLowerCase();
  document.querySelectorAll('#stuList .stu-litem').forEach(function(it){
    var show=(!q || it.textContent.toLowerCase().indexOf(q)>=0);
    it.style.display=show?'':'none';
  });
  document.querySelectorAll('#stuList .stu-grp').forEach(function(g){
    var any=Array.from(g.querySelectorAll('.stu-litem')).some(function(i){return i.style.display!=='none';});
    g.style.display=any?'':'none';
  });
}
function stuOpen(id){
  STU.open=id;
  document.querySelectorAll('#stuList .stu-litem').forEach(function(it){
    var on=(it.dataset.id===id); it.classList.toggle('sel', on);
    if(on){ try{ it.scrollIntoView({block:'nearest', behavior:'smooth'}); }catch(_e){} }
  });
  var main=document.getElementById('stuMain');
  main.innerHTML='<div class="stu-welcome">'+dvLoader('Opening\u2026')+'</div>';
  fetch('/studio_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(id))
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.error){ main.innerHTML='<div class="stu-welcome"><p class="stu-empty">'+esc(d.error)+'</p></div>'; return; }
      d._id=id; stuRender(d);
    })
    .catch(function(e){ main.innerHTML='<div class="stu-welcome"><p class="stu-empty">Could not open: '+esc(e.message)+'</p></div>'; });
}
function stuRender(d){
  var c=d.counts||{};
  var chips=Object.keys(c).map(function(k){return '<span class="stu-chip">'+c[k]+' '+esc(k.toLowerCase())+'</span>';}).join('');
  // main panel content: phases stream the interactive diagram via iframe; EM/CM embed
  // their rendered HTML directly.
  var mainInner;
  if(d.diagram_url===true){
    var pn=d._id.indexOf(':')>=0?d._id.split(':')[1]:d._id;
    // #6: Studio opens a phase as its CLASS (no unit context here), so the Simulator
    // is hidden — same rule as the Explorer's phase-class view. Simulation only makes
    // sense on a phase reached through a deployed unit instance, where aliases resolve.
    var diagUrl='/phase_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&p='+encodeURIComponent(pn);
    mainInner='<div class="stu-diagload" id="stuDiagLoad">'+dvLoader('Rendering diagram\u2026')+'</div>'
      +'<iframe src="'+diagUrl+'" title="'+esc(d.name)+' diagram" onload="var l=document.getElementById(\\'stuDiagLoad\\'); if(l) l.remove();"></iframe>';
  } else if(d.diagram_url==='em' || d.diagram_url==='cm'){
    var _thm=(document.documentElement.dataset.theme==='dark')?'dark':'light';
    var dUrl='/studio_diagram?t='+encodeURIComponent(EXPORT_TOKEN)+'&kind='+d.diagram_url+'&n='+encodeURIComponent(d.obj||d.name)+'&theme='+_thm;
    mainInner='<div class="stu-diagload" id="stuDiagLoad">'+dvLoader('Rendering diagram\u2026')+'</div>'
      +'<iframe class="stu-diag-frame" src="'+dUrl+'" title="'+esc(d.name)+' diagram" onload="var l=document.getElementById(\\'stuDiagLoad\\'); if(l) l.remove();"></iframe>';
  } else {
    mainInner='<div class="stu-embed-wrap">'+(d.main||'<div class="stu-empty">No diagram.</div>')+'</div>';
  }
  var panels=d.panels||[];
  var tabs=panels.map(function(p,i){return '<div class="stu-tab'+(i===0?' on':'')+'" data-t="'+esc(p.key)+'" onclick="stuTab(this,\\''+esc(p.key)+'\\')">'+esc(p.label)+'</div>';}).join('');
  var tabpanels=panels.map(function(p,i){return '<div class="stu-tabpanel'+(i===0?' on':'')+'" data-t="'+esc(p.key)+'">'+(p.html||'')+'</div>';}).join('');
  var sidePanel = panels.length
    ? '<div class="stu-side-panel"><div class="stu-tabs">'+tabs
      +'<span class="stu-dock-btns">'
      +'<button class="stu-dockb" title="Dock left" onclick="stuDock(\\'left\\')">\\u25e7\\u25e8</button>'
      +'<button class="stu-dockb" title="Dock right" onclick="stuDock(\\'right\\')">\\u25e8</button>'
      +'<button class="stu-dockb" title="Dock bottom" onclick="stuDock(\\'bottom\\')">\\u25e7</button>'
      +'</span></div>'+tabpanels+'</div>'
    : '';
  var h='<div class="stu-head"><button class="stu-toggle" onclick="stuToggleSide()" title="Show / hide the object list">\\u2630</button>'
    +'<h2>'+esc(d.name)+'</h2><span class="stu-kind">'+esc(d.kind||'')+'</span>'
    +(d.instance_of?'<span class="stu-instof" title="Instance of class">\\u2192 '+esc(d.instance_of)+'</span>':'')
    +chips
    +'<div class="stu-head-sp"></div>'
    + (d.can_simulate ? '<button class="stu-simbtn" onclick="rsOpen(\\''+esc(d.obj||d.name)+'\\',\\''+esc(d.sim_instance||'')+'\\')" title="Run this EM\\'s command logic with real CM/EM feedback">\\u25b6 Real simulation</button>' : '')
    + (d.can_matrix ? '<button class="stu-matrixbtn" onclick="pmOpen(\\''+esc(d.matrix_class||d.obj||d.name)+'\\')" title="Compare & bulk-edit this parameter across all '+(d.instance_count||0)+' deployed instances">\\u25a6 Parameter Matrix</button>' : '')
    + stuOpenInExplorerBtn(d._id)
    +'</div>'
    + stuPathBar(d.path)
    +'<div class="stu-body stu-dock-'+STU.dock+'">'
    +'<div class="stu-pane stu-diagram">'+mainInner+'</div>'
    + (sidePanel ? '<div class="stu-split" id="stuSplit"></div>'+sidePanel : '')
    +'</div>';
  document.getElementById('stuMain').innerHTML=h;
  stuWireSplit();
}
// #3: full S88 path breadcrumb — the equipment hierarchy needed for the FHX round-trip.
function stuPathBar(path){
  if(!path || !path.crumbs || !path.crumbs.length) return '';
  var kicon={'Plant Area':'\\u25a3','Process Cell':'\\u25a6','Unit':'\\u25a4',
             'Equipment Module':'\\u25c9','Equipment Module class':'\\u25c9',
             'Control Module':'\\u25ce','Control Module class':'\\u25ce',
             'Instance':'\\u25c8','Phase':'\\u25b8'};
  var parts=path.crumbs.map(function(c,i){
    var last=(i===path.crumbs.length-1);
    return '<span class="stu-crumb'+(last?' stu-crumb-cur':'')+'" title="'+esc(c.kind)+'">'
      +'<span class="stu-crumb-k">'+(kicon[c.kind]||'\\u00b7')+' '+esc(c.kind)+'</span>'
      +'<span class="stu-crumb-n">'+esc(c.name)+'</span>'
      +(c.sub?'<span class="stu-crumb-sub">'+esc(c.sub)+'</span>':'')+'</span>';
  }).join('<span class="stu-crumb-sep">\\u203a</span>');
  var warn = path.found ? '' :
    '<span class="stu-path-warn" title="No deployed instance path found — class shown without equipment context">class only</span>';
  return '<div class="stu-pathbar">'+parts+warn+'</div>';
}
function stuOpenInExplorerBtn(id){
  var exp='';
  var canExport=(id.indexOf('phase:')===0||id.indexOf('em:')===0||id.indexOf('cm:')===0||id.indexOf('dep:')===0);
  if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN && canExport){
    exp='<button class="exp-btn" style="padding:5px 10px" onclick="window.location.href=\\'/export?token=\\'+encodeURIComponent(EXPORT_TOKEN)+\\'&fmt=excel&obj=\\'+encodeURIComponent(\\''+esc(id)+'\\')" title="Export this object to Excel">'+_EXCEL_ICON_RAW+'Excel</button>'
      +'<button class="exp-btn" style="padding:5px 10px" onclick="window.location.href=\\'/export?token=\\'+encodeURIComponent(EXPORT_TOKEN)+\\'&fmt=word&obj=\\'+encodeURIComponent(\\''+esc(id)+'\\')" title="Export this object to Word">'+_WORD_ICON_RAW+'Word</button>';
  }
  // deployed instances open in the Explorer's deployed view; classes/phases via show()
  var openCall = (id.indexOf('dep:')===0)
    ? ("switchView('explorer');show('"+esc(id)+"')")
    : ("switchView('explorer');show('"+esc(id)+"')");
  return exp+'<button class="exp-btn" style="padding:5px 10px" onclick="'+openCall+'" title="Show this object in the Explorer">Open in Explorer</button>';
}
// ─── Real simulation ────────────────────────────────────────────────────────
// Runs an EM's command SFC with real CM/EM feedback: each device closes its own
// output->feedback loop with a configurable travel time. Mode 2 (vs the offline
// phase "verify steps" simulator, which assumes commands are instantly satisfied).
var RS={em:'',emClass:'',instance:'',instances:[],devices:[],commands:[],trace:[],cur:0,timer:null,playing:false,speed:1,completed:false,mode:'auto',overrides:{},host:'dock'};
// The sim renders the same card into either a docked Studio region (default, full
// width) or a floating window. rsOpen(em, instance, host) — host 'dock' or 'float'.
function rsCardHtml(){
  return '<div class="rs-card" id="rsCard"><div class="rs-head" id="rsHead"><h2>Real simulation</h2>'
    +'<span class="sub" id="rsSub">'+esc(RS.instance||RS.em)+'</span>'
    +'<span class="rs-head-sp"></span>'
    +'<button class="rs-hostb" id="rsHostBtn" title="Pop out / dock" onclick="rsToggleHost()">'+(RS.host==='float'?'\\u25f1 Dock':'\\u2197 Pop out')+'</button>'
    +'<span class="x" onclick="rsClose()">\\u00d7</span></div>'
    +'<div class="rs-body"><div class="rs-config" id="rsConfig">'+dvLoader('Loading EM\\u2026')+'</div>'
    +'<div class="rs-split-v" id="rsSplitV"></div>'
    +'<div class="rs-run" id="rsRun"><div class="rs-empty">Pick a command and press Run to simulate the EM logic with real device feedback.</div></div>'
    +'</div></div>';
}
function rsMountHost(){
  // remove any existing hosts
  var ov=document.getElementById('rsOverlay'); if(ov) ov.remove();
  var dk=document.getElementById('rsDockHost'); if(dk) dk.remove();
  if(RS.host==='float'){
    ov=document.createElement('div'); ov.id='rsOverlay'; ov.className='rs-ov';
    ov.innerHTML=rsCardHtml(); document.body.appendChild(ov);
    rsWireDrag();
  } else {
    // dock into the Studio main area as a full-width region below the head
    var main=document.getElementById('stuMain')||document.body;
    dk=document.createElement('div'); dk.id='rsDockHost'; dk.className='rs-dockhost';
    dk.innerHTML=rsCardHtml(); main.appendChild(dk);
  }
  rsWireConfigSplit();
}
function rsToggleHost(){
  RS.host=(RS.host==='float')?'dock':'float';
  rsMountHost();
  if(RS.trace && RS.trace.length){ rsRenderConfig(); rsRenderFrame(); }
  else rsRenderConfig();
}
function rsOpen(em, instance, host){
  RS.em=em; RS.instance=instance||''; RS.trace=[]; RS.cur=0; RS.completed=false;
  RS.host=host||'dock';
  var idParam = RS.instance || em;
  rsMountHost();
  fetch('/em_sim_meta?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(idParam))
    .then(function(r){return r.json();})
    .then(function(m){
      if(m.error){ var c=document.getElementById('rsConfig'); if(c) c.innerHTML='<div class="rs-empty">'+esc(m.error)+'</div>'; return; }
      RS.devices=m.devices||[]; RS.commands=m.commands||[];
      RS.instances=m.instances||[]; RS.emClass=m.em||RS.em;
      if(m.instance) RS.instance=m.instance;
      rsRenderConfig();
    })
    .catch(function(e){ var c=document.getElementById('rsConfig'); if(c) c.innerHTML='<div class="rs-empty">'+esc(e.message)+'</div>'; });
}
function rsClose(){ rsStop(); rsCloseCM(); rsCloseFace();
  var o=document.getElementById('rsOverlay'); if(o) o.remove();
  var d=document.getElementById('rsDockHost'); if(d) d.remove();
}
// draggable divider to resize the left config panel (#2)
function rsWireConfigSplit(){
  var sp=document.getElementById('rsSplitV'); if(!sp) return;
  sp.addEventListener('mousedown',function(e){
    var cfg=document.getElementById('rsConfig'); if(!cfg) return;
    var startX=e.clientX, startW=cfg.getBoundingClientRect().width;
    // block iframe capture during drag
    function mv(ev){ var w=Math.max(180,Math.min(560,startW+(ev.clientX-startX))); cfg.style.width=w+'px'; cfg.style.flex='0 0 '+w+'px'; }
    function up(){ document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up); document.body.style.userSelect=''; }
    document.body.style.userSelect='none'; document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up); e.preventDefault();
  });
}
// drag the floating sim window by its header
function rsWireDrag(){
  var head=document.getElementById('rsHead'), card=document.getElementById('rsCard');
  if(!head||!card) return;
  head.addEventListener('mousedown',function(e){
    if(e.target.classList.contains('x')) return;
    var r=card.getBoundingClientRect();
    // switch from translateX centering to absolute left/top so drag is stable
    card.style.transform='none'; card.style.left=r.left+'px'; card.style.top=r.top+'px';
    var ox=e.clientX-r.left, oy=e.clientY-r.top;
    function mv(ev){
      card.style.left=Math.max(0,Math.min(window.innerWidth-80,ev.clientX-ox))+'px';
      card.style.top=Math.max(0,Math.min(window.innerHeight-40,ev.clientY-oy))+'px';
    }
    function up(){ document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up); document.body.style.userSelect=''; }
    document.body.style.userSelect='none';
    document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
    e.preventDefault();
  });
}
function rsRenderConfig(){
  var cmds=RS.commands.map(function(c){return '<option>'+esc(c)+'</option>';}).join('');
  // instance picker: only when opened from a CLASS and >1 deployment exists
  var instPicker='';
  if(!RS.instance && RS.instances && RS.instances.length){
    var opts=RS.instances.map(function(i){return '<option value="'+esc(i.tag)+'">'+esc(i.tag)+(i.area?' \\u00b7 '+esc(i.area):'')+'</option>';}).join('');
    instPicker='<p class="rs-lbl">Instance</p><select class="rs-cmd" id="rsInst" onchange="rsPickInstance(this.value)">'
      +'<option value="">Class (generic members)</option>'+opts+'</select>';
  }
  var devs=RS.devices.map(function(d){
    var fam=(d.family||'device');
    var dis=d.modelled?'':' disabled';
    var label=d.resolved?esc(d.tag):esc(d.member||d.instance);
    var member=d.member||d.instance;
    var ignoreBadge=d.ignore?'<span class="rs-ign">ignored</span>':'';
    var sub=(d.resolved && d.tag!==member)?'<span class="rs-devrow-mem">'+esc(member)+'</span>':'';
    return '<div class="rs-devrow-cfg'+(d.ignore?' off':'')+'"><span class="nm rs-devopen" title="Open faceplate" onclick="rsOpenFace(\\''+esc(member)+'\\')">'+label+sub+'</span>'
      +'<span class="rs-fam '+esc(fam)+'">'+esc(fam)+'</span>'+ignoreBadge
      +'<input class="rs-travel" id="rsTv_'+esc(member)+'" value="'+(d.default_travel||10)+'"'+dis+(d.ignore?' disabled':'')+'>'
      +'<span class="rs-travel-u">ticks</span></div>';
  }).join('');
  document.getElementById('rsConfig').innerHTML=''
    +instPicker
    +'<p class="rs-lbl">Command</p><select class="rs-cmd" id="rsCmd">'+cmds+'</select>'
    +'<p class="rs-lbl">Run mode</p>'
    +'<div class="rs-mode">'
    +'<label class="rs-moderb"><input type="radio" name="rsMode" value="auto"'+(RS.mode==='auto'?' checked':'')+' onchange="rsSetMode(\\'auto\\')"> Auto <small>time-based flow</small></label>'
    +'<label class="rs-moderb"><input type="radio" name="rsMode" value="semi"'+(RS.mode==='semi'?' checked':'')+' onchange="rsSetMode(\\'semi\\')"> Semi <small>step tick-by-tick</small></label>'
    +'<label class="rs-moderb"><input type="radio" name="rsMode" value="full"'+(RS.mode==='full'?' checked':'')+' onchange="rsSetMode(\\'full\\')"> Manual <small>drive from faceplate</small></label>'
    +'</div>'
    +'<p class="rs-lbl">Device travel times</p>'+devs
    +'<div class="rs-actions"><button class="rs-btn primary" id="rsRunBtn" onclick="rsRun()">\\u25b6 Run</button>'
    +'<button class="rs-btn" onclick="rsResetConfig()">Reset</button></div>'
    +'<div class="rs-note" id="rsModeNote">1 tick \\u2248 100\\u202fms. Travel time is how long each device takes to move and report feedback. Raise it to study sequencing and timeouts.</div>';
}
function rsPickInstance(tag){ RS.instance=tag; rsReloadMeta(); }
function rsReloadMeta(){
  var idParam=RS.instance||RS.emClass||RS.em;
  document.getElementById('rsConfig').innerHTML=dvLoader('Resolving\\u2026');
  fetch('/em_sim_meta?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(idParam))
    .then(function(r){return r.json();}).then(function(m){
      if(m.error){ document.getElementById('rsConfig').innerHTML='<div class="rs-empty">'+esc(m.error)+'</div>'; return; }
      RS.devices=m.devices||[]; RS.commands=m.commands||[]; RS.instances=m.instances||RS.instances;
      rsRenderConfig();
      var sub=document.querySelector('#rsCard .sub'); if(sub) sub.textContent=RS.instance||RS.emClass||RS.em;
    });
}
function rsSetMode(mode){
  RS.mode=mode;
  var n=document.getElementById('rsModeNote');
  var notes={
    'auto':'1 tick \\u2248 100\\u202fms. Travel time is how long each device takes to move and report feedback. Raise it to study sequencing and timeouts.',
    'semi':'Semi-auto: press Run, then Step one tick at a time to watch each confirm resolve. Hold or force a device from its faceplate to test the waiting path.',
    'full':'Manual: press Run, open a device faceplate, and drive it yourself \\u2014 your command satisfies the step\\'s confirm instead of the travel-time model.'
  };
  if(n) n.textContent=notes[mode]||notes.auto;
}
function rsResetConfig(){
  RS.devices.forEach(function(d){ var k=d.member||d.instance; var el=document.getElementById('rsTv_'+k); if(el) el.value=d.default_travel||10; });
}
function rsTravelMap(){
  var m={};
  RS.devices.forEach(function(d){ var k=d.member||d.instance; var el=document.getElementById('rsTv_'+k); if(el && el.value!=='') m[k]=parseInt(el.value,10)||0; });
  return m;
}
function rsRun(){
  rsStop();
  var cmd=(document.getElementById('rsCmd')||{}).value||'';
  var btn=document.getElementById('rsRunBtn'); if(btn){ btn.disabled=true; btn.textContent='Running\\u2026'; }
  var run=document.getElementById('rsRun');
  run.innerHTML='<div class="rs-empty">'+dvLoader('Simulating '+esc(cmd)+'\\u2026')+'</div>';
  var fd=new FormData();
  fd.append('t',EXPORT_TOKEN); fd.append('em',RS.emClass||RS.em); fd.append('command',cmd);
  if(RS.instance) fd.append('instance', RS.instance);
  fd.append('travel_map', JSON.stringify(rsTravelMap()));
  if(RS.overrides) fd.append('overrides', JSON.stringify(RS.overrides));
  fetch('/em_sim_run',{method:'POST',body:fd})
    .then(function(r){return r.json();})
    .then(function(d){
      if(btn){ btn.disabled=false; btn.textContent='\\u25b6 Run'; }
      if(d.error){ run.innerHTML='<div class="rs-empty">'+esc(d.error)+'</div>'; return; }
      RS.trace=d.trace||[]; RS.completed=d.completed; RS.notes=d.notes||[]; RS.cur=0;
      RS.layout=d.layout||{steps:[],transitions:[]}; RS.sel=null; RS.selManual=false;
      if(!RS.trace.length){ run.innerHTML='<div class="rs-empty">No steps ran for this command.</div>'; return; }
      rsRenderFrame();
      if(RS.mode==='auto'){ rsPlay(); }              // auto: animate immediately
      else { RS.playing=false; rsRenderFrame(); }    // semi/full: wait for step / manual drive
    })
    .catch(function(e){ if(btn){btn.disabled=false;btn.textContent='\\u25b6 Run';} run.innerHTML='<div class="rs-empty">'+esc(e.message)+'</div>'; });
}
function rsStepFwd(){ rsStop(); if(RS.cur<RS.trace.length-1){ RS.cur++; } rsRenderFrame(); }
function rsStepBack(){ rsStop(); if(RS.cur>0){ RS.cur--; } rsRenderFrame(); }
function rsPinClass(v, active){
  // active(true)=asserted/confirmed -> hi; waiting sentinel -> wait; else neutral
  if(v==='\\u2026'||v==='wait') return 'pin wait';
  return active?'pin hi':'pin';
}
function rsFmt(v){
  if(v===1||v===true) return '1';
  if(v===0||v===false) return '0';
  if(v===null||v===undefined) return '\\u2013';
  var s=String(v);
  var m=s.split(':'); return esc((m[m.length-1]||s).toUpperCase());
}
function rsIsActive(v){
  if(v===1||v===true) return true;
  var s=String(v).toUpperCase();
  return s.indexOf('OPEN')>=0||s.indexOf('RUNNING')>=0||s.indexOf('START')>=0||s.indexOf('RUN')>=0||s==='ON';
}
function rsRenderFrame(){
  var row=RS.trace[RS.cur]; if(!row) return;
  var last=RS.trace[RS.trace.length-1];
  var badge = RS.completed ? '<span class="rs-badge done">completed</span>'
            : (RS.cur>=RS.trace.length-1 ? '<span class="rs-badge timeout">did not confirm</span>' : '<span class="rs-badge run">running</span>');
  var curStep=row.step;
  // selected step defaults to the active one, but the user can click another
  if(!RS.sel || RS.selManual!==true) RS.sel=curStep;
  var seen=[]; RS.trace.forEach(function(r){ if(r.step && seen.indexOf(r.step)<0) seen.push(r.step); });
  var curIdx=seen.indexOf(curStep);
  var sfc=rsBuildSFC(seen, curStep, curIdx, row);
  var verify=rsBuildVerify(row);
  document.getElementById('rsRun').innerHTML=''
    +'<div class="rs-sfc-col">'
    +'<div class="rs-status"><span class="rs-clock">tick '+row.tick+' / '+last.tick+'</span>'
    +'<span class="rs-step-now">'+esc(curStep||'')+(row.step_desc?' \\u00b7 '+esc(row.step_desc):'')+'</span>'+badge+'</div>'
    +'<div class="rs-sfc-wrap">'+sfc+'</div></div>'
    +'<div class="rs-verify">'+verify+'</div>'
    +'<div class="rs-scrub"><button class="rs-play" title="Step back" onclick="rsStepBack()">\\u23ea</button>'
    +'<button class="rs-play" onclick="rsToggle()">'+(RS.playing?'\\u2759\\u2759':'\\u25b6')+'</button>'
    +'<button class="rs-play" title="Step forward" onclick="rsStepFwd()">\\u23e9</button>'
    +'<input type="range" min="0" max="'+(RS.trace.length-1)+'" value="'+RS.cur+'" oninput="rsSeek(this.value)">'
    +'<button class="rs-play" title="Speed" onclick="rsCycleSpeed()">'+RS.speed+'\\u00d7</button></div>';
  if(RS.faceInst) rsRenderFace();   // keep the floating faceplate in sync while animating
  rsFocusActive();                  // #4: highlight + scroll to the running action
}
// #4: bring the currently-active action into view and pulse it while running.
function rsFocusActive(){
  var host=document.getElementById('rsRun'); if(!host) return;
  var el=host.querySelector('.rs-act.rs-act-live');
  if(el && RS.playing){
    // scroll the verify panel (not the page) so the active action stays visible
    var panel=host.querySelector('.rs-verify');
    if(panel){ var pr=panel.getBoundingClientRect(), er=el.getBoundingClientRect();
      if(er.top<pr.top+8||er.bottom>pr.bottom-8){ el.scrollIntoView({block:'nearest',behavior:'smooth'}); } }
  }
}
// draw the SFC as inline SVG from the run layout, active step highlighted
function rsBuildSFC(seen, curStep, curIdx, row){
  var L=RS.layout||{steps:[],transitions:[]};
  if(!L.steps.length) return '<div class="rs-empty">No SFC layout.</div>';
  // normalise stored X/Y into a tidy vertical ladder (real coords can be sparse)
  var xs=L.steps.map(function(s){return s.x;}), ys=L.steps.map(function(s){return s.y;});
  var minX=Math.min.apply(null,xs), minY=Math.min.apply(null,ys);
  var BW=150, BH=54, GAPY=86, LEFT=70;
  var order={}; seen.forEach(function(s,i){order[s]=i;});
  function sy(sid){ return 20 + (order[sid]!==undefined?order[sid]:0)*GAPY; }
  var h=20+seen.length*GAPY+10;
  var parts=['<svg viewBox="0 0 240 '+h+'" width="100%" height="'+Math.min(h,520)+'">'];
  // lines + transitions between consecutive steps
  L.transitions.forEach(function(tr){
    var from=(L.step_to_trans&&Object.keys(L.step_to_trans).filter(function(s){return (L.step_to_trans[s]||[]).indexOf(tr.id)>=0;})[0])||'';
    var to=((L.trans_to_step||{})[tr.id]||[])[0]||'';
    if(from){
      var y1=sy(from)+BH, y2=(to?sy(to):y1+GAPY-BH);
      var hot = (from===curStep && row.pending===0);
      parts.push('<line class="sfc-line" x1="145" y1="'+y1+'" x2="145" y2="'+(y1+16)+'"/>');
      parts.push('<g class="sfc-trans'+(hot?' hot':'')+'" transform="translate(120,'+(y1+16)+')"><rect x="0" y="0" width="50" height="6"/><text class="sfc-tid" x="56" y="7">'+esc(tr.id)+'</text></g>');
      if(to) parts.push('<line class="sfc-line" x1="145" y1="'+(y1+22)+'" x2="145" y2="'+sy(to)+'"/>');
    }
  });
  // step boxes
  seen.forEach(function(sid){
    var s=L.steps.filter(function(x){return x.id===sid;})[0]||{id:sid,desc:''};
    var i=order[sid];
    var cls='sfc-step'+(sid===curStep?' active':(i<curIdx?' past':''))+(sid===RS.sel?' sel':'');
    var y=sy(sid);
    parts.push('<g class="'+cls+'" transform="translate('+LEFT+','+y+')" onclick="rsSelStep(\\''+esc(sid)+'\\')">'
      +'<rect class="sfc-box" width="'+BW+'" height="'+BH+'" rx="6"/>'
      +'<text class="sfc-sid" x="10" y="22">'+esc(sid)+'</text>'
      +'<text class="sfc-sd" x="10" y="40">'+esc((s.desc||'').slice(0,20))+'</text></g>');
  });
  parts.push('</svg>');
  return parts.join('');
}
function rsSelStep(sid){ RS.sel=sid; RS.selManual=true; rsRenderFrame(); }
// Animated colored device symbol: a valve or motor glyph that colors by state
// (green=confirmed/running, amber pulsing=moving, red=interlocked, grey=idle).
function rsDeviceSymbol(family, state){
  var isMotor=/mtr|motor|pump/i.test(family);
  var cls='rs-sym rs-sym-'+state;
  if(isMotor){
    // motor: a rotor circle that spins while moving
    return '<span class="'+cls+'" title="'+esc(state)+'"><svg viewBox="0 0 22 22" width="20" height="20">'
      +'<circle cx="11" cy="11" r="9" class="rs-sym-body"/>'
      +'<g class="rs-sym-rot"><line x1="11" y1="4" x2="11" y2="18"/><line x1="4" y1="11" x2="18" y2="11"/></g>'
      +'</svg></span>';
  }
  // valve: a two-triangle bowtie that fills when open
  return '<span class="'+cls+'" title="'+esc(state)+'"><svg viewBox="0 0 22 22" width="20" height="20">'
    +'<path class="rs-sym-body" d="M3 5 L11 11 L3 17 Z M19 5 L11 11 L19 17 Z"/>'
    +'</svg></span>';
}
// requested-vs-actual verification panel for the selected step at the current tick
function rsBuildVerify(row){
  var sel=RS.sel||row.step;
  // the trace row carries actions only for the step ACTIVE at that tick; if the user
  // selected a different step, find the latest frame where that step was active.
  var acts=row.actions;
  if(sel!==row.step){
    for(var i=RS.cur;i>=0;i--){ if(RS.trace[i].step===sel){ acts=RS.trace[i].actions; break; } }
  }
  var stepDesc=''; for(var j=0;j<RS.trace.length;j++){ if(RS.trace[j].step===sel){ stepDesc=RS.trace[j].step_desc||''; break; } }
  if(!acts||!acts.length) return '<p class="rs-vhead">'+esc(sel)+'</p><p class="rs-vsub">No actions on this step.</p>';
  var childNow=(RS.trace[RS.cur]||{}).children||{};
  // the "live" action is the first not-yet-confirmed, not-gated one on the active step
  var liveIdx=-1;
  if(sel===row.step){ for(var li=0;li<acts.length;li++){ if(!acts[li].confirmed && !acts[li].gated){ liveIdx=li; break; } } }
  var rows=acts.map(function(a,ai){
    var stCls=a.gated?'gated':(a.confirmed?'ok':'wait');
    var stTxt=a.gated?'gated':(a.confirmed?'confirmed':'waiting');
    var actMatch=(String(a.actual).toUpperCase()===String(a.expected).toUpperCase()) && a.expected!=='';
    var expHtml = a.expected? '<div><div class="k">Expected</div><div class="v exp">'+esc(a.expected)+'</div></div>'
                              +'<div><div class="k">Actual</div><div class="v act '+(actMatch?'match':'miss')+'">'+esc(a.actual)+'</div></div>' : '';
    // the live device being driven by this action (DO output + PV feedback right now)
    var devHtml='';
    var dev=a.req_target?childNow[a.req_target]:null;
    if(dev){
      var doA=rsIsActive(dev.do), pvA=rsIsActive(dev.pv), diWaiting=doA&&!rsIsActive(dev.di);
      var ilkOn=dev.interlock_active;
      var symState = ilkOn?'ilk':(pvA?'on':(diWaiting?'move':'off'));
      devHtml='<div class="rs-actdev'+(ilkOn?' ilk':'')+(a.req_target===RS.faceInst?' focus':'')+'">'
        +rsDeviceSymbol(dev.family||(a.req_target||''), symState)
        +'<span class="rs-actdev-nm rs-devopen" onclick="rsOpenFace(\\''+esc(a.req_target)+'\\')" title="Open faceplate">'+esc(dev.tag||a.req_target)+'</span>'
        +'<span class="rs-actdev-pin '+(doA?'hi':'')+'">DO '+rsFmt(dev.do)+'</span>'
        +'<span class="rs-actdev-pin '+(diWaiting?'wait':(rsIsActive(dev.di)?'hi':''))+'">DI '+(diWaiting?'\\u2026':rsFmt(dev.di))+'</span>'
        +'<span class="rs-actdev-pin '+(pvA?'hi':'')+'">PV '+rsFmt(dev.pv)+'</span>'
        +(ilkOn?'<span class="rs-actdev-ilk">interlocked</span>':'')
        +'<span class="rs-actdev-open" onclick="rsOpenFace(\\''+esc(a.req_target)+'\\')" title="Open faceplate">faceplate \\u203a</span>'
        +'</div>';
    }
    return '<div class="rs-act '+(a.gated?'':(a.confirmed?'ok':'wait'))+(ai===liveIdx?' rs-act-live':'')+'">'
      +'<div class="rs-act-h"><span class="rs-act-id">'+esc(a.action)+'</span>'
      +'<span class="rs-act-d">'+esc(a.desc||a.request||'')+'</span>'
      +'<span class="rs-act-st '+stCls+'">'+stTxt+'</span></div>'
      +'<div class="rs-io"><div><div class="k">Requested</div><div class="v">'+esc(a.request||'')+'</div></div>'
      +'<div><div class="k">Confirm</div><div class="v '+(a.confirmed?'act match':'')+'">'+(a.confirmed?'\\u2713 met':'pending')+'</div></div>'
      + expHtml + '</div>'+devHtml+'</div>';
  }).join('');
  return '<p class="rs-vhead">'+esc(sel)+(stepDesc?' \\u00b7 '+esc(stepDesc):'')+'</p>'
    +'<p class="rs-vsub">'+acts.length+' action'+(acts.length!==1?'s':'')+' \\u2014 requested vs actual</p>'+rows;
}
// ─── Device faceplate ───────────────────────────────────────────────────────
// A full DeltaV-style faceplate for a device: identity, mode/status, the
// command->feedback chain, interlock panel, and (in Manual run mode) command
// buttons that DRIVE the device so your action satisfies the sequence's confirm.
// Opens without leaving the sim; draggable; stays in sync while animating.
function rsOpenFace(inst){
  RS.faceInst=inst;
  var w=document.getElementById('rsFaceWin');
  if(!w){ w=document.createElement('div'); w.id='rsFaceWin'; w.className='rs-face'; document.body.appendChild(w); }
  rsRenderFace(); rsWireFaceDrag();
  if(RS.trace&&RS.trace.length) rsRenderFrame();  // refresh focus highlight
}
function rsCloseFace(){ RS.faceInst=null; var w=document.getElementById('rsFaceWin'); if(w) w.remove(); }
// alias kept so older callers still work
function rsOpenCM(inst){ rsOpenFace(inst); }
function rsCloseCM(){ rsCloseFace(); }
function rsRenderCM(){ rsRenderFace(); }
function rsFaceMeta(inst){ return (RS.devices||[]).filter(function(d){return (d.member||d.instance)===inst;})[0]||{}; }
function rsRenderFace(){
  var w=document.getElementById('rsFaceWin'); if(!w||!RS.faceInst) return;
  var inst=RS.faceInst;
  var row=RS.trace[RS.cur]||{}; var c=(row.children||{})[inst];
  var meta=rsFaceMeta(inst);
  var famRaw=(c&&c.family)||meta.family||'';
  var isMotor=/mtr|motor|pump/i.test(famRaw);
  var famLabel=isMotor?'motor':(/valve|vlv/i.test(famRaw)?'valve':'device');
  if(!c){
    w.innerHTML='<div class="rs-face-head" id="rsFaceHead"><b>'+esc(meta.tag||inst)+'</b><span class="x" onclick="rsCloseFace()">\\u00d7</span></div>'
      +'<div class="rs-face-body"><div class="rs-empty">This device isn\\'t part of the current command.</div></div>';
    return;
  }
  var doA=rsIsActive(c.do), diA=rsIsActive(c.di), pvA=rsIsActive(c.pv), rspA=rsIsActive(c.rsp);
  var diWaiting=doA&&!diA;
  var symState=c.interlock_active?'ilk':(pvA?'on':(diWaiting?'move':'off'));
  function pin(lbl,val,cls){ return '<div class="rs-sig"><div class="'+cls+'">'+val+'</div><div class="pl">'+lbl+'</div></div>'; }
  var chain='<div class="rs-loop">'
    + pin('RSP',rsFmt(c.rsp),rsPinClass(c.rsp,rspA))+'<div class="rs-arrow">\\u2192</div>'
    + pin('DO',rsFmt(c.do),rsPinClass(c.do,doA))
    + '<div class="rs-arrow">'+(diWaiting?'<span class="tt">travel '+(c.travel||'')+'t</span>':'')+'\\u2192</div>'
    + pin('DI',diWaiting?'\\u2026':rsFmt(c.di),diWaiting?'pin wait':rsPinClass(c.di,diA))+'<div class="rs-arrow">\\u2192</div>'
    + pin('PV',rsFmt(c.pv),rsPinClass(c.pv,pvA))+'</div>';
  var perm=c.permissive;
  var permBadge=perm?'<span class="rs-perm ok">permissive \\u2014 clear to move</span>':'<span class="rs-perm blk">interlocked \\u2014 held</span>';
  var ilkRows=(c.ilks||[]).map(function(k){
    return '<div class="rs-ilk'+(k.active?' on':'')+'" title="'+esc(k.expr||'')+'"><span class="rs-ilk-dot"></span>'
      +'<span class="rs-ilk-nm">'+esc(k.name)+'</span><span class="rs-ilk-st">'+(k.active?'ACTIVE':'clear')+'</span></div>';
  }).join('');
  var nActive=(c.ilks||[]).filter(function(k){return k.active;}).length;
  var ilkHdr=nActive?(nActive+' interlock condition'+(nActive!==1?'s':'')+' active'):'no interlock conditions active';
  // status word
  var statusWord=pvA?(isMotor?'RUNNING':'OPEN'):(diWaiting?'MOVING':(isMotor?'STOPPED':'CLOSED'));
  var pv=rsFmt(c.pv);
  // manual command buttons (full mode) — drive the device to satisfy the sequence
  var driveHtml=rsFaceDrive(inst, isMotor, c);
  w.innerHTML=''
    +'<div class="rs-face-head" id="rsFaceHead">'
    + rsDeviceSymbol(famRaw, symState)
    +'<div class="rs-face-id"><b>'+esc(c.tag||inst)+'</b>'
    +'<span class="rs-face-cls">'+esc(meta.module||c.module||'')+(meta.member&&meta.member!==(c.tag||inst)?' \\u00b7 '+esc(meta.member):'')+'</span></div>'
    +'<span class="rs-face-fam '+famLabel+'">'+famLabel+'</span>'
    +'<span class="x" onclick="rsCloseFace()">\\u00d7</span></div>'
    +'<div class="rs-face-body">'
    // status band
    +'<div class="rs-face-status '+symState+'"><div class="rs-face-pv">'+esc(pv.toUpperCase())+'</div>'
    +'<div class="rs-face-sw">'+statusWord+'</div></div>'
    + driveHtml
    +'<p class="rs-cmw-lbl">Command \\u2192 feedback</p>'+chain
    +'<p class="rs-cmw-lbl" style="margin-top:15px">Interlock status</p>'
    +'<div class="rs-perm-row">'+permBadge+'<span class="rs-ilk-hdr">'+ilkHdr+'</span></div>'
    +'<div class="rs-ilk-grid">'+(ilkRows||'<span class="rs-vsub">No interlock conditions modelled.</span>')+'</div>'
    +'<p class="rs-cmw-foot">Travel '+(c.travel||'?')+' ticks \\u00b7 tick '+(row.tick)+'. '
    +(pvA?'Confirmed.':(doA?'Output driven \\u2014 waiting for feedback.':(perm?'Idle.':'Held by interlock.')))+'</p>'
    + rsManualControls(inst)
    +'</div>';
}
// command buttons for full-manual mode: writing force_do drives the device so its
// feedback (after travel) satisfies the step confirm — you act as the operator.
function rsFaceDrive(inst, isMotor, c){
  if(RS.mode!=='full') return '';
  var ov=(RS.overrides&&RS.overrides[inst])||{};
  var onLabel=isMotor?'Start':'Open', offLabel=isMotor?'Stop':'Close';
  var onActive=ov.force_do===1, offActive=ov.force_do===0;
  return '<div class="rs-face-drive"><p class="rs-cmw-lbl">Manual command</p>'
    +'<div class="rs-face-cmds">'
    +'<button class="rs-cmdbtn on'+(onActive?' active':'')+'" onclick="rsDrive(\\''+esc(inst)+'\\',1)">'+onLabel+'</button>'
    +'<button class="rs-cmdbtn off'+(offActive?' active':'')+'" onclick="rsDrive(\\''+esc(inst)+'\\',0)">'+offLabel+'</button>'
    +'<button class="rs-cmdbtn clr" onclick="rsDrive(\\''+esc(inst)+'\\',null)">Release</button>'
    +'</div><p class="rs-face-drivenote">Your command drives the device; after its travel time the feedback satisfies the sequence step.</p></div>';
}
function rsDrive(inst, val){
  RS.overrides=RS.overrides||{}; RS.overrides[inst]=RS.overrides[inst]||{};
  if(val===null){ delete RS.overrides[inst].force_do; }
  else { RS.overrides[inst].force_do=val; }
  if(!Object.keys(RS.overrides[inst]).length) delete RS.overrides[inst];
  rsRun();
}
// advanced hold/force controls — available in Semi and Manual modes
function rsManualControls(inst){
  if(RS.mode==='auto') return '';
  var ov=(RS.overrides&&RS.overrides[inst])||{};
  return '<details class="rs-manual"'+((ov.hold||ov.force_di!==undefined)?' open':'')+'><summary class="rs-cmw-lbl">Advanced \\u2014 hold / force signals</summary>'
    +'<label class="rs-mctl"><input type="checkbox" '+(ov.hold?'checked':'')+' onchange="rsOverride(\\''+esc(inst)+'\\',\\'hold\\',this.checked)"> Hold feedback <small>DI never arrives</small></label>'
    +'<div class="rs-mbtns">'
    +'<button class="rs-btn sm'+(ov.force_di===1?' on':'')+'" onclick="rsOverride(\\''+esc(inst)+'\\',\\'force_di\\','+(ov.force_di===1?'null':'1')+')">Force DI 1</button>'
    +'<button class="rs-btn sm'+(ov.force_di===0?' on':'')+'" onclick="rsOverride(\\''+esc(inst)+'\\',\\'force_di\\','+(ov.force_di===0?'null':'0')+')">Force DI 0</button>'
    +'<button class="rs-btn sm'+(ov.force_do===1?' on':'')+'" onclick="rsOverride(\\''+esc(inst)+'\\',\\'force_do\\','+(ov.force_do===1?'null':'1')+')">Force DO 1</button>'
    +'<button class="rs-btn sm'+(ov.force_do===0?' on':'')+'" onclick="rsOverride(\\''+esc(inst)+'\\',\\'force_do\\','+(ov.force_do===0?'null':'0')+')">Force DO 0</button>'
    +'</div></details>';
}
function rsOverride(inst, key, val){
  RS.overrides=RS.overrides||{}; RS.overrides[inst]=RS.overrides[inst]||{};
  if(val===null) delete RS.overrides[inst][key]; else RS.overrides[inst][key]=val;
  if(!Object.keys(RS.overrides[inst]).length) delete RS.overrides[inst];
  rsRun();
}
function rsWireFaceDrag(){
  var head=document.getElementById('rsFaceHead'), win=document.getElementById('rsFaceWin');
  if(!head||!win) return;
  head.addEventListener('mousedown',function(e){
    if(e.target.classList.contains('x')) return;
    var r=win.getBoundingClientRect(); win.style.left=r.left+'px'; win.style.top=r.top+'px'; win.style.right='auto';
    var ox=e.clientX-r.left, oy=e.clientY-r.top;
    function mv(ev){ win.style.left=Math.max(0,Math.min(window.innerWidth-60,ev.clientX-ox))+'px'; win.style.top=Math.max(0,Math.min(window.innerHeight-30,ev.clientY-oy))+'px'; }
    function up(){ document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up); document.body.style.userSelect=''; }
    document.body.style.userSelect='none'; document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up); e.preventDefault();
  });
}
function _rsCmClass(inst){
  var d=(RS.devices||[]).filter(function(x){return x.instance===inst;})[0];
  return d?d.module:inst;
}
// ─── Parameter Matrix ───────────────────────────────────────────────────────
// Lay every deployed instance of a class into one grid (params x instances), spot
// the outliers, bulk-edit, and export a minimal-diff FHX to re-import into DeltaV.
// Native DeltaV makes you open each module one at a time — this compares all at once.
var PM={cls:'',data:null,edits:{},filter:'',group:'All',onlyVary:false};
function pmOpen(cls){
  PM={cls:cls,data:null,edits:{},filter:'',group:'All',onlyVary:false};
  var ov=document.getElementById('pmOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='pmOverlay'; ov.className='pm-ov'; document.body.appendChild(ov); }
  ov.innerHTML='<div class="pm-card" id="pmCard"><div class="pm-head" id="pmHead"><h2>Parameter Matrix</h2>'
    +'<span class="sub" id="pmSub">'+esc(cls)+'</span><span class="x" onclick="pmClose()">\\u00d7</span></div>'
    +'<div id="pmToolbar"></div><div class="pm-gridwrap" id="pmGrid">'+dvLoader('Loading instances\\u2026')+'</div>'
    +'<div id="pmFoot"></div></div>';
  pmWireDrag();
  fetch('/param_matrix?t='+encodeURIComponent(EXPORT_TOKEN)+'&cls='+encodeURIComponent(cls))
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.error){ document.getElementById('pmGrid').innerHTML='<div class="pm-empty">'+esc(d.error)+'</div>'; return; }
      PM.data=d; pmRender();
    })
    .catch(function(e){ document.getElementById('pmGrid').innerHTML='<div class="pm-empty">'+esc(e.message)+'</div>'; });
}
function pmClose(){ var o=document.getElementById('pmOverlay'); if(o) o.remove(); }
function pmWireDrag(){
  var head=document.getElementById('pmHead'), card=document.getElementById('pmCard');
  if(!head||!card) return;
  head.addEventListener('mousedown',function(e){
    if(e.target.classList.contains('x')) return;
    var r=card.getBoundingClientRect(); card.style.transform='none'; card.style.left=r.left+'px'; card.style.top=r.top+'px';
    var ox=e.clientX-r.left, oy=e.clientY-r.top;
    function mv(ev){ card.style.left=Math.max(0,Math.min(window.innerWidth-80,ev.clientX-ox))+'px'; card.style.top=Math.max(0,Math.min(window.innerHeight-40,ev.clientY-oy))+'px'; }
    function up(){ document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up); document.body.style.userSelect=''; }
    document.body.style.userSelect='none'; document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up); e.preventDefault();
  });
}
function pmGroups(){
  var gs={}; (PM.data.params||[]).forEach(function(p){ gs[p.group]=1; });
  return ['All'].concat(Object.keys(gs).sort());
}
function pmRender(){
  var d=PM.data; if(!d) return;
  document.getElementById('pmSub').textContent=d.class+' \\u00b7 '+d.instances.length+' instances';
  // toolbar
  var chips=pmGroups().map(function(g){return '<span class="pm-chip'+(g===PM.group?' on':'')+'" onclick="pmSetGroup(\\''+esc(g)+'\\')">'+esc(g)+'</span>';}).join('');
  document.getElementById('pmToolbar').innerHTML='<div class="pm-toolbar">'
    +'<input class="pm-search" placeholder="Filter parameters\\u2026" value="'+esc(PM.filter)+'" oninput="pmSetFilter(this.value)">'
    +chips
    +'<label class="pm-vary-toggle"><input type="checkbox" '+(PM.onlyVary?'checked':'')+' onchange="pmSetVary(this.checked)"> Only params that vary</label>'
    +'<button class="pm-btn" onclick="pmExportXlsx()">Export .xlsx</button></div>';
  pmRenderGrid();
  pmRenderFoot();
}
function pmVisibleParams(){
  var f=PM.filter.toLowerCase();
  return (PM.data.params||[]).filter(function(p){
    if(PM.onlyVary && p.distinct<=1) return false;
    if(PM.group!=='All' && p.group!==PM.group) return false;
    if(f && p.name.toLowerCase().indexOf(f)<0) return false;
    return true;
  });
}
function pmRenderGrid(){
  var d=PM.data, insts=d.instances;
  var params=pmVisibleParams();
  if(!params.length){ document.getElementById('pmGrid').innerHTML='<div class="pm-empty">No parameters match.</div>'; return; }
  var head='<thead><tr><th class="pm-corner">Parameter</th>'
    +insts.map(function(i){var dsc=(i.desc||'').slice(0,22);return '<th class="pm-inst">'+esc(i.tag)+(dsc?'<small>'+esc(dsc)+'</small>':'')+'</th>';}).join('')+'</tr></thead>';
  var lastG=null, rows='';
  params.forEach(function(p){
    if(p.group!==lastG){ lastG=p.group; rows+='<tr class="pm-grp"><td class="pm-grp pm-pname">'+esc(p.group)+'</td>'+insts.map(function(){return '<td class="pm-grp"></td>';}).join('')+'</tr>'; }
    var badge = p.distinct>1 ? '<span class="pm-badge">'+p.distinct+' distinct</span>' : '';
    rows+='<tr><td class="pm-pname" title="'+esc(p.name)+'">'+esc(p.name)+badge+'</td>';
    insts.forEach(function(i){
      var v=(d.values[p.name]||{})[i.tag];
      if(v===undefined){ rows+='<td class="pm-cell empty">\\u2014</td>'; return; }
      var edited=PM.edits[i.tag]&&PM.edits[i.tag][p.name]!==undefined;
      var shown=edited?PM.edits[i.tag][p.name]:v;
      var cls='pm-cell'+(p.varies||p.distinct>1?' vary':'')+(edited?' edited':'');
      rows+='<td class="'+cls+'"><input value="'+esc(String(shown))+'" '
        +'onchange="pmEdit(\\''+esc(i.tag)+'\\',\\''+esc(p.name)+'\\',this.value,\\''+esc(String(v))+'\\')"></td>';
    });
    rows+='</tr>';
  });
  document.getElementById('pmGrid').innerHTML='<table class="pm-grid">'+head+'<tbody>'+rows+'</tbody></table>';
}
function pmEdit(tag,param,val,orig){
  PM.edits[tag]=PM.edits[tag]||{};
  if(String(val)===String(orig)) delete PM.edits[tag][param]; else PM.edits[tag][param]=val;
  if(!Object.keys(PM.edits[tag]).length) delete PM.edits[tag];
  pmRenderGrid(); pmRenderFoot();
}
function pmDirtyCount(){ var n=0; for(var t in PM.edits) n+=Object.keys(PM.edits[t]).length; return n; }
function pmRenderFoot(){
  var n=pmDirtyCount();
  document.getElementById('pmFoot').innerHTML='<div class="pm-foot">'
    +(n?'<span class="pm-dirty">'+n+' cell'+(n!==1?'s':'')+' edited</span><button class="pm-btn" onclick="pmReset()">Reset</button>':'<span>No edits</span>')
    +'<span style="margin-left:auto"></span>'
    +'<span>Minimal-diff FHX \\u2014 only changed values rewritten</span>'
    +'<button class="pm-btn primary" '+(n?'':'disabled')+' onclick="pmExportFHX()">Export FHX for DeltaV</button></div>';
}
function pmSetGroup(g){ PM.group=g; pmRender(); }
function pmSetFilter(v){ PM.filter=v; pmRenderGrid(); }
function pmSetVary(b){ PM.onlyVary=b; pmRenderGrid(); }
function pmReset(){ PM.edits={}; pmRenderGrid(); pmRenderFoot(); }
function pmExportXlsx(){
  window.location.href='/param_matrix_xlsx?t='+encodeURIComponent(EXPORT_TOKEN)+'&cls='+encodeURIComponent(PM.cls);
}
function pmExportFHX(){
  if(!pmDirtyCount()) return;
  var foot=document.getElementById('pmFoot');
  fetch('/param_matrix_apply',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token:EXPORT_TOKEN,edits:PM.edits})})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.error){ alert(d.error); return; }
      var tok=d.token||d.download_token||'';
      // trigger download of the minimal-diff FHX
      window.location.href='/param_matrix_download?t='+encodeURIComponent(tok)+'&name='+encodeURIComponent(PM.cls);
      // brief confirmation of what changed
      if(foot){ var na=(typeof d.applied==='number')?d.applied:((d.applied||[]).length);
        foot.innerHTML='<div class="pm-foot"><span class="pm-dirty">\\u2713 '+na
        +' value'+(na!==1?'s':'')+' written \\u00b7 '+(d.diff_lines||0)+' diff lines</span>'
        +(d.skipped&&d.skipped.length?'<span style="color:var(--vary)"> \\u00b7 '+d.skipped.length+' skipped</span>':'')
        +'<span style="margin-left:auto"></span><button class="pm-btn" onclick="pmRenderFoot()">Back</button></div>'; }
    })
    .catch(function(e){ alert(e.message); });
}
function rsPlay(){ RS.playing=true; rsTick(); }
function rsStop(){ RS.playing=false; if(RS.timer){ clearTimeout(RS.timer); RS.timer=null; } }
function rsToggle(){ if(RS.playing){ rsStop(); rsRenderFrame(); } else { if(RS.cur>=RS.trace.length-1) RS.cur=0; rsPlay(); } }
function rsTick(){
  if(!RS.playing) return;
  rsRenderFrame();
  if(RS.cur>=RS.trace.length-1){ RS.playing=false; rsRenderFrame(); return; }
  RS.timer=setTimeout(function(){ RS.cur++; rsTick(); }, Math.max(60, 260/RS.speed));
}
function rsSeek(v){ rsStop(); RS.cur=parseInt(v,10)||0; rsRenderFrame(); }
function rsCycleSpeed(){ var s=[1,2,4,8]; RS.speed=s[(s.indexOf(RS.speed)+1)%s.length]; rsRenderFrame(); }
function stuTab(el,t){
  var sp=el.closest('.stu-side-panel');
  sp.querySelectorAll('.stu-tab').forEach(function(x){x.classList.toggle('on',x===el);});
  sp.querySelectorAll('.stu-tabpanel').forEach(function(p){p.classList.toggle('on',p.getAttribute('data-t')===t);});
}
function stuToggleSide(){
  var shell=document.querySelector('.stu-shell'); if(shell) shell.classList.toggle('side-hidden');
}
// dockable side panel: right (default) or bottom
function stuDock(where){
  STU.dock=where;
  var body=document.querySelector('#stuMain .stu-body'); if(!body) return;
  body.classList.remove('stu-dock-right','stu-dock-bottom','stu-dock-left');
  body.classList.add('stu-dock-'+where);
  body.style.gridTemplateColumns=''; body.style.gridTemplateRows=''; // reset any manual resize
}
// draggable splitter between diagram and side panel
function stuWireSplit(){
  var split=document.getElementById('stuSplit'); if(!split) return;
  var body=split.parentElement;
  split.onmousedown=function(e){
    e.preventDefault();
    var isRight=body.classList.contains('stu-dock-right');
    var isLeft=body.classList.contains('stu-dock-left');
    var horiz=isRight||isLeft;
    var rect=body.getBoundingClientRect();
    // The diagram pane is an <iframe>. Once the cursor crosses into it, mouse events go
    // to the iframe's document and the parent stops getting mousemove/mouseup — so the
    // drag freezes over the diagram and only resumes (or a stray click ends it) back on
    // the parent. Disabling pointer-events on all iframes for the duration of the drag
    // keeps every event on the parent, fixing the stuck/one-directional feel (#4).
    var frames=Array.prototype.slice.call(document.querySelectorAll('iframe'));
    frames.forEach(function(f){ f.style.pointerEvents='none'; });
    document.body.style.userSelect='none';
    function mv(ev){
      if(horiz){
        var w=ev.clientX-rect.left; var pct=Math.max(20,Math.min(85,100*w/rect.width));
        body.style.gridTemplateColumns=pct+'% 5px minmax(0,1fr)';
      } else {
        var hh=ev.clientY-rect.top; var pctv=Math.max(20,Math.min(85,100*hh/rect.height));
        body.style.gridTemplateRows=pctv+'% 5px minmax(0,1fr)';
      }
    }
    function up(){
      document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up);
      frames.forEach(function(f){ f.style.pointerEvents=''; });
      document.body.style.userSelect='';
    }
    document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
  };
}
// ── standalone Recipes workspace (rail view) ──
// RECWS holds the workspace's data source: by default the Explorer import, replaced
// wholesale when a recipe FHX is imported directly here (Explorer untouched).
var RECWS={token:(typeof EXPORT_TOKEN!=='undefined'?EXPORT_TOKEN:''),
           views:(typeof RECIPE_VIEWS!=='undefined'?RECIPE_VIEWS:{}),
           stepViews:(typeof RECIPE_STEP_VIEWS!=='undefined'?RECIPE_STEP_VIEWS:{})};
var _REC_BADGE='<span class="ic-badge ic-recipe"><svg viewBox="0 0 15 15" width="15" height="15" aria-hidden="true"><path d="M4 2.4h4.6l2.6 2.6v7.6h-7.2z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/><path d="M8.4 2.4v2.8h2.8M5.5 8h6M5.5 10h3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/></svg></span>';
// ─── Formula Studio ─────────────────────────────────────────────────────────
// Bulk-edit recipe formula values in a grid, compare two formulas (a diff DeltaV
// doesn't make easy), and export a minimal-diff, DeltaV-ready FHX for re-import.
var FS={token:'',grid:null,recipe:'',edits:{},tab:'edit'};
function fsOpen(){
  var tok=(typeof RECWS!=='undefined' && RECWS.token) ? RECWS.token
         : (typeof EXPORT_TOKEN!=='undefined'?EXPORT_TOKEN:'');
  if(!tok){ alert('Import a recipe first.'); return; }
  FS.token=tok; FS.edits={};
  var ov=document.getElementById('fsOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='fsOverlay'; ov.className='fs-ov'; document.body.appendChild(ov); }
  ov.innerHTML='<div class="fs-card"><div class="fs-head"><h2>\\u2317 Formula Studio</h2>'
    +'<span class="fs-sub" id="fsSub"></span><span class="x" onclick="fsClose()">\\u00d7</span></div>'
    +'<div class="fs-tabs"><button class="fs-tab on" id="fsTabEdit" onclick="fsSetTab(\\'edit\\')">Bulk edit</button>'
    +'<button class="fs-tab" id="fsTabDiff" onclick="fsSetTab(\\'diff\\')">Compare</button>'
    +'<span class="fs-tabsp"></span>'
    +'<span class="fs-dirty" id="fsDirty"></span>'
    +'<button class="fs-btn" onclick="fsReset()">Reset</button>'
    +'<button class="fs-btn primary" id="fsExport" onclick="fsExport()">Export FHX for DeltaV</button></div>'
    +'<div class="fs-body" id="fsBody">'+dvLoader('Loading formulas\\u2026')+'</div></div>';
  fetch('/formula_grid?t='+encodeURIComponent(FS.token)).then(function(r){return r.json();})
    .then(function(d){
      if(d.error){ document.getElementById('fsBody').innerHTML='<div class="fs-empty">'+esc(d.error)+'</div>'; return; }
      FS.grid=d.grid||{};
      var recs=Object.keys(FS.grid);
      if(!recs.length){ document.getElementById('fsBody').innerHTML='<div class="fs-empty">No formulas in this recipe export.</div>'; return; }
      FS.recipe=recs[0];
      document.getElementById('fsSub').textContent=FS.recipe;
      fsRenderEdit();
    })
    .catch(function(e){ document.getElementById('fsBody').innerHTML='<div class="fs-empty">'+esc(e.message)+'</div>'; });
}
function fsClose(){ var o=document.getElementById('fsOverlay'); if(o) o.remove(); }
function fsSetTab(t){
  FS.tab=t;
  document.getElementById('fsTabEdit').classList.toggle('on',t==='edit');
  document.getElementById('fsTabDiff').classList.toggle('on',t==='diff');
  if(t==='edit') fsRenderEdit(); else fsRenderDiff();
}
function fsGr(){ return FS.grid[FS.recipe]||{params:[],formulas:[],values:{}}; }
function fsCellVal(param, formula){
  if(FS.edits[formula] && FS.edits[formula][param]!==undefined) return FS.edits[formula][param];
  var v=(fsGr().values[param]||{})[formula];
  return v===undefined?'':v;
}
function fsIsEdited(param, formula){
  return !!(FS.edits[formula] && FS.edits[formula][param]!==undefined
    && String(FS.edits[formula][param])!==String((fsGr().values[param]||{})[formula]||''));
}
function fsRenderEdit(){
  var gr=fsGr();
  var recSel = Object.keys(FS.grid).length>1
    ? '<div class="fs-recpick"><label>Recipe</label><select onchange="FS.recipe=this.value;FS.edits={};document.getElementById(\\'fsSub\\').textContent=this.value;fsRenderEdit();">'
      + Object.keys(FS.grid).map(function(r){return '<option'+(r===FS.recipe?' selected':'')+'>'+esc(r)+'</option>';}).join('')+'</select></div>'
    : '';
  var head='<tr><th class="fs-pcol">Parameter</th><th class="fs-gcol">Group</th>'
    + gr.formulas.map(function(f){return '<th class="fs-fcol'+(gr.released[f]?' rel':'')+'" title="'+(gr.released[f]?'released':'not released')+'">'+esc(f)+'</th>';}).join('')+'</tr>';
  // only rows that are formula parameters (appear in at least one formula) OR all params
  var rows=gr.params.filter(function(p){ return gr.values[p.name]!==undefined || true; }).map(function(p){
    var cells=gr.formulas.map(function(f){
      var val=fsCellVal(p.name,f);
      var ed=fsIsEdited(p.name,f);
      return '<td class="fs-cell'+(ed?' edited':'')+'"><input value="'+esc(String(val))+'" '
        +'oninput="fsEdit(\\''+esc(p.name).replace(/'/g,"&#39;")+'\\',\\''+esc(f).replace(/'/g,"&#39;")+'\\',this.value)"></td>';
    }).join('');
    return '<tr><td class="fs-pcol" title="'+esc(p.desc||'')+'">'+esc(p.name)+'</td><td class="fs-gcol">'+esc(p.group||'')+'</td>'+cells+'</tr>';
  }).join('');
  document.getElementById('fsBody').innerHTML=recSel
    +'<div class="fs-gridwrap"><table class="fs-grid"><thead>'+head+'</thead><tbody>'+rows+'</tbody></table></div>'
    +'<div class="fs-note">Edit any cell to override a formula value. Only changed cells are written; everything else stays byte-identical. Export produces a DeltaV-ready FHX with just the formula value changes.</div>';
  fsUpdateDirty();
}
function fsEdit(param, formula, val){
  FS.edits[formula]=FS.edits[formula]||{};
  var orig=(fsGr().values[param]||{})[formula];
  if(String(val)===String(orig===undefined?'':orig)){ delete FS.edits[formula][param]; if(!Object.keys(FS.edits[formula]).length) delete FS.edits[formula]; }
  else FS.edits[formula][param]=val;
  fsUpdateDirty();
  // toggle cell highlight without full re-render
  fsMarkCells();
}
function fsMarkCells(){
  var inputs=document.querySelectorAll('#fsBody .fs-cell input');
  // lightweight: re-render just marks; simplest is to re-render edit table
}
function fsUpdateDirty(){
  var n=0; Object.keys(FS.edits).forEach(function(f){ n+=Object.keys(FS.edits[f]).length; });
  var d=document.getElementById('fsDirty'); if(d) d.textContent = n? (n+' change'+(n!==1?'s':'')) : '';
  var ex=document.getElementById('fsExport'); if(ex) ex.disabled = (n===0);
}
function fsReset(){ FS.edits={}; if(FS.tab==='edit') fsRenderEdit(); else fsRenderDiff(); }
function fsRenderDiff(){
  var gr=fsGr();
  if(gr.formulas.length<2){ document.getElementById('fsBody').innerHTML='<div class="fs-empty">Need at least two formulas to compare.</div>'; return; }
  if(!FS.diffA) FS.diffA=gr.formulas[0];
  if(!FS.diffB) FS.diffB=gr.formulas[1];
  var opts=function(sel){return gr.formulas.map(function(f){return '<option'+(f===sel?' selected':'')+'>'+esc(f)+'</option>';}).join('');};
  var picker='<div class="fs-diffpick"><label>A</label><select id="fsDiffA" onchange="FS.diffA=this.value;fsLoadDiff();">'+opts(FS.diffA)+'</select>'
    +'<span class="fs-vs">vs</span><label>B</label><select id="fsDiffB" onchange="FS.diffB=this.value;fsLoadDiff();">'+opts(FS.diffB)+'</select></div>';
  document.getElementById('fsBody').innerHTML=picker+'<div id="fsDiffBody">'+dvLoader('Comparing\\u2026')+'</div>';
  fsLoadDiff();
}
function fsLoadDiff(){
  var url='/formula_diff?t='+encodeURIComponent(FS.token)+'&recipe='+encodeURIComponent(FS.recipe)
    +'&a='+encodeURIComponent(FS.diffA)+'&b='+encodeURIComponent(FS.diffB);
  fetch(url).then(function(r){return r.json();}).then(function(d){
    var b=document.getElementById('fsDiffBody'); if(!b) return;
    if(d.error){ b.innerHTML='<div class="fs-empty">'+esc(d.error)+'</div>'; return; }
    var rows=d.rows||[];
    var counts={changed:0,only_a:0,only_b:0,same:0};
    rows.forEach(function(r){counts[r.status]=(counts[r.status]||0)+1;});
    var summary='<div class="fs-diffsum">'
      +'<span class="fs-chip changed">'+counts.changed+' changed</span>'
      +'<span class="fs-chip only_a">'+counts.only_a+' only in A</span>'
      +'<span class="fs-chip only_b">'+counts.only_b+' only in B</span>'
      +'<span class="fs-chip same">'+counts.same+' same</span>'
      +'<label class="fs-hidesame"><input type="checkbox" id="fsHideSame" checked onchange="fsLoadDiff()"> hide identical</label></div>';
    var hide=(document.getElementById('fsHideSame')||{}).checked; if(hide===undefined) hide=true;
    var trs=rows.filter(function(r){return !(hide && r.status==='same');}).map(function(r){
      return '<tr class="fs-drow '+r.status+'"><td class="fs-pcol">'+esc(r.param)+'</td>'
        +'<td class="fs-gcol">'+esc(r.group||'')+'</td>'
        +'<td class="fs-dv">'+esc(String(r.a))+'</td><td class="fs-dv">'+esc(String(r.b))+'</td>'
        +'<td class="fs-dstat"><span class="fs-sbadge '+r.status+'">'+({changed:'changed',only_a:'A only',only_b:'B only',same:'same'}[r.status])+'</span></td></tr>';
    }).join('');
    b.innerHTML=summary+'<div class="fs-gridwrap"><table class="fs-grid fs-difftable"><thead><tr>'
      +'<th class="fs-pcol">Parameter</th><th class="fs-gcol">Group</th>'
      +'<th>'+esc(FS.diffA)+'</th><th>'+esc(FS.diffB)+'</th><th></th></tr></thead><tbody>'+trs+'</tbody></table></div>'
      +'<div class="fs-note">Copy a value from one formula to the other by editing in the Bulk edit tab. This side-by-side compare isn\\'t available in native DeltaV.</div>';
  }).catch(function(e){ var b=document.getElementById('fsDiffBody'); if(b) b.innerHTML='<div class="fs-empty">'+esc(e.message)+'</div>'; });
}
function fsExport(){
  var n=0; Object.keys(FS.edits).forEach(function(f){ n+=Object.keys(FS.edits[f]).length; });
  if(!n){ return; }
  var ex=document.getElementById('fsExport'); if(ex){ ex.disabled=true; ex.textContent='Exporting\\u2026'; }
  fetch('/formula_bulk_apply',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token:FS.token,recipe:FS.recipe,edits:FS.edits})})
    .then(function(r){return r.json();}).then(function(d){
      if(ex){ ex.disabled=false; ex.textContent='Export FHX for DeltaV'; }
      if(d.error){ alert(d.error); return; }
      // download via the existing formula download route
      var url='/recipe_formula_download?t='+encodeURIComponent(d.token)+'&name='+encodeURIComponent(FS.recipe);
      window.location.href=url;
      var dd=document.getElementById('fsDirty'); if(dd) dd.textContent=d.applied+' applied \\u00b7 '+d.diff_lines+' FHX lines changed';
    })
    .catch(function(e){ if(ex){ex.disabled=false;ex.textContent='Export FHX for DeltaV';} alert(e.message); });
}
function recImportFile(inp){
  if(!inp.files||!inp.files.length) return;
  var file=inp.files[0];
  inp.value='';
  // #4: per-import prompt — Replace the workspace, or Merge with what's already here.
  // Either choice can also push into the Explorer session.
  var hasExisting = RECWS.views && Object.keys(RECWS.views).length>0;
  var ov=document.getElementById('recImpOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='recImpOverlay'; ov.className='ip-pop-overlay'; document.body.appendChild(ov); }
  ov.innerHTML=''
    +'<div class="ip-pop rec-imp-pop">'
    +'<div class="ip-pop-h">Import '+esc(file.name)
    +'<span class="ip-pop-x" onclick="var o=document.getElementById(\\'recImpOverlay\\');if(o)o.remove();">\\u00d7</span></div>'
    +'<div class="rec-imp-body">'
    +(hasExisting
       ?'<p class="rec-imp-q">You already have recipes loaded in the workspace. How should this file be brought in?</p>'
        +'<label class="rec-imp-choice"><input type="radio" name="recImpMode" value="merge" checked>'
        +'<span><b>Merge</b><small>keep the current recipes and add the ones from this file</small></span></label>'
        +'<label class="rec-imp-choice"><input type="radio" name="recImpMode" value="replace">'
        +'<span><b>Replace</b><small>clear the workspace and show only this file</small></span></label>'
       :'<p class="rec-imp-q">Import this recipe file into the workspace.</p>'
        +'<input type="hidden" id="recImpModeSolo" value="replace">')
    +'<label class="rec-imp-exp"><input type="checkbox" id="recImpToExplorer" checked> '
    +'also add to the Explorer session</label>'
    +'</div>'
    +'<div class="ip-pop-foot">'
    +'<button class="exp-btn" onclick="var o=document.getElementById(\\'recImpOverlay\\');if(o)o.remove();">Cancel</button>'
    +'<button class="exp-btn primary" id="recImpGo">Import</button>'
    +'</div></div>';
  document.getElementById('recImpGo').onclick=function(){
    var mode='replace';
    var r=document.querySelector('input[name=recImpMode]:checked');
    if(r) mode=r.value;
    var toExp=(document.getElementById('recImpToExplorer')||{}).checked;
    ov.remove();
    recDoImport(file, mode, toExp);
  };
}
function recDoImport(file, mode, toExplorer){
  var src=document.getElementById('recSrc');
  src.innerHTML='<span class="dv-dots"><i></i><i></i><i></i></span> Importing '+esc(file.name)+'\u2026';
  var fd=new FormData();
  fd.append('file', file);
  fd.append('mode', mode);
  fd.append('token', RECWS.token||'');
  fetch('/recipe_import',{method:'POST',body:fd})
    .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
    .then(function(res){
      if(!res.ok||res.j.error){ src.innerHTML='<span style="color:#dc2626">'+esc(res.j.error||'Import failed')+'</span>'; return; }
      RECWS={token:res.j.token, views:res.j.views||{}, stepViews:res.j.step_views||{}, phases:res.j.phases||[]};
      recBuildList(res.j.tree||[]);
      var first=(res.j.tree[0]&&res.j.tree[0].items[0])?res.j.tree[0].items[0].name:'';
      if(first) recShow(first);
      if(toExplorer){
        src.innerHTML='Imported'+esc((res.j.name||'').indexOf('merged')>=0?' & merged':'')+'. Adding to the Explorer\u2026';
        recMergeIntoExplorer(file, res.j.name||file.name, src);
      } else {
        src.textContent='Showing recipes from '+res.j.name+' (workspace only \u2014 Explorer untouched).';
      }
    })
    .catch(function(e){ src.innerHTML='<span style="color:#dc2626">Import error: '+esc(e.message)+'</span>'; });
}
// Merge the ENTIRE recipe workspace into the Explorer session. Uses /append with the
// workspace's own stash token as the add-content (add_token) so ALL imported recipes go
// across, not just the most recent file (#4). The single file is still sent as a base
// fallback in case a host restart evicted the stash.
function recMergeIntoExplorer(file, label, src){
  var fd=new FormData();
  fd.append('token', (typeof EXPORT_TOKEN!=='undefined'?EXPORT_TOKEN:''));
  fd.append('mode', 'skip');
  fd.append('add_token', RECWS.token||'');   // the whole workspace (all recipes)
  fd.append('name', label||'recipes');
  if(file){ fd.append('file', file); fd.append('base', file); }  // fallbacks only
  fetch('/append',{method:'POST',body:fd})
    .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
    .then(function(res){
      if(res.ok && res.j && res.j.token){
        src.innerHTML='Imported and merged into the Explorer. '
          +'<a class="link" href="/explore_stashed?t='+encodeURIComponent(res.j.token)
          +'&name='+encodeURIComponent(label)+'">open in Explorer \u2192</a>';
        // update the live Explorer token so subsequent workspace exports stay in sync
        try{ EXPORT_TOKEN=res.j.token; RECWS.token=res.j.token; }catch(e){}
      } else {
        src.innerHTML='Imported to the workspace. (Could not merge into the Explorer: '
          +esc((res.j&&res.j.error)||'unknown')+')';
      }
    })
    .catch(function(e){ src.innerHTML='Imported to the workspace. (Explorer merge failed: '+esc(e.message)+')'; });
}
function recBuildList(tree){
  var h='';
  tree.forEach(function(cat){
    h+='<div class="rec-cat">'+esc(cat.cat)+' ('+cat.items.length+')</div>';
    cat.items.forEach(function(it){
      var kids=it.children||[];
      var bases={}; kids.forEach(function(k){ bases[k.name]=bases[k.name]||k.loaded; });
      var nb=Object.keys(bases).length, nl=0; for(var b in bases){ if(bases[b]) nl++; }
      var sub=nb?(' <span class="inst-cls">('+nl+'/'+nb+' children imported)</span>'):'';
      if(kids.length){
        // #3: collapsible parent — a caret toggles the children group (like the
        // Explorer tree). The recipe name itself still opens on click.
        h+='<div class="navgroup">';
        h+='<div class="navitem rec-item rec-parent" data-rec="'+esc(it.name)+'">'
          +'<span class="tog" onclick="recTog(this,event)">\\u25b8</span>'
          +'<span class="rec-open" onclick="recShow(\\''+jsq(it.name)+'\\')">'+_REC_BADGE+esc(it.name)+sub+'</span></div>';
        h+='<div class="navchildren" style="display:none">';
        kids.forEach(function(k){
          if(k.loaded){
            h+='<div class="navitem navchild rec-item" data-rec="'+esc(k.name)+'" onclick="recShow(\\''+jsq(k.name)+'\\',{fromChildEl:this})">'+_REC_BADGE+esc(k.step)+' <span class="inst-cls">('+esc(k.layer)+')</span></div>';
          } else if(k.has_params){
            h+='<div class="navitem navchild navghost rec-item" onclick="recShowStep(\\''+jsq(it.name)+'\\',\\''+jsq(k.step)+'\\',\\''+jsq(k.layer)+'\\')">'+_REC_BADGE+esc(k.step)+' <span class="inst-cls">('+esc(k.layer)+')</span></div>';
          }
        });
        h+='</div></div>';
      } else {
        h+='<div class="navitem rec-item" data-rec="'+esc(it.name)+'" onclick="recShow(\\''+jsq(it.name)+'\\')">'+_REC_BADGE+esc(it.name)+sub+'</div>';
      }
    });
  });
  document.getElementById('recListBody').innerHTML=h||'<div class="rec-empty">No recipe objects found.</div>';
}
// toggle a recipe workspace group open/closed without triggering the recipe open
function recTog(el,ev){
  if(ev){ ev.stopPropagation(); }
  var grp=el.closest('.navgroup'); if(!grp) return;
  var kids=grp.querySelector('.navchildren'); if(!kids) return;
  var open=kids.style.display==='none';
  kids.style.display=open?'':'none';
  el.textContent=open?'\\u25be':'\\u25b8';
}
function recShow(name, opts){
  var d=document.getElementById('rdetail'); if(!d) return;
  // #6: a recipe object can appear twice in the tree — nested under its parent (as a
  // child) AND standalone in its category section. Highlight only ONE. When we arrive
  // via a drill-down from a parent (opts.fromChildEl given), select that nested row;
  // otherwise prefer the standalone (top-level) row.
  opts = opts || {};
  document.querySelectorAll('.rec-item.sel').forEach(function(n){ n.classList.remove('sel'); });
  var matches = Array.prototype.slice.call(document.querySelectorAll('.rec-item[data-rec="'+cssEsc(name)+'"]'));
  var pick=null;
  if(opts.fromChildEl && matches.indexOf(opts.fromChildEl)>=0){
    pick=opts.fromChildEl;
  } else {
    // prefer a NON-child (standalone) row; fall back to the first match
    for(var i=0;i<matches.length;i++){ if(!matches[i].classList.contains('navchild') && !matches[i].classList.contains('rec-parent')){ pick=matches[i]; break; } }
    if(!pick){ for(var j=0;j<matches.length;j++){ if(!matches[j].classList.contains('navchild')){ pick=matches[j]; break; } } }
    if(!pick) pick=matches[0];
  }
  if(pick) pick.classList.add('sel');
  var v=RECWS.views[name]||'';
  var o=(typeof DB!=='undefined'&&DB.objs['recipe:'+name])||{};
  var h='<h2 class="dt">'+esc(name)+' <span class="dt-type b-recipe">Recipe</span>'
    +' <button class="pfc-diagram-btn" onclick="recViewPfc(\\''+esc(name)+'\\')" title="Open the interactive PFC diagram">\u2317 PFC diagram</button>'
    +'<span class="rec-dl-group">'
    +'<a class="link rec-xl" href="javascript:void 0" onclick="recDownloadWord(\\''+esc(name)+'\\')" title="Formal DDS-style Word recipe document">\u2b07 Recipe doc (.docx)</a>'
    +'<a class="link rec-xl" href="javascript:void 0" onclick="recDownloadExcel(\\''+esc(name)+'\\')" title="Excel workbook: overview, procedure, parameters, formulas">\u2b07 Workbook (.xlsx)</a>'
    +'<a class="link rec-xl" href="javascript:void 0" onclick="recDownloadPfc(\\''+esc(name)+'\\')" title="Structured report: overview, parameters, procedure walk, and the deferral audit">\u2b07 PFC report (.xlsx)</a>'
    +'</span></h2>';
  if(o.description) h+='<p class="dt-desc">'+esc(o.description)+'</p>';
  h+=v||'<div class="card"><span class="empty">No detail parsed for this recipe.</span></div>';
  d.innerHTML=h; d.scrollTop=0;
}
function recShowStep(parent, step, layer){
  var d=document.getElementById('rdetail'); if(!d) return;
  document.querySelectorAll('.rec-item.sel').forEach(function(n){n.classList.remove('sel');});
  var v=RECWS.stepViews[parent+'||'+step]||'';
  var h='<h2 class="dt">'+esc(step)+' <span class="dt-type b-recipe">'+esc(layer||'recipe step')+'</span></h2>';
  h+='<p class="dt-desc">Instance under '+esc(parent)+' \u2014 parameters derived from the parent step.</p>';
  // #7: an OP's children are phases. If this step is a phase that exists in the stash,
  // render its SFC diagram above the deferral/parameter detail.
  var base=(step||'').replace(/:\\d+$/,'');
  var isPhase=(layer||'').toLowerCase().indexOf('phase')>=0
    || (RECWS.phases && RECWS.phases.indexOf(base)>=0);
  var phaseExists=RECWS.phases && RECWS.phases.indexOf(base)>=0;
  if(isPhase && phaseExists && RECWS.token){
    h+='<div class="card" style="max-width:none"><h3>Phase SFC \u2014 '+esc(base)+'</h3>'
      +'<div class="frame-wrap"><div class="frame-load" id="recPhaseLoad"><span class="dv-dots"><i></i><i></i><i></i></span> Loading phase logic\u2026</div>'
      +'<iframe class="phaseframe" src="/phase_view?t='+encodeURIComponent(RECWS.token)+'&p='+encodeURIComponent(base)
      +'" onload="var l=document.getElementById(\\'recPhaseLoad\\');if(l)l.style.display=\\'none\\';"></iframe></div></div>';
  } else if(isPhase && !phaseExists){
    h+='<div class="card"><span class="empty">This phase\\u2019s SFC isn\\u2019t in the current import. '
      +'Import the phase (or the unit that defines it) to see its diagram here.</span></div>';
  }
  h+=v||'<div class="card"><span class="empty">No parameters found on this step.</span></div>';
  d.innerHTML=h; d.scrollTop=0; try{makeCardsCollapsible();}catch(e){}
}
function recDownloadPfc(name){
  if(!RECWS.token) return;
  window.location.href='/recipe_pfc_xlsx?t='+encodeURIComponent(RECWS.token)+'&n='+encodeURIComponent(name);
}
function recDownloadWord(name){
  if(!RECWS.token) return;
  window.location.href='/recipe_word?t='+encodeURIComponent(RECWS.token)+'&n='+encodeURIComponent(name);
}
function recDownloadExcel(name){
  if(!RECWS.token) return;
  window.location.href='/recipe_excel?t='+encodeURIComponent(RECWS.token)+'&n='+encodeURIComponent(name);
}
// #7: open the recipe's PFC (procedure flow) diagram in a large standalone overlay,
// away from the cramped detail pane — a dedicated visual view with pan/zoom.
function recViewPfc(name){
  var v=RECWS.views[name]||'';
  // pull just the PFC diagram wrapper out of the recipe view
  var tmp=document.createElement('div'); tmp.innerHTML=v;
  var wrap=tmp.querySelector('.pfc-wrap');
  var ov=document.getElementById('pfcOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='pfcOverlay'; ov.className='pfc-overlay'; document.body.appendChild(ov); }
  ov.onclick=function(e){ if(e.target===ov) ov.remove(); };
  var panelId='pfcOvPanel';
  if(wrap){
    // point the diagram's click handlers at our popup panel (they look up
    // data-pfc-panel first, then fall back to a .pfc-panel sibling — we set both).
    wrap.setAttribute('data-pfc-panel', panelId);
  }
  var diagram = wrap ? wrap.outerHTML
    : '<div class="pfc-ov-empty">This recipe has no procedure-flow diagram (it may be an operation or a phase-level object).</div>';
  // #3: step-detail card on the RIGHT, resizable via a drag bar. #2: it's a permanent
  // pane in the popup (never a collapsible section), so it can't get stuck closed.
  var bodyHtml=''
    +'<div class="pfc-ov-split">'
    +  '<div class="pfc-ov-diagram">'+diagram+'</div>'
    +  '<div class="pfc-ov-divider" id="pfcOvDivider" title="Drag to resize"></div>'
    +  '<div class="pfc-panel pfc-ov-panel" id="'+panelId+'">'
    +    '<div class="pfc-hint">Click a step or transition in the diagram to see its details here.</div>'
    +  '</div>'
    +'</div>';
  ov.innerHTML='<div class="pfc-ov-card"><div class="pfc-ov-h">'
    +'<b>\\u2317 '+esc(name)+' \\u2014 Procedure Flow Chart</b>'
    +'<span class="pfc-ov-hint">drag to pan \\u00b7 scroll to zoom</span>'
    +'<span style="flex:1"></span>'
    +'<button class="exp-btn" onclick="recDownloadPfc(\\''+esc(name).replace(/'/g,"\\\\'")+'\\')">\\u2b07 PFC report (.xlsx)</button>'
    +'<button class="pfc-ov-x" onclick="var o=document.getElementById(\\'pfcOverlay\\');if(o)o.remove();">\\u00d7</button>'
    +'</div><div class="pfc-ov-body">'+bodyHtml+'</div></div>';
  // wire the resize bar (drag left/right to size the detail panel)
  pfcWireDivider();
  // re-enable pan/zoom on the cloned wrap (the delegated handlers work on any .pfc-wrap)
}
// #3: drag the divider to resize the PFC popup's right-hand detail panel.
function pfcWireDivider(){
  var d=document.getElementById('pfcOvDivider'); if(!d) return;
  var split=d.parentElement, panel=document.getElementById('pfcOvPanel');
  d.onmousedown=function(e){
    e.preventDefault();
    var rect=split.getBoundingClientRect();
    function mv(ev){
      var w=rect.right-ev.clientX;                 // width of the right panel
      w=Math.max(220,Math.min(rect.width-260,w));  // clamp: keep both sides usable
      panel.style.flex='0 0 '+w+'px';
    }
    function up(){ document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up); document.body.style.userSelect=''; }
    document.body.style.userSelect='none';
    document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
  };
}
function downloadAllDeferrals(){
  if(!RECWS.token) return;
  window.location.href='/recipe_deferrals_all_xlsx?t='+encodeURIComponent(RECWS.token);
}
function renderObj(id){
  const o=DB.objs[id]; if(!o)return;
  document.querySelectorAll('.navitem').forEach(n=>n.classList.toggle('sel',n.dataset.id===id));
  // For phases (which have a big interactive diagram), collapse the metadata into a
  // compact disclosure so the diagram sits near the top. Other objects keep the
  // full header inline.
  var isPhase = (o._type==='Phase Class');
  let h='<h2 class="dt">'+esc(o.name)+' <span class="dt-type '+badge(o._type)+'">'+o._type+'</span></h2>';
  var meta='';
  if(o.description) meta+='<p class="dt-desc">'+esc(o.description)+'</p>';
  meta+='<div class="kv">';
  if(o.category) meta+='<div class="k">Category</div><div>'+esc(o.category)+'</div>';
  if(o.area) meta+='<div class="k">Area</div><div><span class="link" onclick="show(\\'area:'+esc(o.area)+'\\')">'+esc(o.area)+'</span></div>';
  if(o.area_path) meta+='<div class="k">Area path</div><div>'+esc(o.area_path)+'</div>';
  if(o.control_type) meta+='<div class="k">Control type</div><div>'+esc(o.control_type)+'</div>';
  if(o.type && o._type==='Recipe') meta+='<div class="k">Recipe type</div><div>'+esc(o.type)+'</div>';
  meta+='</div>';
  if(isPhase){
    h+='<details class="metabinder"><summary>Details</summary>'+meta+'</details>';
  } else {
    h+=meta;
  }

  // "Used by" — every place this class is referenced as a child module
  // (EM embedding a CM, unit embedding an EM, ...). Grouped by parent.
  if(['CM Class','EM Class','Unit Class','Composite'].includes(o._type)){
    const refs=(DB.used_by&&DB.used_by[o.name])||[];
    if(refs.length){
      const byParent={};
      refs.forEach(r=>{(byParent[r.parent]=byParent[r.parent]||[]).push(r.instance);});
      const parents=Object.keys(byParent).sort();
      h+='<div class="card"><h3>Used by ('+parents.length+(parents.length===1?' object':' objects')+', '+refs.length+' instance'+(refs.length===1?'':'s')+')</h3><div class="dtree">';
      parents.forEach(p=>{
        const pid=(DB.objs['em:'+p]?'em:':DB.objs['cm:'+p]?'cm:':DB.objs['uclass:'+p]?'uclass:':'')+p;
        const plink=DB.objs[pid]?'<span class="link" onclick="show(\\''+pid+'\\')">'+esc(p)+'</span>':esc(p);
        h+='<div class="troot">'+plink+'</div>';
        byParent[p].forEach(inst=>{h+='<div class="tnode"><span style="color:#475569">'+esc(inst)+'</span></div>';});
      });
      h+='</div></div>';
    }
  }

  if(o._type==='Unit Instance'){
    var ui=DB.unit_instances[o.name]||{};
    h+='<div class="card"><h3>Identity</h3><div class="kv">';
    h+='<div class="k">Class</div><div>'+(DB.objs['uclass:'+o.class]?'<span class="link" onclick="show(\\'uclass:'+esc(o.class)+'\\')">'+esc(o.class)+'</span>':esc(o.class||'—'))+'</div>';
    if(ui.area_path) h+='<div class="k">Location</div><div><code>'+esc(ui.area_path)+'</code></div>';
    if(o.description) h+='<div class="k">Description</div><div>'+esc(o.description)+'</div>';
    h+='</div></div>';
    var mods=ui.modules||[];
    if(mods.length){
      h+='<div class="card"><h3>Modules in this unit ('+mods.length+')</h3><table class="fbd-table"><thead><tr><th>Tag</th><th>Class</th><th>Kind</th></tr></thead><tbody>';
      mods.forEach(function(t){var d=DB.deployed_modules[t]||{};var k=DB.objs['em:'+(d.cls||'')]?'EM':'CM';h+='<tr><td><span class="link" onclick="showDeployed(\\''+esc(t)+'\\')">'+esc(t)+'</span></td><td>'+modLink(d.cls||'')+'</td><td>'+k+'</td></tr>';});
      h+='</tbody></table></div>';
    }
    var phs=DB.unit_class_phases[o.class]||[];
    if(phs.length){
      h+='<div class="card"><h3>Phases ('+phs.length+')</h3><div class="chips">';
      phs.forEach(function(p){h+=DB.objs['phase:'+p]?'<span class="chip" onclick="show(\\'phase:'+esc(p)+'\\')">'+esc(p)+'</span>':'<span class="chip">'+esc(p)+'</span>';});
      h+='</div></div>';
    }
    var vals=ui.values||[];
    if(vals.length){
      h+='<div class="card"><h3>Configured values ('+vals.length+')</h3><table class="fbd-table"><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>';
      vals.forEach(function(v){var cv=v.cv;h+='<tr><td>'+esc(v.name)+'</td><td>'+((cv===''||cv==='\"\"')?'<span style="color:#94a3b8">(empty)</span>':'<code>'+esc(cv)+'</code>')+'</td></tr>';});
      h+='</tbody></table></div>';
    }
    var als=ui.aliases||[];
    if(als.length){
      h+=aliasCardHTML(als);
    }
  }
  if(o._type==='Unit Class' && o.instances){
    h+='<div class="card"><h3>Instances ('+o.instances.length+')</h3><div class="chips">';
    if(o.instances.length) o.instances.forEach(n=>{h+='<span class="chip" onclick="show(\\'unit:'+esc(n)+'\\')">'+esc(n)+'</span>';});
    else h+='<span class="empty">No instances in this export</span>';
    h+='</div></div>';
  }
  if(o._type==='Area'){
    var tree=DB.area_tree[o.name];
    if(tree){
      var ncells=Object.keys(tree).filter(function(c){return c;}).length;
      var nunits=0; Object.keys(tree).forEach(function(c){nunits+=tree[c].length;});
      h+='<div class="card"><h3>Contains</h3><div class="dtree"><div class="troot">'+esc(o.name)+' <span style="color:#94a3b8;font-weight:400">· '+(ncells?ncells+' process cell(s) · ':'')+nunits+' unit(s)</span></div>';
      Object.keys(tree).sort().forEach(function(cell){
        if(cell) h+='<div class="tnode" style="font-weight:600">'+esc(cell)+' <span style="color:#94a3b8;font-weight:400">· process cell</span></div>';
        tree[cell].forEach(function(un){
          var ui=DB.unit_instances[un]||{};var nm=(ui.modules||[]).length;
          h+='<div class="tnode'+(cell?' navchild2':'')+'"><span class="link" onclick="show(\\'unit:'+esc(un)+'\\')">'+esc(un)+'</span> <span style="color:#94a3b8">· '+esc(ui.cls||'')+' · '+nm+' module(s)</span></div>';
        });
      });
      h+='</div></div>';
    } else if(o.units){
      h+='<div class="card"><h3>Units ('+o.units.length+')</h3><div class="dtree"><div class="troot">'+esc(o.name)+'</div>';
      o.units.forEach(u=>{h+='<div class="tnode"><span class="link" onclick="show(\\'unit:'+esc(u.name)+'\\')">'+esc(u.name)+'</span> <span style="color:#94a3b8">· '+esc(u.class)+'</span></div>';});
      h+='</div></div>';
    }
  }
  // Unit Class -> its phases and EMs (tree)
  if(o._type==='Unit Class'){
    var ucd=(DB.unit_class_detail&&DB.unit_class_detail[o.name])||{};
    var prm=ucd.params||[], als=ucd.aliases||[];
    if(prm.length){
      h+='<div class="card"><h3>Parameters ('+prm.length+')</h3><table class="fbd-table"><thead><tr><th>Name</th><th>Type</th></tr></thead><tbody>';
      prm.forEach(function(p){h+='<tr><td>'+esc(p.name)+'</td><td><code>'+esc(p.type)+'</code></td></tr>';});
      h+='</tbody></table></div>';
    }
    if(als.length){
      h+='<div class="card"><h3>Aliases ('+als.length+')</h3><table class="fbd-table"><thead><tr><th>Alias</th><th>Description</th><th>Purpose</th></tr></thead><tbody>';
      als.forEach(function(a){h+='<tr><td>'+esc(a.name)+'</td><td class="p">'+esc(a.desc||'')+'</td><td>'+(a.purpose?'<code>'+esc(a.purpose)+'</code>':'')+'</td></tr>';});
      h+='</tbody></table></div>';
    }
    const phs=DB.unit_class_phases[o.name]||DB.unit_phases[o.name]||[], ems=DB.unit_ems[o.name]||[];
    if(phs.length||ems.length){
      h+='<div class="card"><h3>Contains</h3><div class="dtree"><div class="troot">'+esc(o.name)+'</div>';
      ems.forEach(e=>{h+='<div class="tnode"><span class="link" onclick="show(\\'em:'+esc(e)+'\\')">'+esc(e)+'</span> <span style="color:#94a3b8">· EM</span></div>';});
      phs.forEach(p=>{h+='<div class="tnode">'+(DB.objs['phase:'+p]?'<span class="link" onclick="show(\\'phase:'+esc(p)+'\\')">'+esc(p)+'</span>':esc(p))+' <span style="color:#94a3b8">· Phase</span></div>';});
      h+='</div></div>';
    }
  }
  // EM Class -> its CM *instances* (actual object names used inside the EM)
  if(o._type==='EM Class'){
    const iids=(DB.parent_instances&&DB.parent_instances[o.name])||[];
    if(iids.length){
      h+='<div class="card"><h3>Control Modules ('+iids.length+')</h3><table class="fbd-table"><thead><tr><th>Module</th><th>Class</th></tr></thead><tbody>';
      iids.forEach(function(iid){var ins=(DB.instances&&DB.instances[iid])||{};
        h+='<tr><td><span class="link" onclick="showInst(\\''+esc(o.name)+'\\',\\''+esc(ins.tag||'')+'\\')">'+esc(ins.tag||'')+'</span></td><td>'+modLink(ins.cls||'')+'</td></tr>';});
      h+='</tbody></table></div>';
    } else {
      const cms=DB.em_cms[o.name]||[];
      if(cms.length){
        h+='<div class="card"><h3>Control Module classes used ('+cms.length+')</h3><div class="dtree"><div class="troot">'+esc(o.name)+'</div>';
        cms.forEach(c=>{h+='<div class="tnode"><span class="link" onclick="show(\\'cm:'+esc(c)+'\\')">'+esc(c)+'</span></div>';});
        h+='</div></div>';
      }
    }
  }
  // Named Set (DeltaV named set / enumeration) -> entries + where used
  if(o._type==='Named Set'){
    var entries=o.entries||[], used=o.used_by||[];
    h+='<div class="card"><h3>Identity</h3><div class="kv">';
    if(o.description) h+='<div class="k">Description</div><div>'+esc(o.description)+'</div>';
    if(o.category) h+='<div class="k">Category</div><div><code>'+esc(o.category)+'</code></div>';
    h+='<div class="k">Entries</div><div>'+entries.length+'</div></div></div>';
    if(used.length){
      h+='<div class="card"><h3>Used by ('+used.length+')</h3><div class="chips">';
      used.forEach(function(u){h+=DB.objs['em:'+u]?'<span class="chip" onclick="show(\\'em:'+esc(u)+'\\')">'+esc(u)+'</span>':'<span class="chip">'+esc(u)+'</span>';});
      h+='</div></div>';
    }
    if(entries.length){
      h+='<div class="card"><h3>Members ('+entries.length+')</h3><table class="fbd-table"><thead><tr><th>Value</th><th>Name</th></tr></thead><tbody>';
      entries.forEach(function(e){h+='<tr><td><code>'+e.value+'</code></td><td>'+esc(e.name)+'</td></tr>';});
      h+='</tbody></table></div>';
    }
  }
  // placeholder for future leaf views
  if(o._type==='Phase Class'){
    if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN) h+=exportBar('phase:'+o.name, o.name);
    var _hasEager = PHASE_VIEWS[o.name];
    var _hasLazy = (typeof PHASE_NAMES!=='undefined') && PHASE_NAMES.indexOf(o.name)>=0;
    var _hasS88 = (typeof S88_SVG!=='undefined' && S88_SVG);
    // Combined card: State Model and Interactive Logic share one space via tabs,
    // instead of two stacked full-width cards (better use of vertical room).
    h+='<div class="card" style="max-width:none">';
    h+='<div class="emtabs">';
    h+='<button class="emtab on" data-e="logic" onclick="phaseTab(this,\\'logic\\')">Interactive Logic</button>';
    if(_hasS88) h+='<button class="emtab" data-e="state" onclick="phaseTab(this,\\'state\\')">State Model (ISA-88)</button>';
    h+='</div>';

    // ── Interactive Logic panel (default) ──
    h+='<div class="empanel on" data-e="logic" id="phasepanel_logic">';
    if(_hasEager){
      h+='<iframe id="phaseFrame" class="phaseframe" srcdoc="'+PHASE_VIEWS[o.name].replace(/&/g,"&amp;").replace(/"/g,"&quot;")+'"></iframe>';
    } else if(_hasLazy && typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
      var _src='/phase_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&p='+encodeURIComponent(o.name);
      h+='<div class="frame-wrap"><div class="frame-load" id="phaseLoad"><span class="dv-dots"><i></i><i></i><i></i></span> Loading phase logic\\u2026</div>';
      h+='<iframe id="phaseFrame" class="phaseframe" src="'+_src+'" onload="var l=document.getElementById(\\'phaseLoad\\');if(l)l.style.display=\\'none\\';"></iframe></div>';
    } else {
      h+='<span class="empty">No parsed logic available for this phase in this export.</span>';
    }
    h+='</div>';

    // ── State Model panel ──
    if(_hasS88){
      h+='<div class="empanel" data-e="state">';
      h+='<div class="s88wrap"><div class="s88diagram">'+S88_SVG+'</div>'
       + '<div class="s88side"><h4 id="s88h">Procedural state model</h4>'
       + '<p id="s88p">The six <b>acting</b> states (blue) always carry logic — Running, Holding, '
       + 'Restarting, Stopping, Aborting and the fault monitor. A <code>· blank</code> tag means the '
       + 'block holds a blank step with no actions. Outlined states are <b>resting</b> states.</p>'
       + '<p style="color:var(--ink-3);font-size:12px">Click an acting state to open its logic in the interactive tab.</p></div></div>'
       + '<div class="s88legend"><span><i style="background:var(--st-active)"></i>Acting state (logic)</span>'
       + '<span><i style="background:var(--st-quiet);border:1px solid var(--st-quiet-bd)"></i>Resting state</span>'
       + '<span><i style="background:var(--st-warn)"></i>Fault monitor</span>'
       + '<span><i style="background:var(--edge-reset)"></i>Reset path</span></div>';
      h+='</div>';
    }
    h+='</div>';  // end combined card
  }
  // CM Class / Composite -> Function Block Diagram (FHX structure/wiring)
  if(o._type==='CM Class' || o._type==='Composite'){
    if(FBD_VIEWS[o.name]){
      h+='<div class="card" style="max-width:none">'+FBD_VIEWS[o.name]+'</div>';
      setTimeout(function(){wireFbdLinks(); try{makeCardsCollapsible();}catch(e){}}, 0);
    } else if(typeof FBD_NAMES!=='undefined' && FBD_NAMES.indexOf(o.name)>=0 && typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
      h+='<div class="card" style="max-width:none" id="fbdLazy"><h3>Detail</h3><span class="empty">Loading diagram…</span></div>';
      (function(nm){ setTimeout(function(){ lazyFbd(nm); },0); })(o.name);
    } else {
      h+='<div class="card"><h3>Detail</h3><span class="empty">No function block diagram in this export (this object may be an expression/action block or referenced type).</span></div>';
    }
    h+=paramsCard(o.name);
  }
  // EM Class -> full view: Function Blocks + Command/State Logic + Control Modules
  if(o._type==='EM Class'){
    _emCurrent=o.name;
    var stateSet=(DB.em_state_set&&DB.em_state_set[o.name])||'';
    if(stateSet){
      h+='<div class="card"><h3>State Set</h3><div class="kv">'
       + '<div class="k">Named set</div><div>'+(DB.objs['nset:'+stateSet]?'<span class="link" onclick="show(\\'nset:'+esc(stateSet)+'\\')">'+esc(stateSet)+'</span>':esc(stateSet))
       + ' <span style="color:var(--ink-3);font-size:12px">— defines this EM\\'s states</span></div></div></div>';
    }
    const ev=EM_VIEWS[o.name];
    if(ev){
      h+=renderEmPanel(ev, stateSet);
      setTimeout(wireFbdLinks,0);
    } else if(typeof EM_NAMES!=='undefined' && EM_NAMES.indexOf(o.name)>=0 && typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
      h+='<div class="card" style="max-width:none" id="emLazy"><h3>Equipment Module</h3><span class="empty">Loading equipment module…</span></div>';
      (function(nm,ss){ setTimeout(function(){ lazyEm(nm,ss); },0); })(o.name, stateSet);
    } else {
      h+='<div class="card"><h3>Detail</h3><span class="empty">No parsed EM view available in this export.</span></div>';
    }
    h+=paramsCard(o.name);
  }
  if(o._type==='Recipe'){
    if(RECIPE_VIEWS[o.name]){
      h+=RECIPE_VIEWS[o.name];
    } else {
      // fallback: fetch the recipe view on demand (covers cases where the embedded
      // RECIPE_VIEWS map is unavailable, e.g. after certain merge/reload paths).
      h+='<div class="card" id="recipeLazy"><h3>Procedure</h3><div class="dv-loader"><span class="dv-dots"><i></i><i></i><i></i></span> Loading procedure\\u2026</div></div>';
      if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
        (function(nm){ setTimeout(function(){
          fetch('/recipe_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(nm))
            .then(function(r){return r.json();})
            .then(function(x){ var b=document.getElementById('recipeLazy');
              if(b && x && x.html){ b.outerHTML=x.html; try{makeCardsCollapsible();}catch(e){} }
              else if(b){ b.innerHTML='<h3>Procedure</h3><span class="empty">No procedure detail parsed for this recipe.</span>'; } })
            .catch(function(){ var b=document.getElementById('recipeLazy'); if(b) b.innerHTML='<h3>Procedure</h3><span class="empty">Could not load procedure detail.</span>'; });
        },0); })(o.name);
      } else {
        h+='<div class="card"><span class="empty">No procedure detail parsed for this recipe.</span></div>';
      }
    }
  }
  if(o._type==='FB Type'){
    h+='<div class="card"><h3>Standard DeltaV Function Block</h3>';
    if(o.glossary) h+='<p style="margin:0 0 8px">'+esc(o.glossary)+'</p>';
    h+='<div class="kv"><div class="k">DeltaV description</div><div>'+esc(o.description||'—')+'</div>';
    h+='<div class="k">Type code</div><div><code>'+esc(o.name)+'</code></div></div>';
    h+='<p class="empty" style="margin-top:10px">A primitive block type provided by DeltaV (not a user composite). Instances of it appear inside control/equipment module diagrams.</p>';
    h+='</div>';
  }
  document.getElementById('detail').innerHTML=h; try{makeCardsCollapsible();}catch(e){}
}

function toggle(el,e){e.stopPropagation();const ul=el.closest('.navgroup').querySelector('.navchildren');if(ul){ul.style.display=ul.style.display==='none'?'block':'none';el.textContent=ul.style.display==='none'?'▸':'▾';}}
function secToggle(sid,el){const b=document.getElementById(sid);if(!b)return;const open=b.style.display!=='none';b.style.display=open?'none':'block';const a=el.querySelector('.secarrow');if(a)a.textContent=open?'▸':'▾';}

// ── view stack so the back button returns to the previous view ──
let VIEW_STACK=[];
let _emCurrent='';
// #1/#3: open an EM's control-module MEMBER in an instance-style view (diagram +
// role context), matching the richer CM-under-unit view rather than the bare class.
// #6/#7: reusable alias-resolution card (used both inline in the unit view and as
// the standalone "Aliases" child object under a unit).
function aliasCardHTML(als){
  if(!als||!als.length) return '';
  var h='<div class="card"><h3>Alias resolution ('+als.length+') <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 #ALIAS# maps to the module tag used by this unit</span></h3>';
  h+='<input class="alias-filter" id="aliasFilter" placeholder="Filter aliases\\u2026" oninput="filterAliases()">';
  h+='<table class="fbd-table" id="aliasTable"><thead><tr><th>Alias</th><th>Resolves to</th><th>Description</th></tr></thead><tbody>';
  als.forEach(function(a){
    var tgt;
    if(a.value){
      tgt='<span class="link" onclick="showTag(\\''+esc(a.value)+'\\')"><code>'+esc(a.value)+'</code></span>';
    } else if(a.ignore){
      // #2: these aren't truly unresolved — they're flagged IGNORE=T in the export
      // (commissioned-out / not wired), so label them as such rather than "unresolved".
      tgt='<span class="alias-ignored" title="Marked IGNORE=T in the export \\u2014 intentionally not wired">Ignored</span>';
    } else {
      tgt='<span class="alias-unres">(unresolved)</span>';
    }
    h+='<tr'+(a.ignore?' class="alias-row-ign"':'')+'><td><code>#'+esc(a.alias)+'#</code></td><td>'+tgt+'</td><td style="font-size:12px;color:var(--ink-2)">'+esc(a.desc||'')+'</td></tr>';
  });
  h+='</tbody></table></div>';
  return h;
}
function rpFilterGrid(inp){
  var q=(inp.value||'').toLowerCase();
  var scope=inp.closest('.card')||document;
  scope.querySelectorAll('.rp-grid tbody .rp-row').forEach(function(r){ r.style.display = (!q || r.textContent.toLowerCase().indexOf(q)>=0) ? '' : 'none'; });
}
function defFilterGrid(inp){
  var q=(inp.value||'').toLowerCase();
  var scope=inp.closest('.card')||document;
  var chk=scope.querySelector('#defOnlyDeferred')||{};
  var onlyDeferred=chk.checked;
  scope.querySelectorAll('.def-step-card').forEach(function(card){
    var anyVisible=false;
    card.querySelectorAll('.def-prow').forEach(function(row){
      var isDeferred=row.classList.contains('def-prow-deferred');
      var matchesText=!q || row.textContent.toLowerCase().indexOf(q)>=0;
      var matchesFilter=!onlyDeferred || isDeferred;
      var show=matchesText && matchesFilter;
      row.classList.toggle('def-hide', !show);
      if(show) anyVisible=true;
    });
    // a step also matches if its own name/definition text matches, even with no
    // matching param rows (e.g. searching a step name should still show it collapsed)
    var stepText=card.querySelector('h4').textContent.toLowerCase();
    var stepNameMatches=!q || stepText.indexOf(q)>=0;
    var stepHasDeferred=!onlyDeferred || parseInt(card.getAttribute('data-defcount')||'0')>0;
    var show=(anyVisible || (stepNameMatches && !q)) && stepHasDeferred && (anyVisible || stepNameMatches);
    card.classList.toggle('def-hide', !show);
    // auto-expand groups that match a live search so results aren't hidden behind a collapse
    if(q && show){ card.classList.remove('collapsed'); }
  });
}
function defSetAll(expand){
  document.querySelectorAll('.def-step-card').forEach(function(card){
    card.classList.toggle('collapsed', !expand);
  });
}
function downloadDeferrals(recipeName, el){
  // workspace exports use the workspace's own token (a recipe imported directly
  // here has a different stash than the Explorer session)
  var tok=(el && el.closest && el.closest('#rdetail')) ? RECWS.token
          : (typeof EXPORT_TOKEN!=='undefined' ? EXPORT_TOKEN : '');
  if(!tok) return;
  window.location.href='/recipe_deferrals_xlsx?t='+encodeURIComponent(tok)+'&n='+encodeURIComponent(recipeName);
}
// clicking a not-yet-imported child in the recipe tree opens the append dialog with
// a hint of exactly which object to bring in next.
function promptImportChild(name, layer){
  openAppend();
  setTimeout(function(){
    var st=document.getElementById('appendStatus');
    if(st) st.innerHTML='Looking for <b>'+esc(name)+'</b> ('+esc(layer)+') \u2014 choose its FHX export below.';
  },0);
}
// a child instance whose own FHX isn't imported, but whose parameters are derivable
// from the parent step (e.g. CENT_HC_INIT_UP:1 -> CENT1_SELECTED \u2191 G007_SELECTED).
function showRecipeStep(parent, step, layer){ navTo({k:'rstep', parent:parent, step:step, layer:layer||''}); }
function renderRecipeStep(parent, step, layer){
  var d=document.getElementById('detail'); if(!d) return;
  var v=(typeof RECIPE_STEP_VIEWS!=='undefined' && RECIPE_STEP_VIEWS[parent+'||'+step])||'';
  var back=VIEW_STACK.length>1?' <span class="link" onclick="goBack()">\u2190 back</span>':'';
  var base=step.replace(/:\\d+$/,'');
  var h='<h2 class="dt">'+esc(step)+' <span class="dt-type b-recipe">'+esc(layer||'recipe step')+'</span></h2>';
  h+='<p class="dt-desc">Instance under <span class="link" onclick="show(\\'recipe:'+esc(parent)+'\\')">'+esc(parent)+'</span>. '
    +'The object\\'s own FHX isn\\'t imported \u2014 this view is derived from the parent step. '
    +'<span class="link" onclick="promptImportChild(\\''+esc(base)+'\\',\\''+esc(layer)+'\\')">Append its export</span> for full detail.'+back+'</p>';
  h+=v||'<div class="card"><span class="empty">No parameters found on this step.</span></div>';
  d.innerHTML=h; d.scrollTop=0; try{makeCardsCollapsible();}catch(e){}
}
function rpApplyFormula(sel){
  var fvals={}; try{ fvals=JSON.parse(sel.getAttribute('data-fvals')||'{}'); }catch(e){}
  var vals=fvals[sel.value]||{};
  var scope=sel.closest('.card')||document;
  if(scope.querySelector('.rp-grid.rp-editing')){ return; } // don't stomp an active edit
  scope.querySelectorAll('.rp-grid tbody .rp-row').forEach(function(r){
    var pn=r.getAttribute('data-pname'); var cell=r.querySelector('.rp-valcell'); if(!cell) return;
    if(vals[pn]!==undefined){
      cell.innerHTML='<code class="rp-val">'+esc(String(vals[pn]))+'</code>';
    } else {
      var up=r.getAttribute('data-upref');
      cell.innerHTML=up?('<code class="rp-upref">'+esc(up)+'</code> <span class="rp-uparrow">\\u2191 parent</span>'):'<span class="rp-none">\\u2014</span>';
    }
  });
}
// ── editing slice: edit the selected formula's values in place, then export a
// minimal-diff FHX that re-imports into DeltaV (only CV= tokens change). ──
function rpToggleEdit(btn){
  var card=btn.closest('.card'); if(!card) return;
  var grid=card.querySelector('.rp-grid');
  var sel=card.querySelector('#rpFormula');
  if(!grid || !sel) return;
  var editing=grid.classList.toggle('rp-editing');
  if(editing){
    btn.innerHTML='\\u2715 Cancel'; btn.classList.add('rp-editbtn-on');
    // add an Export button next to it
    if(!card.querySelector('.rp-exportbtn')){
      var xb=document.createElement('button'); xb.className='exp-btn rp-exportbtn';
      xb.style.cssText='margin-left:8px;background:var(--accent);color:#fff;border:none';
      xb.innerHTML='\\u2b07 Export edited FHX'; xb.onclick=function(){ rpExportEdited(card); };
      btn.parentNode.insertBefore(xb, btn.nextSibling);
    }
    // turn each formula-value cell into an input holding the current formula value
    var fvals={}; try{ fvals=JSON.parse(sel.getAttribute('data-fvals')||'{}'); }catch(e){}
    var vals=fvals[sel.value]||{};
    grid.querySelectorAll('tbody .rp-row').forEach(function(r){
      var pn=r.getAttribute('data-pname'); var cell=r.querySelector('.rp-valcell'); if(!cell) return;
      // only formula literals are editable (up-refs/deferred values live upstream)
      if(vals[pn]!==undefined){
        var cur=String(vals[pn]);
        cell.innerHTML='<input class="rp-editin" data-orig="'+esc(cur)+'" value="'+esc(cur)+'">';
      } else {
        cell.classList.add('rp-noedit');
      }
    });
    // lock the formula selector while editing so values stay consistent
    sel.disabled=true;
  } else {
    rpEndEdit(card, btn, sel);
  }
}
function rpEndEdit(card, btn, sel){
  var grid=card.querySelector('.rp-grid');
  grid.classList.remove('rp-editing');
  btn.innerHTML='\\u270e Edit values'; btn.classList.remove('rp-editbtn-on');
  var xb=card.querySelector('.rp-exportbtn'); if(xb) xb.remove();
  card.querySelectorAll('.rp-noedit').forEach(function(c){c.classList.remove('rp-noedit');});
  sel.disabled=false;
  rpApplyFormula(sel); // restore the display cells
}
function rpExportEdited(card){
  var sel=card.querySelector('#rpFormula'); if(!sel) return;
  var recipe=sel.getAttribute('data-recipe')||'';
  var formula=sel.value;
  var changes={};
  card.querySelectorAll('.rp-grid tbody .rp-row').forEach(function(r){
    var inp=r.querySelector('.rp-editin'); if(!inp) return;
    var pn=r.getAttribute('data-pname');
    var orig=inp.getAttribute('data-orig'); var now=inp.value;
    if(now!==orig) changes[pn]=now;
  });
  var n=Object.keys(changes).length;
  var st=card.querySelector('.rp-editstatus');
  if(!st){ st=document.createElement('div'); st.className='rp-editstatus'; card.querySelector('.rp-formula-bar').appendChild(st); }
  if(!n){ st.textContent='No values changed yet.'; return; }
  st.innerHTML=dvLoader('Building minimal-diff FHX\\u2026');
  fetch('/recipe_formula_edit',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token:(typeof EXPORT_TOKEN!=='undefined'?EXPORT_TOKEN:''),recipe:recipe,formula:formula,changes:changes})})
    .then(function(r){return r.json();})
    .then(function(j){
      if(j.error){ st.textContent='Edit failed: '+j.error; return; }
      var msg='Applied '+j.applied.length+' change'+(j.applied.length===1?'':'s')
        +' \\u00b7 '+j.diff_lines+'-line diff from the original';
      if(j.skipped&&j.skipped.length) msg+=' \\u00b7 skipped: '+j.skipped.join(', ');
      st.innerHTML=esc(msg)+' <a class="link" href="/recipe_formula_download?t='+encodeURIComponent(j.token)+'&name='+encodeURIComponent(recipe)+'">Download edited FHX \\u2193</a>';
    })
    .catch(function(e){ st.textContent='Edit failed: '+e.message; });
}
function showAliases(unitName){ navTo({k:'aliases', unit:unitName}); }
function renderAliases(unitName){
  var d=document.getElementById('detail'); if(!d) return;
  var ui=DB.unit_instances[unitName]||{};
  var als=ui.aliases||[];
  var back=VIEW_STACK.length>1?' <span class="link" onclick="goBack()">← back</span>':'';
  var h='<h2 class="dt">Aliases <span class="dt-type b-nset">'+esc(unitName)+'</span></h2>';
  h+='<p class="dt-desc">Alias resolution for unit '
    +(DB.objs['unit:'+unitName]?'<span class="link" onclick="show(\\'unit:'+esc(unitName)+'\\')">'+esc(unitName)+'</span>':esc(unitName))
    +'.'+back+'</p>';
  h+=als.length?aliasCardHTML(als):'<div class="card"><span class="empty">No aliases defined for this unit.</span></div>';
  d.innerHTML=h; d.scrollTop=0; try{makeCardsCollapsible();}catch(e){}
}
function showEmMember(emName, memberName, cls){  // #3: resolve the member role (e.g. FRAME_INLET_VLV) to the actual deployed module
  // (e.g. FP005_HV_004) so we open the real INSTANCE template, not the class. DeltaV
  // shows this as "FP005_HV_004 (FRAME_INLET_VLV)".
  if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
    // find an EM instance of this class to resolve against (the wiring lives on the instance)
    var emTag=_emInstanceTagFor(emName);
    if(emTag){
      fetch('/em_members?t='+encodeURIComponent(EXPORT_TOKEN)+'&tag='+encodeURIComponent(emTag))
        .then(function(r){return r.json();})
        .then(function(j){
          var real=(j&&j.members&&j.members[memberName])||'';
          if(real && DB.deployed_modules && DB.deployed_modules[real]){
            showDeployed(real, memberName);  // open the actual module instance
          } else {
            navTo({k:'emmember', em:emName, member:memberName, cls:cls, tag:real});
          }
        })
        .catch(function(){ navTo({k:'emmember', em:emName, member:memberName, cls:cls}); });
      return;
    }
  }
  navTo({k:'emmember', em:emName, member:memberName, cls:cls});
}
// find a deployed EM instance tag for a given EM class (to resolve member wiring)
function _emInstanceTagFor(emClass){
  if(!DB.deployed_modules) return '';
  for(var tag in DB.deployed_modules){
    if(DB.deployed_modules[tag] && DB.deployed_modules[tag].cls===emClass) return tag;
  }
  return '';
}
function renderEmMember(emName, memberName, cls){
  var d=document.getElementById('detail'); if(!d) return;
  var back=VIEW_STACK.length>1?' <span class="link" onclick="goBack()">← back</span>':'';
  var h='<h2 class="dt">'+esc(memberName)+' <span class="dt-type" style="background:#6d28d9">CM member</span></h2>';
  h+='<p class="dt-desc">Control module <b>'+esc(memberName)+'</b> within EM '
    +(DB.objs['em:'+emName]?'<span class="link" onclick="show(\\'em:'+esc(emName)+'\\')">'+esc(emName)+'</span>':esc(emName))
    +' \\u00b7 instance of '+modLink(cls)+'.'+back+'</p>';
  h+='<div class="card" style="max-width:none" id="emmDiag"><h3>Diagram <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 from class '+esc(cls)+'</span></h3><div class="frame-load"><span class="dv-dots"><i></i><i></i><i></i></span> Loading diagram\\u2026</div></div>';
  h+=paramsCard(cls);
  d.innerHTML=h; d.scrollTop=0; try{makeCardsCollapsible();}catch(e){}
  // load the class FBD as the member's diagram (member reuses class logic, wired per EM)
  if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
    fetch('/fbd_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(cls))
      .then(function(r){return r.json();})
      .then(function(x){ var b=document.getElementById('emmDiag'); if(b&&x&&x.html){ b.innerHTML='<h3>Diagram <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 from class '+esc(cls)+'</span></h3>'+x.html; setTimeout(wireFbdLinks,0);} else if(b){ b.innerHTML='<h3>Diagram</h3><span class="empty">No diagram for '+esc(cls)+'.</span>'; } try{makeCardsCollapsible();}catch(e){} })
      .catch(function(){ var b=document.getElementById('emmDiag'); if(b) b.innerHTML='<h3>Diagram</h3><span class="empty">Could not load diagram.</span>'; });
  }
}
function renderEntry(e){
  const d=document.getElementById('detail');
  // #6: before leaving the current view, snapshot it if it's a fully-loaded deployed
  // instance so returning to it is instant (no re-fetch of diagram/params/logic/members).
  try{ if(typeof _captureDepView==='function') _captureDepView(); }catch(e2){}
  // paint an immediate loading state so selecting an object feels responsive,
  // then do the (possibly heavier) render on the next frame so the loader shows.
  var label = e.k==='obj' ? ((DB.objs[e.id]&&DB.objs[e.id].name)||'')
            : e.k==='fbd' ? (e.label||e.def)
            : e.k==='inst' ? (e.iid||'').split('\\u0001').pop()
            : e.k==='param' ? e.name : (e.tag||'');
  if(d){
    d.innerHTML='<h2 class="dt">'+esc(label)+'</h2>'+
      '<div class="dv-loader"><span class="dv-dots"><i></i><i></i><i></i></span> Loading '+esc(label)+'\\u2026</div>'+
      '<div class="dv-skel"><div class="ln w2"></div><div class="ln w1"></div><div class="ln w3"></div></div>';
    d.scrollTop=0;
  }
  requestAnimationFrame(function(){
    if(e.k==='obj') renderObj(e.id);
    else if(e.k==='fbd') renderFbd(e.def,e.label);
    else if(e.k==='param') renderParam(e.name);
    else if(e.k==='inst') renderInstance(e.iid);
    else if(e.k==='dep') renderDeployed(e.tag, e.role);
    else if(e.k==='emmember') renderEmMember(e.em,e.member,e.cls);
    else if(e.k==='aliases') renderAliases(e.unit);
    else if(e.k==='iotable') renderIoTable(e.ctrl);
    else if(e.k==='references') renderReferences(e.tag);
    else if(e.k==='rstep') renderRecipeStep(e.parent, e.step, e.layer);
    else if(e.k==='uphase') renderUnitPhase(e.unit, e.phase);
    else if(e.k==='iodev') renderIoDevices();
    else if(e.k==='aliasval') renderAliasValidator();
    var dd=document.getElementById('detail'); if(dd) dd.scrollTop=0;
    makeCardsCollapsible();
    try{ markSelectedObject(e); }catch(_e){}
  });
}
// #1: keep a single persistent "currently open" highlight on the matching nav row.
// Moves to the newly opened object and clears the previously selected one.
function markSelectedObject(e){
  document.querySelectorAll('.obj-selected').forEach(function(n){ n.classList.remove('obj-selected'); });
  if(!e) return;
  var sel=null;
  if(e.k==='obj') sel='.navitem[data-id="'+cssEsc(e.id)+'"]';
  else if(e.k==='dep') sel='.navinst[data-tag="'+cssEsc(e.tag)+'"][data-dep="1"]';
  else if(e.k==='inst'){ var tg=(e.iid||'').split('\\u0001').pop(); sel='.navinst[data-tag="'+cssEsc(tg)+'"]'; }
  else if(e.k==='rstep'||e.k==='recipe') sel='.rec-item[data-rec="'+cssEsc(e.parent||e.rec||'')+'"]';
  else if(e.k==='uphase') sel='.navitem[data-uphase="'+cssEsc(e.unit+'\\u241f'+e.phase)+'"]';
  if(!sel) return;
  var row=document.querySelector(sel);
  if(!row) return;
  // #4a: the row may be nested inside collapsed .navchildren (e.g. its unit isn't
  // expanded). Walk up and open every collapsed ancestor group so the row is visible
  // BEFORE we try to scroll to it.
  try{
    var anc=row.parentElement;
    while(anc && anc!==document.body){
      if(anc.classList && anc.classList.contains('navchildren') && anc.style.display==='none'){
        anc.style.display='';
        // flip the sibling toggle caret if present
        var grp=anc.parentElement;
        var head=grp&&grp.querySelector(':scope > .navitem');
        var tog=head&&head.querySelector('.tog');
        if(tog) tog.textContent='\\u25be';
      }
      anc=anc.parentElement;
    }
  }catch(_e){}
  row.classList.add('obj-selected');
  // #4b: scrollIntoView({block:'nearest'}) can tuck the row under the sticky search
  // header at the top of the tree. Scroll the nav container manually with an offset
  // that clears the sticky search box.
  try{
    var nav=row.closest('.nav')||row.closest('.navwrap')||row.closest('.sidebar');
    var sticky=nav?nav.querySelector('.navsearch'):null;
    if(nav){
      var pad=(sticky?sticky.getBoundingClientRect().height:0)+12;
      var nr=nav.getBoundingClientRect(), rr=row.getBoundingClientRect();
      var delta=(rr.top-nr.top)-pad;
      nav.scrollTop+=delta;
    } else {
      row.scrollIntoView({block:'center'});
    }
  }catch(_e){ try{ row.scrollIntoView({block:'center'}); }catch(_e2){} }
}
function cssEsc(s){ return String(s==null?'':s).replace(/["\\\\]/g,'\\\\$&'); }
// #3/#5: collapse any card OR sub-card by clicking its header. Handles top-level
// .card > h3 and nested sub-cards / h4 headers, so a master card (e.g. Diagram) with
// internal sub-sections can each collapse independently. Pure CSS affordance + one
// delegated handler — works for cards added at any time across ALL object types.
function makeCardsCollapsible(){
  // The click delegation + CSS handle .card / .subcard headers. This pass extends
  // that to (a) bare <h4> sections inside a .card, and (b) the FBD cards used in CM
  // diagram views (.fbd-info-card with an <h4>, and .fbd-diagram-card with .fbd-head)
  // which use a different class structure — so those collapse too (#1).
  try{
    var roots=[document.getElementById('detail'),document.getElementById('rdetail'),document.getElementById('stuMain')];
    roots.forEach(function(root){
      if(!root) return;
      root.querySelectorAll('.card').forEach(function(card){
        var h4s=[]; for(var i=0;i<card.children.length;i++){ if(card.children[i].tagName==='H4') h4s.push(card.children[i]); }
        h4s.forEach(function(h){
          if(h.parentElement.classList.contains('subcard')) return;
          var sub=document.createElement('div'); sub.className='subcard';
          h.parentNode.insertBefore(sub, h);
          var n=h;
          while(n){ var nx=n.nextSibling; sub.appendChild(n); if(nx && nx.nodeType===1 && nx.tagName==='H4') break; n=nx; }
        });
      });
      // FBD info-cards: mark collapsible via their <h4>; the delegated handler below
      // recognises .fbd-collapse just like .subcard.
      root.querySelectorAll('.fbd-info-card').forEach(function(c){ c.classList.add('fbd-collapse'); });
      // FBD diagram cards: the .fbd-head is the toggle; body is .fbd-svg-holder.
      root.querySelectorAll('.fbd-diagram-card').forEach(function(c){ c.classList.add('fbd-collapse'); });
    });
  }catch(e){}
}
// #1/#2: recipe PFC diagram pan + zoom (mirrors the phase SFC interactions).
function pfcZoom(wrap, dir){
  var layer=wrap.querySelector('.pfc-zoomlayer'); if(!layer) return;
  var z=parseFloat(wrap.getAttribute('data-zoom')||'1');
  if(dir==='in') z=Math.min(3, z+0.15);
  else if(dir==='out') z=Math.max(0.4, z-0.15);
  else z=1;
  wrap.setAttribute('data-zoom', z);
  layer.style.transform='scale('+z+')';
}
if(!window._pfcPanWired){
  window._pfcPanWired=1;
  var panW=null, psx=0, psy=0, psl=0, pst=0;
  document.addEventListener('mousedown',function(e){
    var wrap=e.target.closest && e.target.closest('.pfc-wrap');
    if(!wrap) return;
    if(e.target.closest('.pfc-trans,.pfc-zbtn,a,button')) return; // don't pan when clicking a transition
    panW=wrap; psx=e.clientX; psy=e.clientY; psl=wrap.scrollLeft; pst=wrap.scrollTop;
    wrap.classList.add('panning'); e.preventDefault();
  });
  document.addEventListener('mousemove',function(e){
    if(!panW) return;
    panW.scrollLeft=psl-(e.clientX-psx); panW.scrollTop=pst-(e.clientY-psy);
  });
  document.addEventListener('mouseup',function(){ if(panW){ panW.classList.remove('panning'); panW=null; } });
  // #3: inline PFC step-detail panel resize. Delegated + document-level so it works in
  // both the Explorer and the Studio recipe view, and doesn't get stuck if the cursor
  // leaves the bar mid-drag.
  var pfcDiv=null, pfcLayout=null, pfcPanel=null, pfcRect=null, pfcFrames=null;
  document.addEventListener('mousedown',function(e){
    var d=e.target.closest && e.target.closest('.pfc-divider'); if(!d) return;
    pfcDiv=d; pfcLayout=d.closest('.pfc-layout');
    pfcPanel=pfcLayout?pfcLayout.querySelector('.pfc-panel'):null;
    pfcRect=pfcLayout?pfcLayout.getBoundingClientRect():null;
    if(pfcPanel){
      pfcFrames=Array.prototype.slice.call(document.querySelectorAll('iframe'));
      pfcFrames.forEach(function(f){ f.style.pointerEvents='none'; });
      document.body.style.userSelect='none'; e.preventDefault();
    }
  });
  document.addEventListener('mousemove',function(e){
    if(!pfcDiv||!pfcPanel||!pfcRect) return;
    var w=pfcRect.right-e.clientX;                          // panel is on the right
    w=Math.max(200,Math.min(pfcRect.width-260,w));
    pfcPanel.style.flex='0 0 '+w+'px';
  });
  document.addEventListener('mouseup',function(){
    if(pfcDiv){ pfcDiv=null; pfcPanel=null; pfcRect=null;
      if(pfcFrames){ pfcFrames.forEach(function(f){ f.style.pointerEvents=''; }); pfcFrames=null; }
      document.body.style.userSelect=''; }
  });
  // scroll-to-zoom over the diagram
  document.addEventListener('wheel',function(e){
    var wrap=e.target.closest && e.target.closest('.pfc-wrap');
    if(!wrap) return;
    if(e.ctrlKey||e.metaKey||e.shiftKey){ pfcZoom(wrap, e.deltaY<0?'in':'out'); e.preventDefault(); }
  },{passive:false});
}
// ── right-click context menu (prototype) ──────────────────────────────────────
// A single delegated handler reads the object under the cursor from its data-id /
// data-rec and offers the actions that already exist for that object type. It
// shortcuts what would otherwise be a click-then-hunt: exports live right on the
// object, navigation between the Explorer and Recipes views is one step.
if(!window._ctxWired){
  window._ctxWired=1;
  function ctxClose(){ var m=document.getElementById('ctxMenu'); if(m){ if(m._target) m._target.classList.remove('ctx-target'); m.remove(); } }
  function ctxItem(label, fn, opts){
    opts=opts||{};
    return {label:label, fn:fn, disabled:opts.disabled, sep:opts.sep, danger:opts.danger};
  }
  // Build the action list for a given object. Returns [] when there's nothing useful.
  function ctxActionsFor(el){
    var acts=[];
    // recipe workspace item
    var recName=el.getAttribute && el.getAttribute('data-rec');
    // explorer nav item id like "recipe:NAME" / "phase:NAME" / "em:NAME" / "cm:..."
    var id=el.getAttribute && el.getAttribute('data-id');
    var kind='', name='';
    if(id && id.indexOf(':')>=0){ kind=id.slice(0,id.indexOf(':')); name=id.slice(id.indexOf(':')+1); }
    var tag=el.getAttribute && el.getAttribute('data-tag');

    if(recName || kind==='recipe'){
      var rn=recName||name;
      acts.push(ctxItem('Open recipe', function(){ if(typeof recShow==='function' && document.getElementById('view-recipes').classList.contains('on')){recShow(rn);} else {show('recipe:'+rn);} }));
      acts.push(ctxItem('Open in Recipes workspace', function(){ switchView('recipes'); if(typeof recShow==='function') recShow(rn); }));
      acts.push(ctxItem('Export PFC report (.xlsx)', function(){ RECWS.token=RECWS.token||EXPORT_TOKEN; recDownloadPfc(rn); }, {sep:true}));
      acts.push(ctxItem('Copy name', function(){ ctxCopy(rn); }, {sep:true}));
      return acts;
    }
    if(kind==='phase'){
      acts.push(ctxItem('Open phase', function(){ show(id); }));
      acts.push(ctxItem('Open in Studio', function(){ switchView('studio'); stuBuildList(); setTimeout(function(){ stuOpen(id); },0); }));
      if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN)
        acts.push(ctxItem('Export (.xlsx)', function(){ window.location.href='/export?t='+encodeURIComponent(EXPORT_TOKEN)+'&fmt=excel&obj='+encodeURIComponent(id); }, {sep:true}));
      acts.push(ctxItem('Copy name', function(){ ctxCopy(name); }, {sep:true}));
      return acts;
    }
    if(kind==='em' || kind==='cm' || kind==='fbtype' || kind==='composite'){
      acts.push(ctxItem('Open', function(){ show(id); }));
      if(kind==='em' || kind==='cm'){
        acts.push(ctxItem('Open in Studio', function(){ switchView('studio'); stuBuildList(); setTimeout(function(){ stuOpen(id); },0); }));
        if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
          acts.push(ctxItem('Export (.xlsx)', function(){ window.location.href='/export?t='+encodeURIComponent(EXPORT_TOKEN)+'&fmt=excel&obj='+encodeURIComponent(id); }, {sep:true}));
          acts.push(ctxItem('Export (.docx)', function(){ window.location.href='/export?t='+encodeURIComponent(EXPORT_TOKEN)+'&fmt=word&obj='+encodeURIComponent(id); }));
        }
      }
      acts.push(ctxItem('Find references', function(){ showReferencesFloat(name); }));
      acts.push(ctxItem('Copy name', function(){ ctxCopy(name); }, {sep:true}));
      return acts;
    }
    if(tag){
      acts.push(ctxItem('Open instance', function(){ if(typeof showDeployed==='function') showDeployed(tag); }));
      acts.push(ctxItem('Open in Studio', function(){ switchView('studio'); stuBuildList(); setTimeout(function(){ stuOpen('dep:'+tag); },0); }));
      acts.push(ctxItem('Find references', function(){ showReferencesFloat(tag); }));
      acts.push(ctxItem('Copy tag', function(){ ctxCopy(tag); }, {sep:true}));
      return acts;
    }
    if(id){
      acts.push(ctxItem('Open', function(){ show(id); }));
      acts.push(ctxItem('Copy name', function(){ ctxCopy(name||id); }, {sep:true}));
    }
    return acts;
  }
  function ctxCopy(t){ try{ navigator.clipboard.writeText(t); }catch(e){
    var ta=document.createElement('textarea'); ta.value=t; document.body.appendChild(ta); ta.select();
    try{document.execCommand('copy');}catch(e2){} ta.remove(); } }

  document.addEventListener('contextmenu', function(ev){
    // #7: right-click a drillable PFC diagram step -> drill into its child object
    var stepEl=ev.target.closest && ev.target.closest('.pfc-step[data-step]');
    if(stepEl && stepEl.classList.contains('pfc-drillable')){
      var wrapC=stepEl.closest('.pfc-wrap');
      var sn=stepEl.getAttribute('data-step');
      var childName='';
      try{ var SS=JSON.parse(wrapC.getAttribute('data-pfc-steps')||'{}'); childName=(SS[sn]||{}).child||''; }catch(e){}
      if(!childName){ childName=(stepEl.getAttribute('data-drill')||''); }
      if(childName){
        ev.preventDefault(); ctxClose();
        var inWs=document.getElementById('view-recipes') && document.getElementById('view-recipes').classList.contains('on');
        var loaded=inWs ? (RECWS.views && RECWS.views[childName]!==undefined) : (DB.objs && DB.objs['recipe:'+childName]);
        var openFn=inWs ? function(){ recShow(childName); } : function(){ show('recipe:'+childName); };
        var acts2=[{label:(loaded?('Drill into '+childName):(childName+' (not loaded)')),
                    disabled:!loaded, fn:openFn}];
        var m2=document.createElement('div'); m2.id='ctxMenu'; m2.className='ctx-menu';
        acts2.forEach(function(a){ var it=document.createElement('div');
          it.className='ctx-it'+(a.disabled?' ctx-dis':''); it.textContent=a.label;
          if(!a.disabled) it.onclick=function(){ ctxClose(); a.fn(); }; m2.appendChild(it); });
        document.body.appendChild(m2);
        var vw2=window.innerWidth, vh2=window.innerHeight;
        m2.style.left=Math.min(ev.clientX, vw2-m2.offsetWidth-6)+'px';
        m2.style.top=Math.min(ev.clientY, vh2-m2.offsetHeight-6)+'px';
        return;
      }
    }
    var el=ev.target.closest && ev.target.closest('.navitem[data-id], .rec-item[data-rec], .navinst[data-tag]');
    if(!el) return;  // fall through to the browser's native menu elsewhere
    var acts=ctxActionsFor(el);
    if(!acts.length) return;
    ev.preventDefault();
    ctxClose();
    var m=document.createElement('div'); m.id='ctxMenu'; m.className='ctx-menu';
    acts.forEach(function(a){
      if(a.sep){ var s=document.createElement('div'); s.className='ctx-sep'; m.appendChild(s); }
      var it=document.createElement('div');
      it.className='ctx-it'+(a.disabled?' ctx-dis':'')+(a.danger?' ctx-danger':'');
      it.textContent=a.label;
      if(!a.disabled) it.onclick=function(){ ctxClose(); a.fn(); };
      m.appendChild(it);
    });
    document.body.appendChild(m);
    // position within viewport
    var vw=window.innerWidth, vh=window.innerHeight, mw=m.offsetWidth, mh=m.offsetHeight;
    var x=Math.min(ev.clientX, vw-mw-6), y=Math.min(ev.clientY, vh-mh-6);
    m.style.left=x+'px'; m.style.top=y+'px';
    // highlight the target row briefly
    el.classList.add('ctx-target');
    m._target=el;
  });
  document.addEventListener('click', function(e){ if(!e.target.closest('#ctxMenu')){ var m=document.getElementById('ctxMenu'); if(m&&m._target)m._target.classList.remove('ctx-target'); ctxClose(); } });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape'){ var m=document.getElementById('ctxMenu'); if(m&&m._target)m._target.classList.remove('ctx-target'); ctxClose(); } });
  window.addEventListener('scroll', function(){ ctxClose(); }, true);
}
if(!window._cardCollapseWired){
  window._cardCollapseWired=1;
  document.addEventListener('click',function(ev){
    var t=ev.target;
    if(!t.closest) return;
    if(t.closest('a,.link,button,input,select') && !t.closest('.pfc-zbtn')) return; // let controls work
    // PFC (recipe) zoom buttons
    var zb=t.closest('.pfc-zbtn');
    if(zb){
      var card=zb.closest('.card'); var wrap2=card?card.querySelector('.pfc-wrap'):null;
      if(wrap2) pfcZoom(wrap2, zb.getAttribute('data-pfc-zoom'));
      return;
    }
    // recipe drill-down: step definition references another recipe object
    var drill=t.closest('.rf-drill');
    if(drill){
      var rn=drill.getAttribute('data-recipe');
      if(rn && DB.objs['recipe:'+rn]){ show('recipe:'+rn); }
      return;
    }
    // #4/#7: clicking a step box shows its detail (definition, parameters, deferred-to
    // bindings) in the side panel — and if the step has a child object, offers a
    // drill-down link. Left-click = show detail; the child link/right-click drills in.
    var stepG=t.closest('.pfc-step');
    if(stepG){
      var wrapS=stepG.closest('.pfc-wrap');
      var sn=stepG.getAttribute('data-step');
      if(wrapS && sn){
        var S={}; try{ S=JSON.parse(wrapS.getAttribute('data-pfc-steps')||'{}'); }catch(e){}
        var panelIdS=wrapS.getAttribute('data-pfc-panel');
        var panelS=panelIdS?document.getElementById(panelIdS):wrapS.parentElement.querySelector('.pfc-panel');
        var info=S[sn];
        // in the Recipes workspace, child objects live in RECWS.views + recShow();
        // in the Explorer they live in DB.objs + show(). Resolve for the active context.
        var inWorkspace=document.getElementById('view-recipes') && document.getElementById('view-recipes').classList.contains('on');
        if(panelS){
          if(info){
            var childLoaded = info.child && (inWorkspace
              ? (RECWS.views && RECWS.views[info.child]!==undefined)
              : (DB.objs && DB.objs['recipe:'+info.child]));
            var openCall = inWorkspace
              ? ("recShow('"+jsq(info.child)+"')")
              : ("show('recipe:"+jsq(info.child)+"')");
            var ph='<div class="pfc-shead"><div class="pfc-tname">'+esc(sn)+'</div>';
            var tags='';
            if(info.initial) tags+='<span class="pfc-tag pfc-tag-init">initial</span>';
            if(info.layer) tags+='<span class="pfc-tag">'+esc(info.layer)+'</span>';
            if(info.n_def) tags+='<span class="pfc-tag pfc-tag-def">'+info.n_def+' deferred</span>';
            if(tags) ph+='<div class="pfc-tags">'+tags+'</div>';
            ph+='</div>';
            if(info.def) ph+='<div class="pfc-sdef">instantiates <code>'+esc(info.def)+'</code></div>';
            if(info.child){
              ph+='<div class="pfc-sdrill">'+(childLoaded
                ?'<a class="link" onclick="'+openCall+'">\\u25c9 open child object '+esc(info.child)+' \\u2192</a>'
                :'<span class="pfc-sdrill-ghost">\\u25c9 child <b>'+esc(info.child)+'</b> not loaded \\u2014 import it to drill in</span>')+'</div>';
            }
            // sequence context: what leads in, what leads out
            if((info.ins&&info.ins.length)||(info.outs&&info.outs.length)){
              ph+='<div class="pfc-seq">';
              if(info.ins&&info.ins.length) ph+='<div class="pfc-seqrow"><span class="pfc-seqlbl">from</span> '+info.ins.map(function(x){return '<code>'+esc(x)+'</code>';}).join(', ')+'</div>';
              if(info.outs&&info.outs.length) ph+='<div class="pfc-seqrow"><span class="pfc-seqlbl">via</span> '+info.outs.map(function(x){return '<code class="pfc-seqtrans" data-goto-trans="'+esc(x)+'">'+esc(x)+'</code>';}).join(', ')+'</div>';
              ph+='</div>';
            }
            if(info.params && info.params.length){
              ph+='<div class="pfc-plabel">Parameters ('+info.params.length+')</div>';
              ph+='<table class="pfc-sparams"><thead><tr><th>Parameter</th><th>Group</th><th>Deferred to</th></tr></thead><tbody>';
              info.params.forEach(function(p){
                ph+='<tr'+(p.deferred?' class="pfc-pdef"':'')+'><td>'+esc(p.name)+'</td><td>'+esc(p.group||'')+'</td><td>'+(p.deferred?('<code>'+esc(p.deferred)+'</code>'):'\\u2014')+'</td></tr>';
              });
              ph+='</tbody></table>';
            } else {
              ph+='<div class="pfc-hint">No parameters on this step.</div>';
            }
            panelS.innerHTML=ph;
          } else {
            panelS.innerHTML='<div class="pfc-tname">'+esc(sn)+'</div><div class="pfc-hint">No detail for this step.</div>';
          }
        }
        wrapS.querySelectorAll('.pfc-step.sel,.pfc-trans.sel').forEach(function(x){x.classList.remove('sel');});
        stepG.classList.add('sel');
      }
      return;
    }
    // PFC (recipe) transition click -> show expression in the recipe's panel
    var g=t.closest('.pfc-trans');
    if(g){
      var wrap=g.closest('.pfc-wrap');
      if(wrap){
        var tn=g.getAttribute('data-trans');
        var E={}; try{ E=JSON.parse(wrap.getAttribute('data-pfc-expr')||'{}'); }catch(e){}
        var panelId=wrap.getAttribute('data-pfc-panel');
        var panel=panelId?document.getElementById(panelId):wrap.parentElement.querySelector('.pfc-panel');
        if(panel){
          var e=(E[tn]!==undefined?E[tn]:'')||'(no expression \\u2014 state transition)';
          panel.innerHTML='<div class="pfc-tname">'+esc(tn)+'</div><div class="pfc-texpr">'+esc(e)+'</div>';
        }
        wrap.querySelectorAll('.pfc-trans.sel').forEach(function(x){x.classList.remove('sel');});
        g.classList.add('sel');
      }
      return;
    }
    // FBD cards (#1): .fbd-info-card toggles on its <h4>; .fbd-diagram-card on .fbd-head.
    var fbdCard=t.closest && t.closest('.fbd-collapse');
    if(fbdCard){
      var onHead = t.closest('h4') || t.closest('.fbd-head');
      if(onHead && (onHead.parentElement===fbdCard)){
        fbdCard.classList.toggle('collapsed');
        ev.stopPropagation();
        return;
      }
    }
    // a header is a direct h3/h4 child of a .card or .subcard container.
    // Walk up from the click target to find an h3/h4 whose parent is a card/subcard —
    // more robust than closest('.card > h3') (child-combinator in closest is finicky).
    var node=t, hdr=null;
    for(var k=0;k<4 && node && node!==document;k++){
      var tag=(node.tagName||'').toLowerCase();
      if((tag==='h3'||tag==='h4') && node.parentElement){
        var pc=node.parentElement.classList;
        if(pc && (pc.contains('card')||pc.contains('subcard'))){ hdr=node; break; }
      }
      node=node.parentElement;
    }
    if(!hdr) return;
    if(!hdr.closest('#detail') && !hdr.closest('#rdetail') && !hdr.closest('#stuMain')) return;
    // #3 fix: an <h4> sitting *directly* inside a .card (common after a lazy innerHTML
    // swap that ran AFTER makeCardsCollapsible) has no .subcard wrapper — toggling the
    // card would collapse the whole card. Wrap this h4 + its following siblings (up to
    // the next h4) into a .subcard on the fly, then toggle just that subcard.
    var parent=hdr.parentElement, target=parent;
    if(hdr.tagName==='H4' && parent.classList.contains('card') && !parent.classList.contains('subcard')){
      var sub=document.createElement('div'); sub.className='subcard';
      parent.insertBefore(sub, hdr);
      var m=hdr;
      while(m){ var nx=m.nextSibling; sub.appendChild(m); if(nx && nx.nodeType===1 && nx.tagName==='H4') break; m=nx; }
      target=sub;
    }
    target.classList.toggle('collapsed');
    ev.stopPropagation();
  });
}
function navTo(e){ VIEW_STACK.push(e); renderEntry(e); }
function goBack(){ if(VIEW_STACK.length>1){ VIEW_STACK.pop(); renderEntry(VIEW_STACK[VIEW_STACK.length-1]); } }
function show(id){
  if(id && id.indexOf('param:')===0){ var pn=id.slice(6); if(PARAM_INDEX[pn]) navTo({k:'param',name:pn}); return; }
  if(id && id.indexOf('inst:')===0){ var iid=id.slice(5); if(DB.instances&&DB.instances[iid]) navTo({k:'inst',iid:iid}); return; }
  if(id && id.indexOf('dep:')===0){ var dt=id.slice(4); if(DB.deployed_modules&&DB.deployed_modules[dt]) navTo({k:'dep',tag:dt,role:''}); return; }
  if(DB.objs[id]) navTo({k:'obj',id:id});
}
function showFbd(def,label){ if(FBD_VIEWS[def] || (typeof FBD_NAMES!=='undefined' && FBD_NAMES.indexOf(def)>=0)) navTo({k:'fbd',def:def,label:label}); }

// #6: a phase opened on a specific deployed unit instance. Same interactive phase
// view as the class, but the simulator resolves #aliases# against THIS unit's wired
// devices (server passes &unit=), so the walk actuates real modules — which is why
// the Simulate button belongs here and not on the bare class.
function showUnitPhase(unit, phase){ navTo({k:'uphase', unit:unit, phase:phase}); }
function showIoDevices(){ navTo({k:'iodev'}); }
function showAliasValidator(){ navTo({k:'aliasval'}); }
function renderAliasValidator(){
  var d=document.getElementById('detail'); if(!d) return;
  var back=VIEW_STACK.length>1?' <span class="link" onclick="goBack()">\\u2190 back</span>':'';
  d.innerHTML='<h2 class="dt">Alias Resolution Validator <span class="dt-type b-unit">Unit tool</span></h2>'
    +'<p class="dt-desc">For each deployed unit, checks that every alias used in its phase '
    +'logic resolves to a real deployed device \\u2014 flagging unresolved, ignored-but-used, '
    +'and dangling references for commissioning and Part 11 review.'+back+'</p>'
    +'<div class="card" style="max-width:none" id="avBox"><div class="frame-load">'
    +'<span class="dv-dots"><i></i><i></i><i></i></span> Analyzing aliases\\u2026</div></div>';
  d.scrollTop=0;
  if(typeof EXPORT_TOKEN==='undefined'||!EXPORT_TOKEN){ var b0=document.getElementById('avBox'); if(b0) b0.innerHTML='<span class="empty">Unavailable.</span>'; return; }
  fetch('/alias_validate?t='+encodeURIComponent(EXPORT_TOKEN))
    .then(function(r){return r.json();})
    .then(function(x){ var b=document.getElementById('avBox'); if(!b) return;
      b.innerHTML=(x&&x.html)||'<span class="empty">No result.</span>';
      try{ wireAvCollapse(); }catch(e){} })
    .catch(function(){ var b=document.getElementById('avBox'); if(b) b.innerHTML='<span class="empty">Could not run the validator.</span>'; });
}
function wireAvCollapse(){
  var box=document.getElementById('avBox'); if(!box) return;
  box.querySelectorAll('.av-unit > h4').forEach(function(h){
    h.onclick=function(){ h.parentElement.classList.toggle('collapsed'); };
  });
}
function renderIoDevices(){
  var d=document.getElementById('detail'); if(!d) return;
  var back=VIEW_STACK.length>1?' <span class="link" onclick="goBack()">\\u2190 back</span>':'';
  d.innerHTML='<h2 class="dt">DeviceNet I/O <span class="dt-type b-cm">Hardware</span></h2>'
    +'<p class="dt-desc">Physical DeviceNet devices parsed from the export\\u2019s hardware '
    +'records, grouped by controller \\u2192 card \\u2192 port.'+back+'</p>'
    +'<div class="card" style="max-width:none" id="ioDevBox"><div class="frame-load">'
    +'<span class="dv-dots"><i></i><i></i><i></i></span> Loading I/O devices\\u2026</div></div>';
  d.scrollTop=0;
  if(typeof EXPORT_TOKEN==='undefined'||!EXPORT_TOKEN){ var b0=document.getElementById('ioDevBox'); if(b0) b0.innerHTML='<span class="empty">Unavailable.</span>'; return; }
  fetch('/io_devices?t='+encodeURIComponent(EXPORT_TOKEN))
    .then(function(r){return r.json();})
    .then(function(x){ var b=document.getElementById('ioDevBox'); if(!b) return;
      if(x&&x.html){ b.innerHTML=x.html; try{ wireIoCollapse(); }catch(e){} }
      else b.innerHTML='<span class="empty">No DeviceNet hardware records in this export.</span>'; })
    .catch(function(){ var b=document.getElementById('ioDevBox'); if(b) b.innerHTML='<span class="empty">Could not load I/O devices.</span>'; });
}
function wireIoCollapse(){
  var box=document.getElementById('ioDevBox'); if(!box) return;
  box.querySelectorAll('.io-info-card > h4').forEach(function(h){
    h.onclick=function(){ h.parentElement.classList.toggle('collapsed'); };
  });
}
function renderUnitPhase(unit, phase){
  var d=document.getElementById('detail'); if(!d) return;
  var back=VIEW_STACK.length>1?' <span class="link" onclick="goBack()">\\u2190 back</span>':'';
  var h='<h2 class="dt">'+esc(phase)+' <span class="dt-type b-phase">Phase on unit</span></h2>';
  h+='<p class="dt-desc">Phase <b>'+esc(phase)+'</b> running on unit instance '
    +'<span class="link" onclick="show(\\'unit:'+esc(unit)+'\\')">'+esc(unit)+'</span>. '
    +'The simulator resolves this unit\\u2019s aliases to real device tags.'+back+'</p>';
  h+='<div class="card" style="max-width:none">';
  if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
    var src='/phase_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&p='+encodeURIComponent(phase)
      +'&sim=1&unit='+encodeURIComponent(unit);
    h+='<div class="frame-wrap"><div class="frame-load" id="uphaseLoad"><span class="dv-dots"><i></i><i></i><i></i></span> Loading phase logic\\u2026</div>';
    h+='<iframe id="phaseFrame" class="phaseframe" src="'+src+'" onload="var l=document.getElementById(\\'uphaseLoad\\');if(l)l.style.display=\\'none\\';"></iframe></div>';
  } else {
    h+='<span class="empty">Phase logic unavailable in this export.</span>';
  }
  h+='</div>';
  d.innerHTML=h; d.scrollTop=0; try{makeCardsCollapsible();}catch(e){}
  try{ markSelectedObject({k:'uphase',unit:unit,phase:phase}); }catch(_e){}
}

// ── lazy view loaders (large exports don't build FBD/EM views up front) ──
function renderEmPanel(ev, stateSet){
  _emCurrent=(ev&&ev.name)||_emCurrent||'';
  var mem=(ev.members&&ev.members.length)?ev.members:null;
  var cmCount=mem?mem.length:((ev.cms&&ev.cms.length)||0);
  var h='<div class="card" style="max-width:none">';
  h+='<div class="emtabs">';
  h+='<button class="emtab on" data-e="fb" onclick="emTab(this,\\'fb\\')">Function Blocks</button>';
  if(ev.state) h+='<button class="emtab" data-e="state" onclick="emTab(this,\\'state\\')">'+(stateSet?'State Table':'Command Logic')+'</button>';
  if(cmCount) h+='<button class="emtab" data-e="cms" onclick="emTab(this,\\'cms\\')">Control Modules ('+cmCount+')</button>';
  h+='</div>';
  h+='<div class="empanel on" data-e="fb" id="empanel_fb">'+(ev.fbd||'<span class="empty">No function block layer.</span>')+'</div>';
  if(ev.state) h+='<div class="empanel" data-e="state"><iframe class="phaseframe" srcdoc="'+ev.state.replace(/&/g,"&amp;").replace(/"/g,"&quot;")+'"></iframe></div>';
  if(cmCount){
    h+='<div class="empanel" data-e="cms">';
    if(mem){
      // group by ownership (shared vs private), each group collapsible (#5, #6)
      var shared=mem.filter(function(m){return (m.ownership||'').toUpperCase()==='SHARED';});
      var priv=mem.filter(function(m){return (m.ownership||'').toUpperCase()==='PRIVATE';});
      var other=mem.filter(function(m){var o=(m.ownership||'').toUpperCase();return o!=='SHARED'&&o!=='PRIVATE';});
      h+=cmGroup('Shared',shared,'shared');
      h+=cmGroup('Private',priv,'private');
      h+=cmGroup('Unspecified ownership',other,'');
    } else {
      h+='<details class="cm-group" open><summary>Control Modules ('+ev.cms.length+')</summary><div class="cm-list">';
      ev.cms.forEach(function(c){h+='<span class="cm-chip" onclick="show(\\'cm:'+esc(c.name)+'\\')"><span class="cm-ico cm-ico-none"></span>'+esc(c.name)+' <span class="cm-sub">· '+c.n_blocks+' blocks</span></span>';});
      h+='</div></details>';
    }
    h+='</div>';
  }
  h+='</div>';
  return h;
}
// one collapsible ownership group of CM members
function cmGroup(label, list, kind){
  if(!list.length) return '';
  var icoClass=kind==='shared'?'cm-ico-shared':(kind==='private'?'cm-ico-private':'cm-ico-none');
  var icoTitle=kind==='shared'?'Shared — usable by multiple EMs':(kind==='private'?'Private — owned by this EM':'Ownership unspecified');
  var h='<details class="cm-group" open><summary>'+esc(label)+' <span class="cm-count">'+list.length+'</span></summary><div class="cm-list">';
  list.forEach(function(m){
    var cls=m.module||'';
    h+='<span class="cm-chip" title="'+esc(m.desc||'')+'" onclick="showEmMember(\\''+esc(_emCurrent).replace(/'/g,"\\\\'")+'\\',\\''+esc(m.name).replace(/'/g,"\\\\'")+'\\',\\''+esc(cls).replace(/'/g,"\\\\'")+'\\')">'
      +'<span class="cm-ico '+icoClass+'" title="'+icoTitle+'"></span>'
      +'<b>'+esc(m.name)+'</b> <span class="cm-sub">'+esc(cls)+'</span></span>';
  });
  h+='</div></details>';
  return h;
}
// #2/#11: load an EM INSTANCE's command list and offer a Simulate button for each.
// Simulation runs against the instance so its actual wired CMs/aliases resolve.
// #1/#2: resolve this EM instance's member roles to actual deployed CM tags and
// link each to the real CM instance view (e.g. BYP_INLET_VLV -> FP005-HV-027).
function lazyInstMembers(d){
  var box=document.getElementById('instMembersList'); if(!box) return;
  fetch('/em_members?t='+encodeURIComponent(EXPORT_TOKEN)+'&tag='+encodeURIComponent(d.tag))
    .then(function(r){return r.json();})
    .then(function(j){
      var mm=(j&&j.members)||{};
      var roles=Object.keys(mm);
      if(!roles.length){ box.outerHTML='<div class="empty" id="instMembersList">No resolved control modules for this instance.</div>'; return; }
      // count ignored (commissioned-out) roles for the header note
      var nIgn=roles.filter(function(r){return mm[r]===null;}).length;
      var note=nIgn?(' <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 '+nIgn+' ignored (commissioned-out)</span>'):'';
      var h='<table class="fbd-table"><thead><tr><th>Role in EM</th><th>Wired device</th></tr></thead><tbody>';
      roles.sort().forEach(function(role){
        var dev=mm[role];
        var cell;
        if(dev===null){
          // #4: intentionally commissioned-out member (MODULE="" IGNORE=T) — keep it
          // visible but disabled, labelled Ignored, matching the alias-table treatment.
          cell='<span class="alias-ignored" title="MODULE=\\u0022\\u0022 IGNORE=T \\u2014 intentionally not wired / commissioned-out">Ignored ('+esc(role)+')</span>';
        } else if(DB.deployed_modules&&DB.deployed_modules[dev]){
          cell='<span class="link" onclick="showDeployed(\\''+esc(dev).replace(/\'/g,"\\\\'")+'\\')">'+esc(dev)+'</span>';
        } else {
          cell='<code>'+esc(dev)+'</code>';
        }
        h+='<tr'+(dev===null?' class="mem-row-ign" style="opacity:.62"':'')+'><td><code>'+esc(role)+'</code></td><td>'+cell+'</td></tr>';
      });
      h+='</tbody></table>';
      if(note){ h=h.replace('<table','<div style="margin:-2px 0 6px">'+note.replace(/^ /,'')+'</div><table'); }
      box.outerHTML='<div id="instMembersList">'+h+'</div>';
    })
    .catch(function(){ var b=document.getElementById('instMembersList'); if(b) b.textContent='Could not load control modules.'; });
}
function lazyInstSim(d){
  var box=document.getElementById('instSimList'); if(!box) return;
  fetch('/em_sim?t='+encodeURIComponent(EXPORT_TOKEN)+'&e='+encodeURIComponent(d.cls)+'&tag='+encodeURIComponent(d.tag))
    .then(function(r){return r.json();})
    .then(function(j){
      var cmds=(j&&j.commands)||[];
      if(!cmds.length){ box.outerHTML='<div class="empty" id="instSimList">This EM has no command SFCs to simulate (it may be a monitor or message module).</div>'; return; }
      var h='<div class="chips">';
      cmds.forEach(function(cn){
        h+='<span class="chip sim-chip" onclick="openInstSim(\\''+esc(d.cls).replace(/\'/g,"\\\\'")+'\\',\\''+esc(d.tag).replace(/\'/g,"\\\\'")+'\\',\\''+esc(cn).replace(/\'/g,"\\\\'")+'\\')">\\u25b6 '+esc(cn)+'</span>';
      });
      h+='</div>';
      box.outerHTML='<div id="instSimList">'+h+'</div>';
    })
    .catch(function(){ var b=document.getElementById('instSimList'); if(b) b.textContent='Could not load commands.'; });
}
function openInstSim(cls, tag, cmd){
  var ov=document.getElementById('emSimOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='emSimOverlay'; ov.className='emsim-overlay'; document.body.appendChild(ov); }
  ov.innerHTML='<div class="emsim-modal"><div class="emsim-h"><b>'+esc(tag)+' \\u2014 '+esc(cmd)+' <span style="font-weight:400;color:#94a3b8">(instance devices)</span></b>'
    +'<span class="emsim-x" onclick="var o=document.getElementById(\\'emSimOverlay\\');if(o)o.remove();">\\u00d7</span></div>'
    +'<iframe class="emsim-frame" src="/em_sim?t='+encodeURIComponent(EXPORT_TOKEN)+'&e='+encodeURIComponent(cls)+'&c='+encodeURIComponent(cmd)+'&tag='+encodeURIComponent(tag)+'"></iframe></div>';
}
function lazyEm(name, stateSet){
  var box=document.getElementById('emLazy');
  fetch('/em_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(name))
    .then(function(r){return r.json();})
    .then(function(ev){
      if(!box) box=document.getElementById('emLazy');
      if(ev && !ev.error){ EM_VIEWS[name]=ev; if(box){ box.outerHTML=renderEmPanel(ev, stateSet); setTimeout(wireFbdLinks,0);} }
      else if(box){ box.innerHTML='<h3>Detail</h3><span class="empty">Could not load EM view'+(ev&&ev.error?': '+ev.error:'')+'.</span>'; }
    })
    .catch(function(){ if(box) box.innerHTML='<h3>Detail</h3><span class="empty">Could not load EM view.</span>'; });
}
function lazyFbd(name){
  var box=document.getElementById('fbdLazy');
  fetch('/fbd_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(name))
    .then(function(r){return r.json();})
    .then(function(d){
      if(!box) box=document.getElementById('fbdLazy');
      if(d && d.html){ FBD_VIEWS[name]=d.html; if(box){ box.outerHTML='<div class="card" style="max-width:none">'+d.html+'</div>'; setTimeout(function(){wireFbdLinks(); try{makeCardsCollapsible();}catch(e){}},0);} }
      else if(box){ box.innerHTML='<h3>Detail</h3><span class="empty">Could not load diagram'+(d&&d.error?': '+d.error:'')+'.</span>'; }
    })
    .catch(function(){ if(box) box.innerHTML='<h3>Detail</h3><span class="empty">Could not load diagram.</span>'; });
}
// ── flat I/O signal table (Control Network) ──
function showIoTable(ctrlFilter){ navTo({k:'iotable', ctrl:ctrlFilter||''}); }
function renderIoTable(ctrlFilter){
  var d=document.getElementById('detail'); if(!d) return;
  var rows=(DB.io_flat||[]);
  var h='<h2 class="dt">I/O Signals <span class="dt-type b-ctrl">Control Network</span></h2>';
  h+='<p class="dt-desc">Every field signal wired by a control module \\u2014 flat and filterable. '
    +'Click a signal or module to jump to it; right-click for references.</p>';
  h+='<div class="card" style="max-width:none">';
  h+='<div class="io-tbl-tools">'
    +'<input class="alias-filter" id="ioFilter" placeholder="Filter by tag, module, controller\\u2026" oninput="ioTblFilter()">'
    +'<select id="ioKindFilter" onchange="ioTblFilter()"><option value="">All types</option>'
    +'<option value="DI">DI</option><option value="DO">DO</option>'
    +'<option value="AI">AI</option><option value="AO">AO</option></select>'
    +'<span class="io-tbl-count" id="ioTblCount"></span></div>';
  h+='<table class="fbd-table io-tbl" id="ioTbl"><thead><tr>'
    +'<th>Type</th><th>Dir</th><th>Signal tag</th><th>Used by (module)</th><th>Controller</th><th>Port</th>'
    +'</tr></thead><tbody>';
  rows.forEach(function(r){
    var arrow=r.direction==='in'?'\\u2190 read':'\\u2192 write';
    var sigDep=(DB.deployed_modules&&DB.deployed_modules[r.signal_tag]);
    var sigCell=sigDep?('<span class="link" onclick="showDeployed(\\''+esc(r.signal_tag)+'\\')">'+esc(r.signal_tag)+'</span>'):('<code>'+esc(r.signal_tag)+'</code>');
    var modDep=(DB.deployed_modules&&DB.deployed_modules[r.module]);
    var modCell=modDep?('<span class="link" onclick="showDeployed(\\''+esc(r.module)+'\\')" oncontextmenu="ioCtx(event,\\''+esc(r.module)+'\\')">'+esc(r.module)+'</span>'):('<code>'+esc(r.module)+'</code>');
    h+='<tr class="io-trow" data-search="'+esc((r.signal_tag+' '+r.module+' '+r.controller+' '+r.kind).toLowerCase())+'" data-kind="'+esc(r.kind)+'">'
      +'<td><span class="io-kind io-'+esc(r.kind.toLowerCase())+'">'+esc(r.kind)+'</span></td>'
      +'<td class="io-dir">'+arrow+'</td>'
      +'<td>'+sigCell+'</td>'
      +'<td>'+modCell+'</td>'
      +'<td>'+esc(r.controller)+'</td>'
      +'<td><code>'+esc(r.port)+'</code></td></tr>';
  });
  h+='</tbody></table></div>';
  d.innerHTML=h; d.scrollTop=0;
  if(ctrlFilter){ var f=document.getElementById('ioFilter'); f.value=ctrlFilter; }
  ioTblFilter();
}
function ioTblFilter(){
  var q=(document.getElementById('ioFilter').value||'').toLowerCase();
  var k=(document.getElementById('ioKindFilter').value||'');
  var n=0, tot=0;
  document.querySelectorAll('#ioTbl tbody .io-trow').forEach(function(tr){
    tot++;
    var show=(!q || tr.getAttribute('data-search').indexOf(q)>=0) && (!k || tr.getAttribute('data-kind')===k);
    tr.style.display=show?'':'none'; if(show) n++;
  });
  var c=document.getElementById('ioTblCount'); if(c) c.textContent=n+' of '+tot+' signals';
}
// right-click a module in the I/O table -> jump to its references
function ioCtx(e, tag){ e.preventDefault(); showReferences(tag); }

// ── references: where a tag/class is used (member-of + logic refs) ──
function refCardHTML(tag){
  var usedBy=(DB.used_by&&DB.used_by[tag])||[];
  var logic=(DB.logic_xref&&DB.logic_xref[tag])||[];
  if(!usedBy.length && !logic.length) return '';
  var h='<div class="card ref-card"><h3>References <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 where this is used</span></h3>';
  if(usedBy.length){
    h+='<h4>Used as a member by ('+usedBy.length+')</h4><div class="ref-chips">';
    usedBy.forEach(function(u){
      h+='<span class="ref-chip" onclick="show(\\'em:'+esc(u.parent)+'\\')" title="member role: '+esc(u.instance||'')+'">'
        +'<span class="ic-badge ic-em" style="width:14px;height:14px"></span>'+esc(u.parent)
        +(u.instance?(' <span class="ref-role">\\u00b7 '+esc(u.instance)+'</span>'):'')+'</span>';
    });
    h+='</div>';
  }
  if(logic.length){
    h+='<h4>Referenced in logic by ('+logic.length+')</h4><div class="ref-chips">';
    logic.forEach(function(r){
      var jump = (DB.deployed_modules&&DB.deployed_modules[r.owner]) ? ('showDeployed(\\''+esc(r.owner)+'\\')')
        : (DB.objs&&DB.objs['cm:'+r.owner]) ? ('show(\\'cm:'+esc(r.owner)+'\\')')
        : (DB.objs&&DB.objs['em:'+r.owner]) ? ('show(\\'em:'+esc(r.owner)+'\\')') : '';
      // the chip body jumps to the owner; the ⤢ button opens the floating exact-use card
      h+='<span class="ref-chip'+(jump?'':' ref-nolink')+'" title="'+r.count+' reference(s)">'
        +'<span'+(jump?(' style="cursor:pointer" onclick="'+jump+'"'):'')+'>'+esc(r.owner)+'</span>'
        +' <span class="ref-cnt">\\u00d7'+r.count+'</span>'
        +' <span class="ref-uses-btn" title="Show exactly where '+esc(tag)+' is used in '+esc(r.owner)+'" '
        +'onclick="event.stopPropagation();showRefUses(\\''+esc(tag).replace(/'/g,"\\\\'")+'\\',\\''+esc(r.owner).replace(/'/g,"\\\\'")+'\\')">\\u2922 uses</span>'
        +'</span>';
    });
    h+='</div>';
  }
  h+='</div>';
  return h;
}
// ── floating "exact use" card: shows block · action · expression for one owner→tag ──
function showRefUses(tag, owner){
  var id='ruse_'+tag.replace(/[^A-Za-z0-9]/g,'_')+'__'+owner.replace(/[^A-Za-z0-9]/g,'_');
  var ex=document.getElementById(id); if(ex){ ex.remove(); return; } // toggle off if open
  var card=document.createElement('div'); card.className='ruse-card'; card.id=id;
  // cascade so multiple cards don't stack exactly
  var n=document.querySelectorAll('.ruse-card').length;
  card.style.left=(Math.min(window.innerWidth-540, 120+n*26))+'px';
  card.style.top=(90+n*26)+'px';
  card.innerHTML='<div class="ruse-h"><b>'+esc(tag)+'</b>'
    +'<span class="ruse-sub">used in '+esc(owner)+'</span>'
    +'<span class="ruse-x" title="Close" onclick="var c=document.getElementById(\\''+id+'\\');if(c)c.remove();">\\u00d7</span></div>'
    +'<div class="ruse-body"><div class="ruse-empty"><span class="dv-dots"><i></i><i></i><i></i></span> Finding exact uses\\u2026</div></div>';
  document.body.appendChild(card);
  _ruseDrag(card);
  if(typeof EXPORT_TOKEN==='undefined'||!EXPORT_TOKEN){
    card.querySelector('.ruse-body').innerHTML='<div class="ruse-empty">Exact-use lookup needs the loaded database session.</div>'; return;
  }
  fetch('/reference_uses?t='+encodeURIComponent(EXPORT_TOKEN)+'&tag='+encodeURIComponent(tag)+'&owner='+encodeURIComponent(owner))
    .then(function(r){return r.json();})
    .then(function(j){
      var body=card.querySelector('.ruse-body'); if(!body) return;
      var uses=(j&&j.uses)||[];
      if(!uses.length){ body.innerHTML='<div class="ruse-empty">No resolvable use-sites found (the reference may be through an alias or removed in this export).</div>'; return; }
      var h='';
      uses.forEach(function(u){
        h+='<div class="ruse-item">';
        if(u.context&&u.context.length){
          h+='<div class="ruse-ctx">';
          u.context.forEach(function(c){
            var sp=c.indexOf(' '); var kind=sp>0?c.slice(0,sp):''; var nm=sp>0?c.slice(sp+1):c;
            h+='<span class="ruse-crumb"><span class="rc-kind">'+esc(kind)+'</span>'+esc(nm)+'</span>';
          });
          h+='</div>';
        }
        if(u.description) h+='<div class="ruse-desc">'+esc(u.description)+'</div>';
        if(u.key) h+='<div class="ruse-key">'+esc(u.key)+'</div>';
        h+='<div class="ruse-expr">'+esc(u.line||'')+'</div>';
        h+='</div>';
      });
      body.innerHTML=h;
    })
    .catch(function(){ var b=card.querySelector('.ruse-body'); if(b) b.innerHTML='<div class="ruse-empty">Could not load use-sites.</div>'; });
}
function _ruseDrag(card){
  var hdr=card.querySelector('.ruse-h'); if(!hdr) return;
  var sx,sy,ox,oy,drag=false;
  hdr.addEventListener('mousedown',function(e){
    if(e.target.closest('.ruse-x')) return;
    drag=true; sx=e.clientX; sy=e.clientY;
    var r=card.getBoundingClientRect(); ox=r.left; oy=r.top;
    e.preventDefault();
  });
  document.addEventListener('mousemove',function(e){
    if(!drag) return;
    card.style.left=Math.max(0,Math.min(window.innerWidth-80, ox+(e.clientX-sx)))+'px';
    card.style.top=Math.max(0,Math.min(window.innerHeight-40, oy+(e.clientY-sy)))+'px';
  });
  document.addEventListener('mouseup',function(){ drag=false; });
}
// #2: floating "references" window — lists every logic use-site of a tag across all
// owners, each row showing the full expression/path and navigating to that owner on click.
function _ownerNav(owner){
  // returns a JS call string that navigates to the owning object, or '' if not openable
  if(DB.deployed_modules&&DB.deployed_modules[owner]) return "show('dep:"+owner.replace(/'/g,"\\\\'")+"')";
  if(DB.objs&&DB.objs['em:'+owner]) return "show('em:"+owner.replace(/'/g,"\\\\'")+"')";
  if(DB.objs&&DB.objs['cm:'+owner]) return "show('cm:"+owner.replace(/'/g,"\\\\'")+"')";
  if(DB.objs&&DB.objs['phase:'+owner]) return "show('phase:"+owner.replace(/'/g,"\\\\'")+"')";
  return '';
}
function showReferencesFloat(tag){
  var id='refs_'+tag.replace(/[^A-Za-z0-9]/g,'_');
  var ex=document.getElementById(id); if(ex){ ex.remove(); return; }
  var card=document.createElement('div'); card.className='ruse-card refs-card'; card.id=id;
  var n=document.querySelectorAll('.ruse-card').length;
  card.style.left=(Math.min(window.innerWidth-560, 140+n*26))+'px';
  card.style.top=(84+n*26)+'px';
  card.innerHTML='<div class="ruse-h"><b>References</b> <span class="ruse-sub">to '+esc(tag)+'</span>'
    +'<span class="ruse-x" title="Close" onclick="var c=document.getElementById(\\''+id+'\\');if(c)c.remove();">\\u00d7</span></div>'
    +'<div class="ruse-body"><div class="ruse-empty"><span class="dv-dots"><i></i><i></i><i></i></span> Finding all references\\u2026</div></div>';
  document.body.appendChild(card);
  _ruseDrag(card);
  if(typeof EXPORT_TOKEN==='undefined'||!EXPORT_TOKEN){
    card.querySelector('.ruse-body').innerHTML='<div class="ruse-empty">Reference lookup needs the loaded database session.</div>'; return;
  }
  fetch('/references_all?t='+encodeURIComponent(EXPORT_TOKEN)+'&tag='+encodeURIComponent(tag))
    .then(function(r){return r.json();})
    .then(function(j){
      var body=card.querySelector('.ruse-body'); if(!body) return;
      var groups=(j&&j.groups)||[];
      // also fold in member-usage (used_by) so the window is the full picture
      var usedBy=(DB.used_by&&DB.used_by[tag])||[];
      if(!groups.length && !usedBy.length){ body.innerHTML='<div class="ruse-empty">No references found \\u2014 this tag isn\\'t used as a member and isn\\'t referenced in any module\\'s logic.</div>'; return; }
      var h='';
      if(usedBy.length){
        h+='<div class="refs-grp"><div class="refs-grp-h">Used as a member by ('+usedBy.length+')</div>';
        usedBy.forEach(function(u){
          h+='<div class="refs-owner" onclick="show(\\'em:'+esc(u.parent)+'\\')"><span class="refs-oname">'+esc(u.parent)+'</span>'
            +(u.instance?'<span class="refs-role">role: '+esc(u.instance)+'</span>':'')+'<span class="refs-go">open \\u2192</span></div>';
        });
        h+='</div>';
      }
      groups.forEach(function(g){
        var nav=_ownerNav(g.owner);
        h+='<div class="refs-grp"><div class="refs-owner refs-owner-hd'+(nav?'':' refs-noopen')+'"'+(nav?(' onclick="'+nav+'"'):'')+'>'
          +'<span class="refs-oname">'+esc(g.owner)+'</span><span class="ref-cnt">\\u00d7'+g.count+'</span>'
          +(nav?'<span class="refs-go">open \\u2192</span>':'')+'</div>';
        (g.uses||[]).forEach(function(u){
          h+='<div class="refs-use">';
          if(u.context&&u.context.length){
            h+='<div class="ruse-ctx">';
            u.context.forEach(function(c){ var sp=c.indexOf(' '); var kind=sp>0?c.slice(0,sp):''; var nm=sp>0?c.slice(sp+1):c;
              h+='<span class="ruse-crumb"><span class="rc-kind">'+esc(kind)+'</span>'+esc(nm)+'</span>'; });
            h+='</div>';
          }
          if(u.description) h+='<div class="ruse-desc">'+esc(u.description)+'</div>';
          if(u.key) h+='<div class="ruse-key">'+esc(u.key)+'</div>';
          h+='<div class="ruse-expr">'+esc(u.line||'')+'</div></div>';
        });
        h+='</div>';
      });
      body.innerHTML=h;
    })
    .catch(function(){ var b=card.querySelector('.ruse-body'); if(b) b.innerHTML='<div class="ruse-empty">Could not load references.</div>'; });
}
function showReferences(tag){ navTo({k:'references', tag:tag}); }function renderReferences(tag){
  var d=document.getElementById('detail'); if(!d) return;
  var card=refCardHTML(tag);
  var h='<h2 class="dt">'+esc(tag)+' <span class="dt-type b-composite">References</span> '
    +'<span class="link" onclick="showTag(\\''+esc(tag)+'\\')">open object \\u2192</span></h2>';
  h+=card||'<div class="card"><span class="empty">No references found for this tag \\u2014 it isn\\'t used as a member and isn\\'t referenced in any module\\'s logic.</span></div>';
  d.innerHTML=h; d.scrollTop=0;
}
function showParam(name){ if(PARAM_INDEX[name]) navTo({k:'param',name:name}); }
function showInst(parent,tag){ var iid=parent+'\\u0001'+tag; if(DB.instances&&DB.instances[iid]) navTo({k:'inst',iid:iid}); }
function showDeployed(tag, roleAlias){ if(DB.deployed_modules&&DB.deployed_modules[tag]) navTo({k:'dep',tag:tag,role:roleAlias||''}); }
// jump to whatever a resolved alias points at: a deployed module tag, an instance,
// or a class object — whichever exists. Falls back to a no-op if not in the export.
function showTag(tag){
  if(!tag) return;
  if(DB.deployed_modules&&DB.deployed_modules[tag]){ navTo({k:'dep',tag:tag}); return; }
  // instance keyed by parent\\u0001tag
  if(DB.instances){ for(var iid in DB.instances){ if(DB.instances[iid].tag===tag){ navTo({k:'inst',iid:iid}); return; } } }
  var c=['cm:'+tag,'em:'+tag,'composite:'+tag,'uclass:'+tag];
  for(var i=0;i<c.length;i++){ if(DB.objs[c[i]]){ show(c[i]); return; } }
  // resolved to a tag not separately catalogued (e.g. a raw field device) — no nav
}
function filterAliases(){
  var f=(document.getElementById('aliasFilter')||{}).value||'';
  f=f.toLowerCase();
  var tb=document.querySelectorAll('#aliasTable tbody tr');
  tb.forEach(function(tr){ tr.style.display = tr.textContent.toLowerCase().indexOf(f)>=0 ? '' : 'none'; });
}

// link to a module by name, resolving to whatever navigable view exists for it
function modLink(name){
  var c=['em:'+name,'cm:'+name,'composite:'+name,'uclass:'+name,'phase:'+name];
  for(var i=0;i<c.length;i++){ if(DB.objs[c[i]]) return '<span class="link" onclick="show(\\''+c[i]+'\\')">'+esc(name)+'</span>'; }
  if(FBD_VIEWS[name] || (typeof FBD_NAMES!=='undefined' && FBD_NAMES.indexOf(name)>=0)) return '<span class="link" onclick="showFbd(\\''+esc(name)+'\\',\\''+esc(name)+'\\')">'+esc(name)+'</span>';
  return esc(name);
}

// ── parameter cross-reference card (database-wide) ──
function renderParam(name){
  if(!SEARCH_IDX_LOADED){
    var dd=document.getElementById('detail');
    if(dd) dd.innerHTML='<h2 class="dt">'+esc(name)+'</h2><div class="loading-detail"><span class="dv-dots"><i></i><i></i><i></i></span> Loading parameter…</div>';
    ensureSearchIndex(function(){ renderParam(name); }); return;
  }
  var v=PARAM_INDEX[name];
  document.querySelectorAll('.navitem').forEach(n=>n.classList.remove('sel'));
  var back = VIEW_STACK.length>1 ? ' <span class="link" onclick="goBack()">← back</span>' : '';
  var h='<h2 class="dt">'+esc(name)+'</h2><span class="dt-type" style="background:#0891b2">Parameter</span>';
  h+='<p class="dt-desc">Database-wide cross-reference: everywhere this parameter / signal is defined, wired, referenced, or used in logic.'+back+'</p>';
  if(!v){ h+='<div class="card"><span class="empty">No usage found.</span></div>'; document.getElementById('detail').innerHTML=h; return; }
  function tbl(title,rows,head,fn){
    if(!rows.length)return '';
    var s='<div class="card"><h3>'+title+' ('+rows.length+')</h3><table class="fbd-table"><thead><tr>'+head+'</tr></thead><tbody>';
    rows.forEach(function(r){s+='<tr>'+fn(r)+'</tr>';});
    return s+'</tbody></table></div>';
  }
  h+=tbl('Defined in', v.defs, '<th>Module</th><th>Direction</th><th>Type</th><th>Group</th><th>Reference</th>',
    function(d){return '<td>'+modLink(d.m)+'</td><td>'+esc(d.dir)+'</td><td>'+esc(d.t)+'</td><td>'+esc(d.g||'—')+'</td><td>'+(d.ref?'<code>'+esc(d.ref)+'</code>':'—')+'</td>';});
  h+=tbl('Configured values', v.vals||[], '<th>Module</th><th>Value</th>',
    function(x){return '<td>'+modLink(x.m)+'</td><td>'+(x.cv===''?'<span style="color:#94a3b8">(empty)</span>':'<code>'+esc(x.cv)+'</code>')+'</td>';});
  h+=tbl('Wired to logic', v.wires, '<th>Module</th><th>Block · Pin</th><th>Direction</th>',
    function(w){return '<td>'+modLink(w.m)+'</td><td><code>'+esc(w.blk)+'/'+esc(w.port)+'</code></td><td>'+(w.dir==='in'?'→ into block':'← from block')+'</td>';});
  h+=tbl('Referenced by', v.refs, '<th>Module</th><th>Parameter</th><th>Via reference</th>',
    function(r){return '<td>'+modLink(r.m)+'</td><td><b>'+esc(r.from)+'</b></td><td><code>'+esc(r.via)+'</code></td>';});
  h+=tbl('Used in expressions', v.exprs, '<th>Module</th><th>Block</th><th>Attribute</th><th>Kind</th>',
    function(e){return '<td>'+modLink(e.m)+'</td><td>'+esc(e.blk)+'</td><td><code>'+esc(e.attr)+'</code></td><td>'+esc(e.kind||'—')+'</td>';});
  var d=document.getElementById('detail'); d.innerHTML=h; d.scrollTop=0; try{makeCardsCollapsible();}catch(e){}
}

// jump from an instance to the class that defines its logic/parameters
function viewClass(cls){
  var c=['cm:'+cls,'composite:'+cls,'em:'+cls,'uclass:'+cls];
  for(var i=0;i<c.length;i++){ if(DB.objs[c[i]]){ show(c[i]); return; } }
  if(FBD_VIEWS[cls] || (typeof FBD_NAMES!=='undefined' && FBD_NAMES.indexOf(cls)>=0)) showFbd(cls,cls);
}

// ── CM instance card: identity + class link + siblings + inherited values ──
function renderInstance(iid){
  var d=DB.instances&&DB.instances[iid]; if(!d){return;}
  // instance parameter values come from the search index (params), which is now
  // lazily loaded — ensure it's available, then (re)render so values appear.
  if(!SEARCH_IDX_LOADED){ ensureSearchIndex(function(){ renderInstance(iid); }); }
  document.querySelectorAll('.navitem').forEach(n=>n.classList.remove('sel'));
  document.querySelectorAll('.navinst').forEach(function(n){
    n.classList.toggle('sel', n.dataset.parent+'\\u0001'+n.dataset.tag===iid);
  });
  var back = VIEW_STACK.length>1 ? ' <span class="link" onclick="goBack()">← back</span>' : '';
  var h='<h2 class="dt">'+esc(d.tag)+'</h2><span class="dt-type" style="background:#6d28d9">CM instance</span>';
  h+='<p class="dt-desc">Instance of '+modLink(d.cls)+' · in '+modLink(d.parent)+'.'+back+'</p>';
  h+='<div class="card"><h3>Identity</h3><div class="kv">';
  h+='<div class="k">Tag</div><div><code>'+esc(d.tag)+'</code></div>';
  h+='<div class="k">Class</div><div>'+modLink(d.cls)+'</div>';
  h+='<div class="k">Parent EM</div><div>'+modLink(d.parent)+'</div>';
  h+='<div class="k">Description</div><div>'+esc(d.desc||'—')+'</div>';
  h+='<div class="k">Ownership</div><div>'+esc(d.ownership||'—')+'</div>';
  if(d.category) h+='<div class="k">Category</div><div style="font-size:12px">'+esc(d.category)+'</div>';
  h+='</div>';
  h+='<button class="bigbtn" onclick="viewClass(\\''+esc(d.cls)+'\\')">View class logic &amp; parameters →</button>';
  h+='</div>';
  var sibs=(DB.parent_instances[d.parent]||[]).map(function(x){return DB.instances[x];})
            .filter(function(s){return s && s.cls===d.cls && s.tag!==d.tag;});
  if(sibs.length){
    h+='<div class="card"><h3>Sibling instances of this class ('+sibs.length+')</h3><div class="chips">';
    sibs.forEach(function(s){ h+='<span class="chip" onclick="showInst(\\''+esc(s.parent)+'\\',\\''+esc(s.tag)+'\\')">'+esc(s.tag)+'</span>'; });
    h+='</div></div>';
  }
  var vals=[];
  for(var pn in PARAM_INDEX){ (PARAM_INDEX[pn].vals||[]).forEach(function(v){ if(v.m===d.cls) vals.push({p:pn,cv:v.cv}); }); }
  if(vals.length){
    h+='<div class="card"><h3>Configured values <span style="font-weight:400;color:#94a3b8">('+vals.length+')</span></h3>';
    h+='<p class="empty" style="margin:0 0 8px">Inherited from class '+esc(d.cls)+'. This instance has no parameter overrides in the export.</p>';
    h+='<table class="fbd-table"><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>';
    vals.forEach(function(v){ h+='<tr><td><span class="link" onclick="showParam(\\''+esc(v.p)+'\\')">'+esc(v.p)+'</span></td><td>'+(v.cv===''?'<span style="color:#94a3b8">(empty)</span>':'<code>'+esc(v.cv)+'</code>')+'</td></tr>'; });
    h+='</tbody></table></div>';
  }
  var dd=document.getElementById('detail'); dd.innerHTML=h; dd.scrollTop=0; try{makeCardsCollapsible();}catch(e){}
}

// ── deployed module instance (a real tag in a unit) ──
// #6: cache of fully-loaded deployed-instance detail views, keyed by tag|role. When a
// user reopens an instance they already viewed, we restore the rendered HTML instantly
// instead of re-firing the diagram/params/logic/members fetches. The cache is captured
// when leaving a loaded dep view (see _captureDepView, called from renderEntry).
var DEP_CACHE={};
var _depViewKey=null;        // key of the dep view currently on screen (or null)
function _depKey(tag,role){ return tag+'\\u0001'+(role||''); }
// snapshot the current dep view if all its lazy cards have finished loading
function _captureDepView(){
  if(!_depViewKey) return;
  var d=document.getElementById('detail'); if(!d){ _depViewKey=null; return; }
  // consider it "loaded" once no loading spinners remain in the instance cards
  if(d.querySelector('.dv-loader, .frame-load, .loading-detail')){ _depViewKey=null; return; }
  var ml=d.querySelector('#instMembersList, #instSimList');
  // members/sim lists show plain "Loading…" text (no spinner) until fetched; treat that as not-ready
  if(ml && /Loading\\u2026/.test(ml.textContent||'')){ _depViewKey=null; return; }
  DEP_CACHE[_depViewKey]=d.innerHTML;
  _depViewKey=null;
}
function renderDeployed(tag, roleAlias){
  var d=DB.deployed_modules&&DB.deployed_modules[tag]; if(!d){return;}
  document.querySelectorAll('.navitem').forEach(n=>n.classList.remove('sel'));
  document.querySelectorAll('.navinst').forEach(function(n){n.classList.toggle('sel',n.dataset.tag===tag&&n.dataset.dep==='1');});
  var key=_depKey(tag,roleAlias);
  // restore instantly from cache if we have a fully-loaded snapshot
  if(DEP_CACHE[key]){
    var dc=document.getElementById('detail');
    if(dc){ dc.innerHTML=DEP_CACHE[key]; dc.scrollTop=0; _depViewKey=key; try{wireFbdLinks();}catch(e){} return; }
  }
  _depViewKey=key;  // mark this as the live dep view so it can be captured on exit
  var isEM=!!DB.objs['em:'+d.cls];
  var back=VIEW_STACK.length>1?' <span class="link" onclick="goBack()">← back</span>':'';
  // DeltaV convention: when reached as an EM member, show "TAG (ROLE)"
  var titleTag=esc(d.tag)+(roleAlias?' <span style="color:var(--ink-3);font-weight:400">('+esc(roleAlias)+')</span>':'');
  var h='<h2 class="dt">'+titleTag+' <span class="dt-type" style="background:'+(isEM?'#0f766e':'#6d28d9')+'">'+(isEM?'EM':'CM')+' instance</span></h2>';
  // small inline class link (per request: click the class name to open the class)
  h+='<p class="dt-desc">Instance of '+modLink(d.cls)+' \\u00b7 unit '
    +(DB.objs['unit:'+d.unit]?'<span class="link" onclick="show(\\'unit:'+esc(d.unit)+'\\')">'+esc(d.unit)+'</span>':esc(d.unit))+'.'+back+'</p>';
  h+='<details class="metabinder"><summary>Identity</summary><div class="kv">';
  h+='<div class="k">Tag</div><div><code>'+esc(d.tag)+'</code></div>';
  h+='<div class="k">Class</div><div>'+modLink(d.cls)+'</div>';
  var ctl=(DB.module_controller&&DB.module_controller[tag])||'';
  if(ctl) h+='<div class="k">Controller</div><div><code>'+esc(ctl)+'</code></div>';
  h+='<div class="k">Location</div><div><code>'+esc(d.path)+'</code></div>';
  h+='</div></details>';
  // instance diagram (its own FBD) + instance parameter values, both lazy-loaded
  h+='<div class="card" style="max-width:none" id="instDiag"><h3>Diagram</h3><div class="frame-load"><span class="dv-dots"><i></i><i></i><i></i></span> Loading diagram\\u2026</div></div>';
  h+='<div class="card" id="instParams"><h3>Instance parameters</h3><div class="loading-detail"><span class="dv-dots"><i></i><i></i><i></i></span> Loading values\\u2026</div></div>';
  // For an EM instance, the command/state LOGIC is identical to the class (an instance
  // reuses the class SFCs, just wired to different devices). Show the class command
  // logic here so the instance is self-contained (#2).
  if(isEM){
    h+='<div class="card" style="max-width:none" id="instLogic"><h3>Command logic <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 from class '+esc(d.cls)+' (shared by all instances)</span></h3><div class="frame-load"><span class="dv-dots"><i></i><i></i><i></i></span> Loading command logic\\u2026</div></div>';
    // #2/#11: command simulator lives on the INSTANCE — simulation resolves this
    // instance's actual wired CMs/aliases, which only exist at the instance level.
    h+='<div class="card" style="max-width:none" id="instSimCard"><h3>Command simulator <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 walk a command with this instance\\'s devices</span></h3><div class="empty" id="instSimList">Loading commands\\u2026</div></div>';
    h+='<div class="card" id="instMembers"><h3>Control modules <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 this instance\\'s wired devices</span></h3><div class="empty" id="instMembersList">Loading\\u2026</div></div>';
  }
  h+=refCardHTML(tag);
  var dd2=document.getElementById('detail'); dd2.innerHTML=h; dd2.scrollTop=0; try{makeCardsCollapsible();}catch(e){}
  // fetch this instance's FBD (falls back to class diagram if the instance has none)
  lazyInstDiagram(d);
  lazyInstParams(tag);
  if(isEM) lazyInstLogic(d);
  if(isEM) lazyInstSim(d);
  if(isEM) lazyInstMembers(d);
}
function lazyInstLogic(d){
  var box=document.getElementById('instLogic'); if(!box) return;
  if(typeof EXPORT_TOKEN==='undefined'||!EXPORT_TOKEN){ box.innerHTML='<h3>Command logic</h3><span class="empty">Unavailable.</span>'; return; }
  // the class EM view carries the command SFCs (state field of em_view)
  fetch('/em_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(d.cls))
    .then(function(r){return r.json();})
    .then(function(ev){
      if(ev&&ev.state){
        box.innerHTML='<h3>Command logic <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 from class '+esc(d.cls)+' (shared by all instances)</span></h3>'
          +'<iframe class="phaseframe" srcdoc="'+ev.state.replace(/&/g,"&amp;").replace(/"/g,"&quot;")+'"></iframe>';
      } else {
        box.innerHTML='<h3>Command logic</h3><span class="empty">This EM class has no command SFC logic (it may be a monitor or message module).</span>';
      }
    })
    .catch(function(){ box.innerHTML='<h3>Command logic</h3><span class="empty">Could not load command logic.</span>'; })
    .finally(function(){ try{ makeCardsCollapsible(); }catch(e){} });
}
function lazyInstDiagram(d){
  var box=document.getElementById('instDiag'); if(!box) return;
  if(typeof EXPORT_TOKEN==='undefined'||!EXPORT_TOKEN){ box.innerHTML='<h3>Diagram</h3><span class="empty">No diagram available.</span>'; return; }
  // try the instance tag first, then the class (many CMs render from the class definition)
  fetch('/fbd_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(d.tag))
    .then(function(r){return r.json();})
    .then(function(x){
      if(x&&x.html){ box.innerHTML='<h3>Diagram</h3>'+x.html; setTimeout(wireFbdLinks,0); try{makeCardsCollapsible();}catch(e){} return; }
      return fetch('/fbd_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(d.cls))
        .then(function(r){return r.json();})
        .then(function(y){
          if(y&&y.html){ box.innerHTML='<h3>Diagram <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 from class '+esc(d.cls)+'</span></h3>'+y.html; setTimeout(wireFbdLinks,0); }
          else box.innerHTML='<h3>Diagram</h3><span class="empty">No function block diagram for this instance or its class.</span>';
          try{makeCardsCollapsible();}catch(e){}
        });
    })
    .catch(function(){ box.innerHTML='<h3>Diagram</h3><span class="empty">Could not load diagram.</span>'; });
}
function lazyInstParams(tag){
  var box=document.getElementById('instParams'); if(!box) return;
  if(typeof EXPORT_TOKEN==='undefined'||!EXPORT_TOKEN){ box.innerHTML='<h3>Instance parameters</h3><span class="empty">Unavailable.</span>'; return; }
  fetch('/inst_params?t='+encodeURIComponent(EXPORT_TOKEN)+'&tag='+encodeURIComponent(tag))
    .then(function(r){return r.json();})
    .then(function(x){
      var pp=(x&&x.params)||[];
      if(!pp.length){ box.innerHTML='<h3>Instance parameters</h3><span class="empty">No instance-level parameter overrides in this export (values inherited from the class).</span>'; return; }
      var h='<h3>Instance parameters ('+pp.length+') <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 configured values for this tag</span></h3>';
      h+='<input class="alias-filter" id="ipFilter" placeholder="filter\\u2026" oninput="filterInstParams()">';
      h+='<table class="fbd-table" id="ipTable"><thead><tr><th>Parameter</th><th>Value</th><th>Type</th></tr></thead><tbody>';
      pp.forEach(function(p,i){
        var v=String(p.value==null?'':p.value);
        var valCell;
        // #9: enum param whose set is defined in the export -> dropdown with the
        // instance's value pre-selected, showing all valid options.
        var setName=(p.set||'').replace(/^\\$/,'');
        var nset=(DB.named_sets&&(DB.named_sets[setName]||DB.named_sets[p.set]))||null;
        if(p.kind==='enum' && nset && nset.entries && nset.entries.length){
          var opts='';
          var matched=false;
          nset.entries.forEach(function(e){
            var sel=(String(e.name)===v||String(e.value)===v)?' selected':'';
            if(sel) matched=true;
            opts+='<option value="'+esc(e.name)+'"'+sel+'>'+esc(e.name)+' ('+e.value+')</option>';
          });
          if(!matched && v!=='') opts='<option selected>'+esc(v)+'</option>'+opts;
          valCell='<select class="ip-enum" disabled title="Instance value (enum set '+esc(setName)+')">'+opts+'</select>';
        }
        else if(v===''){ valCell='<span class="ip-default" title="No instance override — value inherited from the class default">default</span>'; }
        else if(v.length>44){
          valCell='<code>'+esc(v.slice(0,44))+'\\u2026</code> <span class="ip-more" onclick="ipPop('+i+')" title="Show full value">show</span>';
        } else {
          valCell='<code>'+esc(v)+'</code>';
        }
        var badge=p.override?' <span class="ov-badge" title="Explicit instance override">ovr</span>':'';
        window._IP=window._IP||{}; window._IP[i]={name:p.name,value:v,kind:p.kind,set:p.set};
        h+='<tr><td><code>'+esc(p.name)+'</code>'+badge+'</td><td>'+valCell+'</td><td style="color:var(--ink-3);font-size:12px">'+esc(p.kind||'')+(p.set?' \\u00b7 '+esc(p.set):'')+'</td></tr>';
      });
      h+='</tbody></table>';
      box.innerHTML=h;
    })
    .catch(function(){ box.innerHTML='<h3>Instance parameters</h3><span class="empty">Could not load values.</span>'; });
}
function filterInstParams(){
  var f=((document.getElementById('ipFilter')||{}).value||'').toLowerCase();
  document.querySelectorAll('#ipTable tbody tr').forEach(function(tr){ tr.style.display=tr.textContent.toLowerCase().indexOf(f)>=0?'':'none'; });
}
// pop-out for a long instance-parameter value (expression, wiring, state mask)
function ipPop(i){
  var d=(window._IP||{})[i]; if(!d) return;
  var ov=document.getElementById('ipPopOver');
  if(!ov){ ov=document.createElement('div'); ov.id='ipPopOver'; ov.className='ip-pop-overlay'; ov.onclick=function(e){ if(e.target===ov) ov.remove(); }; document.body.appendChild(ov); }
  ov.innerHTML='<div class="ip-pop"><div class="ip-pop-h"><code>'+esc(d.name)+'</code>'
    +'<span class="ip-pop-x" onclick="var o=document.getElementById(\\'ipPopOver\\');if(o)o.remove();">\\u00d7</span></div>'
    +'<div class="ip-pop-meta">'+esc(d.kind||'')+(d.set?' \\u00b7 set '+esc(d.set):'')+'</div>'
    +'<pre class="ip-pop-val">'+esc(d.value)+'</pre></div>';
}

// FBD composite drill-down: clicking a composite block/link shows its diagram.
function renderFbd(defName, label){
  const d=document.getElementById('detail');
  function paint(){
    let h='<h2 class="dt">'+esc(label||defName)+'</h2>';
    h+='<span class="dt-type b-composite">Composite Definition</span>';
    const back = VIEW_STACK.length>1 ? ' <span class="link" onclick="goBack()">← back</span>' : '';
    h+='<p class="dt-desc">Nested composite inside the parent module.'+back+'</p>';
    h+='<div class="card" style="max-width:none">'+FBD_VIEWS[defName]+'</div>';
    d.innerHTML=h; d.scrollTop=0; wireFbdLinks(); try{makeCardsCollapsible();}catch(e){}
  }
  if(FBD_VIEWS[defName]){ paint(); return; }
  if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
    d.innerHTML='<h2 class="dt">'+esc(label||defName)+'</h2><p class="dt-desc"><span class="empty">Loading diagram…</span></p>';
    fetch('/fbd_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(defName))
      .then(function(r){return r.json();})
      .then(function(x){ if(x&&x.html){ FBD_VIEWS[defName]=x.html; paint(); }
        else { d.innerHTML='<p class="dt-desc"><span class="empty">Could not load diagram.</span></p>'; } })
      .catch(function(){ d.innerHTML='<p class="dt-desc"><span class="empty">Could not load diagram.</span></p>'; });
  }
}
function emTab(btn,which){
  const card=btn.closest('.card');
  card.querySelectorAll('.emtab').forEach(t=>t.classList.toggle('on',t===btn));
  card.querySelectorAll('.empanel').forEach(p=>p.classList.toggle('on',p.dataset.e===which));
  if(which==='fb') wireFbdLinks();
}
// phase view uses the same tabbed card structure (Interactive Logic / State Model)
function phaseTab(btn,which){
  const card=btn.closest('.card');
  card.querySelectorAll('.emtab').forEach(t=>t.classList.toggle('on',t===btn));
  card.querySelectorAll('.empanel').forEach(p=>p.classList.toggle('on',p.dataset.e===which));
}
function wireFbdLinks(){
  document.querySelectorAll('.fbd-comp-link').forEach(el=>{
    el.onclick=()=>{ const def=el.getAttribute('data-fbd'); showFbd(def, el.textContent); };
  });
  // also make composite blocks in the SVG clickable
  document.querySelectorAll('.fb-composite').forEach(g=>{
    const def=g.getAttribute('data-composite');
    if(def && FBD_VIEWS[def]){ g.style.cursor='pointer'; g.onclick=()=>showFbd(def, g.getAttribute('data-name')); }
  });
}
"""
    # Escape '</' as '<\/' in the embedded JSON so the HTML parser doesn't see a
    # closing </script> when the data (e.g. an embedded phase-viewer HTML)
    # contains its own </script> tags. In JSON/JS strings '\/' is a valid escape
    # for '/', so the data round-trips identically; only the HTML parser's naive
    # tag scan is affected.
    def _script_safe(s):
        return s.replace('</', '<\\/')
    js = (js.replace('__DATA__', _script_safe(data_json))
            .replace('__PHASE_VIEWS__', _script_safe(phase_views_json))
            .replace('__PHASE_NAMES__', _script_safe(phase_names_json))
            .replace('__FBD_NAMES__', _script_safe(fbd_names_json))
            .replace('__EM_NAMES__', _script_safe(em_names_json))
            .replace('__FBD_VIEWS__', _script_safe(fbd_views_json))
            .replace('__EM_VIEWS__', _script_safe(em_views_json))
            .replace('__RECIPE_VIEWS__', _script_safe(recipe_views_json))
            .replace('__RECIPE_STEP_VIEWS__', _script_safe(json.dumps(recipe_step_views or {})))
            .replace('__PARAM_INDEX__', _script_safe(param_index_json))
            .replace('__EXPR_INDEX__', _script_safe(expr_index_json)))

    # ── build nav tree ──
    nav = []
    nav.append('<div class="navsearch"><input id="navq" autocomplete="off" '
               'placeholder="Search names, logic, values…" '
               'oninput="navSearch(this.value)" onkeydown="navSearchKey(event)">'
               '<div class="navmode">'
               '<button class="nm-btn active" onclick="navMode(this,\'names\')">Names</button>'
               '<button class="nm-btn" onclick="navMode(this,\'expr\')">Expressions</button>'
               '<button class="nm-btn" onclick="navMode(this,\'values\')">Values</button>'
               '</div>'
               '<div id="navres" class="navres" style="display:none"></div></div>')
    # ── data maps for the tree ──
    area_tree = catalog.get('area_tree', {})
    unit_instances = catalog.get('unit_instances', {})
    deployed = catalog.get('deployed_modules', {})
    unit_modules = catalog.get('unit_modules', {})
    ungrouped_modules = catalog.get('ungrouped_modules', {})
    ucph = catalog.get('unit_class_phases', {})
    em_class_names = {e['name'] for e in catalog['em_classes']}
    parent_instances = catalog.get('parent_instances', {})
    instances = catalog.get('instances', {})
    sec_id = [0]

    def _fold(title, collapsed=True, count=None):
        sec_id[0] += 1
        fid = f'fold{sec_id[0]}'
        arrow = '\u25b8' if collapsed else '\u25be'
        disp = 'none' if collapsed else 'block'
        cnt = f' <span class="navcount">{count}</span>' if count is not None else ''
        nav.append(f'<div class="navfolder navsec-tog" onclick="secToggle(\'{fid}\',this)">'
                   f'<span class="secarrow">{arrow}</span> {html.escape(title)}{cnt}</div>')
        nav.append(f'<div class="navfoldbody" id="{fid}" style="display:{disp}">')

    def _endfold():
        nav.append('</div>')

    def _ph(title):
        nav.append(f'<div class="navph" title="No data for this section in this export">'
                   f'{html.escape(title)}</div>')

    def _items(items, prefix):
        for it in sorted(items, key=lambda x: x['name']):
            nav.append(f'<div class="navitem" data-id="{prefix}:{html.escape(it["name"])}" '
                       f'onclick="show(\'{prefix}:{html.escape(it["name"])}\')" title="{html.escape(it["name"])}">'
                       f'{_nav_badge(prefix)}{html.escape(it["name"])}</div>')

    def _ncls(lvl):
        return '' if lvl <= 0 else ('navchild' if lvl == 1 else f'navchild{lvl}')

    def _unit_node(un, lvl=1):
        ui = unit_instances.get(un, {})
        ucls = ui.get('cls', '')
        mods = unit_modules.get(un, [])
        phs = ucph.get(ucls, [])
        nav.append('<div class="navgroup">')
        nav.append(f'<div class="navitem {_ncls(lvl)} navinst" data-id="unit:{html.escape(un)}" '
                   f'onclick="show(\'unit:{html.escape(un)}\')">'
                   f'<span class="tog" onclick="toggle(this,event)">\u25b8</span>'
                   f'{_nav_badge("unit")}<span class="inst-tag">{html.escape(un)}</span>'
                   f'<span class="inst-cls">({html.escape(ucls)})</span></div>')
        nav.append('<div class="navchildren" style="display:none">')
        # #7: an "Aliases" child object under the unit (mirrors the unit's alias card)
        _ui = (catalog.get('unit_instances', {}) or {}).get(un, {})
        if _ui.get('aliases'):
            nav.append(f'<div class="navitem {_ncls(lvl + 1)}" data-id="aliases:{html.escape(un)}" '
                       f'onclick="showAliases(\'{html.escape(un)}\')">'
                       f'{_nav_badge("nset")}Aliases '
                       f'<span class="inst-cls">({len(_ui["aliases"])})</span></div>')
        for tag in mods:
            d = deployed.get(tag, {})
            cls = d.get('cls', '')
            is_em = cls in em_class_names
            key = 'em' if is_em else 'inst'
            child_iids = parent_instances.get(cls, []) if is_em else []
            if child_iids:
                _mmap = (catalog.get('em_member_maps', {}) or {}).get(tag, {})
                nav.append('<div class="navgroup">')
                nav.append(f'<div class="navitem {_ncls(lvl + 1)} navinst" data-tag="{html.escape(tag)}" data-dep="1" '
                           f'onclick="showDeployed(this.dataset.tag)" title="{html.escape(tag)} ({html.escape(cls)})">'
                           f'<span class="tog" onclick="toggle(this,event)">\u25b8</span>'
                           f'{_nav_badge(key)}<span class="inst-tag">{html.escape(tag)}</span>'
                           f'<span class="inst-cls">({html.escape(cls)})</span></div>')
                nav.append('<div class="navchildren" style="display:none">')
                for iid in child_iids:
                    ins = instances.get(iid, {})
                    itag, icls = ins.get('tag', ''), ins.get('cls', '')
                    own = (ins.get('ownership') or '').upper()
                    own_ico = _ownership_nav_ico(own)
                    # #4: resolve the member role (itag, e.g. PRESS_INLET_VLV, defined on
                    # the EM class) to the ACTUAL deployed module tag (FP005-HV-001) via
                    # this EM instance's member map, and open that real instance.
                    real = _mmap.get(itag)
                    if real:
                        nav.append(f'<div class="navitem {_ncls(lvl + 2)} navinst" '
                                   f'data-tag="{html.escape(real)}" data-dep="1" data-role="{html.escape(itag)}" '
                                   f'onclick="showDeployed(this.dataset.tag, this.dataset.role)" '
                                   f'title="{html.escape(real)} ({html.escape(itag)} \u2014 instance of {html.escape(icls)}){(" · "+own.title()) if own else ""}">'
                                   f'{_nav_badge("inst", own)}<span class="inst-tag">{html.escape(real)}</span>{own_ico}'
                                   f'<span class="inst-cls">({html.escape(itag)})</span></div>')
                    else:
                        nav.append(f'<div class="navitem {_ncls(lvl + 2)} navinst" '
                                   f'data-parent="{html.escape(cls)}" data-tag="{html.escape(itag)}" '
                                   f'onclick="showInst(this.dataset.parent,this.dataset.tag)" '
                                   f'title="{html.escape(itag)} (instance of {html.escape(icls)}){(" · "+own.title()) if own else ""}">'
                                   f'{_nav_badge("inst", own)}<span class="inst-tag">{html.escape(itag)}</span>{own_ico}'
                                   f'<span class="inst-cls">({html.escape(icls)})</span></div>')
                nav.append('</div></div>')
            else:
                nav.append(f'<div class="navitem {_ncls(lvl + 1)} navinst" data-tag="{html.escape(tag)}" data-dep="1" '
                           f'onclick="showDeployed(this.dataset.tag)" title="{html.escape(tag)} ({html.escape(cls)})">'
                           f'{_nav_badge(key)}<span class="inst-tag">{html.escape(tag)}</span>'
                           f'<span class="inst-cls">({html.escape(cls)})</span></div>')
        for ph in phs:
            nav.append(f'<div class="navitem {_ncls(lvl + 1)}" data-uphase="{html.escape(un)}\u241f{html.escape(ph)}" '
                       f'onclick="showUnitPhase(\'{html.escape(un)}\',\'{html.escape(ph)}\')" '
                       f'title="{html.escape(ph)} on unit {html.escape(un)} \u2014 simulate with resolved aliases">'
                       f'{_nav_badge("phase")}{html.escape(ph)}</div>')
        nav.append('</div></div>')

    def _ungrouped_node(area, cell, lvl=1):
        # #3: render deployed modules that live under an area/cell but no unit, as a
        # collapsible "Modules (no unit)" node so they're reachable in the Explorer.
        key = f'{area}\u241f{cell}'
        tags = ungrouped_modules.get(key, [])
        if not tags:
            return
        nav.append('<div class="navgroup">')
        nav.append(f'<div class="navitem {_ncls(lvl)} navinst" style="cursor:pointer" '
                   f'onclick="toggle(this.firstElementChild,event)" '
                   f'title="Modules deployed here with no equipment unit">'
                   f'<span class="tog">\u25b8</span>'
                   f'{_nav_badge("unit")}<span class="inst-tag">Modules (no unit)</span>'
                   f'<span class="inst-cls">({len(tags)})</span></div>')
        nav.append('<div class="navchildren" style="display:none">')
        for tag in tags:
            d = deployed.get(tag, {})
            cls = d.get('cls', '')
            is_em = cls in em_class_names
            key2 = 'em' if is_em else 'inst'
            nav.append(f'<div class="navitem {_ncls(lvl + 1)} navinst" data-tag="{html.escape(tag)}" data-dep="1" '
                       f'onclick="showDeployed(this.dataset.tag)" title="{html.escape(tag)} ({html.escape(cls)})">'
                       f'{_nav_badge(key2)}<span class="inst-tag">{html.escape(tag)}</span>'
                       f'<span class="inst-cls">({html.escape(cls)})</span></div>')
        nav.append('</div></div>')

    def _unit_class_node(uc):
        ucn = uc['name']
        uphs = ucph.get(ucn, [])
        if uphs:
            nav.append('<div class="navgroup">')
            nav.append(f'<div class="navitem" data-id="uclass:{html.escape(ucn)}" '
                       f'onclick="show(\'uclass:{html.escape(ucn)}\')">'
                       f'<span class="tog" onclick="toggle(this,event)">\u25b8</span>'
                       f'{_nav_badge("uclass")}{html.escape(ucn)}</div>')
            nav.append('<div class="navchildren" style="display:none">')
            for ph in uphs:
                nav.append(f'<div class="navitem navchild" data-id="phase:{html.escape(ph)}" '
                           f'onclick="show(\'phase:{html.escape(ph)}\')">'
                           f'{_nav_badge("phase")}{html.escape(ph)}</div>')
            nav.append('</div></div>')
        else:
            nav.append(f'<div class="navitem" data-id="uclass:{html.escape(ucn)}" '
                       f'onclick="show(\'uclass:{html.escape(ucn)}\')">'
                       f'{_nav_badge("uclass")}{html.escape(ucn)}</div>')

    def _em_node(em):
        ename = em['name']
        iids = parent_instances.get(ename, [])
        if iids:
            nav.append('<div class="navgroup">')
            nav.append(f'<div class="navitem" data-id="em:{html.escape(ename)}" '
                       f'onclick="show(\'em:{html.escape(ename)}\')">'
                       f'<span class="tog" onclick="toggle(this,event)">\u25b8</span>'
                       f'{_nav_badge("em")}{html.escape(ename)}</div>')
            nav.append('<div class="navchildren" style="display:none">')
            for iid in iids:
                inst = instances.get(iid, {})
                tag, cls = inst.get('tag', ''), inst.get('cls', '')
                own = (inst.get('ownership') or '').upper()
                own_ico = _ownership_nav_ico(own)
                nav.append(f'<div class="navitem navchild navinst" '
                           f'data-parent="{html.escape(ename)}" data-tag="{html.escape(tag)}" '
                           f'onclick="showInst(this.dataset.parent,this.dataset.tag)" '
                           f'title="{html.escape(tag)} (instance of {html.escape(cls)}){(" · "+own.title()) if own else ""}">'
                           f'{_nav_badge("inst")}<span class="inst-tag">{html.escape(tag)}</span>{own_ico}'
                           f'<span class="inst-cls">({html.escape(cls)})</span></div>')
            nav.append('</div></div>')
        else:
            nav.append(f'<div class="navitem" data-id="em:{html.escape(ename)}" '
                       f'onclick="show(\'em:{html.escape(ename)}\')">'
                       f'{_nav_badge("em")}{html.escape(ename)}</div>')

    # ===================== LIBRARY =====================
    _fold('Library', collapsed=False)
    _ph('Device Definitions')
    _ph('Device Templates')
    if catalog['fb_types']:
        _fold('Function Block Templates', collapsed=True, count=len(catalog['fb_types']))
        _items(catalog['fb_types'], 'fbtype'); _endfold()
    else:
        _ph('Function Block Templates')
    class_comps = [c for c in catalog['composites'] if c.get('scope') == 'class']
    if class_comps:
        _fold('Composite Templates', collapsed=True, count=len(class_comps))
        for c in sorted(class_comps, key=lambda x: x['name']):
            nav.append(f'<div class="navitem" data-id="composite:{html.escape(c["name"])}" '
                       f'onclick="show(\'composite:{html.escape(c["name"])}\')" title="{html.escape(c["name"])}">'
                       f'{_nav_badge("composite")}{html.escape(c["name"])}</div>')
        _endfold()
    else:
        _ph('Composite Templates')
    _ph('Module Templates')
    _ph('I/O Studio Library')
    _fold('Advanced Definitions', collapsed=False)
    _ph('Process Cell Classes')
    _ph('Equipment Train Classes')
    if catalog['unit_classes']:
        _fold('Unit Classes', collapsed=False, count=len(catalog['unit_classes']))
        for uc in sorted(catalog['unit_classes'], key=lambda x: x['name']):
            _unit_class_node(uc)
        _endfold()
    else:
        _ph('Unit Classes')
    if catalog['em_classes']:
        _fold('Equipment Module Classes', collapsed=False, count=len(catalog['em_classes']))
        for em in sorted(catalog['em_classes'], key=lambda x: x['name']):
            _em_node(em)
        _endfold()
    else:
        _ph('Equipment Module Classes')
    if catalog['cm_classes']:
        _fold('Control Module Classes', collapsed=True, count=len(catalog['cm_classes']))
        _items(catalog['cm_classes'], 'cm'); _endfold()
    else:
        _ph('Control Module Classes')
    if catalog['phase_classes']:
        _fold('Phase Classes', collapsed=True, count=len(catalog['phase_classes']))
        groups = {}
        for ph in catalog['phase_classes']:
            seg = (ph.get('category', '') or '').rstrip('/').split('/')[-1] or 'General'
            groups.setdefault(seg, []).append(ph)
        if len(groups) > 1 or (len(groups) == 1 and next(iter(groups)) != 'General'):
            for g in sorted(groups):
                _fold(g, collapsed=True, count=len(groups[g]))
                _items(groups[g], 'phase'); _endfold()
        else:
            _items(catalog['phase_classes'], 'phase')
        _endfold()
    else:
        _ph('Phase Classes')
    _endfold()  # Advanced Definitions
    _endfold()  # Library

    # ================ SYSTEM CONFIGURATION ================
    _fold('System Configuration', collapsed=False)
    if catalog['recipes']:
        # #2: split recipes into Procedure / Unit Procedure / Operation categories,
        # nesting referenced children under their parent (a Procedure lists its Unit
        # Procedures, a Unit Procedure lists its Operations, an Operation its Phases).
        _recipe_cat_labels = {'PROCEDURE': 'Procedures', 'UNIT_PROCEDURE': 'Unit Procedures',
                              'OPERATION': 'Operations'}
        _by_type = {'PROCEDURE': [], 'UNIT_PROCEDURE': [], 'OPERATION': []}
        for r in catalog['recipes']:
            t = (r.get('type') or 'PROCEDURE').upper()
            _by_type.setdefault(t if t in _by_type else 'PROCEDURE', []).append(r)
        # child links: parent recipe name -> [{'name','layer','loaded'}] for every
        # step definition it references — even ones not (yet) imported, so the full
        # hierarchy is visible as soon as the parent loads (see #1 fix above).
        _rlinks = catalog.get('recipe_children', {})
        _fold('Recipes', collapsed=True, count=len(catalog['recipes']))
        for _t in ('PROCEDURE', 'UNIT_PROCEDURE', 'OPERATION'):
            group = _by_type.get(_t, [])
            if not group:
                continue
            _fold(_recipe_cat_labels[_t], collapsed=True, count=len(group))
            for r in group:
                kids = _rlinks.get(r['name'], [])
                if kids:
                    _bases = {}
                    for k in kids:
                        _bases[k['name']] = _bases.get(k['name'], False) or k['loaded']
                    n_loaded = sum(1 for v in _bases.values() if v)
                    nav.append('<div class="navgroup">')
                    nav.append(f'<div class="navitem" data-id="recipe:{html.escape(r["name"])}" '
                               f'onclick="show(\'recipe:{html.escape(r["name"])}\')">'
                               f'<span class="tog" onclick="toggle(this,event)">\u25b8</span>'
                               f'{_nav_badge("recipe")}{html.escape(r["name"])}'
                               f'<span class="inst-cls">({n_loaded}/{len(_bases)} imported)</span></div>')
                    nav.append('<div class="navchildren" style="display:none">')
                    for kid in kids:
                        if kid['loaded']:
                            nav.append(f'<div class="navitem navchild" data-id="recipe:{html.escape(kid["name"])}" '
                                       f'onclick="show(\'recipe:{html.escape(kid["name"])}\')">'
                                       f'{_nav_badge("recipe")}{html.escape(kid["step"])} '
                                       f'<span class="inst-cls">({html.escape(kid["layer"])})</span></div>')
                        elif kid.get('has_params'):
                            # not imported, but its parameters are derivable from the
                            # parent step — clicking shows that derived parameter view.
                            nav.append(f'<div class="navitem navchild navghost" '
                                       f'title="Parameters derived from the parent step; import its FHX for full detail" '
                                       f'onclick="showRecipeStep(\'{html.escape(r["name"], quote=True)}\',\'{html.escape(kid["step"], quote=True)}\',\'{html.escape(kid["layer"], quote=True)}\')">'
                                       f'{_nav_badge("recipe")}{html.escape(kid["step"])} '
                                       f'<span class="inst-cls">({html.escape(kid["layer"])})</span></div>')
                        else:
                            nav.append(f'<div class="navitem navchild navghost" '
                                       f'title="Not imported yet \\u2014 append its FHX export to explore it" '
                                       f'onclick="promptImportChild(\'{html.escape(kid["name"], quote=True)}\',\'{html.escape(kid["layer"], quote=True)}\')">'
                                       f'{_nav_badge("recipe")}{html.escape(kid["step"])} '
                                       f'<span class="inst-cls">({html.escape(kid["layer"])} \u2014 not imported)</span></div>')
                    nav.append('</div></div>')
                else:
                    nav.append(f'<div class="navitem" data-id="recipe:{html.escape(r["name"])}" '
                               f'onclick="show(\'recipe:{html.escape(r["name"])}\')">'
                               f'{_nav_badge("recipe")}{html.escape(r["name"])}</div>')
            _endfold()
        _endfold()
    else:
        _ph('Recipes')
    nsets = catalog.get('named_sets', [])
    if nsets:
        _fold('Setup', collapsed=False)
        _fold('Named Sets', collapsed=True, count=len(nsets))
        _items(nsets, 'nset')
        _endfold()
        _endfold()
    else:
        _ph('Setup')
    _fold('Control Strategies', collapsed=False)
    _ph('Unassigned I/O References')
    _ph('Unallocated Devices')
    _ph('External Phases')
    _ph('Equipment Trains')
    if area_tree:
        for aname in sorted(area_tree):
            cells = area_tree[aname]
            nav.append('<div class="navgroup">')
            nav.append(f'<div class="navitem" data-id="area:{html.escape(aname)}" '
                       f'onclick="show(\'area:{html.escape(aname)}\')">'
                       f'<span class="tog" onclick="toggle(this,event)">\u25be</span>'
                       f'{_nav_badge("area")}{html.escape(aname)}</div>')
            nav.append('<div class="navchildren">')
            for cell in sorted(cells):
                if cell:
                    # process cell -> collapsible parent; its units nest underneath
                    nav.append('<div class="navgroup">')
                    nav.append(f'<div class="navitem navchild" style="cursor:pointer" '
                               f'onclick="toggle(this.firstElementChild,event)" '
                               f'title="{html.escape(cell)} (process cell)">'
                               f'<span class="tog">\u25be</span>'
                               f'{_nav_badge("cell")}<span class="inst-tag">{html.escape(cell)}</span>'
                               f'<span class="inst-cls">· process cell</span></div>')
                    nav.append('<div class="navchildren">')
                    for un in cells[cell]:
                        _unit_node(un, lvl=2)
                    _ungrouped_node(aname, cell, lvl=2)
                    nav.append('</div></div>')
                else:
                    for un in cells[cell]:
                        _unit_node(un, lvl=1)
                    _ungrouped_node(aname, cell, lvl=1)
            nav.append('</div></div>')
    elif catalog['areas']:
        for a in catalog['areas']:
            if not a['units']:
                continue
            nav.append('<div class="navgroup">')
            nav.append(f'<div class="navitem" data-id="area:{html.escape(a["name"])}" '
                       f'onclick="show(\'area:{html.escape(a["name"])}\')">'
                       f'<span class="tog" onclick="toggle(this,event)">\u25be</span>'
                       f'{_nav_badge("area")}{html.escape(a["name"])}</div>')
            nav.append('<div class="navchildren">')
            for u in a['units']:
                nav.append(f'<div class="navitem navchild" data-id="unit:{html.escape(u["name"])}" '
                           f'onclick="show(\'unit:{html.escape(u["name"])}\')">'
                           f'{_nav_badge("unit")}{html.escape(u["name"])}</div>')
            nav.append('</div></div>')
    else:
        _ph('(no areas in this export)')
    _endfold()  # Control Strategies
    ctrls = catalog.get('controllers', {})
    if ctrls:
        _fold('Physical Network', collapsed=False)
        _ph('Decommissioned Nodes')
        # Control Network: a flat, filterable I/O signal table (no CM grouping — that
        # would duplicate Control Strategies). Clicking opens the full table in the
        # detail pane; the nav shows a per-controller signal count.
        io_flat = catalog.get('io_flat', []) or []
        _fold('Control Network', collapsed=False)
        nav.append('<div class="nav-note">Every field I/O signal, flat and filterable. '
                   'The control modules themselves live under Control Strategies.</div>')
        nav.append(f'<div class="navitem navchild io-open" onclick="showIoTable()" '
                   f'title="Open the full I/O signal table">'
                   f'{_nav_badge("ctrl")}<span class="inst-tag">All I/O signals</span>'
                   f'<span class="inst-cls">({len(io_flat)})</span></div>')
        from collections import Counter as _Counter
        by_ctrl = _Counter(r['controller'] for r in io_flat)
        for cn in sorted(by_ctrl):
            nav.append(f'<div class="navitem navchild2 io-open" '
                       f'onclick="showIoTable({html.escape(json.dumps(cn), quote=True)})" '
                       f'title="Open I/O for {html.escape(cn)}">'
                       f'\u2937 <span class="inst-tag">{html.escape(cn)}</span>'
                       f'<span class="inst-cls">({by_ctrl[cn]})</span></div>')
        _endfold()  # Control Network
        _endfold()  # Physical Network
    else:
        _ph('Physical Network')

    # ── Unit Tools (analysis built on the parsed model) ──
    _fold('Unit Tools', collapsed=True)
    nav.append('<div class="navitem" data-id="tool:aliasval" '
               'onclick="showAliasValidator()" title="Validate that every alias used '
               'in each unit\u2019s phases resolves to a deployed device">'
               + _nav_badge('unit') + 'Alias resolution validator</div>')
    _endfold()  # Unit Tools

    # ── DeviceNet I/O (only when the export carries hardware records) ──
    if catalog.get('has_devicenet'):
        _fold('I/O Devices', collapsed=True)
        nav.append('<div class="navitem" data-id="io:devicenet" '
                   'onclick="showIoDevices()" title="DeviceNet hardware: controllers, '
                   'cards, ports, devices and their signals">'
                   + _nav_badge('cm') + 'DeviceNet devices</div>')
        _endfold()  # I/O Devices
    _endfold()  # System Configuration

    # ── standalone Recipes workspace (rail view, like the Converter) ──
    # A focused recipe browser: category-grouped list on the left, the same recipe
    # views on the right, with Excel exports front and center.
    rp = []
    _rp_cats = {'PROCEDURE': 'Procedures', 'UNIT_PROCEDURE': 'Unit Procedures',
                'OPERATION': 'Operations'}
    _rp_by_type = {'PROCEDURE': [], 'UNIT_PROCEDURE': [], 'OPERATION': []}
    for r in catalog.get('recipes', []):
        t = (r.get('type') or 'PROCEDURE').upper()
        _rp_by_type.setdefault(t if t in _rp_by_type else 'PROCEDURE', []).append(r)
    _rp_links = catalog.get('recipe_children', {})
    if catalog.get('recipes'):
        for _t in ('PROCEDURE', 'UNIT_PROCEDURE', 'OPERATION'):
            grp = _rp_by_type.get(_t, [])
            if not grp:
                continue
            rp.append('<div class="rec-cat">' + _rp_cats[_t] + ' (' + str(len(grp)) + ')</div>')
            for r in grp:
                kids = _rp_links.get(r['name'], [])
                _bases = {}
                for k in kids:
                    _bases[k['name']] = _bases.get(k['name'], False) or k['loaded']
                sub = (' <span class="inst-cls">(' + str(sum(1 for v in _bases.values() if v))
                       + '/' + str(len(_bases)) + ' children imported)</span>') if _bases else ''
                rp.append('<div class="navitem rec-item" data-rec="' + html.escape(r['name'], quote=True) + '" '
                          'onclick="recShow(\'' + html.escape(r['name'], quote=True) + '\')">'
                          + _nav_badge('recipe') + html.escape(r['name']) + sub + '</div>')
                for k in kids:
                    if k.get('has_params') and not k['loaded']:
                        rp.append('<div class="navitem navchild navghost rec-item" '
                                  'onclick="recShowStep(\'' + html.escape(r['name'], quote=True) + '\',\''
                                  + html.escape(k['step'], quote=True) + '\',\'' + html.escape(k['layer'], quote=True) + '\')">'
                                  + _nav_badge('recipe') + html.escape(k['step'])
                                  + ' <span class="inst-cls">(' + html.escape(k['layer']) + ')</span></div>')
                    elif k['loaded']:
                        rp.append('<div class="navitem navchild rec-item" '
                                  'onclick="recShow(\'' + html.escape(k['name'], quote=True) + '\')">'
                                  + _nav_badge('recipe') + html.escape(k['step'])
                                  + ' <span class="inst-cls">(' + html.escape(k['layer']) + ')</span></div>')
    else:
        rp.append('<div class="rec-empty">No recipe objects in this import.<br>'
                  'Append a recipe FHX (\u002b Append FHX in the header) to browse it here.</div>')
    recipes_pane = ''.join(rp)

    welcome = '<div class="welcome"><h2>' + html.escape(fname) + '</h2>'
    welcome += '<p>DeltaV database explorer. Select an object from the navigation tree to view its details and references.</p>'
    for k, v in summary.items():
        welcome += f'<div class="stat"><b>{v}</b><span>{k}</span></div>'
    welcome += '</div>'

    export_html = ''
    if export_token:
        ft = html.escape(fname, quote=True)
        tk = html.escape(export_token, quote=True)
        # The top-banner export now opens a multi-object export picker (see #7) rather
        # than dumping the whole database; Converter/Append/Settings moved to the rail.
        export_html = (
            f'<div class="hdr-export">'
            f'<a class="exp-btn" href="javascript:void 0" onclick="openExportPicker()" '
            f'title="Choose objects and export them to Excel or Word in one go">{_EXPORT_ICON}Export\u2026</a>'
            f'</div>')

    theme_opts = ''.join(f'<option value="{k}">{html.escape(lbl)}</option>' for k, lbl in _THEME_LABELS)
    icon_theme_opts_json = json.dumps(theme_opts)
    theme_html = ''  # icon selector moved into Settings (was a top-banner dropdown)
    themes_json = json.dumps(_ICON_THEMES)
    tcolors_json = json.dumps(_THEME_COLORS)

    return f"""<!DOCTYPE html><html lang="en" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DeltaV Strategy Workbench — {html.escape(fname)}</title>
<style>{fonts.FONT_CSS}
{_CSS}
{s88_model.S88_CSS}
{fbd_bridge.EXPR_MODAL_CSS}
{_RECIPE_CSS}</style></head><body>
<div class="app">
<nav class="rail">
  <div class="brand" title="DeltaV Strategy Workbench">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M12 2 4 6.5v9L12 20l8-4.5v-9L12 2Z"/><path d="M12 7v6M9 9.5h6"/></svg>
  </div>
  <a class="rail-btn active" id="rb-explorer" href="javascript:void 0" title="Explorer" onclick="switchView('explorer')">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
    <span class="tip">Explorer</span></a>
  <a class="rail-btn" id="rb-studio" href="javascript:void 0" title="Studio" onclick="switchView('studio')">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="5" rx="1"/><rect x="13" y="10" width="8" height="11" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/></svg>
    <span class="tip">Studio</span></a>
  <a class="rail-btn" id="rb-recipes" href="javascript:void 0" title="Recipes" onclick="switchView('recipes')">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 2.5h9l4 4V21a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z"/><path d="M14.5 2.5V7H19M8.5 12h7M8.5 16h5"/></svg>
    <span class="tip">Recipes</span></a>
  <a class="rail-btn" id="rb-converter" href="javascript:void 0" title="FHX Converter" onclick="switchView('converter')">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"><path d="M4 3.5h5.2L11 5.3v6.2H4z"/><path d="M9.2 3.5v1.8H11"/><path d="M13 12.5h5.2L20 14.3v6.2h-7z"/><path d="M18.2 12.5v1.8H20"/><path d="M12.5 6.5a6 6 0 0 1 5 5"/><path d="M17.5 9v2.7h-2.7"/></svg>
    <span class="tip">FHX Converter</span></a>
  <div class="spacer"></div>
  <a class="rail-btn" id="rb-append" href="javascript:void 0" title="Append another FHX" onclick="openAppend()">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 5v14M5 12h14"/></svg>
    <span class="tip">Append FHX</span></a>
  <a class="rail-btn" id="rb-settings" href="javascript:void 0" title="Settings" onclick="openSettings()">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/></svg>
    <span class="tip">Settings</span></a>
</nav>
<header class="topbar">
  <h1>DeltaV Strategy Workbench</h1><span class="sub">{html.escape(fname)}</span><span class="sub" style="opacity:.6;margin-left:8px" title="Build identifier — confirms which deployment is live">build {_BUILD_ID}</span>
  <div class="cmdp-wrap">
    <div class="cmdp-box" onclick="document.getElementById('cmdpInput').focus()">
      <svg class="cmdp-ico" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input id="cmdpInput" autocomplete="off" spellcheck="false" placeholder="Jump to object\u2026  (Ctrl-K)"
             oninput="cmdpSearch(this.value)" onkeydown="cmdpKey(event)"
             onfocus="if(this.value)cmdpSearch(this.value)" onblur="setTimeout(cmdpClose,150)">
      <span class="cmdp-kbd">\u2318K</span>
    </div>
    <div class="cmdp-pop" id="cmdpPop"></div>
  </div>
  <div class="hdr-right">{theme_html}
    <button class="iconbtn" id="themeBtn" title="Toggle light / dark" onclick="toggleMode()">
      <svg id="themeIco" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/></svg>
    </button>{export_html}</div>
</header>
<main class="main">
  <div class="panes">
    <div class="nav">{''.join(nav)}</div>
    <div class="pane-divider" id="paneDivider" title="Drag to resize"></div>
    <div class="detail" id="detail">{welcome}</div>
  </div>
</main>
<div id="view-converter"><iframe id="convFrame" title="FHX Converter"></iframe></div>
<div id="view-studio">
  <div class="stu-shell">
    <div class="stu-side">
      <div class="stu-side-h">Studio</div>
      <div class="stu-side-sub">Open a phase, class, or deployed instance in a focused, multi-panel workspace. Instances show their full equipment path (Plant Area \u203a Cell \u203a Unit).</div>
      <input class="alias-filter" id="stuFilter" placeholder="Filter objects & instances\u2026" oninput="stuFilterList(this)" style="margin:8px 0">
      <div id="stuList"></div>
    </div>
    <div class="stu-main" id="stuMain">
      <div class="stu-welcome"><h2>Studio</h2><p>Pick an object on the left \u2014 or right-click any instance in the Explorer and choose \u201cOpen in Studio\u201d to bring it here with its full S88 path. The diagram is fully interactive; the simulator runs inside the Studio too.</p></div>
    </div>
  </div>
</div>
<div id="view-recipes">
  <div class="rec-panes">
    <div class="rec-list">
      <div class="rec-toolbar">
        <button class="exp-btn" onclick="document.getElementById('recFile').click()"
          title="Import a recipe FHX \u2014 you'll be asked whether to replace or merge">\u2b06 Import recipe FHX\u2026</button>
        <input type="file" id="recFile" accept=".fhx" style="display:none" onchange="recImportFile(this)">
        <button class="exp-btn" onclick="fsOpen()"
          title="Bulk-edit and compare recipe formulas, then export a DeltaV-ready FHX">\u2317 Formula Studio</button>
      </div>
      <div class="rec-src" id="recSrc">Showing recipes from the Explorer import.</div>
      <div id="recListBody">{recipes_pane}</div>
    </div>
    <div class="rec-detail" id="rdetail"><div class="welcome"><h2>Recipes</h2>
      <p>A focused view of recipe objects \u2014 Procedures, Unit Procedures and Operations \u2014 with parameter grids, deferrals and Excel exports. Select one on the left, or import a recipe FHX directly (the Explorer session is untouched).</p></div></div>
  </div>
</div>
</div>
<script>
const ICON_THEMES={themes_json};
const _ICON_THEME_OPTS={icon_theme_opts_json};
const THEME_COLORS={tcolors_json};
const EXPORT_TOKEN={json.dumps(export_token or "")};
const _EXCEL_ICON_RAW='<svg viewBox="0 0 16 16" width="13" height="13" style="vertical-align:-2px;margin-right:3px"><rect x="1.5" y="2" width="13" height="12" rx="1.5" fill="#107C41"/><path d="M5.2 5L8 8 5.2 11M10.8 5L8 8l2.8 3" stroke="#fff" stroke-width="1.3" fill="none"/></svg>';
const _WORD_ICON_RAW='<svg viewBox="0 0 16 16" width="13" height="13" style="vertical-align:-2px;margin-right:3px"><rect x="1.5" y="2" width="13" height="12" rx="1.5" fill="#185ABD"/><path d="M4 5l1.2 6L6.6 6.5 8 11l1.4-4.5L10.6 11 12 5" stroke="#fff" stroke-width="1.1" fill="none"/></svg>';
function exportBar(obj,name){{
  if(!EXPORT_TOKEN) return '';
  var base='/export?token='+encodeURIComponent(EXPORT_TOKEN)+'&obj='+encodeURIComponent(obj)+'&name='+encodeURIComponent(name);
  var xi='<svg viewBox="0 0 16 16" width="12" height="12" style="vertical-align:-2px;margin-right:3px"><rect x="1.5" y="2" width="13" height="12" rx="1.5" fill="#107C41"/><path d="M5.2 5L8 8 5.2 11M10.8 5L8 8l2.8 3" stroke="#fff" stroke-width="1.3" fill="none"/></svg>';
  var wi='<svg viewBox="0 0 16 16" width="12" height="12" style="vertical-align:-2px;margin-right:3px"><rect x="1.5" y="2" width="13" height="12" rx="1.5" fill="#185ABD"/><path d="M4 5l1.2 6L6.6 6.5 8 11l1.4-4.5L10.6 11 12 5" stroke="#fff" stroke-width="1.1" fill="none"/></svg>';
  return '<div class="obj-export">'
    +'<a class="exp-mini" href="'+base+'&fmt=excel" title="Download an Excel workbook for this object">'+xi+'Excel</a>'
    +'<a class="exp-mini" href="'+base+'&fmt=word" title="Download a Word DDS document for this object">'+wi+'Word</a></div>';
}}
function skinTree(theme){{
  var set=ICON_THEMES[theme], cols=THEME_COLORS[theme];
  if(!set) return;
  document.querySelectorAll('.ic-badge[data-ic]').forEach(function(el){{
    var t=el.dataset.ic;
    if(set[t]!==undefined) el.innerHTML='<svg viewBox="0 0 15 15" width="15" height="15" aria-hidden="true">'+set[t]+'</svg>';
    if(cols&&cols[t]) el.style.color=cols[t];
  }});
  try{{localStorage.setItem('dvexp_icontheme',theme);}}catch(e){{}}
  var sel=document.getElementById('set-icontheme'); if(sel) sel.value=theme;
}}
(function(){{ try{{ var t=localStorage.getItem('dvexp_icontheme'); if(t&&ICON_THEMES[t]) skinTree(t); }}catch(e){{}} }})();
const _SUN='<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/>';
const _MOON='<path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.5 6.5 0 0 0 9.8 9.8Z"/>';
function applyMode(m){{document.documentElement.dataset.theme=m;
  var i=document.getElementById('themeIco'); if(i) i.innerHTML=(m==='dark'?_MOON:_SUN);
  // keep the Studio diagram iframe (its own document) in sync with the theme
  try{{
    var fr=document.querySelector('.stu-diag-frame');
    if(fr&&fr.src){{ fr.src=fr.src.replace(/([?&]theme=)(dark|light)/,'$1'+m); }}
  }}catch(e){{}}
}}
function toggleMode(){{var m=document.documentElement.dataset.theme==='dark'?'light':'dark';
  applyMode(m); try{{localStorage.setItem('dvexp_mode',m);}}catch(e){{}}}}
(function(){{ try{{ var m=localStorage.getItem('dvexp_mode'); if(m) applyMode(m); }}catch(e){{}} }})();
(function(){{ try{{ applySettings(); }}catch(e){{}} }})();
</script>
<script>const S88_SVG={s88_svg_json};
{s88_model.S88_JS}</script>
<script>{js}
{fbd_bridge.EXPR_MODAL_JS}</script>
</body></html>"""
