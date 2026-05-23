"""Alle SQL-Abfragen zentral an einem Ort."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg2.extras

from solar_sites.config import settings
from solar_sites.db.connection import get_cursor


@dataclass
class Building:
    id: str
    geom_wkt: str
    area_sqm: float
    roof_type: str | None
    source: str  # "alkis" | "osm"


@dataclass
class SolarAnalysis:
    building_id: str
    address_id: str | None
    annual_energy_kwh: float
    installable_kwp: float
    usable_area_sqm: float
    pvgis_irradiation: float
    panels_detected: bool
    mastr_registered: bool
    mastr_capacity_kw: float | None


# ── Migrationen ──────────────────────────────────────────────────────────────

def ensure_schema() -> None:
    """Erstellt das solar_sites-Schema und alle benötigten Tabellen.
    Benötigt Admin-Rechte. Einmalig via 'solar-sites db-init' ausführen."""
    schema = settings.db_schema
    with get_cursor() as cur:
        try:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        except Exception as e:
            raise RuntimeError(
                f"Kein Recht das Schema '{schema}' anzulegen. "
                "Bitte einmalig mit einem Admin-User ausführen: "
                "psql -d energy -f migrations/001_initial_schema.sql"
            ) from e
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.addresses (
                id          SERIAL PRIMARY KEY,
                raw_address TEXT NOT NULL,
                street      TEXT,
                house_nr    TEXT,
                city        TEXT,
                postal_code TEXT,
                country     TEXT DEFAULT 'Deutschland',
                lat         DOUBLE PRECISION,
                lon         DOUBLE PRECISION,
                geocoded    BOOLEAN DEFAULT FALSE,
                job_id      TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.solar_analyses (
                id                  SERIAL PRIMARY KEY,
                building_id         TEXT NOT NULL,
                address_id          INTEGER REFERENCES {schema}.addresses(id),
                annual_energy_kwh   DOUBLE PRECISION,
                installable_kwp     DOUBLE PRECISION,
                usable_area_sqm     DOUBLE PRECISION,
                pvgis_irradiation   DOUBLE PRECISION,
                panels_detected     BOOLEAN DEFAULT FALSE,
                mastr_registered    BOOLEAN DEFAULT FALSE,
                mastr_capacity_kw   DOUBLE PRECISION,
                building_source     TEXT,
                building_type       TEXT,
                lat                 DOUBLE PRECISION,
                lon                 DOUBLE PRECISION,
                job_id              TEXT,
                created_at          TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_analyses_job
            ON {schema}.solar_analyses(job_id)
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_addresses_job
            ON {schema}.addresses(job_id)
        """)


# ── Adressen ─────────────────────────────────────────────────────────────────

def insert_addresses(rows: list[dict[str, Any]], job_id: str) -> list[int]:
    """Fügt Adressen ein und gibt die vergebenen IDs zurück."""
    schema = settings.db_schema
    ids: list[int] = []
    with get_cursor() as cur:
        for row in rows:
            cur.execute(
                f"""
                INSERT INTO {schema}.addresses
                    (raw_address, street, house_nr, city, postal_code, country, job_id)
                VALUES (%(raw)s, %(street)s, %(house_nr)s, %(city)s, %(postal_code)s,
                        %(country)s, %(job_id)s)
                RETURNING id
                """,
                {**row, "job_id": job_id},
            )
            ids.append(cur.fetchone()["id"])
    return ids


def update_geocode(address_id: int, lat: float, lon: float) -> None:
    schema = settings.db_schema
    with get_cursor() as cur:
        cur.execute(
            f"""
            UPDATE {schema}.addresses
            SET lat=%(lat)s, lon=%(lon)s, geocoded=TRUE
            WHERE id=%(id)s
            """,
            {"lat": lat, "lon": lon, "id": address_id},
        )


def get_ungeooded_addresses(job_id: str) -> list[dict]:
    schema = settings.db_schema
    with get_cursor() as cur:
        cur.execute(
            f"SELECT * FROM {schema}.addresses WHERE job_id=%(job_id)s AND geocoded=FALSE",
            {"job_id": job_id},
        )
        return cur.fetchall()


# ── Gebäude ──────────────────────────────────────────────────────────────────

