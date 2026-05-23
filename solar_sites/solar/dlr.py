"""DLR Solar-Potenzialatlas Deutschland – WMTS GetFeatureInfo.

Layer solarde:SDE_BUILDINGS: gebäudespezifisches PV-Potenzial aus
digitalem Geländemodell (DGM) und ALKIS-Gebäudedaten.
Quelle: https://geoservice.dlr.de/eoc/gwc/service/wmts

Zoom-Hinweis: Der DLR-Dienst generiert Tiles typischerweise nur bis
Zoom 19. Anfragen mit höherem Zoom liefern leere Features.
Deshalb wird automatisch über niedrigere Zoom-Stufen iteriert.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import requests

from solar_sites.config import settings

log = logging.getLogger(__name__)

_cache: dict[tuple[float, float], "DLRResult | None"] = {}

# Zoom-Stufen die probiert werden (configured zuerst, dann Fallbacks)
_ZOOM_FALLBACKS = [19, 18, 17, 16]

# Pixel-Offsets für letzten Jitter-Versuch (Zentroid liegt evtl. auf Gebäudekante)
_JITTER = [(2, 0), (-2, 0), (0, 2), (0, -2), (4, 4)]


@dataclass
class DLRResult:
    annual_energy_kwh: float        # pveppmwhrp × 1000 (MWh→kWh)
    panel_area_sqm: float | None    # pvareamqm – nutzbare PV-Fläche laut DGM
    sunlight_hours: float | None    # sunlightrhrs


def get_dlr_potential(lat: float, lon: float) -> "DLRResult | None":
    """Gibt das gebäudespezifische DLR-Solarpotenzial zurück (gecacht)."""
    key = (round(lat, 5), round(lon, 5))
    if key not in _cache:
        _cache[key] = _query(lat, lon)
    return _cache[key]


def clear_cache() -> None:
    """Leert den In-Memory-Cache (nötig nach Code-Updates in laufender QGIS-Session)."""
    _cache.clear()


def _query(lat: float, lon: float) -> "DLRResult | None":
    """Probiert mehrere Zoom-Stufen; bei Misserfolg abschließend Pixel-Jitter."""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    configured = settings.dlr_zoom
    zooms = [configured] + [z for z in _ZOOM_FALLBACKS if z != configured]

    # Phase 1: jede Zoom-Stufe mit dem exakten Zentroid probieren
    for zoom in zooms:
        col, row, px, py = _coord_to_tile_pixel(lat, lon, zoom)
        result = _fetch(lat, lon, zoom, col, row, px, py)
        if result is not None:
            if zoom != configured:
                log.debug("DLR: Treffer bei zoom=%d für (%.4f, %.4f)", zoom, lat, lon)
            return result

    # Phase 2: Jitter auf Zoom 18 (guter Kompromiss Auflösung / Verfügbarkeit)
    jitter_zoom = 18
    col, row, px, py = _coord_to_tile_pixel(lat, lon, jitter_zoom)
    for dx, dy in _JITTER:
        result = _fetch(
            lat, lon, jitter_zoom, col, row,
            max(0, min(255, px + dx)), max(0, min(255, py + dy)),
        )
        if result is not None:
            log.debug("DLR: Treffer per Jitter (%+d,%+d) bei zoom=%d für (%.4f, %.4f)",
                      dx, dy, jitter_zoom, lat, lon)
            return result

    log.debug("DLR: kein Ergebnis für (%.5f, %.5f)", lat, lon)
    return None


def _fetch(
    lat: float, lon: float,
    zoom: int, col: int, row: int, px: int, py: int,
) -> "DLRResult | None":
    params = {
        "SERVICE":       "WMTS",
        "REQUEST":       "GetFeatureInfo",
        "VERSION":       "1.0.0",
        "LAYER":         settings.dlr_layer,
        "STYLE":         "",
        "FORMAT":        "image/png",
        "TILEMATRIXSET": "EPSG:900913",
        "TILEMATRIX":    f"EPSG:900913:{zoom}",
        "TILECOL":       col,
        "TILEROW":       row,
        "I":             px,
        "J":             py,
        "INFOFORMAT":    "application/json",
    }
    try:
        resp = requests.get(settings.dlr_wmts_url, params=params, timeout=10, verify=False)
        if resp.status_code != 200:
            return None
        features = resp.json().get("features", [])
        if not features:
            return None
        props = features[0].get("properties", {})
        mwh = props.get("pveppmwhrp")
        if not mwh:
            return None
        return DLRResult(
            annual_energy_kwh=float(mwh) * 1000,   # MWh → kWh
            panel_area_sqm=float(props["pvareamqm"]) if props.get("pvareamqm") else None,
            sunlight_hours=float(props["sunlightrhrs"]) if props.get("sunlightrhrs") else None,
        )
    except Exception as e:
        log.warning("DLR-Abfrage fehlgeschlagen (lat=%.4f, lon=%.4f, zoom=%d): %s", lat, lon, zoom, e)
        return None


def _coord_to_tile_pixel(lat: float, lon: float, zoom: int) -> tuple[int, int, int, int]:
    """Konvertiert WGS84 → WMTS-Tile + Pixel (EPSG:900913 / Web Mercator)."""
    R = 6378137
    R_pi = R * math.pi
    x = R * math.radians(lon)
    y = R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    y = max(min(y, R_pi), -R_pi)
    px = (x + R_pi) / (2 * R_pi)
    py = (R_pi - y) / (2 * R_pi)
    n = 2 ** zoom
    tile_col = int(px * n)
    tile_row = int(py * n)
    pix_x = int((px * n - tile_col) * 256)
    pix_y = int((py * n - tile_row) * 256)
    return tile_col, tile_row, pix_x, pix_y
