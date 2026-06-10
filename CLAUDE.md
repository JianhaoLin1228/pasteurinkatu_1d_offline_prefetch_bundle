# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A fully offline, single-page Leaflet map centered on **Pasteurinkatu 1D, Helsinki**. It renders real HSL transit routes (derived from GTFS `shapes.txt`), walking-distance circles, and commute/isochrone reachability polygons computed from GTFS timetables. Everything — basemap tiles, JS library, and data — is bundled locally so `offline/index.html` opens with no network and no build step. UI text is in Chinese (zh-CN).

There is no package manager, build system, test suite, or server. "Running" the app means opening the HTML file in a browser.

## Running

```bash
# Just open the bundled page (all data embedded inline, works from file://):
open offline/index.html
```

`offline/index.html` is **self-contained**: route GeoJSON, stops, metadata, and the commute isochrone polygons are all inlined as JS consts (`ROUTES_GEOJSON`, `STOPS_DATA`, `META_DATA`, etc.). It does **not** use `fetch()`, so it works directly from `file://`.

`offline/index_fetch_version.html` is the alternate variant that `fetch()`es the same data from `offline/data/*.{geojson,json}`. Because of browser CORS rules on `file://`, this version must be served over HTTP:

```bash
cd offline && python3 -m http.server 8000   # then open http://localhost:8000/index_fetch_version.html
```

## Architecture

### Layout
- `offline/index.html` — the main, self-contained app. The Leaflet map, tile layer (`tiles/{z}/{x}/{y}.png`), route polylines, stop markers, walking circles, and commute isochrone overlays are all built here, with a `L.control.layers` overlay toggle. This is the file end users open.
- `offline/index_fetch_version.html` — minimal version that loads data at runtime from `data/`.
- `offline/assets/leaflet.{js,css}` — vendored Leaflet, loaded by relative path.
- `offline/tiles/{z}/{x}/{y}.png` — pre-fetched OSM raster tiles, zoom 10–16, covering the bbox in `data/metadata.json`.
- `offline/data/` — the source data also embedded into `index.html`:
  - `routes.geojson` + `stops.json` + `metadata.json` — HSL route shapes, nearby stops, bbox/route list.
  - `commute_*.geojson` + matching `*_metadata.json` — reachability isochrones. The metadata documents the computation: GTFS timetable-based **CSA (Connection Scan Algorithm)**, sampled departures 07:30–08:30 on `service_date`, waiting time included by schedule, walking at 80 m/min; the union of samples approximates average waiting.
- `offline/raw/hsl.zip` — the raw GTFS feed the route/commute data was derived from.

### The Python scripts are HTML post-processors, not an app
The `*.py` files at the repo root each **idempotently patch `offline/index.html`** by injecting or removing a single uniquely-IDed `<script id="...">` block (and sometimes CSS). They are layered UI tweaks applied one at a time. Key conventions every such script follows — match them when writing a new one:

1. Resolve `offline/index.html` relative to the script; bail if missing.
2. Before the first edit, save a backup to `offline/index_before_<change>.html` **only if it doesn't already exist** (so re-running never clobbers the original).
3. Remove any prior copy of its own `<script id="...">` block before re-inserting, making the script safe to run repeatedly.
4. Inject before `</body></html>` / `</body>`, falling back to append.

The injected client scripts themselves re-run on `DOMContentLoaded` and again on several `setTimeout`s (250ms–3.5s), because later-injected scripts and Leaflet controls may not exist yet when they first fire. Existing injected IDs include `remove-left-info-panel-only-final`, `default-checked-20-30-walk15-final`, `keep-only-title-buttons-final`, `ui-cleanup-v2`, `ui-relayout-title-buttons-bottom-info`, and `final-layer-reset-commute-walking`.

The many `offline/index_before_*.html` files are these auto-generated backups — they are the edit history, not alternate apps; do not treat them as sources.

### Important consequence: data lives in two places
Because `index.html` embeds copies of the `data/` files, regenerating the data under `data/` does **not** update the rendered map. To change what `index.html` shows you must either re-embed the data into `index.html` or edit the inline consts directly.
