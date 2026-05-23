"""YOLO-basierte Solarpanel-Erkennung auf Luftbildern."""

from __future__ import annotations

import logging
from pathlib import Path

from solar_sites.config import MODEL_PATH, settings

log = logging.getLogger(__name__)


def detect_panels(image_path: str | Path) -> bool:
    """
    Führt Panel-Erkennung auf einem Luftbild durch.
    Gibt True zurück wenn Panels mit ausreichender Konfidenz gefunden wurden.
    """
    try:
        from ultralytics import YOLO
        model = YOLO(str(MODEL_PATH))
        results = model(str(image_path), conf=settings.detection_confidence, verbose=False)
        found = any(len(r.boxes) > 0 for r in results)
        log.debug("YOLO %s → %s", Path(image_path).name, "Panels" if found else "keine Panels")
        return found
    except Exception as e:
        log.warning("YOLO-Erkennung fehlgeschlagen: %s", e)
        return False


def detect_for_building(building_id: str, geom_wkt: str) -> bool:
    """
    Vollständige Pipeline für ein Gebäude:
    geom_wkt → Satellitenbild-Download → YOLO → Bild löschen → True/False.

    Gibt False zurück wenn das Modell fehlt oder Download fehlschlägt.
    """
    if not model_available():
        return False

    from solar_sites.imaging.satellite import download_building_image

    image_path = download_building_image(
        building_id=building_id,
        geom_wkt=geom_wkt,
        zoom=settings.satellite_zoom,
        source=settings.satellite_source,
    )
    if image_path is None:
        return False

    try:
        return detect_panels(image_path)
    finally:
        image_path.unlink(missing_ok=True)


def model_available() -> bool:
    return MODEL_PATH.exists()
