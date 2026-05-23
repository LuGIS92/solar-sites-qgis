# Changelog

All notable changes are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
