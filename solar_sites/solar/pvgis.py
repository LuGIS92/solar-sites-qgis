"""PVGIS API-Client (EU-Kommission, kostenlos).

Dokumentation: https://re.jrc.ec.europa.eu/api/v5_2/
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from solar_sites.config import settings

log = logging.getLogger(__name__)


@dataclass
class PVGISResult:
    annual_irradiation_kwh_per_kwp: float  # Jahresertrag pro kWp (kWh/kWp)
    optimal_angle_deg: float
    location_name: str | None = None


class PVGISClient:
    def __init__(self) -> None:
        self._session = requests.Session()

    def get_annual_yield(self, lat: float, lon: float, kwp: float = 1.0) -> PVGISResult | None:
        """
        Fragt den Jahresertrag für einen Standort ab.
        kwp=1.0 liefert normierte kWh/kWp → zum Skalieren multiplizieren.
        """
        params = {
            "lat": lat,
            "lon": lon,
            "peakpower": kwp,
            "loss": settings.pvgis_system_loss,
            "mountingplace": settings.pvgis_mounting,
            "outputformat": "json",
            "browser": 0,
        }
        try:
            resp = self._session.get(
                f"{settings.pvgis_url}/PVcalc",
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            totals = data["outputs"]["totals"]["fixed"]
            result = PVGISResult(
                annual_irradiation_kwh_per_kwp=totals["E_y"],
                optimal_angle_deg=data["inputs"]["mounting_system"]["fixed"]["slope"]["value"],
            )
            log.debug("PVGIS OK (lat=%.4f, lon=%.4f): %.0f kWh/kWp", lat, lon, result.annual_irradiation_kwh_per_kwp)
            return result
        except requests.HTTPError as e:
            log.warning("PVGIS HTTP-Fehler (lat=%.4f, lon=%.4f): %s", lat, lon, e)
        except Exception as e:
            log.warning("PVGIS-Abfrage fehlgeschlagen (lat=%.4f, lon=%.4f): %s", lat, lon, e)
        return None

    def get_irradiation_only(self, lat: float, lon: float) -> float | None:
        """Gibt kWh/kWp/Jahr zurück oder None bei Fehler."""
        result = self.get_annual_yield(lat, lon, kwp=1.0)
        if result is None:
            return None
        return result.annual_irradiation_kwh_per_kwp
