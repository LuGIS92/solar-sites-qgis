"""Workflow 1: Kundenliste verarbeiten.

Schritte: CSV einlesen → Geocoden → Gebäude finden → Potenzial schätzen → MaStR → Speichern
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TextIO

import pandas as pd
from tqdm import tqdm

from solar_sites.buildings.finder import find_buildings
from solar_sites.db import queries
from solar_sites.geocoding.nominatim import NominatimGeocoder
from solar_sites.registry.mastr import check_registered
from solar_sites.solar.detection import detect_for_building, model_available
from solar_sites.solar.estimator import estimate

log = logging.getLogger(__name__)


def run(
    input_path: Path,
    job_id: str | None = None,
    log_out: TextIO | None = None,
) -> str:
    """
    Verarbeitet eine Adressliste und speichert Solarpotenziale in der DB.
    Gibt die job_id zurück.
    """
    import sys
    out = log_out or sys.stdout

    job_id = job_id or str(uuid.uuid4())[:8]

    df = _read_input(input_path)
    print(f"[Job {job_id}] {len(df)} Adressen geladen aus {input_path.name}", file=out)

    geocoder = NominatimGeocoder()
    address_ids = queries.insert_addresses(_df_to_dicts(df, job_id), job_id)

    ok = geocode_fail = no_building = 0

    for idx, (_, row) in enumerate(tqdm(df.iterrows(), total=len(df), desc="Verarbeite", file=out)):
        address_id = address_ids[idx]
        street = f"{row.get('street', '')} {row.get('house_nr', '')}".strip()
        city = str(row.get("city", ""))

        geo = geocoder.geocode(
            street=street,
            city=city,
            postal_code=str(row.get("postal_code", "")),
        )
        if geo is None:
            print(f"  ✗ Geocoding fehlgeschlagen: {street}, {city}", file=out)
            geocode_fail += 1
            continue

        queries.update_geocode(address_id, geo.lat, geo.lon)

        buildings = find_buildings(geo.lat, geo.lon)
        if not buildings:
            print(f"  ✗ Kein Gebäude gefunden: {street}, {city} (lat={geo.lat:.4f}, lon={geo.lon:.4f})", file=out)
            no_building += 1
            continue

        building = buildings[0]
        solar = estimate(building)
        mastr = check_registered(building.lat, building.lon)
        panels = detect_for_building(building.id, building.geom_wkt)

        analysis = {
            "building_id": building.id,
            "address_id": address_id,
            "annual_energy_kwh": solar.annual_energy_kwh,
            "installable_kwp": solar.installable_kwp,
            "usable_area_sqm": solar.usable_area_sqm,
            "pvgis_irradiation": solar.pvgis_irradiation,
            "panels_detected": panels,
            "mastr_registered": mastr.registered,
            "mastr_capacity_kw": mastr.capacity_kw,
            "building_source": building.source,
            "building_type": building.building_type,
            "dlr_annual_kwh": solar.dlr_annual_kwh,
            "dlr_panel_area_sqm": solar.dlr_panel_area_sqm,
            "dlr_potential_score": None,
            "data_source": solar.data_source,
            "lat": building.lat,
            "lon": building.lon,
            "job_id": job_id,
        }
        queries.upsert_analysis(analysis)
        ok += 1

        pvgis_note = "(Fallback)" if solar.pvgis_irradiation == 950.0 else f"{solar.pvgis_irradiation:.0f} kWh/kWp"
        mastr_note = f"MaStR ✓ ({mastr.capacity_kw:.0f} kW)" if mastr.registered else "MaStR –"
        panel_note = "Panels ✓" if panels else ("Panels –" if model_available() else "")
        print(
            f"  ✓ {street}, {city}: {solar.annual_energy_kwh:,.0f} kWh/Jahr | "
            f"PVGIS {pvgis_note} | {mastr_note}"
            + (f" | {panel_note}" if panel_note else ""),
            file=out,
        )

    print(f"\n[Job {job_id}] Fertig: {ok} analysiert, {geocode_fail} Geocoding-Fehler, {no_building} kein Gebäude", file=out)
    return job_id


def _read_input(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".xls", ".xlsx"):
        df = pd.read_excel(path, dtype=str)
    else:
        df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.lower().str.strip()
    df.fillna("", inplace=True)
    return df


def _df_to_dicts(df: pd.DataFrame, job_id: str) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        street = str(r.get("street", "")).strip()
        house_nr = str(r.get("house_nr", "")).strip()
        city = str(r.get("city", "")).strip()
        postal_code = str(r.get("postal_code", "")).strip()
        rows.append({
            "raw": f"{street} {house_nr}, {postal_code} {city}".strip(", "),
            "street": street,
            "house_nr": house_nr,
            "city": city,
            "postal_code": postal_code,
            "country": str(r.get("country", "Deutschland")).strip() or "Deutschland",
            "job_id": job_id,
        })
    return rows
