"""
rail.py — the persistent app-switcher rail, shared by all three surfaces:
landing page (/), explorer (loaded DB), and converter (/tool/).

One source of truth for the dark workbench rail so the three surfaces stay
visually identical. Each surface passes which app is `active`:
    'explorer'  -> Explorer button highlighted
    'converter' -> Converter button highlighted

Buttons are real navigation links:
    Explorer  -> '/'        (upload screen, or the loaded explorer)
    Converter -> '/tool/'
The Workbench mark links home ('/'). Inside the loaded explorer, the page's own
switchView() still swaps Explorer<->Converter live via the embedded iframe (no DB
reload); on the landing and converter pages these are plain links.

The CSS uses fixed positioning with a body left-pad, so it overlays cleanly on a
page that wasn't built with a rail (the landing page). The explorer, which lays
the rail out in its own CSS grid, keeps using its in-grid rail and does NOT use
this fixed variant — it only shares the MARKUP via rail_buttons() if desired.
"""

MOUNT = '/tool'

# Brand mark + the two app buttons. `active` selects which is highlighted.
_BRAND = (
    '<div class="dvx-brand" title="DeltaV Strategy Workbench">'
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" '
    'stroke-width="2"><path d="M12 2 4 6.5v9L12 20l8-4.5v-9L12 2Z"/>'
    '<path d="M12 7v6M9 9.5h6"/></svg></div>'
)
_EXPLORER_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">'
    '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
    '<rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>'
)
_CONVERTER_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">'
    '<path d="M4 7h16M4 12h16M4 17h10"/><path d="M17 15l3 2-3 2"/></svg>'
)


def rail_css(fixed=True):
    """Rail stylesheet. fixed=True overlays the rail with position:fixed and pads
    the body (for pages without a rail layout, like the landing page)."""
    pos = ("position:fixed;left:0;top:0;bottom:0;z-index:9999;"
           if fixed else "")
    bodypad = "body{padding-left:60px!important}" if fixed else ""
    return f"""<style>
.dvx-rail{{{pos}width:60px;background:#10202f;display:flex;flex-direction:column;
  align-items:center;padding:10px 0;gap:4px;font-family:'IBM Plex Sans',system-ui,sans-serif}}
{bodypad}
.dvx-brand{{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;margin-bottom:14px;
  background:linear-gradient(140deg,#2563eb,#0e7490);text-decoration:none}}
.dvx-rbtn{{width:42px;height:42px;border-radius:11px;color:#9fb4c9;display:grid;place-items:center;
  position:relative;transition:.15s;text-decoration:none}}
.dvx-rbtn svg{{width:21px;height:21px}}
.dvx-rbtn:hover{{background:rgba(255,255,255,.07);color:#cfe0f0}}
.dvx-rbtn.active{{background:rgba(96,165,250,.16);color:#fff}}
.dvx-rbtn.active::before{{content:"";position:absolute;left:-10px;top:9px;bottom:9px;width:3px;
  border-radius:3px;background:#60a5fa}}
.dvx-rbtn .dvx-tip{{position:absolute;left:50px;white-space:nowrap;background:#10202f;color:#e6edf3;
  padding:5px 9px;border-radius:7px;font-size:12px;opacity:0;pointer-events:none;transform:translateX(-4px);
  transition:.12s;box-shadow:0 8px 24px -12px rgba(0,0,0,.5);z-index:30}}
.dvx-rbtn:hover .dvx-tip{{opacity:1;transform:translateX(0)}}
.dvx-spacer{{flex:1}}
</style>"""


def rail_html(active='explorer'):
    """The rail markup. active in {'explorer','converter'} highlights that button."""
    exp_cls = 'dvx-rbtn active' if active == 'explorer' else 'dvx-rbtn'
    conv_cls = 'dvx-rbtn active' if active == 'converter' else 'dvx-rbtn'
    return f"""<nav class="dvx-rail">
  <a class="dvx-brand" href="/" title="DeltaV Strategy Workbench">{_BRAND_INNER}</a>
  <a class="{exp_cls}" href="/" title="Explorer">{_EXPLORER_SVG}
    <span class="dvx-tip">Explorer</span></a>
  <a class="{conv_cls}" href="{MOUNT}/" title="FHX Converter">{_CONVERTER_SVG}
    <span class="dvx-tip">FHX Converter</span></a>
  <div class="dvx-spacer"></div>
</nav>"""


# brand mark inner svg (the <a> wrapper is added in rail_html so the mark links home)
_BRAND_INNER = (
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" '
    'stroke-width="2"><path d="M12 2 4 6.5v9L12 20l8-4.5v-9L12 2Z"/>'
    '<path d="M12 7v6M9 9.5h6"/></svg>'
)


def inject(html, active='explorer', fixed=True):
    """Graft the rail CSS into <head> and the rail markup right after <body>."""
    css = rail_css(fixed=fixed)
    nav = rail_html(active=active)
    if '</head>' in html:
        html = html.replace('</head>', css + '</head>', 1)
    else:
        html = css + html
    if '<body>' in html:
        html = html.replace('<body>', '<body>' + nav, 1)
    else:
        html = nav + html
    return html
