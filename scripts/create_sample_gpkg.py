"""
Creates data/sample.gpkg – 20 synthetic buildings in Cologne (WGS84 / EPSG:4326).

Run once from the repo root:
    python scripts/create_sample_gpkg.py

No external dependencies – uses only Python's standard library (sqlite3, struct, math).
"""

from __future__ import annotations

import math
import sqlite3
import struct
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "sample.gpkg"

# ---------------------------------------------------------------------------
# Synthetic buildings: (id, center_lat, center_lon, width_m, depth_m, btype, roof)
# Placed around Cologne main station (50.9427 N, 6.9590 E)
# ---------------------------------------------------------------------------
LAT0, LON0 = 50.9427, 6.9590
M_PER_DEG_LAT = 111_000.0
M_PER_DEG_LON = 111_000.0 * math.cos(math.radians(LAT0))

BUILDINGS = [
    # Residential (31001_1xxx)
    ("DE.NW.K.0001", 50.9410, 6.9555, 12, 10, "31001_1020", "gable"),
    ("DE.NW.K.0002", 50.9418, 6.9562, 14, 11, "31001_1010", "gable"),
    ("DE.NW.K.0003", 50.9405, 6.9571, 10,  9, "31001_1020", "hip"),
    ("DE.NW.K.0004", 50.9422, 6.9540, 20, 15, "31001_1000", "gable"),
    ("DE.NW.K.0005", 50.9431, 6.9548, 18, 13, "31001_1010", "gable"),
    ("DE.NW.K.0006", 50.9438, 6.9560, 22, 16, "31001_1000", "flat"),
    ("DE.NW.K.0007", 50.9445, 6.9535, 15, 12, "31001_1020", "gable"),
    ("DE.NW.K.0008", 50.9452, 6.9552, 13, 11, "31001_1010", "hip"),
    # Commercial / office (31001_2xxx)
    ("DE.NW.K.0009", 50.9415, 6.9600, 35, 28, "31001_2020", "flat"),
    ("DE.NW.K.0010", 50.9425, 6.9612, 42, 32, "31001_2000", "flat"),
    ("DE.NW.K.0011", 50.9435, 6.9598, 30, 25, "31001_2020", "flat"),
    ("DE.NW.K.0012", 50.9442, 6.9615, 50, 40, "31001_2000", "flat"),
    # Industrial / warehouse (31001_3xxx)
    ("DE.NW.K.0013", 50.9400, 6.9530, 65, 55, "31001_3011", "flat"),
    ("DE.NW.K.0014", 50.9392, 6.9548, 80, 60, "31001_3011", "flat"),
    ("DE.NW.K.0015", 50.9388, 6.9570, 70, 52, "31001_3011", "flat"),
    # Mixed / large commercial
    ("DE.NW.K.0016", 50.9458, 6.9580, 55, 45, "31001_2060", "flat"),
    ("DE.NW.K.0017", 50.9465, 6.9560, 48, 38, "31001_2000", "flat"),
    ("DE.NW.K.0018", 50.9472, 6.9575, 40, 33, "31001_2020", "flat"),
    # Extra residential
    ("DE.NW.K.0019", 50.9448, 6.9542, 11,  9, "31001_1020", "gable"),
    ("DE.NW.K.0020", 50.9455, 6.9530, 16, 13, "31001_1010", "hip"),
]


def _rect_polygon(lat_c: float, lon_c: float, w_m: float, d_m: float):
    """Rectangle polygon (lon, lat) corners from center + dimensions."""
    dlat = (d_m / 2) / M_PER_DEG_LAT
    dlon = (w_m / 2) / M_PER_DEG_LON
    return [
        (lon_c - dlon, lat_c - dlat),
        (lon_c + dlon, lat_c - dlat),
        (lon_c + dlon, lat_c + dlat),
        (lon_c - dlon, lat_c + dlat),
        (lon_c - dlon, lat_c - dlat),  # close ring
    ]


