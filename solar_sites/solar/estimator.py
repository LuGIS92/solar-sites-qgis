"""Solarpotenzial-Schätzung: DLR (primär) + PVGIS (Fallback/Ergänzung)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from solar_sites.buildings.finder import Building
from solar_sites.config import settings
from solar_sites.solar.pvgis import PVGISClient

log = logging.getLogger(__name__)

_pvgis = PVGISClient()

_FALLBACK_KWH_PER_KWP = 950.0
_irradiation_cache: dict[tuple[float, float], float] = {}


@dataclass
class SolarEstimate:
    annual_energy_kwh: float        # DLR wenn verfügbar, sonst PVGIS-basiert
    installable_kwp: float          # DLR-Fläche wenn verfügbar, sonst eigene Schätzung
    usable_area_sqm: float          # DLR-Fläche wenn verfügbar, sonst eigene Schätzung
    pvgis_irradiation: float        # kWh/kWp/Jahr (immer von PVGIS)
    roof_coverage_factor: float
    dlr_annual_kwh: float | None    # Rohwert DLR (für Transparenz)
    dlr_panel_area_sqm: float | None
    data_source: str                # "dlr" | "pvgis"


def estimate(building: Building) -> SolarEstimate:
    """Schätzt das Solarpotenzial: DLR-Daten bevorzugt, PVGIS als Fallback."""
    from solar_sites.solar.dlr import get_dlr_potential

    coverage = _roof_coverage(building)
    irradiation = _get_irradiation(building.lat, building.lon)

    # Eigene geometrische Schätzung (immer berechnet als Basis/Fallback)
    own_area = building.area_sqm * coverage
    own_kwp = own_area * settings.panel_power_per_sqm
    own_kwh = own_kwp * irradiation

    dlr = get_dlr_potential(building.lat, building.lon)

    if dlr and dlr.annual_energy_kwh > 0:
        annual_kwh = dlr.annual_energy_kwh
        if dlr.panel_area_sqm and dlr.panel_area_sqm > 0:
            usable_area = dlr.panel_area_sqm
            installable_kwp = usable_area * settings.panel_power_per_sqm
        else:
            usable_area = own_area
            installable_kwp = own_kwp
        source = "dlr"
        log.debug(
            "DLR genutzt für %s: %.0f kWh/Jahr (eigene Schätzung wäre %.0f kWh)",
            building.id[:8], annual_kwh, own_kwh,
        )
    else:
        annual_kwh = own_kwh
        usable_area = own_area
        installable_kwp = own_kwp
        source = "pvgis"

    return SolarEstimate(
        annual_energy_kwh=round(annual_kwh, 1),
        installable_kwp=round(installable_kwp, 2),
        usable_area_sqm=round(usable_area, 1),
        pvgis_irradiation=round(irradiation, 1),
        roof_coverage_factor=coverage,
        dlr_annual_kwh=round(dlr.annual_energy_kwh, 1) if dlr else None,
        dlr_panel_area_sqm=round(dlr.panel_area_sqm, 1) if dlr and dlr.panel_area_sqm else None,
        data_source=source,
    )


def _get_irradiation(lat: float, lon: float) -> float:
    """Gibt kWh/kWp/Jahr zurück – gecacht pro ~11-km-Gitterzelle."""
    key = (round(lat, 1), round(lon, 1))
    if key not in _irradiation_cache:
        value = _pvgis.get_irradiation_only(lat, lon)
        if value is None:
            log.warning("PVGIS Fallback für Gitterzelle %s", key)
            value = _FALLBACK_KWH_PER_KWP
        else:
            log.debug("PVGIS gecacht für Gitterzelle %s: %.0f kWh/kWp", key, value)
        _irradiation_cache[key] = value
    return _irradiation_cache[key]


def cache_stats() -> dict:
    return {"cached_cells": len(_irradiation_cache), "values": dict(_irradiation_cache)}


def _roof_coverage(building: Building) -> float:
    roof = (building.roof_type or "").lower()
    if any(t in roof for t in ("flat", "flach", "terrace")):
        return settings.roof_coverage_flat
    if any(t in roof for t in ("gable", "sattel", "hip", "walm", "pult")):
        return settings.roof_coverage_pitched
    return (settings.roof_coverage_flat + settings.roof_coverage_pitched) / 2
