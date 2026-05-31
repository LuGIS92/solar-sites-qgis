# Changelog

Alle wesentlichen Änderungen werden hier dokumentiert.
Format: [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [2.2.0] - 2026-05-31

### Neu
- **MaStR im OSM-Modus**: optionaler GeoPackage-Picker auf Seite 1 –
  PV-Bestandsanlagen lassen sich jetzt auch bei OSM-Datenquellen abgleichen
- **„Gesamten Layer als Suchgebiet"**: neuer Schnellauswahl-Button auf Seite 2,
  setzt BBox automatisch auf den vollen Extent des gewählten GeoPackage-Layers
  oder der PostGIS-Tabelle (`ST_Extent`); kein manuelles Koordinaten-Eintragen nötig

### Behoben
- `skip_mastr`-Checkbox auf Seite 3 ist im OSM-Modus ohne MaStR-GPKG ausgeblendet
  (war vorher sichtbar, aber wirkungslos)
- `config.py` läuft jetzt auch ohne `pydantic-settings` (Fallback auf stdlib `.env`-Parser);
  behebt `ImportError: cannot import name 'Sentinel' from 'typing_extensions'` in QGIS 4

---

## [2.1.0] - 2026-05-30

### Geändert
- **QGIS 4 / Qt6-Kompatibilität**: unskopierte Enums voll qualifiziert
  (`Qt.AlignmentFlag.AlignCenter`, `Qt.DockWidgetArea.RightDockWidgetArea`,
  `QFrame.Shape.*` / `QFrame.Shadow.*`); `metadata.txt` mit `qgisMaximumVersion=4.99`

### CI
- QGIS-Integrations-Tests via `pytest-qgis` + `qgis/qgis`-Docker (QGIS 3 LTR + QGIS 4)
- CI triggert jetzt auch auf Release-Tags (`v*.*.*`)

---

## [2.0.0] - 2026-05-23

### Neu
- **OpenStreetMap-Datenquelle** via Overpass-API – keine lokalen Daten nötig,
  weltweit einsetzbar (`solar_sites/buildings/overpass.py`)
- `OverpassSource` in `data_sources.py` mit identischem Interface wie PostGIS/GeoPackage
- OSM-Gebäudetyp-Filter (`house`, `industrial`, …) als dritte Kategorie neben ALKIS-Codes
- Wizard-Seite 2 (Spalten-Zuordnung) wird im OSM-Modus automatisch übersprungen
- Konfigurierbare Overpass-URL und Timeout in der UI
- **38 pytest-Tests** (kein QGIS/DB erforderlich): Geometrie-Hilfsfunktionen,
  HTTP-Mocking, Filterlogik, SQL-Injection-Schutz

### Geändert
- **QGIS 4 / Qt6-Kompatibilität** hergestellt (lauffähig unter Qt5 **und** Qt6):
  - alle `PyQt5.*`-Importe auf den `qgis.PyQt`-Shim umgestellt
  - unskopierte Enums voll qualifiziert (`Qt.AlignCenter` → `Qt.AlignmentFlag.AlignCenter`,
    `Qt.RightDockWidgetArea` → `Qt.DockWidgetArea.RightDockWidgetArea`,
    `QFrame.HLine/Sunken/NoFrame` → `QFrame.Shape.*` / `QFrame.Shadow.*`)
  - `QVariant`-Feldtypen mit Fallback auf `QMetaType.Type.*` (PyQt6 kennt `QVariant.String` nicht)
  - `metadata.txt`: `qgisMaximumVersion=4.99` ergänzt
- HTTP-Client für Overpass von `requests` auf `urllib` (Python-Stdlib) umgestellt –
  robuster in QGIS-Python-Umgebung, keine externe Abhängigkeit
- README vollständig auf Deutsch überarbeitet und auf drei Datenquellen aktualisiert

### Behoben
- Alle 52 ruff-Lint-Fehler behoben: Import-Sortierung (I001), Semikolon-Zeilen (E702),
  ambiguous Variable `l` (E741), Multi-Import (E401), f-String ohne Platzhalter (F541)

### CI
- **QGIS-Integrations-Tests** via `pytest-qgis` und `qgis/qgis`-Docker-Images:
  6 Tests für `layer_builder.py` (Layer-Validität, Feldschema, Symbologie, GeoPackage-Export)
- Matrix-Job: QGIS 3 LTR (Pflicht) + QGIS 4 Qt6 (experimental, Fehler bricht Build nicht)
- Regulärer Unit-Test-Job ignoriert `tests/qgis/` (kein QGIS nötig, bleibt schnell)

---

## [1.0.0] - 2025-05-23

### Added
- 5-page wizard UI: data source, column mapping, search area, filters, results
- Data sources: QGIS PostgreSQL/PostGIS (ALKIS) and GeoPackage
- Solar estimation via DLR Building Solar Atlas (primary) and PVGIS API (fallback)
- Multi-zoom fallback for DLR WMTS (zoom 19 -> 18 -> 17 -> 16) + pixel jitter
- MaStR registry check (PostGIS table or GeoPackage layer)
- Optional YOLO panel detection via leafmap + ultralytics
- Optional Nominatim reverse geocoding for address fields in Excel
- Flexible building type filter: ALKIS presets and free-text substring search
- BBox shortcuts: current map view, loaded layer extent, city/ZIP geocoding
- Column mapping UI including MaStR power and geometry columns
- QGIS Auth Manager integration (no plaintext passwords)
- Graduated colour symbology on result layer (red to green by kWh/yr)
- Excel (.xlsx) and GeoPackage export of results
- Background thread for analysis so QGIS stays responsive
- Sample GeoPackage with 20 synthetic buildings (Cologne area, WGS84)
- Build script for distributable ZIP (scripts/build_zip.sh)
