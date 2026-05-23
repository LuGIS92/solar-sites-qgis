"""Datenquellen für Gebäude: PostGIS (via QGIS-Verbindung) oder GeoPackage."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Sichere Spaltenbezeichnung: nur a-z, A-Z, 0-9, _, .
_SAFE_COL = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')


def _safe(col: str, default: str) -> str:
    """Gibt col zurück wenn gültig, sonst default."""
    col = (col or "").strip()
    return col if _SAFE_COL.match(col) else default


@dataclass
class Building:
    """Minimales Gebäude-Modell, kompatibel zu solar_sites.buildings.finder.Building."""
    id: str
    geom_wkt: str
    area_sqm: float
    roof_type: str | None
    building_type: str | None
    source: str
    lat: float
    lon: float


# ── PostGIS-Quelle ────────────────────────────────────────────────────────────

class PostGISSource:
    """Liest Gebäude aus PostGIS (psycopg2, eigene Verbindung – kein solar_sites-Pool).

    column_map – optionales Dict mit Spalten-Overrides:
        id            (Standard: gml_id)
        geom          (Standard: geom)
        area          (Standard: area)
        building_type (Standard: gebaeudefunktion)
        roof_type     (Standard: roof_type)
    """

    def __init__(
        self,
        dsn: str,
        buildings_table: str = "deutschland.gebaeude_deutschland_tbl",
        mastr_table: str | None = "deutschland.mastr_solar",
        column_map: dict | None = None,
    ) -> None:
        self.dsn = dsn
        self.buildings_table = buildings_table
        self.mastr_table = mastr_table
        self.column_map = column_map or {}
        self._conn = None

    def _c(self, key: str, default: str) -> str:
        return _safe(self.column_map.get(key, ""), default) or default

    def connect(self) -> None:
        import psycopg2
        import psycopg2.extras
        self._conn = psycopg2.connect(self.dsn, cursor_factory=psycopg2.extras.RealDictCursor)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def find_buildings(
        self,
        min_lat: float, min_lon: float, max_lat: float, max_lon: float,
        min_area: float = 100.0,
        building_use: str | None = None,
        building_type_filter: str | None = None,
        limit: int | None = None,
    ) -> list[Building]:
        id_col   = self._c("id",            "gml_id")
        geom_col = self._c("geom",          "geom")
        area_col = self._c("area",          "area")
        type_col = self._c("building_type", "gebaeudefunktion")
        roof_col = self._c("roof_type",     "roof_type")

        sql_params: dict = {
            "min_lat": min_lat, "min_lon": min_lon,
            "max_lat": max_lat, "max_lon": max_lon,
            "min_area": min_area,
        }
        if building_type_filter:
            use_filter = f"AND {type_col} ILIKE %(btype)s"
            sql_params["btype"] = f"%{building_type_filter}%"
        elif building_use == "wohnen":
            use_filter = f"AND {type_col} LIKE '31001_1%%'"
        elif building_use == "gewerbe":
            use_filter = f"AND {type_col} ~ '^31001_[23]'"
        else:
            use_filter = ""

        limit_clause = f"LIMIT {int(limit)}" if limit else ""
        t = self.buildings_table

        sql = f"""
            SELECT
                {id_col}                                         AS id,
                ST_AsText(ST_Transform({geom_col}, 4326))        AS geom_wkt,
                COALESCE({area_col}, ST_Area({geom_col}))        AS area_sqm,
                {roof_col}                                       AS roof_type,
                {type_col}                                       AS building_type,
                'alkis'                                          AS source,
                ST_Y(ST_Transform(ST_Centroid({geom_col}), 4326)) AS lat,
                ST_X(ST_Transform(ST_Centroid({geom_col}), 4326)) AS lon
            FROM {t}
            WHERE ST_Intersects(
                {geom_col},
                ST_Transform(
                    ST_MakeEnvelope(%(min_lon)s, %(min_lat)s, %(max_lon)s, %(max_lat)s, 4326),
                    3035
                )
            )
            AND COALESCE({area_col}, ST_Area({geom_col})) >= %(min_area)s
            {use_filter}
            ORDER BY COALESCE({area_col}, ST_Area({geom_col})) DESC
            {limit_clause}
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, sql_params)
            rows = cur.fetchall()

        return [Building(
            id=str(r["id"]),
            geom_wkt=r["geom_wkt"],
            area_sqm=float(r["area_sqm"]),
            roof_type=r.get("roof_type"),
            building_type=r.get("building_type"),
            source="alkis",
            lat=float(r["lat"]),
            lon=float(r["lon"]),
        ) for r in rows]

    def check_mastr(self, lat: float, lon: float, radius_m: float = 100) -> tuple[bool, float | None]:
        """Gibt (registered, capacity_kw) zurück."""
        if not self.mastr_table:
            return False, None
        t = self.mastr_table
        kw_col   = _safe(self.column_map.get("mastr_kw",   ""), "bruttoleistung") or "bruttoleistung"
        geom_col = _safe(self.column_map.get("mastr_geom", ""), "geom")           or "geom"
        sql = rf"""
            SELECT
                COUNT(*) AS cnt,
                SUM(
                    CASE WHEN {kw_col} ~ '^[0-9]+(\.[0-9]+)?$'
                         THEN {kw_col}::DOUBLE PRECISION ELSE 0
                    END
                ) AS total_kw
            FROM {t}
            WHERE ST_DWithin(
                {geom_col},
                ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 3035),
                %(r)s
            )
        """
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql, {"lat": lat, "lon": lon, "r": radius_m})
                row = cur.fetchone()
                if row and row["cnt"] and row["cnt"] > 0:
                    return True, float(row["total_kw"]) if row["total_kw"] else None
        except Exception as e:
            log.warning("MaStR-Abfrage fehlgeschlagen: %s", e)
        return False, None

    @staticmethod
    def load_columns(dsn: str, table: str) -> list[str]:
        """Liest Spaltenbezeichnungen der Tabelle aus PostgreSQL (für Mapping-UI)."""
        import psycopg2
        parts = table.rsplit(".", 1)
        schema, tbl = (parts[0], parts[1]) if len(parts) == 2 else ("public", parts[0])
        try:
            with psycopg2.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = %s AND table_name = %s "
                        "ORDER BY ordinal_position",
                        (schema, tbl),
                    )
                    return [r[0] for r in cur.fetchall()]
        except Exception as e:
            log.warning("Spalten konnten nicht geladen werden: %s", e)
            return []


