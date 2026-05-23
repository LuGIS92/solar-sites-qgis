#!/usr/bin/env python3
"""
Export eines kleinen Test-GeoPackages aus PostgreSQL/PostGIS.

Exportiert via ogr2ogr (Teil von GDAL/QGIS) – keine fiona/PROJ-Abhängigkeit.

Voraussetzungen:
  - ogr2ogr im PATH (kommt mit QGIS oder GDAL)
  - psycopg2: pip install psycopg2-binary  (nur für den Verbindungstest)

Aufruf:
  python export_test_gpkg.py \
    --host localhost --port 5432 --dbname energy \
    --user readonly --password geheim \
    --buildings-table deutschland.gebaeude_deutschland_tbl \
    --output test_gebaeude.gpkg \
    --city-bbox "48.137,11.575,48.145,11.590"

  # Mit MaStR-Layer:
  python export_test_gpkg.py \
    --host localhost --port 5432 --dbname energy \
    --user readonly --password geheim \
    --buildings-table deutschland.gebaeude_deutschland_tbl \
    --mastr-table deutschland.mastr_solar \
    --output test_gebaeude.gpkg \
    --city-bbox "48.137,11.575,48.145,11.590"

QGIS-Plugin-Einstellungen danach:
  GeoPackage:       test_gebaeude.gpkg
  Layer:            buildings
  MaStR GeoPackage: test_gebaeude.gpkg  (gleiche Datei)
  MaStR-Layer:      mastr_solar

Spalten-Mapping (Seite 2 im Wizard):
  ID-Spalte:         id
  Gebäudetyp-Spalte: building_type
  Dachtyp-Spalte:    roof_type
  Fläche-Spalte:     area_sqm
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


_QGIS_ROOTS = [
    "/Applications/QGIS.app/Contents/MacOS",
    "/Applications/QGIS-LTR.app/Contents/MacOS",
    "/Applications/QGIS-3.app/Contents/MacOS",
    # Homebrew QGIS
    "/opt/homebrew/opt/qgis/QGIS.app/Contents/MacOS",
    "/usr/local/opt/qgis/QGIS.app/Contents/MacOS",
]


def _qgis_env() -> dict[str, str]:
    """Gibt PROJ_DATA / GDAL_DATA aus dem QGIS-Bundle zurück (falls vorhanden)."""
    for root in _QGIS_ROOTS:
        proj = f"{root}/share/proj"
        if os.path.isdir(proj):
            env = os.environ.copy()
            env["PROJ_DATA"] = proj
            env["PROJ_LIB"]  = proj
            gdal = f"{root}/share/gdal"
            if os.path.isdir(gdal):
                env["GDAL_DATA"] = gdal
            return env
    return os.environ.copy()


def _check_ogr2ogr() -> str:
    """Gibt den Pfad zu ogr2ogr zurück, oder bricht ab.

    QGIS-Bundle-Pfade werden zuerst geprüft, damit das richtige PROJ
    verwendet wird (System-ogr2ogr findet proj.db oft nicht).
    """
    candidates = [
        f"{root}/bin/ogr2ogr" for root in _QGIS_ROOTS
    ] + [
        "ogr2ogr",
        r"C:\Program Files\QGIS 3.40\bin\ogr2ogr.exe",
        r"C:\Program Files\QGIS 3.34\bin\ogr2ogr.exe",
        r"C:\OSGeo4W\bin\ogr2ogr.exe",
    ]
    for c in candidates:
        if shutil.which(c) or os.path.isfile(c):
            return c
    sys.exit(
        "ogr2ogr nicht gefunden.\n"
        "Tipp (macOS): QGIS installieren oder\n"
        "  export PATH=/Applications/QGIS.app/Contents/MacOS/bin:$PATH\n"
        "Dann nochmal ausführen."
    )


def _pg_uri(host: str, port: int, dbname: str, user: str, password: str) -> str:
    return f"PG:host={host} port={port} dbname={dbname} user={user} password={password}"


def export_buildings(
    ogr2ogr: str,
    pg_uri: str,
    buildings_table: str,
    min_lat: float, min_lon: float,
    max_lat: float, max_lon: float,
    output: str,
    limit: int,
) -> None:
    sql = (
        f"SELECT "
        f"  gml_id AS id, "
        f"  ST_Transform(geom, 4326) AS geom, "
        f"  COALESCE(area, ST_Area(geom)) AS area_sqm, "
        f"  roof_type, "
        f"  gebaeudefunktion AS building_type, "
        f"  ST_Y(ST_Transform(ST_Centroid(geom), 4326)) AS lat, "
        f"  ST_X(ST_Transform(ST_Centroid(geom), 4326)) AS lon "
        f"FROM {buildings_table} "
        f"WHERE ST_Intersects( "
        f"  geom, "
        f"  ST_Transform( "
        f"    ST_MakeEnvelope({min_lon}, {min_lat}, {max_lon}, {max_lat}, 4326), "
        f"    3035 "
        f"  ) "
        f") "
        f"AND COALESCE(area, ST_Area(geom)) >= 50 "
        f"ORDER BY COALESCE(area, ST_Area(geom)) DESC "
        f"LIMIT {limit}"
    )

    cmd = [
        ogr2ogr,
        "-f", "GPKG",
        output,
        pg_uri,
        "-sql", sql,
        "-nln", "buildings",
        "-t_srs", "EPSG:4326",
        "-overwrite",
    ]

    _run_cmd(cmd, "Gebäude-Export")


def export_mastr(
    ogr2ogr: str,
    pg_uri: str,
    mastr_table: str,
    min_lat: float, min_lon: float,
    max_lat: float, max_lon: float,
    output: str,
    buffer_deg: float = 0.05,
) -> None:
    # Prüft beide gängigen CRS für MaStR-Tabellen (4326 oder 3035)
    # Einfachster Weg: direkte BBox in Geo-Koordinaten, ogr2ogr transformiert
    sql = (
        f"SELECT "
        f"  geom, "
        f"  bruttoleistung, "
        f"  einheittyp, "
        f"  inbetriebnahmedatum "
        f"FROM {mastr_table} "
        f"WHERE ST_Intersects( "
        f"  geom, "
        f"  ST_SetSRID( "
        f"    ST_MakeEnvelope( "
        f"      {min_lon - buffer_deg}, {min_lat - buffer_deg}, "
        f"      {max_lon + buffer_deg}, {max_lat + buffer_deg} "
        f"    ), 4326 "
        f"  ) "
        f") "
        f"LIMIT 5000"
    )

    cmd = [
        ogr2ogr,
        "-f", "GPKG",
        output,
        pg_uri,
        "-sql", sql,
        "-nln", "mastr_solar",
        "-t_srs", "EPSG:4326",
        "-update",   # vorhandenes GPKG erweitern statt überschreiben
    ]

    _run_cmd(cmd, "MaStR-Export")


def _run_cmd(cmd: list[str], label: str) -> None:
    env = _qgis_env()
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"FEHLER beim {label}:")
        print(result.stderr[:1000])
        sys.exit(1)
    if result.stderr.strip():
        # ogr2ogr gibt Warnings nach stderr aus
        for line in result.stderr.splitlines():
            if line.strip():
                print(f"  [ogr2ogr] {line}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Exportiert Test-GeoPackage aus PostGIS")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--dbname", required=True, help="Datenbankname")
    parser.add_argument("--user", required=True, help="DB-Benutzer")
    parser.add_argument("--password", default="", help="DB-Passwort")
    parser.add_argument("--buildings-table", default="deutschland.gebaeude_deutschland_tbl")
    parser.add_argument("--mastr-table", default=None,
                        help="Schema.Tabelle für MaStR (optional)")
    parser.add_argument("--output", default="test_gebaeude.gpkg")
    parser.add_argument("--city-bbox", default="48.137,11.575,48.145,11.590",
                        help="min_lat,min_lon,max_lat,max_lon")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    bbox_parts = [float(x) for x in args.city_bbox.split(",")]
    if len(bbox_parts) != 4:
        sys.exit("--city-bbox braucht genau 4 Werte: min_lat,min_lon,max_lat,max_lon")
    min_lat, min_lon, max_lat, max_lon = bbox_parts

    ogr2ogr = _check_ogr2ogr()
    print(f"ogr2ogr: {ogr2ogr}")
    env = _qgis_env()
    proj_data = env.get("PROJ_DATA", "(System)")
    print(f"PROJ_DATA: {proj_data}")

    pg_uri = _pg_uri(args.host, args.port, args.dbname, args.user, args.password)

    print(f"Exportiere Gebäude aus '{args.buildings_table}' …")
    export_buildings(ogr2ogr, pg_uri, args.buildings_table,
                     min_lat, min_lon, max_lat, max_lon,
                     args.output, args.limit)
    print(f"  → Layer 'buildings' in {args.output}")

    if args.mastr_table:
        print(f"Exportiere MaStR aus '{args.mastr_table}' …")
        try:
            export_mastr(ogr2ogr, pg_uri, args.mastr_table,
                         min_lat, min_lon, max_lat, max_lon,
                         args.output)
            print(f"  → Layer 'mastr_solar' in {args.output}")
        except SystemExit:
            print("  MaStR-Export fehlgeschlagen – Gebäude-Layer bleibt erhalten.")

    print(f"\nFertig: {args.output}")
    print()
    print("Im QGIS-Plugin (GeoPackage-Modus):")
    print(f"  GeoPackage:    {args.output}")
    print(f"  Layer:         buildings")
    if args.mastr_table:
        print(f"  MaStR GeoPackage: {args.output}")
        print(f"  MaStR-Layer:      mastr_solar")
    print()
    print("Spalten-Mapping (Seite 2 im Wizard):")
    print("  ID-Spalte:         id")
    print("  Gebäudetyp-Spalte: building_type")
    print("  Dachtyp-Spalte:    roof_type")
    print("  Fläche-Spalte:     area_sqm")


if __name__ == "__main__":
    main()