def _gpkg_geometry(ring: list[tuple[float, float]]) -> bytes:
    """Encode a closed ring as a GPKG geometry blob (WGS84 polygon, little-endian)."""
    # WKB polygon body
    num_points = len(ring)
    coords = b"".join(struct.pack("<dd", x, y) for x, y in ring)
    wkb = (
        struct.pack("<b", 1)           # byte order: little-endian
        + struct.pack("<I", 3)         # WKB type: Polygon
        + struct.pack("<I", 1)         # num rings
        + struct.pack("<I", num_points)
        + coords
    )
    # GPKG standard header (magic GP + version + flags + SRS id)
    header = b"GP" + b"\x00" + b"\x01" + struct.pack("<i", 4326)
    return header + wkb


def _area_sqm(w_m: float, d_m: float) -> float:
    return round(w_m * d_m, 1)


def create(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    con = sqlite3.connect(path)
    con.execute("PRAGMA application_id = 1196444487")   # GPKG magic
    con.execute("PRAGMA user_version = 10200")

    con.executescript("""
        CREATE TABLE gpkg_spatial_ref_sys (
            srs_name TEXT NOT NULL,
            srs_id   INTEGER NOT NULL PRIMARY KEY,
            organization TEXT NOT NULL,
            organization_coordsys_id INTEGER NOT NULL,
            definition TEXT NOT NULL,
            description TEXT
        );
        CREATE TABLE gpkg_contents (
            table_name  TEXT NOT NULL PRIMARY KEY,
            data_type   TEXT NOT NULL,
            identifier  TEXT,
            description TEXT DEFAULT '',
            last_change TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            min_x REAL, min_y REAL, max_x REAL, max_y REAL,
            srs_id INTEGER
        );
        CREATE TABLE gpkg_geometry_columns (
            table_name         TEXT NOT NULL,
            column_name        TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL,
            srs_id             INTEGER NOT NULL,
            z TINYINT NOT NULL,
            m TINYINT NOT NULL,
            CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name)
        );
    """)

    con.execute("""
        INSERT INTO gpkg_spatial_ref_sys VALUES
        ('WGS 84', 4326, 'EPSG', 4326,
         'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],
          PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
         'WGS 84 geographic 2D')
    """)

    con.execute("""
        CREATE TABLE buildings (
            fid           INTEGER PRIMARY KEY AUTOINCREMENT,
            geom          BLOB,
            id            TEXT,
            area_sqm      REAL,
            building_type TEXT,
            roof_type     TEXT,
            lat           REAL,
            lon           REAL
        )
    """)

    lats, lons = [], []
    rows = []
    for bid, lat, lon, w, d, btype, roof in BUILDINGS:
        ring = _rect_polygon(lat, lon, w, d)
        geom = _gpkg_geometry(ring)
        area = _area_sqm(w, d)
        rows.append((geom, bid, area, btype, roof, round(lat, 6), round(lon, 6)))
        lats.append(lat)
        lons.append(lon)

    con.executemany(
        "INSERT INTO buildings (geom, id, area_sqm, building_type, roof_type, lat, lon) "
        "VALUES (?,?,?,?,?,?,?)",
        rows,
    )

    con.execute("""
        INSERT INTO gpkg_contents VALUES
        ('buildings', 'features', 'buildings',
         'Synthetic sample buildings – Cologne area (WGS84)',
         strftime('%Y-%m-%dT%H:%M:%fZ','now'),
         ?, ?, ?, ?, 4326)
    """, (min(lons), min(lats), max(lons), max(lats)))

    con.execute("""
        INSERT INTO gpkg_geometry_columns VALUES
        ('buildings', 'geom', 'POLYGON', 4326, 0, 0)
    """)

    con.commit()
    con.close()
    print(f"Created {path}  ({len(BUILDINGS)} buildings)")


if __name__ == "__main__":
    create(OUT)