# ── GeoPackage-Quelle ─────────────────────────────────────────────────────────

class GeoPackageSource:
    """Liest Gebäude aus einer GeoPackage-Datei via QGIS OGR-Provider.

    column_map – optionales Dict mit Spalten-Overrides (Schlüssel wie PostGISSource).
    Wenn ein Schlüssel belegt ist, wird dieser Spaltenname gegenüber den
    eingebauten Kandidatenlisten bevorzugt.

    Optional: mastr_gpkg_path / mastr_layer für lokale MaStR-GeoPackage.
    MaStR-GeoPackage aus BNetzA-CSV erstellen:
      QGIS → Layer → Delimited Text → CSV importieren → Als GeoPackage speichern
    Benötigte Spalten: geom (Punkt EPSG:4326), bruttoleistung (TEXT, kW)
    """

    def __init__(
        self,
        gpkg_path: str,
        layer_name: str,
        mastr_gpkg_path: str | None = None,
        mastr_layer: str | None = "mastr_solar",
        column_map: dict | None = None,
    ) -> None:
        self.gpkg_path = gpkg_path
        self.layer_name = layer_name
        self.mastr_gpkg_path = mastr_gpkg_path
        self.mastr_layer = mastr_layer or "mastr_solar"
        self.column_map = column_map or {}
        self._mastr_layer_obj = None

    def connect(self) -> None:
        if self.mastr_gpkg_path:
            from qgis.core import QgsVectorLayer
            uri = f"{self.mastr_gpkg_path}|layername={self.mastr_layer}"
            lyr = QgsVectorLayer(uri, "_mastr_tmp", "ogr")
            self._mastr_layer_obj = lyr if lyr.isValid() else None

    def close(self) -> None:
        self._mastr_layer_obj = None

    def find_buildings(
        self,
        min_lat: float, min_lon: float, max_lat: float, max_lon: float,
        min_area: float = 100.0,
        building_use: str | None = None,
        building_type_filter: str | None = None,
        limit: int | None = None,
    ) -> list[Building]:
        from qgis.core import (
            QgsVectorLayer, QgsFeatureRequest, QgsRectangle,
            QgsCoordinateReferenceSystem, QgsCoordinateTransform,
            QgsProject, QgsDistanceArea,
        )

        uri = f"{self.gpkg_path}|layername={self.layer_name}"
        layer = QgsVectorLayer(uri, "_solar_tmp", "ogr")
        if not layer.isValid():
            raise ValueError(f"Kann Layer '{self.layer_name}' aus {self.gpkg_path} nicht lesen")

        crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        to_layer = QgsCoordinateTransform(crs_4326, layer.crs(), QgsProject.instance())
        to_wgs   = QgsCoordinateTransform(layer.crs(), crs_4326, QgsProject.instance())

        bbox_4326  = QgsRectangle(min_lon, min_lat, max_lon, max_lat)
        bbox_layer = to_layer.transformBoundingBox(bbox_4326)

        da = QgsDistanceArea()
        da.setEllipsoid("WGS84")
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())

        request = QgsFeatureRequest().setFilterRect(bbox_layer)
        fields   = [f.name().lower() for f in layer.fields()]
        cm       = {k: v.lower() for k, v in self.column_map.items() if v and v.strip()}

        def _attr(feature, key: str, candidates: list[str], default=None):
            # explicit mapping has priority
            mapped = cm.get(key, "")
            if mapped and mapped in fields:
                v = feature.attribute(mapped)
                return v if v is not None and str(v) not in ("NULL", "None", "") else default
            for c in candidates:
                if c in fields:
                    v = feature.attribute(c)
                    if v is not None and str(v) not in ("NULL", "None", ""):
                        return v
            return default

        buildings: list[Building] = []
        for feat in layer.getFeatures(request):
            geom = feat.geometry()
            if geom.isNull():
                continue

            area = float(da.measureArea(geom))
            if area < min_area:
                continue

            building_type = _attr(feat, "building_type",
                                  ["gebaeudefunktion", "building_type", "type", "nutzung"])

            bt = str(building_type or "").strip()
            if building_type_filter:
                if building_type_filter.lower() not in bt.lower():
                    continue
            elif building_use == "wohnen":
                if not bt.startswith("31001_1"):
                    continue
            elif building_use == "gewerbe":
                if not (bt.startswith("31001_2") or bt.startswith("31001_3")):
                    continue

            centroid = geom.centroid().asPoint()
            centroid_wgs = to_wgs.transform(centroid)

            buildings.append(Building(
                id=str(_attr(feat, "id", ["gml_id", "fid", "id", "ogc_fid"]) or feat.id()),
                geom_wkt=geom.asWkt(),
                area_sqm=area,
                roof_type=_attr(feat, "roof_type", ["roof_type", "dachform", "dachtyp"]),
                building_type=str(building_type) if building_type else None,
                source="gpkg",
                lat=centroid_wgs.y(),
                lon=centroid_wgs.x(),
            ))

        buildings.sort(key=lambda b: b.area_sqm, reverse=True)
        if limit:
            buildings = buildings[:limit]
        return buildings

    def check_mastr(self, lat: float, lon: float, radius_m: float = 100) -> tuple[bool, float | None]:
        """Sucht PV-Einträge in einer optionalen MaStR-GeoPackage-Datei."""
        if self._mastr_layer_obj is None:
            return False, None

        from qgis.core import (
            QgsRectangle, QgsFeatureRequest, QgsDistanceArea,
            QgsCoordinateReferenceSystem, QgsCoordinateTransform,
            QgsPointXY, QgsProject,
        )

        layer    = self._mastr_layer_obj
        crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        to_layer = QgsCoordinateTransform(crs_4326, layer.crs(), QgsProject.instance())

        deg       = radius_m / 111_000
        bbox_4326 = QgsRectangle(lon - deg, lat - deg, lon + deg, lat + deg)
        bbox_lyr  = to_layer.transformBoundingBox(bbox_4326)

        da = QgsDistanceArea()
        da.setEllipsoid("WGS84")
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())

        center_lyr = to_layer.transform(QgsPointXY(lon, lat))
        fields     = [f.name().lower() for f in layer.fields()]
        kw_field   = next(
            (f for f in fields if "brutto" in f or "leistung" in f or "power" in f), None
        )

        total_kw = 0.0
        count    = 0
        for feat in layer.getFeatures(QgsFeatureRequest().setFilterRect(bbox_lyr)):
            geom = feat.geometry()
            if geom.isNull():
                continue
            if da.measureLine(center_lyr, geom.asPoint()) > radius_m:
                continue
            count += 1
            if kw_field:
                try:
                    total_kw += float(str(feat.attribute(kw_field)).replace(",", "."))
                except (ValueError, TypeError):
                    pass

        return (True, total_kw if total_kw > 0 else None) if count > 0 else (False, None)

    @staticmethod
    def load_columns(gpkg_path: str, layer_name: str) -> list[str]:
        """Liest Spaltenbezeichnungen des Layers (für Mapping-UI)."""
        from qgis.core import QgsVectorLayer
        layer = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", "_tmp", "ogr")
        return [f.name() for f in layer.fields()] if layer.isValid() else []
