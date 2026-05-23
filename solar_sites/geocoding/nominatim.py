from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

from solar_sites.config import settings


@dataclass
class GeocodedAddress:
    lat: float
    lon: float
    display_name: str
    bbox: tuple[float, float, float, float] | None = None  # (min_lat, min_lon, max_lat, max_lon)


class NominatimGeocoder:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": settings.nominatim_user_agent})
        self._last_call: float = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < settings.nominatim_delay_s:
            time.sleep(settings.nominatim_delay_s - elapsed)
        self._last_call = time.monotonic()

    def _parse(self, r: dict) -> GeocodedAddress:
        bbox = None
        if "boundingbox" in r:
            # Nominatim: [min_lat, max_lat, min_lon, max_lon]
            bb = r["boundingbox"]
            bbox = (float(bb[0]), float(bb[2]), float(bb[1]), float(bb[3]))
        return GeocodedAddress(
            lat=float(r["lat"]),
            lon=float(r["lon"]),
            display_name=r["display_name"],
            bbox=bbox,
        )

    def geocode(self, street: str, city: str, postal_code: str = "", country: str = "Deutschland") -> GeocodedAddress | None:
        self._wait()
        params = {
            "street": street,
            "city": city,
            "postalcode": postal_code,
            "country": country,
            "format": "json",
            "limit": 1,
        }
        resp = self._session.get(f"{settings.nominatim_url}/search", params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        return self._parse(results[0])

    def geocode_raw(self, query: str) -> GeocodedAddress | None:
        self._wait()
        resp = self._session.get(
            f"{settings.nominatim_url}/search",
            params={"q": query, "format": "json", "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        return self._parse(results[0])

    def reverse(self, lat: float, lon: float) -> dict | None:
        self._wait()
        resp = self._session.get(
            f"{settings.nominatim_url}/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("address")
