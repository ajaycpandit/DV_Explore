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
.stu-shell{display:grid;grid-template-columns:260px 1fr;height:100%;overflow:hidden}
.stu-side{border-right:1px solid var(--border);padding:14px 12px;overflow:auto;background:var(--surface)}
.stu-side-h{font-size:15px;font-weight:700;color:var(--ink)}
.stu-side-sub{font-size:11px;color:var(--ink-3);line-height:1.5;margin-top:4px}
.stu-litem{padding:7px 9px;border-radius:7px;cursor:pointer;font-size:12.5px;display:flex;align-items:center;gap:7px}
.stu-litem:hover{background:var(--surface-2)}
.stu-litem.sel{background:var(--accent-soft);color:var(--accent);font-weight:600}
.stu-main{overflow:hidden;display:flex;flex-direction:column;min-height:0;height:100%}
.stu-side{border-right:1px solid var(--border);padding:14px 12px;overflow:auto;background:var(--surface);min-height:0}
.stu-welcome{padding:26px}
.stu-head{display:flex;align-items:center;gap:12px;padding:12px 18px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.stu-head h2{margin:0;font-size:17px}
.stu-kind{font-size:11px;font-weight:600;background:var(--accent-soft);color:var(--accent);padding:3px 9px;border-radius:20px}
.stu-chip{font-size:11px;font-weight:600;background:var(--surface-2);color:var(--ink-2);padding:3px 9px;border-radius:20px}
.stu-body{flex:1 1 auto;display:grid;grid-template-columns:1.35fr 1fr;grid-template-rows:minmax(0,1fr);overflow:hidden;min-height:0}
.stu-pane{overflow:auto;padding:0;min-height:0;min-width:0}
.stu-pane.stu-diagram{border-right:1px solid var(--border);padding:0;background:#fff;overflow:hidden;display:flex}
.stu-diagram iframe{flex:1 1 auto;width:100%;height:100%;border:0;display:block;min-height:0}
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
.stu-split{cursor:col-resize;width:5px;background:transparent}
@media(max-width:1100px){.stu-body{grid-template-columns:1fr;grid-template-rows:minmax(0,1fr) minmax(0,1fr)}.stu-pane.stu-diagram{border-right:0;border-bottom:1px solid var(--border)}}
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
.rec-empty{color:var(--ink-3);font-size:13px;padding:16px 8px;line-height:1.6}
.rec-src{font-size:11px;color:var(--ink-3);margin:0 4px 10px;line-height:1.5}
.rec-xl{font-size:11.5px;font-weight:600;margin-left:10px;vertical-align:middle}
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
.topbar h1{margin:0;font-size:15px;font-weight:600;letter-spacing:-.01em}
.topbar .sub{color:var(--ink-3);font-size:12px;font-family:'IBM Plex Mono'}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:12px}
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
.ic-composite{color:var(--b-composite)}.ic-fbtype{color:var(--b-fbtype)}
.navchild{padding-left:34px}
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
.fbd-diagram-card{border:1px solid var(--border);border-radius:10px;background:#fcfcfd;overflow:hidden}
.fbd-head{padding:10px 14px;background:var(--surface-2);font-weight:600;font-size:13px;border-bottom:1px solid var(--border);color:var(--ink)}
.fbd-sub{color:var(--ink-3);font-weight:400;font-size:12px}
.fbd-svg-holder{padding:10px;overflow:auto;max-height:78vh;background:#fcfcfd}
.fbd-info-card{border:1px solid var(--border);border-radius:10px;padding:12px 14px;background:var(--surface)}
.fbd-info-card h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:var(--ink-3)}
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


def _nav_badge(key):
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
    return (f'<span class="ic-badge {cls}" data-ic="{key}" title="{title}">'
            f'<svg viewBox="0 0 15 15" width="15" height="15" aria-hidden="true">'
            f'{_NAV_ICON.get(key, "")}</svg></span>')


_EXCEL_ICON = '<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="1.5" y="2" width="13" height="12" rx="1.5" fill="#107C41"/><path d="M5.2 5L8 8 5.2 11M10.8 5L8 8l2.8 3" stroke="#fff" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>'
_WORD_ICON = '<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="1.5" y="2" width="13" height="12" rx="1.5" fill="#185ABD"/><path d="M4 5l1.2 6L6.6 6.5 8 11l1.4-4.5L10.6 11 12 5" stroke="#fff" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>'
_BUILD_ID = "20260705-2029"


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
function badge(t){const m={'Area':'b-area','Unit Instance':'b-unit','EM Class':'b-em','CM Class':'b-cm','Phase Class':'b-phase','Recipe':'b-recipe','Composite':'b-composite','Unit Class':'b-uclass','FB Type':'b-fbtype','Named Set':'b-nset'};return m[t]||'b-composite';}
function badgeColor(t){const m={'b-area':'#0ea5e9','b-unit':'#6366f1','b-em':'#0f766e','b-cm':'#7c3aed','b-phase':'#b45309','b-recipe':'#be123c','b-composite':'#475569','b-uclass':'#2563eb','b-fbtype':'#334155'};if(t==='Parameter')return '#0891b2';if(t==='Instance')return '#6d28d9';return m[badge(t)]||'#475569';}

// ── global search: Names | Expressions | Values ──
var SIDX=null, SRES=[], SSEL=-1, SMODE='names';
function searchIndex(){
  if(SIDX)return SIDX;
  SIDX=[];
  for(var id in DB.objs){var o=DB.objs[id];SIDX.push({id:id,name:o.name||'',type:o._type||'',desc:o.description||''});}
  for(var pn in PARAM_INDEX){SIDX.push({id:'param:'+pn,name:pn,type:'Parameter',desc:''});}
  for(var iid in (DB.instances||{})){var ins=DB.instances[iid];SIDX.push({id:'inst:'+iid,name:ins.tag,type:'Instance',desc:ins.cls});}
  SIDX.sort(function(a,b){return a.name.localeCompare(b.name);});
  return SIDX;
}
function escRe(s){return s.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');}
function hiQ(t,q){if(!q)return esc(t);try{return esc(t).replace(new RegExp('('+escRe(q)+')','ig'),'<mark>$1</mark>');}catch(e){return esc(t);}}
function navMode(btn,m){
  SMODE=m;
  document.querySelectorAll('.navmode .nm-btn').forEach(b=>b.classList.toggle('active',b===btn));
  var q=document.getElementById('navq');
  q.placeholder=(m==='expr'?'Search expression logic…':m==='values'?'Search configured values…':'Search…  (Ctrl-K)');
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
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();var q=document.getElementById('navq');if(q){q.focus();q.select();}}
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
    +'<div class="set-row"><div><div class="set-lbl">Loading animation</div><div class="set-hint">Shown while diagrams and data load</div></div>'
    +'<div style="display:flex;align-items:center;gap:12px">'
    +'<span id="loaderPreview" style="min-width:70px">'+dvLoader('')+'</span>'
    +'<select id="set-loader" onchange="document.body.setAttribute(\\'data-loader\\',this.value)">'
    +['dots','ring','bars','pulse'].map(function(x){return '<option value="'+x+'"'+(x===APP_SETTINGS.loader?' selected':'')+'>'+x.charAt(0).toUpperCase()+x.slice(1)+'</option>';}).join('')
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
// #4: append another FHX (e.g. a recipe) onto the current import without losing it.
function openAppend(){
  var tok=(typeof EXPORT_TOKEN!=='undefined')?EXPORT_TOKEN:'';
  if(!tok){ alert('Append needs the current import token, which is unavailable. Re-import the base file and try again.'); return; }
  var ov=document.getElementById('appendOverlay');
  if(!ov){ ov=document.createElement('div'); ov.id='appendOverlay'; ov.className='ip-pop-overlay'; document.body.appendChild(ov); }
  ov.onclick=function(e){ if(e.target===ov) ov.remove(); };
  ov.innerHTML='<div class="ip-pop" style="max-width:520px"><div class="ip-pop-h"><b>Append another FHX</b>'
    +'<span class="ip-pop-x" onclick="var o=document.getElementById(\\'appendOverlay\\');if(o)o.remove();">\\u00d7</span></div>'
    +'<div style="padding:16px 18px">'
    +'<p style="margin:0 0 12px;color:var(--ink-2);font-size:13px;line-height:1.5">Merge a second export (for example a recipe) into this one. The current import is kept; the new file is added on top. If an object with the same name already exists, choose what to do with the duplicate.</p>'
    +'<input type="file" id="appendFile" accept=".fhx" style="display:block;margin-bottom:12px;font-size:13px">'
    +'<div style="display:flex;gap:14px;margin-bottom:14px;font-size:13px">'
    +'<label style="display:flex;align-items:center;gap:6px;cursor:pointer"><input type="radio" name="appendMode" value="skip" checked> Skip duplicates <span style="color:var(--ink-3)">(keep original)</span></label>'
    +'<label style="display:flex;align-items:center;gap:6px;cursor:pointer"><input type="radio" name="appendMode" value="overwrite"> Overwrite <span style="color:var(--ink-3)">(new wins)</span></label>'
    +'</div>'
    +'<div id="appendStatus" style="font-size:12.5px;color:var(--ink-3);min-height:18px;margin-bottom:10px"></div>'
    +'<div id="appendBaseWrap" style="display:none;margin-bottom:12px;padding:10px 12px;background:#fff7ed;border:1px solid #fdba74;border-radius:8px">'
    +'<div style="font-size:12.5px;color:#9a3412;margin-bottom:7px">The original import isn\\'t available on the server anymore (the free host may have restarted). Re-select the <b>base</b> FHX so the merge can proceed \\u2014 you won\\'t lose anything.</div>'
    +'<input type="file" id="appendBaseFile" accept=".fhx" style="display:block;font-size:13px"></div>'
    +'<button class="exp-btn" style="background:var(--accent);color:#fff;border:none" onclick="doAppend()">Merge &amp; reload</button>'
    +'</div></div>';
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
function stuBuildList(){
  var box=document.getElementById('stuList'); if(!box || box._built) return;
  var names=(typeof PHASE_NAMES!=='undefined'?PHASE_NAMES:[]).slice().sort();
  if(!names.length){ box.innerHTML='<div class="stu-empty">No phases in this import.</div>'; return; }
  box.innerHTML=names.map(function(n){
    return '<div class="stu-litem" data-ph="'+esc(n)+'" onclick="stuOpen(\\''+esc(n).replace(/'/g,"\\\\'")+'\\')">'
      +'<span class="ic-badge ic-phase"><svg viewBox="0 0 15 15" width="14" height="14"><rect x="2.5" y="2.5" width="10" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M5 7.5h5M7.5 5v5" stroke="currentColor" stroke-width="1.4"/></svg></span>'
      +esc(n)+'</div>';
  }).join('');
  box._built=1;
}
function stuFilterList(inp){
  var q=(inp.value||'').toLowerCase();
  document.querySelectorAll('#stuList .stu-litem').forEach(function(it){
    it.style.display=(!q || it.textContent.toLowerCase().indexOf(q)>=0)?'':'none';
  });
}
function stuOpen(name){
  document.querySelectorAll('#stuList .stu-litem').forEach(function(it){ it.classList.toggle('sel', it.dataset.ph===name); });
  var main=document.getElementById('stuMain');
  main.innerHTML='<div class="stu-welcome">'+dvLoader('Opening '+esc(name)+'\u2026')+'</div>';
  fetch('/studio_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(name))
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.error){ main.innerHTML='<div class="stu-welcome"><p class="stu-empty">'+esc(d.error)+'</p></div>'; return; }
      stuRender(d);
    })
    .catch(function(e){ main.innerHTML='<div class="stu-welcome"><p class="stu-empty">Could not open: '+esc(e.message)+'</p></div>'; });
}
function stuRender(d){
  var c=d.counts||{};
  var diagUrl='/phase_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&p='+encodeURIComponent(d.name);
  var h=''
    +'<div class="stu-head"><h2>'+esc(d.name)+'</h2><span class="stu-kind">'+esc(d.kind||'')+'</span>'
    +'<span class="stu-chip">'+(c.params||0)+' parameters</span>'
    +'<span class="stu-chip">'+(c.attrs||0)+' attributes</span></div>'
    +'<div class="stu-body">'
    +'<div class="stu-pane stu-diagram"><iframe src="'+diagUrl+'" title="'+esc(d.name)+' diagram"></iframe></div>'
    +'<div class="stu-pane">'
    +'<div class="stu-tabs">'
    +'<div class="stu-tab on" data-t="params" onclick="stuTab(this,\\'params\\')">Parameters</div>'
    +'<div class="stu-tab" data-t="attrs" onclick="stuTab(this,\\'attrs\\')">Attributes</div>'
    +'<div class="stu-tab" data-t="mon" onclick="stuTab(this,\\'mon\\')">Monitors</div>'
    +'</div>'
    +'<div class="stu-tabpanel on" data-t="params">'+(d.params||'')+'</div>'
    +'<div class="stu-tabpanel" data-t="attrs">'+(d.attrs||'')+'</div>'
    +'<div class="stu-tabpanel" data-t="mon">'+(d.monitors||'')+'</div>'
    +'</div></div>';
  document.getElementById('stuMain').innerHTML=h;
}
function stuTab(el,t){
  var main=document.getElementById('stuMain');
  main.querySelectorAll('.stu-tab').forEach(function(x){x.classList.toggle('on',x===el);});
  main.querySelectorAll('.stu-tabpanel').forEach(function(p){p.classList.toggle('on',p.getAttribute('data-t')===t);});
}
// ── standalone Recipes workspace (rail view) ──
// RECWS holds the workspace's data source: by default the Explorer import, replaced
// wholesale when a recipe FHX is imported directly here (Explorer untouched).
var RECWS={token:(typeof EXPORT_TOKEN!=='undefined'?EXPORT_TOKEN:''),
           views:(typeof RECIPE_VIEWS!=='undefined'?RECIPE_VIEWS:{}),
           stepViews:(typeof RECIPE_STEP_VIEWS!=='undefined'?RECIPE_STEP_VIEWS:{})};
