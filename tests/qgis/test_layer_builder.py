"""
Integration-Tests für layer_builder.py – benötigen echtes QGIS.

Ausführung (in qgis/qgis Docker-Image oder lokal mit QGIS Python):
    xvfb-run pytest tests/qgis/ -v

Der `qgis_app`-Fixture stammt von pytest-qgis und initialisiert
QgsApplication inkl. Provider-Registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Hilfs-Dict mit einem vollständigen Analyse-Datensatz
# ---------------------------------------------------------------------------
_SAMPLE = {
    "building_id":       "way/123456",
    "building_source":   "osm",
    "building_type":     "house",
    "lat":               50.938_361,
    "lon":               6.959_974,
    "area_sqm":          300.0,
    "annual_energy_kwh": 85_000.0,
    "installable_kwp":   42.5,
    "usable_area_sqm":   210.0,
    "pvgis_irradiation": 1_050.0,
    "dlr_annual_kwh":    None,
    "data_source":       "pvgis",
    "mastr_registered":  False,
    "mastr_capacity_kw": None,
    "panels_detected":   False,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_layer_ist_valid(qgis_app):
    """build_memory_layer erzeugt einen validen QGIS-Layer."""
    from qgis_solar_plugin.layer_builder import build_memory_layer

    layer = build_memory_layer([_SAMPLE], job_id="ci-001")
    assert layer.isValid(), "Layer ist nicht valid – QgsVectorLayer-Fehler?"


def test_feature_count(qgis_app):
    """Jeder Eintrag mit lat/lon landet als Feature im Layer."""
    from qgis_solar_plugin.layer_builder import build_memory_layer

    analyses = [_SAMPLE, {**_SAMPLE, "building_id": "way/999", "lat": 50.94}]
    layer = build_memory_layer(analyses, job_id="ci-002")
    assert layer.featureCount() == 2


def test_fehlende_koordinaten_werden_uebersprungen(qgis_app):
    """Einträge ohne lat oder lon dürfen nicht im Layer landen."""
    from qgis_solar_plugin.layer_builder import build_memory_layer

    analyses = [
        _SAMPLE,                                     # gültig → landet im Layer
        {**_SAMPLE, "lat": None},                    # kein lat → wird übersprungen
        {**_SAMPLE, "lon": None},                    # kein lon → wird übersprungen
    ]
    layer = build_memory_layer(analyses, job_id="ci-003")
    assert layer.featureCount() == 1


def test_pflichtfelder_vorhanden(qgis_app):
    """Alle dokumentierten Ausgabe-Felder müssen im Schema vorhanden sein."""
    from qgis_solar_plugin.layer_builder import build_memory_layer

    layer = build_memory_layer([_SAMPLE], job_id="ci-004")
    field_names = {f.name() for f in layer.fields()}

    expected = {
        "annual_energy_kwh",
        "installable_kwp",
        "usable_area_sqm",
        "pvgis_irradiation",
        "dlr_annual_kwh",
        "data_source",
        "mastr_registered",
        "mastr_capacity_kw",
        "panels_detected",
        "building_type",
        "building_source",
        "area_sqm",
        "building_id",
    }
    fehlend = expected - field_names
    assert not fehlend, f"Fehlende Felder: {fehlend}"


def test_renderer_gestaffelt_nach_annual_energy(qgis_app):
    """Symbologie: QgsGraduatedSymbolRenderer auf annual_energy_kwh, 3 Klassen."""
    from qgis.core import QgsGraduatedSymbolRenderer

    from qgis_solar_plugin.layer_builder import build_memory_layer

    layer = build_memory_layer([_SAMPLE], job_id="ci-005")
    renderer = layer.renderer()

    assert isinstance(renderer, QgsGraduatedSymbolRenderer), (
        f"Falscher Renderer-Typ: {type(renderer)}"
    )
    assert renderer.classAttribute() == "annual_energy_kwh"
    assert len(renderer.ranges()) == 3, "Erwartet: 3 Farb-Klassen (rot/gelb/grün)"


def test_gpkg_export(qgis_app, tmp_path):
    """save_to_gpkg schreibt eine nicht-leere Datei auf Platte."""
    from qgis_solar_plugin.layer_builder import build_memory_layer, save_to_gpkg

    layer = build_memory_layer([_SAMPLE], job_id="ci-006")
    out = str(tmp_path / "ergebnis.gpkg")
    returned_path = save_to_gpkg(layer, out)

    assert Path(returned_path).exists(), "GeoPackage wurde nicht erstellt"
    assert Path(returned_path).stat().st_size > 1_000, "GeoPackage ist verdächtig klein"
