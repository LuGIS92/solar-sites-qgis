"""Baut QGIS-Vektorlayer aus Analyse-Ergebnissen + GeoPackage-Export."""

from __future__ import annotations


def build_memory_layer(analyses: list[dict], job_id: str):
    """Erstellt einen QGIS-Memory-Layer (Punkte) mit allen Analysewerten."""
    from PyQt5.QtCore import QVariant
    from qgis.core import (
        QgsFeature,
        QgsField,
        QgsGeometry,
        QgsGraduatedSymbolRenderer,
        QgsMarkerSymbol,
        QgsPointXY,
        QgsRendererRange,
        QgsVectorLayer,
    )

    layer = QgsVectorLayer("Point?crs=EPSG:4326", f"Solar {job_id}", "memory")
    pr = layer.dataProvider()

    pr.addAttributes([
        QgsField("building_id",        QVariant.String),
        QgsField("annual_energy_kwh",  QVariant.Double),
        QgsField("installable_kwp",    QVariant.Double),
        QgsField("usable_area_sqm",    QVariant.Double),
        QgsField("pvgis_irradiation",  QVariant.Double),
        QgsField("dlr_annual_kwh",     QVariant.Double),
        QgsField("data_source",        QVariant.String),
        QgsField("mastr_registered",   QVariant.Int),
        QgsField("mastr_capacity_kw",  QVariant.Double),
        QgsField("panels_detected",    QVariant.Int),
        QgsField("building_type",      QVariant.String),
        QgsField("building_source",    QVariant.String),
        QgsField("area_sqm",           QVariant.Double),
    ])
    layer.updateFields()

    features = []
    for a in analyses:
        lat, lon = a.get("lat"), a.get("lon")
        if lat is None or lon is None:
            continue
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(lon), float(lat))))
        f.setAttributes([
            str(a.get("building_id", "")),
            _f(a, "annual_energy_kwh"),
            _f(a, "installable_kwp"),
            _f(a, "usable_area_sqm"),
            _f(a, "pvgis_irradiation"),
            _f(a, "dlr_annual_kwh"),
            str(a.get("data_source", "pvgis")),
            1 if a.get("mastr_registered") else 0,
            _f(a, "mastr_capacity_kw"),
            1 if a.get("panels_detected") else 0,
            str(a.get("building_type") or ""),
            str(a.get("building_source", "")),
            _f(a, "area_sqm"),
        ])
        features.append(f)

    pr.addFeatures(features)
    layer.updateExtents()
    _apply_symbology(layer)
    return layer


def _f(d: dict, key: str) -> float | None:
    v = d.get(key)
    return float(v) if v is not None else None


def _apply_symbology(layer) -> None:
    """Gestaffelte Farbcodierung nach annual_energy_kwh (rot → gelb → grün)."""
    from qgis.core import QgsGraduatedSymbolRenderer, QgsMarkerSymbol, QgsRendererRange

    ranges_def = [
        (0,       50_000,    "#e74c3c", "< 50 MWh/Jahr"),
        (50_000,  150_000,   "#f39c12", "50 – 150 MWh/Jahr"),
        (150_000, 10_000_000,"#27ae60", "> 150 MWh/Jahr"),
    ]
    renderer_ranges = []
    for lo, hi, color, label in ranges_def:
        sym = QgsMarkerSymbol.createSimple(
            {"color": color, "size": "6", "outline_style": "no"}
        )
        renderer_ranges.append(QgsRendererRange(lo, hi, sym, label))

    layer.setRenderer(QgsGraduatedSymbolRenderer("annual_energy_kwh", renderer_ranges))


def add_to_project(layer, iface) -> None:
    """Layer zum QGIS-Projekt hinzufügen und Kartenausschnitt anpassen."""
    from qgis.core import (
        QgsCoordinateTransform,
        QgsProject,
    )
    QgsProject.instance().addMapLayer(layer)
    if not layer.extent().isEmpty():
        canvas = iface.mapCanvas()
        # Extent vom Layer-CRS (4326) in den Canvas-CRS (oft 3857) transformieren
        xform = QgsCoordinateTransform(
            layer.crs(),
            canvas.mapSettings().destinationCrs(),
            QgsProject.instance(),
        )
        canvas.setExtent(xform.transformBoundingBox(layer.extent()))
        canvas.refresh()


def save_to_gpkg(layer, path: str) -> str:
    """Speichert den Layer als GeoPackage. Gibt den Dateipfad zurück."""
    from qgis.core import QgsCoordinateTransformContext, QgsVectorFileWriter

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.fileEncoding = "UTF-8"

    error, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        path,
        QgsCoordinateTransformContext(),
        options,
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"GeoPackage-Export fehlgeschlagen: {msg}")
    return path