def find_buildings_near(lat: float, lon: float, radius_m: float = 100) -> list[dict]:
    """Sucht ALKIS-Gebäude im Umkreis via PostGIS."""
    table = settings.buildings_table
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                gml_id                                          AS id,
                ST_AsText(ST_Transform(geom, 4326))            AS geom_wkt,
                COALESCE(area, ST_Area(geom))                  AS area_sqm,
                roof_type,
                gebaeudefunktion,
                'alkis'                                        AS source,
                ST_Y(ST_Transform(ST_Centroid(geom), 4326))    AS lat,
                ST_X(ST_Transform(ST_Centroid(geom), 4326))    AS lon
            FROM {table}
            WHERE ST_DWithin(
                geom,
                ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 3035),
                %(radius)s
            )
            ORDER BY ST_Distance(
                geom,
                ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 3035)
            )
            LIMIT 20
            """,
            {"lat": lat, "lon": lon, "radius": radius_m},
        )
        return cur.fetchall()


def find_osm_buildings_near(lat: float, lon: float, radius_m: float = 100) -> list[dict]:
    """Sucht OSM-Gebäude im Umkreis via PostGIS."""
    table = settings.osm_buildings_table
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                osm_id::TEXT                                            AS id,
                ST_AsText(ST_Transform(geom, 4326))                    AS geom_wkt,
                ST_Area(ST_Transform(geom, 3035))                      AS area_sqm,
                NULL                                                   AS roof_type,
                'osm'                                                  AS source,
                ST_Y(ST_Transform(ST_Centroid(geom), 4326))            AS lat,
                ST_X(ST_Transform(ST_Centroid(geom), 4326))            AS lon
            FROM {table}
            WHERE ST_DWithin(
                ST_Transform(geom, 3035),
                ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 3035),
                %(radius)s
            )
            ORDER BY ST_Distance(
                ST_Transform(geom, 3035),
                ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 3035)
            )
            LIMIT 20
            """,
            {"lat": lat, "lon": lon, "radius": radius_m},
        )
        return cur.fetchall()


def find_buildings_in_bbox(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float,
    min_area_sqm: float = 200,
    building_use: str | None = None,
) -> list[dict]:
    """Alle Gebäude in einer Bounding-Box, gefiltert nach Mindestfläche und optional Nutzungsart."""
    table = settings.buildings_table

    # building_use: "wohnen" | "gewerbe" | None
    if building_use == "wohnen":
        use_filter = "AND gebaeudefunktion LIKE '31001_1%%'"
    elif building_use == "gewerbe":
        use_filter = "AND gebaeudefunktion ~ '^31001_[23]'"
    else:
        use_filter = ""

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                gml_id                                          AS id,
                ST_AsText(ST_Transform(geom, 4326))            AS geom_wkt,
                COALESCE(area, ST_Area(geom))                  AS area_sqm,
                roof_type,
                gebaeudefunktion,
                'alkis'                                        AS source,
                ST_Y(ST_Transform(ST_Centroid(geom), 4326))    AS lat,
                ST_X(ST_Transform(ST_Centroid(geom), 4326))    AS lon
            FROM {table}
            WHERE ST_Intersects(
                geom,
                ST_Transform(
                    ST_MakeEnvelope(%(min_lon)s, %(min_lat)s, %(max_lon)s, %(max_lat)s, 4326),
                    3035
                )
            )
            AND COALESCE(area, ST_Area(geom)) >= %(min_area)s
            {use_filter}
            ORDER BY COALESCE(area, ST_Area(geom)) DESC
            """,
            {
                "min_lat": min_lat, "min_lon": min_lon,
                "max_lat": max_lat, "max_lon": max_lon,
                "min_area": min_area_sqm,
            },
        )
        return cur.fetchall()


# ── Analysen speichern ───────────────────────────────────────────────────────

def upsert_analysis(analysis: dict[str, Any]) -> None:
    schema = settings.db_schema
    with get_cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {schema}.solar_analyses
                (building_id, address_id, annual_energy_kwh, installable_kwp,
                 usable_area_sqm, pvgis_irradiation, panels_detected,
                 mastr_registered, mastr_capacity_kw, building_source, building_type,
                 dlr_annual_kwh, dlr_panel_area_sqm, dlr_potential_score, data_source,
                 lat, lon, job_id)
            VALUES
                (%(building_id)s, %(address_id)s, %(annual_energy_kwh)s,
                 %(installable_kwp)s, %(usable_area_sqm)s, %(pvgis_irradiation)s,
                 %(panels_detected)s, %(mastr_registered)s, %(mastr_capacity_kw)s,
                 %(building_source)s, %(building_type)s,
                 %(dlr_annual_kwh)s, %(dlr_panel_area_sqm)s, %(dlr_potential_score)s, %(data_source)s,
                 %(lat)s, %(lon)s, %(job_id)s)
            ON CONFLICT DO NOTHING
            """,
            analysis,
        )


def get_analyses_for_job(job_id: str) -> list[dict]:
    schema = settings.db_schema
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                sa.*,
                a.raw_address,
                a.street,
                a.house_nr,
                a.city,
                a.postal_code
            FROM {schema}.solar_analyses sa
            LEFT JOIN {schema}.addresses a ON sa.address_id = a.id
            WHERE sa.job_id = %(job_id)s
            ORDER BY sa.annual_energy_kwh DESC NULLS LAST
            """,
            {"job_id": job_id},
        )
        return cur.fetchall()
