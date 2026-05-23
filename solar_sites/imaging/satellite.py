"""Satellitenbild-Download via leafmap für Gebäudeanalyse."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def download_building_image(
    building_id: str,
    geom_wkt: str,
    zoom: int = 19,
    source: str = "Satellite",
) -> Path | None:
    """
    Lädt ein Satellitenbild für ein Gebäude herunter.

    Extrahiert die Bounding Box aus dem WKT-Polygon (WGS84), fügt einen
    kleinen Puffer hinzu und schreibt ein GeoTIFF in ein Temp-Verzeichnis.
    Gibt None zurück wenn der Download fehlschlägt.
    """
    try:
        import leafmap
        from shapely import wkt as shapely_wkt

        geom = shapely_wkt.loads(geom_wkt)
        minx, miny, maxx, maxy = geom.bounds   # (min_lon, min_lat, max_lon, max_lat)

        # ~10 m Puffer damit das Gebäude nicht am Bildrand abgeschnitten wird
        pad = 0.0001
        bbox = [minx - pad, miny - pad, maxx + pad, maxy + pad]

        tmp_path = tempfile.mktemp(suffix=".tif", prefix=f"solar_{building_id[:8]}_")

        leafmap.map_tiles_to_geotiff(
            output=tmp_path,
            bbox=bbox,
            zoom=zoom,
            source=source,
            overwrite=True,
        )

        path = Path(tmp_path)
        if path.exists() and path.stat().st_size > 0:
            log.debug(
                "Satellitenbild OK: %s (%.1f KB)", building_id[:8], path.stat().st_size / 1024
            )
            return path

        log.warning("Satellitenbild leer für %s", building_id[:8])
        return None

    except Exception as e:
        log.warning("Satellitenbild fehlgeschlagen für %s: %s", building_id[:8], e)
        return None
