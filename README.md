# DeltaV Single-Object Viewers

Standalone tools to view ONE control module (CM) or equipment module (EM)
export at a time — for quick verification without running the whole database
explorer. They reuse the same parsing/rendering engines as the explorer, so
output stays consistent.

## CM Viewer
    python cm_viewer.py  CM_export.fhx  [output.html]

Produces a focused page for the control module:
- sectioned function block diagram (resembles the DeltaV print)
- clickable nested composite drill-down
- module parameter interface table (params -> internal references)
- block inventory + connection list

## EM Viewer
    python em_viewer.py  EM_export.fhx  [output.html]

Produces a focused page for the equipment module, with tabs:
- Function Blocks: the EM's FBD layer (acquire/release, monitors, timers)
- Command / State Logic: each command (HOLD, RUN, etc.) as its own SFC diagram
- Control Modules: the embedded CMs the EM references

## Notes
- FHX-only: structure, wiring, composites, interface, command logic. No
  configured tuning/alarm values (those aren't in a class export).
- Reuses ../db_explorer (FBD engine) and ../db_explorer/core (converter SFC
  engine). Keep those alongside, or set FHX_CORE_DIR.
- If an export bundles multiple modules, the most substantial one is shown by
  default; others are listed.
