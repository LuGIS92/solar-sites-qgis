"""Tests für solar_sites/buildings/overpass.py – kein QGIS, keine DB, kein Netz."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from solar_sites.buildings.overpass import (
    _centroid,
    _coords_to_wkt,
    _polygon_area_sqm,
    _relation_to_dict,
    _way_to_dict,
    fetch_buildings,
)


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _rect(lon0, lat0, lon1, lat1):
    """Geschlossenes Rechteck-Polygon (5 Punkte)."""
    return [
        (lon0, lat0), (lon1, lat0), (lon1, lat1), (lon0, lat1), (lon0, lat0),
    ]


# ── _polygon_area_sqm ─────────────────────────────────────────────────────────

class TestPolygonAreaSqm:
    def test_approximate_square_100m(self):
        # ~100 m × 100 m bei Breitengrad 51° → ≈ 8 000 – 12 000 m²
        coords = _rect(7.0, 51.0, 7.0 + 0.001, 51.0 + 0.001)
        area = _polygon_area_sqm(coords)
        assert 5_000 < area < 15_000

    def test_larger_building(self):
        # ~300 m × 200 m Lager
        coords = _rect(7.0, 51.0, 7.0 + 0.003, 51.0 + 0.002)
        area = _polygon_area_sqm(coords)
        assert area > 20_000

    def test_degenerate_too_few_points(self):
        assert _polygon_area_sqm([(7.0, 51.0), (7.1, 51.0)]) == 0.0

    def test_empty(self):
        assert _polygon_area_sqm([]) == 0.0

    def test_area_positive_regardless_of_winding(self):
        cw  = _rect(7.0, 51.0, 7.001, 51.001)
        ccw = list(reversed(cw))
        assert abs(_polygon_area_sqm(cw) - _polygon_area_sqm(ccw)) < 1.0


# ── _centroid ─────────────────────────────────────────────────────────────────

class TestCentroid:
    def test_square_centroid(self):
        # Geschlossenes Polygon: Schlusspunkt == Startpunkt verzerrt den Mittelwert leicht.
        coords = _rect(6.0, 50.0, 8.0, 52.0)
        lon, lat = _centroid(coords)
        assert abs(lon - 7.0) < 0.5
        assert abs(lat - 51.0) < 0.5

    def test_single_point(self):
        lon, lat = _centroid([(5.5, 50.5)])
        assert lon == pytest.approx(5.5)
        assert lat == pytest.approx(50.5)


# ── _coords_to_wkt ────────────────────────────────────────────────────────────

class TestCoordsToWkt:
    def test_format(self):
        coords = [(7.0, 51.0), (7.1, 51.0), (7.1, 51.1), (7.0, 51.0)]
        wkt = _coords_to_wkt(coords)
        assert wkt.startswith("Polygon ((")
        assert wkt.endswith("))")
        assert "7.0 51.0" in wkt
        assert "7.1 51.1" in wkt


# ── _way_to_dict ──────────────────────────────────────────────────────────────

def _make_way(element_id=123, tags=None, geometry=None):
    if geometry is None:
        geometry = [
            {"lon": 7.0, "lat": 51.0},
            {"lon": 7.001, "lat": 51.0},
            {"lon": 7.001, "lat": 51.001},
            {"lon": 7.0, "lat": 51.001},
        ]
    return {"type": "way", "id": element_id, "tags": tags or {"building": "yes"}, "geometry": geometry}


class TestWayToDict:
    def test_basic_way(self):
        result = _way_to_dict(_make_way())
        assert result is not None
        assert result["id"] == "w123"
        assert result["source"] == "osm"
        assert result["building_type"] == "yes"
        assert result["area_sqm"] > 0
        assert result["geom_wkt"].startswith("Polygon")

    def test_way_with_roof_type(self):
        tags = {"building": "house", "roof:shape": "gabled"}
        result = _way_to_dict(_make_way(tags=tags))
        assert result["roof_type"] == "gabled"
        assert result["building_type"] == "house"

    def test_too_few_nodes_returns_none(self):
        way = _make_way(geometry=[{"lon": 7.0, "lat": 51.0}, {"lon": 7.1, "lat": 51.0}])
        assert _way_to_dict(way) is None

    def test_polygon_is_closed(self):
        result = _way_to_dict(_make_way())
        # WKT-Polygon muss geschlossen sein (erster = letzter Punkt)
        inner = result["geom_wkt"][len("Polygon (("):-2]
        pairs = inner.split(", ")
        assert pairs[0] == pairs[-1]


# ── _relation_to_dict ─────────────────────────────────────────────────────────

def _make_relation(tags=None, members=None):
    if members is None:
        members = [
            {
                "type": "way",
                "role": "outer",
                "geometry": [
                    {"lon": 7.0, "lat": 51.0},
                    {"lon": 7.002, "lat": 51.0},
                    {"lon": 7.002, "lat": 51.002},
                    {"lon": 7.0, "lat": 51.002},
                ],
            }
        ]
    return {"type": "relation", "id": 99, "tags": tags or {"building": "yes"}, "members": members}


class TestRelationToDict:
    def test_basic_relation(self):
        result = _relation_to_dict(_make_relation())
        assert result is not None
        assert result["id"] == "r99"
        assert result["area_sqm"] > 0

    def test_no_outer_member_returns_none(self):
        rel = _make_relation(members=[{"type": "way", "role": "inner", "geometry": [
            {"lon": 7.0, "lat": 51.0}, {"lon": 7.001, "lat": 51.0}, {"lon": 7.001, "lat": 51.001},
        ]}])
        assert _relation_to_dict(rel) is None

    def test_empty_members_returns_none(self):
        assert _relation_to_dict(_make_relation(members=[])) is None


# ── fetch_buildings (mit gemocktem urlopen) ───────────────────────────────────

def _overpass_response(elements):
    return json.dumps({"elements": elements}).encode()


class TestFetchBuildings:
    def _mock_urlopen(self, payload: bytes):
        cm = MagicMock()
        cm.__enter__ = lambda s: s
        cm.__exit__ = MagicMock(return_value=False)
        cm.read.return_value = payload
        return cm

    def test_returns_list_of_dicts(self):
        payload = _overpass_response([_make_way()])
        with patch("solar_sites.buildings.overpass.urllib.request.urlopen",
                   return_value=self._mock_urlopen(payload)):
            result = fetch_buildings(51.0, 7.0, 51.01, 7.01)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["source"] == "osm"

    def test_empty_response(self):
        payload = _overpass_response([])
        with patch("solar_sites.buildings.overpass.urllib.request.urlopen",
                   return_value=self._mock_urlopen(payload)):
            result = fetch_buildings(51.0, 7.0, 51.01, 7.01)
        assert result == []

    def test_skips_unknown_element_types(self):
        elements = [
            _make_way(element_id=1),
            {"type": "node", "id": 2, "lat": 51.0, "lon": 7.0},
        ]
        payload = _overpass_response(elements)
        with patch("solar_sites.buildings.overpass.urllib.request.urlopen",
                   return_value=self._mock_urlopen(payload)):
            result = fetch_buildings(51.0, 7.0, 51.01, 7.01)
        assert len(result) == 1

    def test_http_error_raises_runtime_error(self):
        import urllib.error
        with patch("solar_sites.buildings.overpass.urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError(None, 429, "Too Many Requests", {}, None)):
            with pytest.raises(RuntimeError, match="429"):
                fetch_buildings(51.0, 7.0, 51.01, 7.01)
