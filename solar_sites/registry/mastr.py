"""MaStR-Abfragen (Marktstammdatenregister) aus der lokalen DB."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from solar_sites.config import settings
from solar_sites.db.connection import get_cursor

log = logging.getLogger(__name__)


@dataclass
class MastrResult:
    registered: bool
    capacity_kw: float | None
    nearest_distance_m: float | None
    count: int


def check_registered(lat: float, lon: float, radius_m: float = 100) -> MastrResult:
    """Prüft ob für eine Koordinate bereits eine PV-Anlage im MaStR eingetragen ist."""
    table = settings.mastr_table
    try:
        with get_cursor() as cur:
            cur.execute(
                rf"""
                SELECT
                    COUNT(*) AS cnt,
                    SUM(
                        CASE WHEN bruttoleistung ~ '^[0-9]+(\.[0-9]+)?$'
                             THEN bruttoleistung::DOUBLE PRECISION
                             ELSE 0
                        END
                    ) AS total_kw,
                    MIN(ST_Distance(
                        geom,
                        ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 3035)
                    )) AS min_dist
                FROM {table}
                WHERE ST_DWithin(
                    geom,
                    ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 3035),
                    %(radius)s
                )
                """,
                {"lat": lat, "lon": lon, "radius": radius_m},
            )
            row = cur.fetchone()
            if row and row["cnt"] and row["cnt"] > 0:
                return MastrResult(
                    registered=True,
                    capacity_kw=float(row["total_kw"]) if row["total_kw"] else None,
                    nearest_distance_m=float(row["min_dist"]) if row["min_dist"] else None,
                    count=int(row["cnt"]),
                )
            return MastrResult(registered=False, capacity_kw=None, nearest_distance_m=None, count=0)
    except Exception as e:
        log.warning("MaStR-Abfrage fehlgeschlagen (lat=%.4f, lon=%.4f): %s", lat, lon, e)
        return MastrResult(registered=False, capacity_kw=None, nearest_distance_m=None, count=0)


def diagnose() -> dict:
    """Prüft ob die MaStR-Tabelle erreichbar ist und gibt Basis-Statistiken zurück."""
    table = settings.mastr_table
    try:
        with get_cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
            total = cur.fetchone()["cnt"]

            cur.execute(f"SELECT Find_SRID('{table.split('.')[0]}', '{table.split('.')[1]}', 'geom') AS srid")
            srid = cur.fetchone()["srid"]

            return {"status": "ok", "total_rows": total, "srid": srid, "table": table}
    except Exception as e:
        return {"status": "error", "error": str(e), "table": table}