var _REC_BADGE='<span class="ic-badge ic-recipe"><svg viewBox="0 0 15 15" width="15" height="15" aria-hidden="true"><path d="M4 2.4h4.6l2.6 2.6v7.6h-7.2z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/><path d="M8.4 2.4v2.8h2.8M5.5 8h6M5.5 10h3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/></svg></span>';
function recImportFile(inp){
  if(!inp.files||!inp.files.length) return;
  var src=document.getElementById('recSrc');
  src.innerHTML='<span class="dv-dots"><i></i><i></i><i></i></span> Importing '+esc(inp.files[0].name)+'\u2026';
  var fd=new FormData(); fd.append('file', inp.files[0]);
  fetch('/recipe_import',{method:'POST',body:fd})
    .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
    .then(function(res){
      if(!res.ok||res.j.error){ src.innerHTML='<span style="color:#dc2626">'+esc(res.j.error||'Import failed')+'</span>'; return; }
      RECWS={token:res.j.token, views:res.j.views||{}, stepViews:res.j.step_views||{}};
      recBuildList(res.j.tree||[]);
      src.textContent='Showing recipes from '+res.j.name+' (imported here \u2014 Explorer untouched).';
      var first=(res.j.tree[0]&&res.j.tree[0].items[0])?res.j.tree[0].items[0].name:'';
      if(first) recShow(first);
    })
    .catch(function(e){ src.innerHTML='<span style="color:#dc2626">Import error: '+esc(e.message)+'</span>'; });
  inp.value='';
}
function recBuildList(tree){
  var h='';
  tree.forEach(function(cat){
    h+='<div class="rec-cat">'+esc(cat.cat)+' ('+cat.items.length+')</div>';
    cat.items.forEach(function(it){
      var bases={}; (it.children||[]).forEach(function(k){ bases[k.name]=bases[k.name]||k.loaded; });
      var nb=Object.keys(bases).length, nl=0; for(var b in bases){ if(bases[b]) nl++; }
      var sub=nb?(' <span class="inst-cls">('+nl+'/'+nb+' children imported)</span>'):'';
      h+='<div class="navitem rec-item" data-rec="'+esc(it.name)+'" onclick="recShow(\\''+esc(it.name)+'\\')">'+_REC_BADGE+esc(it.name)+sub+'</div>';
      (it.children||[]).forEach(function(k){
        if(k.loaded){
          h+='<div class="navitem navchild rec-item" onclick="recShow(\\''+esc(k.name)+'\\')">'+_REC_BADGE+esc(k.step)+' <span class="inst-cls">('+esc(k.layer)+')</span></div>';
        } else if(k.has_params){
          h+='<div class="navitem navchild navghost rec-item" onclick="recShowStep(\\''+esc(it.name)+'\\',\\''+esc(k.step)+'\\',\\''+esc(k.layer)+'\\')">'+_REC_BADGE+esc(k.step)+' <span class="inst-cls">('+esc(k.layer)+')</span></div>';
        }
      });
    });
  });
  document.getElementById('recListBody').innerHTML=h||'<div class="rec-empty">No recipe objects found.</div>';
}
function recShow(name){
  var d=document.getElementById('rdetail'); if(!d) return;
  document.querySelectorAll('.rec-item').forEach(function(n){n.classList.toggle('sel',n.dataset.rec===name);});
  var v=RECWS.views[name]||'';
  var o=(typeof DB!=='undefined'&&DB.objs['recipe:'+name])||{};
  var h='<h2 class="dt">'+esc(name)+' <span class="dt-type b-recipe">Recipe</span>'
    +' <a class="link rec-xl" href="javascript:void 0" onclick="recDownloadPfc(\\''+esc(name)+'\\')">\u2b07 PFC report (.xlsx)</a>'
    +' <a class="link rec-xl" href="javascript:void 0" onclick="downloadDeferrals(\\''+esc(name)+'\\',this)">\u2b07 Deferrals (.xlsx)</a></h2>';
  if(o.description) h+='<p class="dt-desc">'+esc(o.description)+'</p>';
  h+=v||'<div class="card"><span class="empty">No detail parsed for this recipe.</span></div>';
  d.innerHTML=h; d.scrollTop=0;
}
function recShowStep(parent, step, layer){
  var d=document.getElementById('rdetail'); if(!d) return;
  document.querySelectorAll('.rec-item').forEach(function(n){n.classList.remove('sel');});
  var v=RECWS.stepViews[parent+'||'+step]||'';
  var h='<h2 class="dt">'+esc(step)+' <span class="dt-type b-recipe">'+esc(layer||'recipe step')+'</span></h2>';
  h+='<p class="dt-desc">Instance under '+esc(parent)+' \u2014 parameters derived from the parent step.</p>';
  h+=v||'<div class="card"><span class="empty">No parameters found on this step.</span></div>';
  d.innerHTML=h; d.scrollTop=0;
}
function recDownloadPfc(name){
  if(!RECWS.token) return;
  window.location.href='/recipe_pfc_xlsx?t='+encodeURIComponent(RECWS.token)+'&n='+encodeURIComponent(name);
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
      setTimeout(wireFbdLinks, 0);
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
    var tgt=a.value?('<span class="link" onclick="showTag(\\''+esc(a.value)+'\\')"><code>'+esc(a.value)+'</code></span>'):'<span style="color:#94a3b8">(unresolved)</span>';
    h+='<tr'+(a.ignore?' style="opacity:.5"':'')+'><td><code>#'+esc(a.alias)+'#</code></td><td>'+tgt+'</td><td style="font-size:12px;color:var(--ink-2)">'+esc(a.desc||'')+'</td></tr>';
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
    else if(e.k==='rstep') renderRecipeStep(e.parent, e.step, e.layer);
    var dd=document.getElementById('detail'); if(dd) dd.scrollTop=0;
    makeCardsCollapsible();
  });
}
// #3/#5: collapse any card OR sub-card by clicking its header. Handles top-level
// .card > h3 and nested sub-cards / h4 headers, so a master card (e.g. Diagram) with
// internal sub-sections can each collapse independently. Pure CSS affordance + one
// delegated handler — works for cards added at any time across ALL object types.
function makeCardsCollapsible(){
  // The click delegation + CSS already handle .card and .subcard headers. This pass
  // ensures nested sections that were rendered as a bare <h4> inside a .card (without
  // an explicit .subcard wrapper) also collapse: we wrap each such <h4> and its
  // following siblings up to the next <h4> in a .subcard so the same rules apply.
  try{
    var scope=document.getElementById('detail'); var scope2=document.getElementById('rdetail');
    [scope,scope2].forEach(function(root){
      if(!root) return;
      root.querySelectorAll('.card').forEach(function(card){
        // only when a card has 2+ inner h4 sections and none are already wrapped
        var h4s=[]; for(var i=0;i<card.children.length;i++){ if(card.children[i].tagName==='H4') h4s.push(card.children[i]); }
        if(h4s.length<1) return;
        h4s.forEach(function(h){
          if(h.parentElement.classList.contains('subcard')) return; // already
          var sub=document.createElement('div'); sub.className='subcard';
          h.parentNode.insertBefore(sub, h);
          var n=h;
          while(n){ var nx=n.nextSibling; sub.appendChild(n); if(nx && nx.nodeType===1 && nx.tagName==='H4') break; n=nx; }
        });
      });
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
  function ctxClose(){ var m=document.getElementById('ctxMenu'); if(m) m.remove(); }
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
      acts.push(ctxItem('Export deferrals (.xlsx)', function(){ var t=RECWS.token||EXPORT_TOKEN; window.location.href='/recipe_deferrals_xlsx?t='+encodeURIComponent(t)+'&n='+encodeURIComponent(rn); }));
      acts.push(ctxItem('Copy name', function(){ ctxCopy(rn); }, {sep:true}));
      return acts;
    }
    if(kind==='phase'){
      acts.push(ctxItem('Open phase', function(){ show(id); }));
      if(typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN)
        acts.push(ctxItem('Export (.xlsx)', function(){ window.location.href='/export?t='+encodeURIComponent(EXPORT_TOKEN)+'&fmt=excel&obj='+encodeURIComponent(id); }, {sep:true}));
      acts.push(ctxItem('Copy name', function(){ ctxCopy(name); }, {sep:true}));
      return acts;
    }
    if(kind==='em' || kind==='cm' || kind==='fbtype' || kind==='composite'){
      acts.push(ctxItem('Open', function(){ show(id); }));
      acts.push(ctxItem('Copy name', function(){ ctxCopy(name); }, {sep:true}));
      return acts;
    }
    if(tag){
      acts.push(ctxItem('Open instance', function(){ if(typeof showDeployed==='function') showDeployed(tag); }));
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
    // #6: clicking a drillable step box in the PFC opens that referenced object
    var stepG=t.closest('.pfc-drillable');
    if(stepG){
      var dr=stepG.getAttribute('data-drill');
      if(dr && DB.objs['recipe:'+dr]){ show('recipe:'+dr); return; }
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
    if(!hdr.closest('#detail') && !hdr.closest('#rdetail')) return;
    hdr.parentElement.classList.toggle('collapsed');
    ev.stopPropagation();
  });
}
function navTo(e){ VIEW_STACK.push(e); renderEntry(e); }
function goBack(){ if(VIEW_STACK.length>1){ VIEW_STACK.pop(); renderEntry(VIEW_STACK[VIEW_STACK.length-1]); } }
function show(id){
  if(id && id.indexOf('param:')===0){ var pn=id.slice(6); if(PARAM_INDEX[pn]) navTo({k:'param',name:pn}); return; }
  if(id && id.indexOf('inst:')===0){ var iid=id.slice(5); if(DB.instances&&DB.instances[iid]) navTo({k:'inst',iid:iid}); return; }
  if(DB.objs[id]) navTo({k:'obj',id:id});
}
function showFbd(def,label){ if(FBD_VIEWS[def] || (typeof FBD_NAMES!=='undefined' && FBD_NAMES.indexOf(def)>=0)) navTo({k:'fbd',def:def,label:label}); }

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
      var h='<table class="fbd-table"><thead><tr><th>Role in EM</th><th>Wired device</th></tr></thead><tbody>';
      roles.sort().forEach(function(role){
        var dev=mm[role];
        var link=(DB.deployed_modules&&DB.deployed_modules[dev])
          ? '<span class="link" onclick="showDeployed(\\''+esc(dev).replace(/\'/g,"\\\\'")+'\\')">'+esc(dev)+'</span>'
          : '<code>'+esc(dev)+'</code>';
        h+='<tr><td><code>'+esc(role)+'</code></td><td>'+link+'</td></tr>';
      });
      h+='</tbody></table>';
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
      if(d && d.html){ FBD_VIEWS[name]=d.html; if(box){ box.outerHTML='<div class="card" style="max-width:none">'+d.html+'</div>'; setTimeout(wireFbdLinks,0);} }
      else if(box){ box.innerHTML='<h3>Detail</h3><span class="empty">Could not load diagram'+(d&&d.error?': '+d.error:'')+'.</span>'; }
    })
    .catch(function(){ if(box) box.innerHTML='<h3>Detail</h3><span class="empty">Could not load diagram.</span>'; });
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
function renderDeployed(tag, roleAlias){
  var d=DB.deployed_modules&&DB.deployed_modules[tag]; if(!d){return;}
  document.querySelectorAll('.navitem').forEach(n=>n.classList.remove('sel'));
  document.querySelectorAll('.navinst').forEach(function(n){n.classList.toggle('sel',n.dataset.tag===tag&&n.dataset.dep==='1');});
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
      if(x&&x.html){ box.innerHTML='<h3>Diagram</h3>'+x.html; setTimeout(wireFbdLinks,0); return; }
      return fetch('/fbd_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&n='+encodeURIComponent(d.cls))
        .then(function(r){return r.json();})
        .then(function(y){
          if(y&&y.html){ box.innerHTML='<h3>Diagram <span style="font-weight:400;color:var(--ink-3);font-size:12px">\\u2014 from class '+esc(d.cls)+'</span></h3>'+y.html; setTimeout(wireFbdLinks,0); }
          else box.innerHTML='<h3>Diagram</h3><span class="empty">No function block diagram for this instance or its class.</span>';
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
               'placeholder="Search…  (Ctrl-K)" '
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
                    nav.append(f'<div class="navitem {_ncls(lvl + 2)} navinst" '
                               f'data-parent="{html.escape(cls)}" data-tag="{html.escape(itag)}" '
                               f'onclick="showInst(this.dataset.parent,this.dataset.tag)" '
                               f'title="{html.escape(itag)} (instance of {html.escape(icls)}){(" · "+own.title()) if own else ""}">'
                               f'{_nav_badge("inst")}<span class="inst-tag">{html.escape(itag)}</span>{own_ico}'
                               f'<span class="inst-cls">({html.escape(icls)})</span></div>')
                nav.append('</div></div>')
            else:
                nav.append(f'<div class="navitem {_ncls(lvl + 1)} navinst" data-tag="{html.escape(tag)}" data-dep="1" '
                           f'onclick="showDeployed(this.dataset.tag)" title="{html.escape(tag)} ({html.escape(cls)})">'
                           f'{_nav_badge(key)}<span class="inst-tag">{html.escape(tag)}</span>'
                           f'<span class="inst-cls">({html.escape(cls)})</span></div>')
        for ph in phs:
            nav.append(f'<div class="navitem {_ncls(lvl + 1)}" data-id="phase:{html.escape(ph)}" '
                       f'onclick="show(\'phase:{html.escape(ph)}\')">'
                       f'{_nav_badge("phase")}{html.escape(ph)}</div>')
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
                    nav.append('</div></div>')
                else:
                    for un in cells[cell]:
                        _unit_node(un, lvl=1)
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
        _fold('Control Network', collapsed=False)
        for cn in sorted(ctrls):
            sec_id[0] += 1
            cid = f'fold{sec_id[0]}'
            nav.append(f'<div class="navfolder navsec-tog" onclick="secToggle(\'{cid}\',this)">'
                       f'<span class="secarrow">\u25be</span> {_nav_badge("ctrl")}'
                       f'<span style="margin-left:2px">{html.escape(cn)}</span>'
                       f' <span class="navcount">{len(ctrls[cn])}</span></div>')
            nav.append(f'<div class="navfoldbody" id="{cid}" style="display:block">')
            for tag in sorted(ctrls[cn]):
                d = deployed.get(tag, {})
                cls = d.get('cls', '')
                key = 'em' if cls in em_class_names else 'inst'
                nav.append(f'<div class="navitem navinst" data-tag="{html.escape(tag)}" data-dep="1" '
                           f'onclick="showDeployed(this.dataset.tag)" title="{html.escape(tag)} ({html.escape(cls)})">'
                           f'{_nav_badge(key)}<span class="inst-tag">{html.escape(tag)}</span>'
                           f'<span class="inst-cls">({html.escape(cls)})</span></div>')
            nav.append('</div>')
        _endfold()  # Control Network
        _endfold()  # Physical Network
    else:
        _ph('Physical Network')
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
        export_html = (
            f'<div class="hdr-export">'
            f'<a class="exp-btn" href="/export?token={tk}&amp;fmt=excel&amp;name={ft}" '
            f'title="Download an Excel workbook generated from this database">{_EXCEL_ICON}Excel</a>'
            f'<a class="exp-btn" href="/export?token={tk}&amp;fmt=word&amp;name={ft}" '
            f'title="Download a Word DDS document generated from this database">{_WORD_ICON}Word DDS</a>'
            f'<a class="exp-btn" href="javascript:void 0" title="Open the FHX Converter wizard" onclick="switchView(\'converter\')">&#9881; Converter</a>'
            f'<a class="exp-btn" href="javascript:void 0" title="Append another FHX such as a recipe without losing this import" onclick="openAppend()">&#43; Append FHX</a>'
            f'<a class="exp-btn" href="javascript:void 0" title="Settings" onclick="openSettings()">&#9881; Settings</a>'
            f'</div>')

    theme_opts = ''.join(f'<option value="{k}">{html.escape(lbl)}</option>' for k, lbl in _THEME_LABELS)
    theme_html = (f'<div class="hdr-theme"><label for="iconTheme">Icons</label>'
                  f'<select id="iconTheme" onchange="skinTree(this.value)">{theme_opts}</select></div>')
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
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M4 12h16M4 17h10"/><path d="M17 15l3 2-3 2"/></svg>
    <span class="tip">FHX Converter</span></a>
  <div class="spacer"></div>
</nav>
<header class="topbar">
  <h1>DeltaV Strategy Workbench</h1><span class="sub">{html.escape(fname)}</span><span class="sub" style="opacity:.6;margin-left:8px" title="Build identifier — confirms which deployment is live">build {_BUILD_ID}</span>
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
      <div class="stu-side-sub">Open one object in a focused, multi-panel workspace \u2014 diagram, parameters and algorithm side by side. Phases first.</div>
      <input class="alias-filter" id="stuFilter" placeholder="Filter phases\u2026" oninput="stuFilterList(this)" style="margin:8px 0">
      <div id="stuList"></div>
    </div>
    <div class="stu-main" id="stuMain">
      <div class="stu-welcome"><h2>Studio</h2><p>Select a phase on the left to open it here. The diagram is fully interactive \u2014 the simulator runs inside the Studio too.</p></div>
    </div>
  </div>
</div>
<div id="view-recipes">
  <div class="rec-panes">
    <div class="rec-list">
      <div class="rec-toolbar">
        <button class="exp-btn" onclick="document.getElementById('recFile').click()"
          title="Import a recipe FHX here without touching the Explorer session">\u2b06 Import recipe FHX\u2026</button>
        <input type="file" id="recFile" accept=".fhx" style="display:none" onchange="recImportFile(this)">
        <button class="exp-btn" onclick="downloadAllDeferrals()"
          title="One workbook, one sheet per recipe object">\u2b07 All deferrals (.xlsx)</button>
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
const THEME_COLORS={tcolors_json};
const EXPORT_TOKEN={json.dumps(export_token or "")};
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
  var sel=document.getElementById('iconTheme'); if(sel) sel.value=theme;
}}
(function(){{ try{{ var t=localStorage.getItem('dvexp_icontheme'); if(t&&ICON_THEMES[t]) skinTree(t); }}catch(e){{}} }})();
const _SUN='<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/>';
const _MOON='<path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.5 6.5 0 0 0 9.8 9.8Z"/>';
function applyMode(m){{document.documentElement.dataset.theme=m;
  var i=document.getElementById('themeIco'); if(i) i.innerHTML=(m==='dark'?_MOON:_SUN);}}
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
