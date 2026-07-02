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
#view-converter.on{display:block}
#convFrame{width:100%;height:100%;border:0;display:block}
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
.panes{flex:1;display:grid;grid-template-columns:316px 1fr;overflow:hidden}

/* tree */
.nav{border-right:1px solid var(--border);overflow:auto;background:color-mix(in srgb,var(--surface) 55%,transparent);padding:6px 8px}
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
.navchild2{padding-left:50px}
.navchild3{padding-left:66px}
.navchild4{padding-left:82px}
.navinst{align-items:center}
.navinst .inst-tag{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.navinst .inst-cls{color:var(--ink-3);font-size:10.5px;margin-left:auto;padding-left:8px;white-space:nowrap;flex:0 0 auto}
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
.detail{overflow:auto;padding:22px 24px 48px}
h2.dt{margin:0;font-size:21px;font-weight:600;letter-spacing:-.01em;font-family:'IBM Plex Mono'}
.dt-type{display:inline-block;font-size:11px;color:#fff;padding:3px 10px;border-radius:8px;margin:8px 0 14px;font-weight:600;letter-spacing:.02em}
.dt-desc{color:var(--ink-2);margin:0 0 18px;font-size:13.5px}
.kv{display:grid;grid-template-columns:170px 1fr;gap:5px 16px;font-size:13px;margin-bottom:6px;max-width:760px}
.kv .k{color:var(--ink-3)}
.card{border:1px solid var(--border);border-radius:12px;padding:15px 16px;margin-bottom:14px;background:var(--surface);max-width:920px;box-shadow:var(--shadow)}
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
.phaseframe{width:100%;height:75vh;border:1px solid var(--border);border-radius:10px;background:#fff}
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


def build_explorer_html(catalog, fname, phase_views=None, phase_names=None, fbd_views=None,
                        fbd_names=None, em_views=None, em_names=None,
                        param_index=None, expr_index=None, export_token=None):
    """phase_names/fbd_names/em_names: lists of objects available for lazy drill-down
    (built on click via /phase_view, /fbd_view, /em_view). The *_views maps are the
    legacy eager form, still accepted as a fallback."""
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
const PARAM_INDEX = __PARAM_INDEX__;
const EXPR_INDEX = __EXPR_INDEX__;
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
function switchView(v){
  var conv=document.getElementById('view-converter');
  var re=document.getElementById('rb-explorer'), rc=document.getElementById('rb-converter');
  if(v==='converter'){
    var fr=document.getElementById('convFrame');
    if(!fr.getAttribute('src')) fr.setAttribute('src','/tool/?embed=1');
    conv.classList.add('on');
    re.classList.remove('active'); rc.classList.add('active');
  } else {
    conv.classList.remove('on');
    rc.classList.remove('active'); re.classList.add('active');
  }
}
function renderObj(id){
  const o=DB.objs[id]; if(!o)return;
  document.querySelectorAll('.navitem').forEach(n=>n.classList.toggle('sel',n.dataset.id===id));
  let h='<h2 class="dt">'+esc(o.name)+'</h2>';
  h+='<span class="dt-type '+badge(o._type)+'">'+o._type+'</span>';
  if(o.description) h+='<p class="dt-desc">'+esc(o.description)+'</p>';
  // key-values
  h+='<div class="kv">';
  if(o.category) h+='<div class="k">Category</div><div>'+esc(o.category)+'</div>';
  if(o.area) h+='<div class="k">Area</div><div><span class="link" onclick="show(\\'area:'+esc(o.area)+'\\')">'+esc(o.area)+'</span></div>';
  if(o.area_path) h+='<div class="k">Area path</div><div>'+esc(o.area_path)+'</div>';
  if(o.control_type) h+='<div class="k">Control type</div><div>'+esc(o.control_type)+'</div>';
  if(o.type && o._type==='Recipe') h+='<div class="k">Recipe type</div><div>'+esc(o.type)+'</div>';
  h+='</div>';

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
    if(typeof S88_SVG!=='undefined' && S88_SVG){
      h+='<div class="card s88card" style="max-width:none"><h3>State Model (ISA-88) '
       + '<span style="font-weight:400;color:var(--ink-3);text-transform:none;letter-spacing:0">'
       + 'click an acting state to open its logic below</span></h3>'
       + '<div class="s88wrap"><div class="s88diagram">'+S88_SVG+'</div>'
       + '<div class="s88side"><h4 id="s88h">Procedural state model</h4>'
       + '<p id="s88p">The six <b>acting</b> states (blue) always carry logic — Running, Holding, '
       + 'Restarting, Stopping, Aborting and the fault monitor. A <code>· blank</code> tag means the '
       + 'block holds a blank step with no actions. Outlined states are <b>resting</b> states.</p></div></div>'
       + '<div class="s88legend"><span><i style="background:var(--st-active)"></i>Acting state (logic)</span>'
       + '<span><i style="background:var(--st-quiet);border:1px solid var(--st-quiet-bd)"></i>Resting state</span>'
       + '<span><i style="background:var(--st-warn)"></i>Fault monitor</span>'
       + '<span><i style="background:var(--edge-reset)"></i>Reset path</span></div></div>';
    }
    var _hasEager = PHASE_VIEWS[o.name];
    var _hasLazy = (typeof PHASE_NAMES!=='undefined') && PHASE_NAMES.indexOf(o.name)>=0;
    if(_hasEager){
      h+='<div class="card" style="max-width:none"><h3>Phase logic — interactive</h3>';
      h+='<iframe id="phaseFrame" class="phaseframe" srcdoc="'+PHASE_VIEWS[o.name].replace(/&/g,"&amp;").replace(/"/g,"&quot;")+'"></iframe>';
      h+='</div>';
    } else if(_hasLazy && typeof EXPORT_TOKEN!=='undefined' && EXPORT_TOKEN){
      // lazy: fetch this phase's interactive view on demand (built server-side only
      // when opened, so large exports don't render every phase up front)
      var _src='/phase_view?t='+encodeURIComponent(EXPORT_TOKEN)+'&p='+encodeURIComponent(o.name);
      h+='<div class="card" style="max-width:none"><h3>Phase logic — interactive</h3>';
      h+='<iframe id="phaseFrame" class="phaseframe" src="'+_src+'" loading="lazy"></iframe>';
      h+='</div>';
    } else {
      h+='<div class="card"><h3>Phase logic</h3><span class="empty">No parsed logic available for this phase in this export.</span></div>';
    }
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
    h+='<div class="card"><h3>Detail</h3><span class="empty">Detailed Recipe view (procedure tree, parameters) plugs in here.</span></div>';
  }
  if(o._type==='FB Type'){
    h+='<div class="card"><h3>Standard DeltaV Function Block</h3>';
    if(o.glossary) h+='<p style="margin:0 0 8px">'+esc(o.glossary)+'</p>';
    h+='<div class="kv"><div class="k">DeltaV description</div><div>'+esc(o.description||'—')+'</div>';
    h+='<div class="k">Type code</div><div><code>'+esc(o.name)+'</code></div></div>';
    h+='<p class="empty" style="margin-top:10px">A primitive block type provided by DeltaV (not a user composite). Instances of it appear inside control/equipment module diagrams.</p>';
    h+='</div>';
  }
  document.getElementById('detail').innerHTML=h;
}

function toggle(el,e){e.stopPropagation();const ul=el.closest('.navgroup').querySelector('.navchildren');if(ul){ul.style.display=ul.style.display==='none'?'block':'none';el.textContent=ul.style.display==='none'?'▸':'▾';}}
function secToggle(sid,el){const b=document.getElementById(sid);if(!b)return;const open=b.style.display!=='none';b.style.display=open?'none':'block';const a=el.querySelector('.secarrow');if(a)a.textContent=open?'▸':'▾';}

// ── view stack so the back button returns to the previous view ──
let VIEW_STACK=[];
function renderEntry(e){
  if(e.k==='obj') renderObj(e.id);
  else if(e.k==='fbd') renderFbd(e.def,e.label);
  else if(e.k==='param') renderParam(e.name);
  else if(e.k==='inst') renderInstance(e.iid);
  else if(e.k==='dep') renderDeployed(e.tag);
  const d=document.getElementById('detail'); if(d) d.scrollTop=0;
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
  var h='<div class="card" style="max-width:none">';
  h+='<div class="emtabs">';
  h+='<button class="emtab on" data-e="fb" onclick="emTab(this,\\'fb\\')">Function Blocks</button>';
  if(ev.state) h+='<button class="emtab" data-e="state" onclick="emTab(this,\\'state\\')">'+(stateSet?'State Table':'Command Logic')+'</button>';
  if(ev.cms&&ev.cms.length) h+='<button class="emtab" data-e="cms" onclick="emTab(this,\\'cms\\')">Control Modules ('+ev.cms.length+')</button>';
  h+='</div>';
  h+='<div class="empanel on" data-e="fb" id="empanel_fb">'+(ev.fbd||'<span class="empty">No function block layer.</span>')+'</div>';
  if(ev.state) h+='<div class="empanel" data-e="state"><iframe class="phaseframe" srcdoc="'+ev.state.replace(/&/g,"&amp;").replace(/"/g,"&quot;")+'"></iframe></div>';
  if(ev.cms&&ev.cms.length){
    h+='<div class="empanel" data-e="cms"><div class="chips">';
    ev.cms.forEach(function(c){h+='<span class="chip" onclick="show(\\'cm:'+esc(c.name)+'\\')">'+esc(c.name)+' · '+c.n_blocks+' blocks</span>';});
    h+='</div></div>';
  }
  h+='</div>';
  return h;
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
function showDeployed(tag){ if(DB.deployed_modules&&DB.deployed_modules[tag]) navTo({k:'dep',tag:tag}); }

// link to a module by name, resolving to whatever navigable view exists for it
function modLink(name){
  var c=['em:'+name,'cm:'+name,'composite:'+name,'uclass:'+name,'phase:'+name];
  for(var i=0;i<c.length;i++){ if(DB.objs[c[i]]) return '<span class="link" onclick="show(\\''+c[i]+'\\')">'+esc(name)+'</span>'; }
  if(FBD_VIEWS[name] || (typeof FBD_NAMES!=='undefined' && FBD_NAMES.indexOf(name)>=0)) return '<span class="link" onclick="showFbd(\\''+esc(name)+'\\',\\''+esc(name)+'\\')">'+esc(name)+'</span>';
  return esc(name);
}

// ── parameter cross-reference card (database-wide) ──
function renderParam(name){
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
  var d=document.getElementById('detail'); d.innerHTML=h; d.scrollTop=0;
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
  var dd=document.getElementById('detail'); dd.innerHTML=h; dd.scrollTop=0;
}

// ── deployed module instance (a real tag in a unit) ──
function renderDeployed(tag){
  var d=DB.deployed_modules&&DB.deployed_modules[tag]; if(!d){return;}
  document.querySelectorAll('.navitem').forEach(n=>n.classList.remove('sel'));
  document.querySelectorAll('.navinst').forEach(function(n){n.classList.toggle('sel',n.dataset.tag===tag&&n.dataset.dep==='1');});
  var isEM=!!DB.objs['em:'+d.cls];
  var back=VIEW_STACK.length>1?' <span class="link" onclick="goBack()">← back</span>':'';
  var h='<h2 class="dt">'+esc(d.tag)+'</h2><span class="dt-type" style="background:'+(isEM?'#0f766e':'#6d28d9')+'">'+(isEM?'EM':'CM')+' instance</span>';
  h+='<p class="dt-desc">Deployed '+(isEM?'equipment':'control')+' module · instance of '+modLink(d.cls)+'.'+back+'</p>';
  h+='<div class="card"><h3>Identity</h3><div class="kv">';
  h+='<div class="k">Tag</div><div><code>'+esc(d.tag)+'</code></div>';
  h+='<div class="k">Class</div><div>'+modLink(d.cls)+'</div>';
  h+='<div class="k">Unit</div><div>'+(DB.objs['unit:'+d.unit]?'<span class="link" onclick="show(\\'unit:'+esc(d.unit)+'\\')">'+esc(d.unit)+'</span>':esc(d.unit))+'</div>';
  var ctl=(DB.module_controller&&DB.module_controller[tag])||'';
  if(ctl) h+='<div class="k">Controller</div><div><code>'+esc(ctl)+'</code> <span style="color:var(--ink-3);font-size:12px">· Physical Network</span></div>';
  h+='<div class="k">Location</div><div><code>'+esc(d.path)+'</code></div>';
  h+='</div>';
  h+='<button class="bigbtn" onclick="viewClass(\\''+esc(d.cls)+'\\')">View class logic &amp; parameters →</button></div>';
  // sibling tags of the same class in the same unit
  var sibs=(DB.unit_modules[d.unit]||[]).map(function(t){return DB.deployed_modules[t];}).filter(function(s){return s&&s.cls===d.cls&&s.tag!==d.tag;});
  if(sibs.length){
    h+='<div class="card"><h3>Other '+esc(d.cls)+' tags in this unit ('+sibs.length+')</h3><div class="chips">';
    sibs.forEach(function(s){h+='<span class="chip" onclick="showDeployed(\\''+esc(s.tag)+'\\')">'+esc(s.tag)+'</span>';});
    h+='</div></div>';
  }
  var vals=[];
  for(var pn in PARAM_INDEX){(PARAM_INDEX[pn].vals||[]).forEach(function(v){if(v.m===d.cls)vals.push({p:pn,cv:v.cv});});}
  if(vals.length){
    h+='<div class="card"><h3>Configured values ('+vals.length+')</h3>';
    h+='<p class="empty" style="margin:0 0 8px">Inherited from class '+esc(d.cls)+'. No instance overrides in the export.</p>';
    h+='<table class="fbd-table"><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>';
    vals.forEach(function(v){h+='<tr><td><span class="link" onclick="showParam(\\''+esc(v.p)+'\\')">'+esc(v.p)+'</span></td><td>'+(v.cv===''?'<span style="color:#94a3b8">(empty)</span>':'<code>'+esc(v.cv)+'</code>')+'</td></tr>';});
    h+='</tbody></table></div>';
  }
  var dd2=document.getElementById('detail'); dd2.innerHTML=h; dd2.scrollTop=0;
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
    d.innerHTML=h; d.scrollTop=0; wireFbdLinks();
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
                    nav.append(f'<div class="navitem {_ncls(lvl + 2)} navinst" '
                               f'data-parent="{html.escape(cls)}" data-tag="{html.escape(itag)}" '
                               f'onclick="showInst(this.dataset.parent,this.dataset.tag)" '
                               f'title="{html.escape(itag)} (instance of {html.escape(icls)})">'
                               f'{_nav_badge("inst")}<span class="inst-tag">{html.escape(itag)}</span>'
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
                nav.append(f'<div class="navitem navchild navinst" '
                           f'data-parent="{html.escape(ename)}" data-tag="{html.escape(tag)}" '
                           f'onclick="showInst(this.dataset.parent,this.dataset.tag)" '
                           f'title="{html.escape(tag)} (instance of {html.escape(cls)})">'
                           f'{_nav_badge("inst")}<span class="inst-tag">{html.escape(tag)}</span>'
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
        _fold('Recipes', collapsed=True, count=len(catalog['recipes']))
        _items(catalog['recipes'], 'recipe'); _endfold()
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
            f'title="Download an Excel workbook generated from this database">&#8681; Excel</a>'
            f'<a class="exp-btn" href="/export?token={tk}&amp;fmt=word&amp;name={ft}" '
            f'title="Download a Word DDS document generated from this database">&#8681; Word DDS</a>'
            f'<a class="exp-btn" href="javascript:void 0" title="Open the FHX Converter wizard" onclick="switchView(\'converter\')">&#9881; Converter</a>'
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
{fbd_bridge.EXPR_MODAL_CSS}</style></head><body>
<div class="app">
<nav class="rail">
  <div class="brand" title="DeltaV Strategy Workbench">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M12 2 4 6.5v9L12 20l8-4.5v-9L12 2Z"/><path d="M12 7v6M9 9.5h6"/></svg>
  </div>
  <a class="rail-btn active" id="rb-explorer" href="javascript:void 0" title="Explorer" onclick="switchView('explorer')">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
    <span class="tip">Explorer</span></a>
  <a class="rail-btn" id="rb-converter" href="javascript:void 0" title="FHX Converter" onclick="switchView('converter')">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M4 12h16M4 17h10"/><path d="M17 15l3 2-3 2"/></svg>
    <span class="tip">FHX Converter</span></a>
  <div class="spacer"></div>
</nav>
<header class="topbar">
  <h1>DeltaV Strategy Workbench</h1><span class="sub">{html.escape(fname)}</span>
  <div class="hdr-right">{theme_html}
    <button class="iconbtn" id="themeBtn" title="Toggle light / dark" onclick="toggleMode()">
      <svg id="themeIco" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/></svg>
    </button>{export_html}</div>
</header>
<main class="main">
  <div class="panes">
    <div class="nav">{''.join(nav)}</div>
    <div class="detail" id="detail">{welcome}</div>
  </div>
</main>
<div id="view-converter"><iframe id="convFrame" title="FHX Converter"></iframe></div>
</div>
<script>
const ICON_THEMES={themes_json};
const THEME_COLORS={tcolors_json};
const EXPORT_TOKEN={json.dumps(export_token or "")};
function exportBar(obj,name){{
  if(!EXPORT_TOKEN) return '';
  var base='/export?token='+encodeURIComponent(EXPORT_TOKEN)+'&obj='+encodeURIComponent(obj)+'&name='+encodeURIComponent(name);
  return '<div class="card"><h3>Export this object</h3>'
    +'<div style="display:flex;gap:8px">'
    +'<a class="exp-btn" href="'+base+'&fmt=excel">&#8681; Excel</a>'
    +'<a class="exp-btn" href="'+base+'&fmt=word">&#8681; Word DDS</a></div>'
    +'<div style="margin-top:9px;color:var(--ink-3);font-size:12px">Generates a validation-ready document for this object only.</div></div>';
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
</script>
<script>const S88_SVG={s88_svg_json};
{s88_model.S88_JS}</script>
<script>{js}
{fbd_bridge.EXPR_MODAL_JS}</script>
</body></html>"""
