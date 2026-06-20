# DeltaV Database Explorer

Upload a DeltaV database FHX export and browse it live: areas, units,
equipment/control/phase classes, recipes, composites — with class/instance
cross-linking and interactive phase logic (SFC diagram, parameters, monitors).

## Run locally
    pip install -r requirements.txt
    python server.py
    # open http://localhost:5000

## Deploy on Render  (NO Dockerfile needed)
Create a new **Web Service** from this repo with:
- **Language / Runtime:** Python 3
- **Build Command:**  `pip install -r requirements.txt`
- **Start Command:**  `gunicorn server:app`
- **Plan:** Free is fine

That's it. The earlier "failed to read dockerfile" error happened because
Render didn't detect a Python web service and fell back to Docker. Setting the
Build/Start commands above (or committing the included `render.yaml`) makes
Render use the Python runtime instead — no Dockerfile required.

## Project layout
- `server.py`        — Flask web app (upload form + /explore route)
- `db_parser.py`     — catalogs an FHX export into the object model
- `db_explorer.py`   — renders the navigable explorer HTML
- `phase_bridge.py`  — bridges to the parsing core for phase drill-down
- `core/`            — copy of the converter's parsing core (phase parser,
                       sfc_html, sfc_image, recipe_module). Self-contained so
                       the explorer deploys independently of the converter repo.
- `requirements.txt`, `render.yaml`, `Procfile` — deployment config

## Notes
- Free tier spins down after ~15 min idle (30–60 s cold start). Large exports
  (full Area, ~30 MB) take a minute to parse on first request.
- Phase drill-down reuses the validated converter parsing core; if `core/` is
  absent the explorer still works (catalog + navigation), just without the
  embedded phase viewer.
