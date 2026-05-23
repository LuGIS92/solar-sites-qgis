# Solar Sites – QGIS PV Analysis Plugin

A QGIS plugin for automated rooftop solar potential screening of buildings.
Loads building footprints from **ALKIS/PostGIS** or a **GeoPackage**, queries
irradiance data from **PVGIS** and the **DLR Solar Atlas**, cross-checks
registrations in the **Marktstammdatenregister (MaStR)**, and produces a
colour-coded vector layer plus an Excel report — all without leaving QGIS.

> Focused on Germany, but works with any building dataset that can be loaded
> into QGIS.

---

## Features

| Feature | Details |
|---|---|
| **Two data sources** | QGIS PostgreSQL connection (ALKIS/PostGIS) or any GeoPackage |
| **Solar estimation** | DLR Building Solar Atlas (primary) · PVGIS API (fallback) |
| **MaStR check** | Marks buildings already registered in the German PV registry |
| **Panel detection** | Optional YOLO-based detection on satellite imagery (requires `leafmap`) |
| **Flexible filters** | Min. roof area · building type presets · free-text filter |
| **BBox shortcuts** | Current map view · any loaded layer's extent · city/ZIP geocoding |
| **Column mapping** | Map arbitrary column names to required fields (Wizard page 2) |
| **Exports** | QGIS vector layer (graduated colour) · Excel (.xlsx) · GeoPackage |
| **Non-blocking** | Analysis runs in a background thread; QGIS stays responsive |

---

## Requirements

| Requirement | Version |
|---|---|
| QGIS | ≥ 3.16 |
| Python | ≥ 3.9 (ships with QGIS) |

### Python packages (install once in QGIS Python)

Open **QGIS → Plugins → Python Console** and run:

```python
import pip
# Minimum (Excel export + config):
pip.main(['install', 'pandas', 'openpyxl', 'pydantic-settings'])

# PostGIS mode:
pip.main(['install', 'psycopg2-binary'])

# Optional – YOLO panel detection:
pip.main(['install', 'leafmap', 'ultralytics'])
```

`requests` is already bundled with QGIS.

---

## Installation

