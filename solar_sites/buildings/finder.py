"""Gebäude aus ALKIS oder OSM für eine Koordinate suchen."""

from __future__ import annotations

from dataclasses import dataclass

from solar_sites.config import settings
from solar_sites.db import queries


@dataclass
class Building:
    id: str
    geom_wkt: str
    area_sqm: float
    roof_type: str | None
    building_type: str | None  # gebaeudefunktion (Klartext)
    source: str
    lat: float
    lon: float


def find_buildings(lat: float, lon: float, radius_m: float | None = None) -> list[Building]:
    """
    Gibt alle Gebäude im Umkreis zurück, bevorzugt ALKIS, Fallback auf OSM.
    Filtert auf Mindestgröße aus Config.
    """
    radius = radius_m or settings.building_search_radius_m
    rows = queries.find_buildings_near(lat, lon, radius)

    if not rows:
        rows = queries.find_osm_buildings_near(lat, lon, radius)

    buildings = []
    for r in rows:
        if (r["area_sqm"] or 0) < settings.min_roof_area_sqm:
            continue
        buildings.append(_row_to_building(r))
    return buildings


def find_buildings_in_area(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    min_area_sqm: float | None = None,
    building_use: str | None = None,
) -> list[Building]:
    """Alle Gebäude in einem geografischen Bereich (für die freie Flächensuche)."""
    min_area = min_area_sqm or settings.min_roof_area_sqm
    rows = queries.find_buildings_in_bbox(min_lat, min_lon, max_lat, max_lon, min_area, building_use)
    return [_row_to_building(r) for r in rows]


def _row_to_building(r: dict) -> Building:
    return Building(
        id=r["id"],
        geom_wkt=r["geom_wkt"],
        area_sqm=r["area_sqm"],
        roof_type=r.get("roof_type"),
        building_type=r.get("gebaeudefunktion"),
        source=r["source"],
        lat=r["lat"],
        lon=r["lon"],
    )
