"""Hintergrund-Thread für die PV-Analyse (verhindert QGIS-Freeze)."""

from __future__ import annotations

import traceback

from PyQt5.QtCore import QThread, pyqtSignal


class AnalysisWorker(QThread):
    """
    Führt die Analyse in einem separaten Thread durch.

    Signale:
        progress(str)            – Log-Zeile für die UI
        finished(list)           – Liste von Analyse-Dicts
        error(str)               – Fehlermeldung
    """

    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, source, params: dict) -> None:
        super().__init__()
        self.source = source   # PostGISSource, GeoPackageSource oder OverpassSource
        self.params = params

    def run(self) -> None:
        log = _ThreadLog(self.progress)
        try:
            self._run(log)
        except Exception as e:
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")

    def _run(self, log) -> None:
        p = self.params

        # 1. Gebäude laden
        print("\nSuche Gebäude ...", file=log)
        self.source.connect()

        buildings = self.source.find_buildings(
            p["min_lat"], p["min_lon"], p["max_lat"], p["max_lon"],
            min_area=p.get("min_area", 100),
            building_use=p.get("building_use"),
            building_type_filter=p.get("building_type_filter"),
            limit=p.get("limit"),
        )

        if not buildings:
            print("Keine Gebäude gefunden.", file=log)
            self.finished.emit([])
            self.source.close()
            return

        print(f"{len(buildings)} Gebäude gefunden.", file=log)

        # 2. Hilfsmodule laden + Voraussetzungen prüfen
        from solar_sites.solar.detection import detect_for_building, model_available
        from solar_sites.solar.dlr import get_dlr_potential
        from solar_sites.solar.estimator import estimate as _estimate
        try:
            from solar_sites.solar.dlr import clear_cache as _dlr_clear
            _dlr_clear()
        except ImportError:
            pass  # ältere dlr.py ohne clear_cache

        has_yolo = model_available()
        if has_yolo:
            # Leafmap-Verfügbarkeit testen
            try:
                import leafmap  # noqa: F401
                print("YOLO: Modell + leafmap gefunden – Panel-Erkennung aktiv.", file=log)
            except ImportError:
                has_yolo = False
                print(
                    "YOLO: Modell gefunden, aber leafmap fehlt in QGIS-Python.\n"
                    "  → In QGIS-Konsole ausführen:\n"
                    "    import pip; pip.main(['install','leafmap','shapely'])",
                    file=log,
                )
        else:
            print("YOLO: Kein Modell – Panel-Erkennung deaktiviert.", file=log)

        # DLR-Verfügbarkeit am ersten Gebäude testen
        b0 = buildings[0]
        try:
            import requests as _req
            import urllib3

            from solar_sites.config import settings as _cfg
            from solar_sites.solar.dlr import _coord_to_tile_pixel
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            _col, _row, _px, _py = _coord_to_tile_pixel(b0.lat, b0.lon, _cfg.dlr_zoom)
            _params = {
                "SERVICE": "WMTS", "REQUEST": "GetFeatureInfo", "VERSION": "1.0.0",
                "LAYER": _cfg.dlr_layer, "STYLE": "", "FORMAT": "image/png",
                "TILEMATRIXSET": "EPSG:900913",
                "TILEMATRIX": f"EPSG:900913:{_cfg.dlr_zoom}",
                "TILECOL": _col, "TILEROW": _row, "I": _px, "J": _py,
                "INFOFORMAT": "application/json",
            }
            _resp = _req.get(_cfg.dlr_wmts_url, params=_params, timeout=10, verify=False)
            if _resp.status_code == 200:
                _feats = _resp.json().get("features", [])
                if _feats:
                    _mwh = _feats[0].get("properties", {}).get("pveppmwhrp")
                    if _mwh:
                        print(f"DLR-Atlas: {float(_mwh) * 1000:.0f} kWh/Jahr ✓ (raw={_mwh} MWh)", file=log)
                    else:
                        _keys = list(_feats[0].get("properties", {}).keys())
                        print(f"DLR-Atlas: Felder unerwartet – {_keys}", file=log)
                else:
                    print(
                        f"DLR-Atlas: Kein Gebäude bei (lat={b0.lat:.4f} lon={b0.lon:.4f}"
                        f" zoom={_cfg.dlr_zoom}) – Fallback PVGIS.",
                        file=log,
                    )
            else:
                print(f"DLR-Atlas: HTTP {_resp.status_code} – {_resp.text[:120]}", file=log)
        except Exception as _e:
            print(f"DLR-Atlas: Fehler – {type(_e).__name__}: {_e}", file=log)

        # 3. Reverse-Geocoding (optional)
        addresses: dict[str, dict] = {}
        if p.get("geocode_addresses", False) and buildings:
            from solar_sites.geocoding.nominatim import NominatimGeocoder
            geocoder = NominatimGeocoder()
            print(
                f"Reverse-Geocoding: {len(buildings)} Gebäude "
                f"(~{len(buildings)} s) ...",
                file=log,
            )
            for i, b in enumerate(buildings, 1):
                try:
                    addresses[b.id] = geocoder.reverse(b.lat, b.lon) or {}
                except Exception:
                    addresses[b.id] = {}
                if i % 20 == 0 or i == len(buildings):
                    print(f"  Geocoding {i}/{len(buildings)} ...", file=log)

        # 4. Solar-Schätzung + MaStR + YOLO pro Gebäude
        analyses = []
        skip_mastr = p.get("skip_mastr", False)

        for i, b in enumerate(buildings, 1):
            bobj = _to_solar_building(b)
            solar = _estimate(bobj)

            mastr_reg, mastr_kw = (
                (False, None) if skip_mastr
                else self.source.check_mastr(b.lat, b.lon)
            )
            panels = detect_for_building(b.id, b.geom_wkt) if has_yolo else False

            addr = addresses.get(b.id, {})
            analyses.append({
                "building_id":        b.id,
                "building_source":    b.source,
                "building_type":      b.building_type,
                "lat":                b.lat,
                "lon":                b.lon,
                "area_sqm":           b.area_sqm,
                "annual_energy_kwh":  solar.annual_energy_kwh,
                "installable_kwp":    solar.installable_kwp,
                "usable_area_sqm":    solar.usable_area_sqm,
                "pvgis_irradiation":  solar.pvgis_irradiation,
                "dlr_annual_kwh":     solar.dlr_annual_kwh,
                "dlr_panel_area_sqm": solar.dlr_panel_area_sqm,
                "data_source":        solar.data_source,
                "mastr_registered":   mastr_reg,
                "mastr_capacity_kw":  mastr_kw,
                "panels_detected":    panels,
                # Adressfelder aus Nominatim reverse()
                "raw_address":  _fmt_address(addr),
                "street":       addr.get("road", ""),
                "house_nr":     addr.get("house_number", ""),
                "city":         addr.get("city") or addr.get("town") or addr.get("village") or "",
                "postal_code":  addr.get("postcode", ""),
            })

            if i % 5 == 0 or i == len(buildings):
                print(f"  {i}/{len(buildings)} analysiert ...", file=log)

        self.source.close()

        mastr_hits = sum(1 for a in analyses if a["mastr_registered"])
        panel_hits = sum(1 for a in analyses if a["panels_detected"])
        dlr_hits   = sum(1 for a in analyses if a["dlr_annual_kwh"])

        print(f"\nFertig: {len(analyses)} Gebäude analysiert", file=log)
        if not skip_mastr:
            print(f"  MaStR: {mastr_hits} mit PV-Anlage registriert", file=log)
        print(f"  DLR-Daten: {dlr_hits} Gebäude", file=log)
        if has_yolo:
            print(f"  YOLO: {panel_hits} Panels erkannt", file=log)

        self.finished.emit(analyses)


def _fmt_address(addr: dict) -> str:
    parts = []
    road = addr.get("road", "")
    nr   = addr.get("house_number", "")
    if road:
        parts.append(f"{road} {nr}".strip())
    city = addr.get("city") or addr.get("town") or addr.get("village") or ""
    plz  = addr.get("postcode", "")
    if city:
        parts.append(f"{plz} {city}".strip() if plz else city)
    return ", ".join(parts)


def _to_solar_building(b):
    """Konvertiert das Plugin-Building zu solar_sites.buildings.finder.Building."""
    try:
        from solar_sites.buildings.finder import Building
        return Building(
            id=b.id,
            geom_wkt=b.geom_wkt,
            area_sqm=b.area_sqm,
            roof_type=b.roof_type,
            building_type=b.building_type,
            source=b.source,
            lat=b.lat,
            lon=b.lon,
        )
    except ImportError:
        return b


class _ThreadLog:
    """File-like Objekt das Log-Zeilen als Qt-Signal emittiert."""

    def __init__(self, signal) -> None:
        self._signal = signal

    def write(self, msg: str) -> None:
        stripped = msg.rstrip()
        if stripped:
            self._signal.emit(stripped)

    def flush(self) -> None:
        pass
