"""
Generate the explorer HTML from an FHX file — no server needed.

Usage:
    python make_explorer.py  path/to/export.fhx  [output.html]

Then just open the resulting .html in any browser.
"""
import sys, os
import db_parser, db_explorer
try:
    import phase_bridge
    HAS_PHASE = True
except Exception:
    HAS_PHASE = False

if len(sys.argv) < 2:
    print("Usage: python make_explorer.py  path/to/export.fhx  [output.html]")
    sys.exit(1)

infile = sys.argv[1]
outfile = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(infile)[0] + "_explorer.html"

raw = open(infile, "rb").read()
text = db_parser.decode_fhx(raw)
fname = os.path.splitext(os.path.basename(infile))[0]

print(f"Parsing {infile} ...")
catalog = db_parser.parse_database(text)
s = db_parser.catalog_summary(catalog)
print("  " + ", ".join(f"{k}={v}" for k, v in s.items() if v))

phase_views = {}
if HAS_PHASE:
    try:
        print("Building phase views ...")
        phase_views = phase_bridge.phase_view_map(text)
        print(f"  {len(phase_views)} phase view(s)")
    except Exception as e:
        print(f"  (phase views skipped: {e})")

html = None
fbd_views, em_views = {}, {}
try:
    import fbd_bridge
    fbd_views = fbd_bridge.build_fbd_views(text)
    print(f"  {len(fbd_views)} FBD view(s)")
    _ix = fbd_bridge.build_indexes(text)
    param_index, expr_index = _ix['params'], _ix['exprs']
    print(f"  {len(param_index)} parameter(s), {len(expr_index)} expression(s) indexed")
except Exception as e:
    print(f"  (FBD views skipped: {e})")
    param_index, expr_index = {}, []
try:
    import em_bridge
    em_views = em_bridge.build_em_views(text)
    print(f"  {len(em_views)} EM view(s)")
except Exception as e:
    print(f"  (EM views skipped: {e})")

html = db_explorer.build_explorer_html(catalog, fname, phase_views=phase_views,
                                       fbd_views=fbd_views, em_views=em_views,
                                       param_index=param_index, expr_index=expr_index)
open(outfile, "w", encoding="utf-8").write(html)
print(f"\nDone -> {outfile}\nOpen that file in any browser.")
