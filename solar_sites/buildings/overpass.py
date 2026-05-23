"""Gebäude-Polygone aus der Overpass-API (OpenStreetMap) für eine Bounding-Box laden."""

from __future__ import annotations

import math

import requests

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_DEFAULT_TIMEOUT = 60


def fetch_buildings(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    timeout: int = _DEFAULT_TIMEOUT,
    overpass_url: str = _OVERPASS_URL,
) -> list[dict]:
    """Lädt Gebäude-Polygone (Ways + Multipolygon-Relations) aus der Overpass-API.

    Gibt eine Liste von Dicts zurück, jedes mit:
        id            – OSM-Element-ID als String ("w123456" oder "r123456")
        geom_wkt      – WKT POLYGON (EPSG:4326)
        area_sqm      – Grundfläche in m² (Shoelace-Näherung)
        lat, lon      – Schwerpunkt in WGS84
        building_type – Wert des OSM-Tags "building" (z.B. "house", "yes", ...)
        roof_type     – Wert des OSM-Tags "roof:shape" oder None
        source        – "osm"
    """
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    query = (
        f"[out:json][timeout:{timeout}];\n"
        f"(\n"
        f'  way["building"]({bbox});\n'
        f'  relation["building"]["type"="multipolygon"]({bbox});\n'
        f");\n"
        f"out geom;\n"
    )
    headers = {
        "User-Agent": "solar-sites-qgis/1.0 (QGIS Plugin; OpenStreetMap Overpass)",
        "Accept": "application/json",
    }
    resp = requests.get(overpass_url, params={"data": query}, headers=headers, timeout=timeout + 10)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for element in data.get("elements", []):
        if element["type"] == "way":
            item = _way_to_dict(element)
        elif element["type"] == "relation":
            item = _relation_to_dict(element)
        else:
            continue
        if item is not None:
            results.append(item)

    return results


def _way_to_dict(element: dict) -> dict | None:
    geometry = element.get("geometry", [])
    if len(geometry) < 3:
        return None

    coords = [(pt["lon"], pt["lat"]) for pt in geometry]
    # Polygon schließen falls nötig
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    area = _polygon_area_sqm(coords)
    centroid = _centroid(coords)
    tags = element.get("tags", {})

    return {
        "id": f"w{element['id']}",
        "geom_wkt": _coords_to_wkt(coords),
        "area_sqm": area,
        "lat": centroid[1],
        "lon": centroid[0],
        "building_type": tags.get("building"),
        "roof_type": tags.get("roof:shape"),
        "source": "osm",
    }


def _relation_to_dict(element: dict) -> dict | None:
    """Nimmt den ersten outer-Ring einer Multipolygon-Relation als repräsentatives Polygon."""
    for member in element.get("members", []):
        if member.get("role") == "outer" and member.get("type") == "way":
            geometry = member.get("geometry", [])
            if len(geometry) >= 3:
                coords = [(pt["lon"], pt["lat"]) for pt in geometry]
                if coords[0] != coords[-1]:
                    coords.append(coords[0])

                area = _polygon_area_sqm(coords)
                centroid = _centroid(coords)
                tags = element.get("tags", {})

                return {
                    "id": f"r{element['id']}",
                    "geom_wkt": _coords_to_wkt(coords),
                    "area_sqm": area,
                    "lat": centroid[1],
                    "lon": centroid[0],
                    "building_type": tags.get("building"),
                    "roof_type": tags.get("roof:shape"),
                    "source": "osm",
                }
    return None


def _coords_to_wkt(coords: list[tuple[float, float]]) -> str:
    inner = ", ".join(f"{lon} {lat}" for lon, lat in coords)
    return f"Polygon (({inner}))"


def _polygon_area_sqm(coords: list[tuple[float, float]]) -> float:
    """Shoelace-Formel auf Meter-Koordinaten (Equirectangular-Näherung, < 1 % Fehler)."""
    if len(coords) < 3:
        return 0.0
    avg_lat = sum(c[1] for c in coords) / len(coords)
    lat_rad = math.radians(avg_lat)
    m_lon = 111_320.0 * math.cos(lat_rad)
    m_lat = 110_574.0
    n = len(coords)
    area = 0.0
    for i in range(n):
        x1 = coords[i][0] * m_lon
        y1 = coords[i][1] * m_lat
        x2 = coords[(i + 1) % n][0] * m_lon
        y2 = coords[(i + 1) % n][1] * m_lat
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return sum(lons) / len(lons), sum(lats) / len(lats)