1. Download `solar_sites_pv_analysis_vX.X.X.zip` from the
   [Releases page](https://github.com/LuGIS92/solar_sites_search/releases).
2. In QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**.
3. Select the downloaded ZIP → **Install Plugin**.
4. Enable the plugin if not already checked.
5. A sun icon appears in the toolbar. Click it to open the analysis panel.

### Build the ZIP yourself

```bash
git clone https://github.com/LuGIS92/solar_sites_search.git
cd solar_sites_search
bash scripts/build_zip.sh
# → dist/solar_sites_pv_analysis_vX.X.X.zip
```

---

## Quick Start (with sample data)

A small test GeoPackage with 20 synthetic buildings in the Cologne area is
included in `data/sample.gpkg`.

1. Open QGIS and load a basemap (e.g. OpenStreetMap via QuickMapServices).
2. Open the Solar Sites panel (toolbar or **Plugins → Solar Sites**).
3. **Step 1 – Data source:** select *GeoPackage*, choose `data/sample.gpkg`,
   layer `buildings`.
4. **Step 2 – Column mapping:** click *Load columns*, then *Next* (auto-detect works).
5. **Step 3 – Search area:** click *Current map view* or type `Köln` and press Enter.
6. **Step 4 – Filters:** leave defaults, click **Start Analysis**.
7. A new point layer *Solar XXXX* appears on the map, colour-coded by annual yield.
   Green = high potential, red = low potential.

---

## Data Sources

### Option A – PostGIS (ALKIS)

Requires a PostgreSQL/PostGIS database with ALKIS building data.

| Setting | Default | Description |
|---|---|---|
| Connection | — | QGIS-managed PostgreSQL connection |
| Buildings table | `deutschland.gebaeude_deutschland_tbl` | ALKIS polygon table (SRID 3035) |
| MaStR table | `deutschland.mastr_solar` | Point table with PV registrations (optional) |

**Expected columns (ALKIS standard):**

| Column | Type | Notes |
|---|---|---|
| `gml_id` | TEXT | Unique building ID |
| `geom` | GEOMETRY(Polygon, 3035) | Footprint |
| `area` | DOUBLE PRECISION | Roof area m² (or computed via ST_Area) |
| `gebaeudefunktion` | TEXT | ALKIS building function code |
| `roof_type` | TEXT | Roof shape (optional) |

Non-standard column names can be remapped on Wizard page 2.

### Option B – GeoPackage

Any polygon layer works. The plugin auto-detects common column names and
falls back gracefully when fields are missing.

**Create a test GeoPackage from your PostGIS:**

```bash
python scripts/export_test_gpkg.py \
  --host localhost --dbname energy \
  --user readonly --password secret \
  --buildings-table deutschland.gebaeude_deutschland_tbl \
  --mastr-table deutschland.mastr_solar \
  --output test.gpkg \
  --city-bbox "50.920,6.930,50.960,6.990"
```

**MaStR as GeoPackage** – easiest via
[open-mastr](https://open-mastr.readthedocs.io/en/latest/advanced/):

```bash
pip install open-mastr
python -c "
from open_mastr import Mastr
db = Mastr()
db.download(date='today')
db.to_csv()
# Then import the solar CSV into QGIS → save as GeoPackage
"
```

---

## Output Fields

| Field | Unit | Source |
|---|---|---|
| `annual_energy_kwh` | kWh/yr | DLR or PVGIS |
| `installable_kwp` | kWp | DLR panel area or estimated |
| `usable_area_sqm` | m² | DLR or estimated |
| `pvgis_irradiation` | kWh/kWp/yr | PVGIS API |
| `dlr_annual_kwh` | kWh/yr | DLR Building Solar Atlas |
| `data_source` | `dlr` / `pvgis` | Which source was used |
| `mastr_registered` | 0 / 1 | Found in MaStR registry |
| `mastr_capacity_kw` | kW | Total registered capacity nearby |
| `panels_detected` | 0 / 1 | YOLO detection result |
| `building_type` | text | ALKIS code or source value |
| `area_sqm` | m² | Building footprint area |

---

## Building Type Filter

The filter on Wizard page 4 accepts:

| Input | Effect |
|---|---|
| *(empty)* | All buildings |
| *Wohngebäude* preset | ALKIS codes `31001_1xxx` |
| *Gewerbe / Industrie* preset | ALKIS codes `31001_2xxx` / `31001_3xxx` |
| `31001_2620` | Exactly one ALKIS type (e.g. warehouse) |
| `industrial` | Free-text – any `building_type` containing this string |
| `Lager` | Same, case-insensitive |

---

## Configuration (`.env`)

Copy `.env.example` to `.env` next to the plugin and adjust as needed.
The plugin works without a `.env` file using sensible defaults.

```ini
# DLR Solar Atlas (public service, no API key)
DLR_ZOOM=19                  # Tile zoom level (17-19 recommended)

# PVGIS (EU JRC public API, no key)
PVGIS_SYSTEM_LOSS=14.0       # System losses in %

# Solar panel parameters
PANEL_EFFICIENCY=0.20        # Module efficiency (20 %)
PANEL_POWER_PER_SQM=0.175    # kWp per m²
ROOF_COVERAGE_FLAT=0.65      # Usable fraction on flat roofs
ROOF_COVERAGE_PITCHED=0.55   # Usable fraction on pitched roofs
```

---

## Development Setup

```bash
git clone https://github.com/LuGIS92/solar_sites_search.git
cd solar_sites_search
pip install -r requirements-dev.txt

# Symlink plugin into QGIS plugins folder (adjust path for your OS/profile)
# macOS / Linux:
ln -s "$(pwd)/qgis_solar_plugin" \
  ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/solar_sites_pv_analysis

# Windows:
# mklink /D "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\solar_sites_pv_analysis" \
#   "%CD%\qgis_solar_plugin"
```

After code changes, reload the plugin in QGIS via the
[Plugin Reloader](https://plugins.qgis.org/plugins/plugin_reloader/) extension.

---

## Repository Structure

```
solar_sites_search/
├── qgis_solar_plugin/       ← QGIS plugin (the UI layer)
│   ├── solar_dock.py        ← 5-page wizard (QStackedWidget)
│   ├── worker.py            ← Background analysis thread
│   ├── data_sources.py      ← PostGIS + GeoPackage data access
│   ├── layer_builder.py     ← Results → QGIS vector layer
│   └── qgis_db_utils.py     ← QGIS auth manager integration
├── solar_sites/             ← Pure-Python analysis library
│   ├── solar/               ← estimator, DLR, PVGIS, YOLO detection
│   ├── buildings/           ← building finder
│   ├── geocoding/           ← Nominatim reverse geocoding
│   └── export/              ← Excel export
├── data/
│   └── sample.gpkg          ← 20 sample buildings (Cologne, WGS84)
├── scripts/
│   ├── build_zip.sh         ← Build installable plugin ZIP
│   ├── create_sample_gpkg.py← Generate sample.gpkg (run once)
│   └── export_test_gpkg.py  ← Export test GeoPackage from PostGIS
└── migrations/              ← SQL for optional PostGIS result storage
```

---

## License

[GNU General Public License v3.0](LICENSE)

This plugin is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or any later version.
