"""Tests für qgis_solar_plugin/data_sources.py – kein QGIS erforderlich."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from qgis_solar_plugin.data_sources import (
    OverpassSource,
    _safe,
)


# ── _safe ─────────────────────────────────────────────────────────────────────

class TestSafe:
    def test_valid_column_name(self):
        assert _safe("geom", "default") == "geom"

    def test_valid_with_schema(self):
        assert _safe("my_schema.geom_col", "default") == "my_schema.geom_col"

    def test_valid_with_numbers(self):
        assert _safe("col_123", "default") == "col_123"

    def test_empty_returns_default(self):
        assert _safe("", "default") == "default"

    def test_none_returns_default(self):
        assert _safe(None, "default") == "default"  # type: ignore[arg-type]

    def test_semicolon_injection_blocked(self):
        assert _safe("col; DROP TABLE foo", "default") == "default"

    def test_space_blocked(self):
        assert _safe("my col", "default") == "default"

    def test_leading_number_blocked(self):
        assert _safe("1col", "default") == "default"

    def test_sql_keyword_with_valid_chars_allowed(self):
        # "select" ist ein gültiger Bezeichner (auch wenn schlechter Name)
        assert _safe("select", "default") == "select"


# ── OverpassSource ────────────────────────────────────────────────────────────

def _raw_building(osm_id="w1", area=500.0, bt="yes", lat=51.0, lon=7.0):
    return {
        "id": osm_id,
        "geom_wkt": "Polygon ((7.0 51.0, 7.001 51.0, 7.001 51.001, 7.0 51.0))",
        "area_sqm": area,
        "lat": lat,
        "lon": lon,
        "building_type": bt,
        "roof_type": None,
        "source": "osm",
    }


def _source():
    return OverpassSource(overpass_url="http://mock", timeout=10)


class TestOverpassSource:
    def test_connect_and_close_are_noops(self):
        src = _source()
        src.connect()
        src.close()

    def test_check_mastr_always_false(self):
        src = _source()
        registered, kw = src.check_mastr(51.0, 7.0)
        assert registered is False
        assert kw is None

    def test_find_buildings_returns_list(self):
        raw = [_raw_building()]
        with patch("solar_sites.buildings.overpass.fetch_buildings", return_value=raw):
            result = _source().find_buildings(51.0, 7.0, 51.01, 7.01)
        assert len(result) == 1
        assert result[0].source == "osm"

    def test_min_area_filter(self):
        raw = [_raw_building(area=50.0), _raw_building(osm_id="w2", area=500.0)]
        with patch("solar_sites.buildings.overpass.fetch_buildings", return_value=raw):
            result = _source().find_buildings(51.0, 7.0, 51.01, 7.01, min_area=200.0)
        assert len(result) == 1
        assert result[0].id == "w2"

    def test_limit(self):
        raw = [_raw_building(osm_id=f"w{i}", area=float(1000 - i)) for i in range(5)]
        with patch("solar_sites.buildings.overpass.fetch_buildings", return_value=raw):
            result = _source().find_buildings(51.0, 7.0, 51.01, 7.01, limit=3)
        assert len(result) == 3

    def test_sorted_by_area_descending(self):
        raw = [
            _raw_building(osm_id="small", area=100.0),
            _raw_building(osm_id="big",   area=900.0),
            _raw_building(osm_id="mid",   area=500.0),
        ]
        with patch("solar_sites.buildings.overpass.fetch_buildings", return_value=raw):
            result = _source().find_buildings(51.0, 7.0, 51.01, 7.01)
        areas = [b.area_sqm for b in result]
        assert areas == sorted(areas, reverse=True)

    def test_building_use_wohnen_filter(self):
        raw = [
            _raw_building(osm_id="w1", bt="house"),
            _raw_building(osm_id="w2", bt="industrial"),
            _raw_building(osm_id="w3", bt="apartments"),
        ]
        with patch("solar_sites.buildings.overpass.fetch_buildings", return_value=raw):
            result = _source().find_buildings(51.0, 7.0, 51.01, 7.01, building_use="wohnen")
        ids = {b.id for b in result}
        assert "w1" in ids
        assert "w3" in ids
        assert "w2" not in ids

    def test_building_use_gewerbe_filter(self):
        raw = [
            _raw_building(osm_id="w1", bt="industrial"),
            _raw_building(osm_id="w2", bt="house"),
            _raw_building(osm_id="w3", bt="warehouse"),
        ]
        with patch("solar_sites.buildings.overpass.fetch_buildings", return_value=raw):
            result = _source().find_buildings(51.0, 7.0, 51.01, 7.01, building_use="gewerbe")
        ids = {b.id for b in result}
        assert "w1" in ids
        assert "w3" in ids
        assert "w2" not in ids

    def test_custom_type_filter(self):
        raw = [
            _raw_building(osm_id="w1", bt="retail"),
            _raw_building(osm_id="w2", bt="house"),
        ]
        with patch("solar_sites.buildings.overpass.fetch_buildings", return_value=raw):
            result = _source().find_buildings(
                51.0, 7.0, 51.01, 7.01, building_type_filter="retail"
            )
        assert len(result) == 1
        assert result[0].id == "w1"

    def test_empty_raw_returns_empty(self):
        with patch("solar_sites.buildings.overpass.fetch_buildings", return_value=[]):
            result = _source().find_buildings(51.0, 7.0, 51.01, 7.01)
        assert result == []
