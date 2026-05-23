"""Workflow 2: Freie Flächensuche."""

from __future__ import annotations

import logging
import uuid
from typing import TextIO

from tqdm import tqdm

from solar_sites.buildings.finder import Building, find_buildings_in_area
from solar_sites.config import settings
from solar_sites.db import queries
from solar_sites.geocoding.nominatim import NominatimGeocoder
from solar_sites.registry.mastr import MastrResult, check_registered
from solar_sites.solar.detection import detect_for_building, model_available
from solar_sites.solar.estimator import cache_stats, estimate

log = logging.getLogger(__name__)


def _geocode_addresses(buildings: list[Building], job_id: str, out) -> dict[str, int | None]:
    """Reverse-geocodiert Gebäude via Nominatim und speichert Adressen in DB."""
    geocoder = NominatimGeocoder()
    result: dict[str, int | None] = {}
    for b in tqdm(buildings, desc="Adressen", file=out):
        try:
            addr = geocoder.reverse(b.lat, b.lon)
            if addr:
                street = addr.get("road", "")
                house_nr = addr.get("house_number", "")
                city = (addr.get("city") or addr.get("town") or
                        addr.get("village") or addr.get("municipality") or "")
                postal = addr.get("postcode", "")
                raw = f"{street} {house_nr}, {postal} {city}".strip(", ")
                ids = queries.insert_addresses([{
                    "raw": raw,
                    "street": street,
                    "house_nr": house_nr,
                    "city": city,
                    "postal_code": postal,
                    "country": addr.get("country", "Deutschland"),
                }], job_id)
                queries.update_geocode(ids[0], b.lat, b.lon)
                result[b.id] = ids[0]
            else:
                result[b.id] = None
        except Exception as e:
            log.warning("Reverse geocoding fehlgeschlagen für %s: %s", b.id, e)
            result[b.id] = None
    return result


def run_by_city(
    city: str,
    postal_code: str = "",
    min_area_sqm: float | None = None,
    limit: int | None = None,
    skip_mastr: bool = False,
    building_use: str | None = None,
    job_id: str | None = None,
    log_out: TextIO | None = None,
) -> str:
    import sys
    out = log_out or sys.stdout

    geocoder = NominatimGeocoder()
    query = f"{postal_code} {city}".strip() if postal_code else city
    geo = geocoder.geocode_raw(query)
    if geo is None:
        raise ValueError(f"Konnte '{query}' nicht geocoden.")

    print(f"  Geocoding: {geo.display_name}", file=out)

    if geo.bbox:
        min_lat, min_lon, max_lat, max_lon = geo.bbox
        print(f"  Bounding-Box: {min_lat:.4f},{min_lon:.4f} → {max_lat:.4f},{max_lon:.4f}", file=out)
    else:
        delta = 0.045
        min_lat, min_lon = geo.lat - delta, geo.lon - delta
        max_lat, max_lon = geo.lat + delta, geo.lon + delta
        print(f"  Bounding-Box (Fallback ±5 km): {min_lat:.4f},{min_lon:.4f} → {max_lat:.4f},{max_lon:.4f}", file=out)

    return run_by_bbox(
        min_lat=min_lat, min_lon=min_lon,
        max_lat=max_lat, max_lon=max_lon,
        min_area_sqm=min_area_sqm,
        limit=limit,
        skip_mastr=skip_mastr,
        building_use=building_use,
        job_id=job_id,
        label=query,
        log_out=log_out,
    )


def run_by_bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    min_area_sqm: float | None = None,
    limit: int | None = None,
    skip_mastr: bool = False,
    building_use: str | None = None,
    job_id: str | None = None,
    label: str = "BBox",
    log_out: TextIO | None = None,
) -> str:
    import sys
    out = log_out or sys.stdout

    job_id = job_id or str(uuid.uuid4())[:8]
    min_area = min_area_sqm or settings.min_roof_area_sqm

    use_label = {"wohnen": " [nur Wohngebäude]", "gewerbe": " [nur Gewerbe/Industrie]"}.get(building_use or "", "")
    print(f"\n[Job {job_id}] Suche Gebäude in: {label}{use_label}", file=out)
    buildings = find_buildings_in_area(min_lat, min_lon, max_lat, max_lon, min_area, building_use)

    if limit and len(buildings) > limit:
        print(f"[Job {job_id}] {len(buildings)} Gebäude gefunden → auf {limit} begrenzt (größte zuerst)", file=out)
        buildings = buildings[:limit]
    else:
        print(f"[Job {job_id}] {len(buildings)} Gebäude gefunden (≥{min_area:.0f} m²)", file=out)

    if not buildings:
        return job_id

    print(f"[Job {job_id}] Suche Adressen via Reverse-Geocoding (≈1 sec/Gebäude)...", file=out)
    address_ids = _geocode_addresses(buildings, job_id, out)

    _no_mastr = MastrResult(registered=False, capacity_kw=None, nearest_distance_m=None, count=0)
    pvgis_errors = mastr_hits = panel_hits = 0

    if model_available():
        print(f"[Job {job_id}] YOLO-Modell gefunden – Panel-Erkennung aktiv", file=out)

    for b in tqdm(buildings, desc="Analysiere", file=out):
        solar = estimate(b)
        if solar.pvgis_irradiation == 950.0:
            pvgis_errors += 1

        mastr = _no_mastr if skip_mastr else check_registered(b.lat, b.lon)
        if mastr.registered:
            mastr_hits += 1

        panels = detect_for_building(b.id, b.geom_wkt)
        if panels:
            panel_hits += 1

        queries.upsert_analysis({
            "building_id": b.id,
            "address_id": address_ids.get(b.id),
            "annual_energy_kwh": solar.annual_energy_kwh,
            "installable_kwp": solar.installable_kwp,
            "usable_area_sqm": solar.usable_area_sqm,
            "pvgis_irradiation": solar.pvgis_irradiation,
            "panels_detected": panels,
            "mastr_registered": mastr.registered,
            "mastr_capacity_kw": mastr.capacity_kw,
            "building_source": b.source,
            "building_type": b.building_type,
            "dlr_annual_kwh": solar.dlr_annual_kwh,
            "dlr_panel_area_sqm": solar.dlr_panel_area_sqm,
            "dlr_potential_score": None,
            "data_source": solar.data_source,
            "lat": b.lat,
            "lon": b.lon,
            "job_id": job_id,
        })

    stats = cache_stats()
    print(f"\n[Job {job_id}] Fertig: {len(buildings)} Gebäude analysiert", file=out)
    print(f"  PVGIS: {len(buildings) - pvgis_errors} OK, {pvgis_errors} Fallback | {stats['cached_cells']} API-Aufrufe (Cache)", file=out)
    if not skip_mastr:
        print(f"  MaStR: {mastr_hits} mit PV-Anlage registriert", file=out)
    else:
        print("  MaStR: übersprungen (--no-mastr)", file=out)
    if model_available():
        print(f"  YOLO: {panel_hits} Gebäude mit Panels erkannt", file=out)
    return job_id
