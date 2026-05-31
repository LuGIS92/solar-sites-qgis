"""
Konfiguration via pydantic-settings (primär) oder einfachem .env-Fallback.

pydantic-settings benötigt typing_extensions >= 4.6.0 (Sentinel).
Ältere QGIS-Bundles (z.B. QGIS 4.0.2) liefern eine ältere Version mit →
ImportError. Der Fallback repliziert dasselbe Interface ohne externe Abhängigkeit.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
MODEL_PATH = DATA_DIR / "models" / "solar_panels.pt"
EXPORTS_DIR = ROOT_DIR / "exports"


# ---------------------------------------------------------------------------
# Primär: pydantic-settings (falls korrekt installiert)
# ---------------------------------------------------------------------------
try:
    from pydantic import field_validator
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=str(ROOT_DIR / ".env"),
            env_file_encoding="utf-8",
            extra="ignore",
        )

        # Datenbank
        postgres_host: str = "localhost"
        postgres_port: int = 5432
        postgres_db: str = "energy"
        postgres_user: str = "postgres"
        postgres_password: str = ""

        # Schema & Tabellen
        db_schema: str = "solar_sites"
        buildings_table: str = "deutschland.gebaeude_deutschland_tbl"
        osm_buildings_table: str = "osm.osm_buildings"
        mastr_table: str = "deutschland.mastr_solar"

        # Solarpotenzial-Parameter
        panel_efficiency: float = 0.20
        roof_coverage_flat: float = 0.65
        roof_coverage_pitched: float = 0.55
        panel_power_per_sqm: float = 0.175
        min_roof_area_sqm: float = 100.0
        building_search_radius_m: float = 250.0

        # YOLO
        detection_confidence: float = 0.80
        satellite_zoom: int = 19
        satellite_source: str = "Satellite"

        # DLR
        dlr_wmts_url: str = "https://geoservice.dlr.de/eoc/gwc/service/wmts"
        dlr_layer: str = "solarde:SDE_BUILDINGS"
        dlr_zoom: int = 21

        # Geocoding
        nominatim_url: str = "https://nominatim.openstreetmap.org"
        nominatim_user_agent: str = "solar-sites/2.0"
        nominatim_delay_s: float = 1.1

        # PVGIS
        pvgis_url: str = "https://re.jrc.ec.europa.eu/api/v5_2"
        pvgis_system_loss: float = 14.0
        pvgis_mounting: str = "free"

        @field_validator("postgres_password", mode="before")
        @classmethod
        def _strip(cls, v: str) -> str:
            return str(v).strip()

        @property
        def db_dsn(self) -> str:
            return (
                f"host={self.postgres_host} port={self.postgres_port} "
                f"dbname={self.postgres_db} user={self.postgres_user} "
                f"password={self.postgres_password}"
            )

    settings = Settings()

# ---------------------------------------------------------------------------
# Fallback: einfaches .env-Parsing ohne externe Abhängigkeit
# Wird z.B. bei altem typing_extensions in QGIS-Bundle-Python genutzt.
# ---------------------------------------------------------------------------
except ImportError:

    class _SimpleSettings:
        """Minimale Settings-Implementierung: liest .env + os.environ."""

        def __init__(self) -> None:
            env = _load_dotenv(ROOT_DIR / ".env")

            def g(key: str, default, cast=str):
                """Holt Wert aus .env oder Umgebungsvariable, mit Typ-Cast."""
                v = env.get(key.lower()) or os.environ.get(key.upper())
                if v is None:
                    return default
                try:
                    return cast(v)
                except (ValueError, TypeError):
                    return default

            # Datenbank
            self.postgres_host = g("postgres_host", "localhost")
            self.postgres_port = g("postgres_port", 5432, int)
            self.postgres_db   = g("postgres_db",   "energy")
            self.postgres_user = g("postgres_user", "postgres")
            self.postgres_password = g("postgres_password", "").strip()

            # Schema & Tabellen
            self.db_schema            = g("db_schema",            "solar_sites")
            self.buildings_table      = g("buildings_table",      "deutschland.gebaeude_deutschland_tbl")
            self.osm_buildings_table  = g("osm_buildings_table",  "osm.osm_buildings")
            self.mastr_table          = g("mastr_table",          "deutschland.mastr_solar")

            # Solarpotenzial-Parameter
            self.panel_efficiency          = g("panel_efficiency",          0.20,  float)
            self.roof_coverage_flat        = g("roof_coverage_flat",        0.65,  float)
            self.roof_coverage_pitched     = g("roof_coverage_pitched",     0.55,  float)
            self.panel_power_per_sqm       = g("panel_power_per_sqm",       0.175, float)
            self.min_roof_area_sqm         = g("min_roof_area_sqm",         100.0, float)
            self.building_search_radius_m  = g("building_search_radius_m",  250.0, float)

            # YOLO
            self.detection_confidence = g("detection_confidence", 0.80, float)
            self.satellite_zoom       = g("satellite_zoom",       19,   int)
            self.satellite_source     = g("satellite_source",     "Satellite")

            # DLR
            self.dlr_wmts_url = g("dlr_wmts_url", "https://geoservice.dlr.de/eoc/gwc/service/wmts")
            self.dlr_layer    = g("dlr_layer",    "solarde:SDE_BUILDINGS")
            self.dlr_zoom     = g("dlr_zoom",     21, int)

            # Geocoding
            self.nominatim_url        = g("nominatim_url",        "https://nominatim.openstreetmap.org")
            self.nominatim_user_agent = g("nominatim_user_agent", "solar-sites/2.0")
            self.nominatim_delay_s    = g("nominatim_delay_s",    1.1, float)

            # PVGIS
            self.pvgis_url         = g("pvgis_url",         "https://re.jrc.ec.europa.eu/api/v5_2")
            self.pvgis_system_loss = g("pvgis_system_loss", 14.0, float)
            self.pvgis_mounting    = g("pvgis_mounting",    "free")

        @property
        def db_dsn(self) -> str:
            return (
                f"host={self.postgres_host} port={self.postgres_port} "
                f"dbname={self.postgres_db} user={self.postgres_user} "
                f"password={self.postgres_password}"
            )

    def _load_dotenv(path: Path) -> dict[str, str]:
        """Liest eine .env-Datei in ein Dict (Keys lowercase, ohne Anführungszeichen)."""
        result: dict[str, str] = {}
        if not path.exists():
            return result
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            result[key.strip().lower()] = val.strip().strip("\"'")
        return result

    settings = _SimpleSettings()
