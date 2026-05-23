from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
MODEL_PATH = DATA_DIR / "models" / "solar_panels.pt"
EXPORTS_DIR = ROOT_DIR / "exports"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    # Datenbank
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "energy"
    postgres_user: str = "postgres"
    postgres_password: str = ""

    # Schema & Tabellen in der bestehenden DB
    db_schema: str = "solar_sites"
    buildings_table: str = "deutschland.gebaeude_deutschland_tbl"
    osm_buildings_table: str = "osm.osm_buildings"
    mastr_table: str = "deutschland.mastr_solar"

    # Solarpotenzial-Parameter
    panel_efficiency: float = 0.20          # 20 % Modulwirkungsgrad
    roof_coverage_flat: float = 0.65        # Nutzbare Fläche auf Flachdach
    roof_coverage_pitched: float = 0.55     # Nutzbare Fläche auf Satteldach
    panel_power_per_sqm: float = 0.175      # kWp pro m²
    min_roof_area_sqm: float = 100.0        # Mindestdachfläche für Analyse
    building_search_radius_m: float = 250.0 # Suchradius um geocodierte Adresse

    # YOLO-Erkennung + Satellitenbild
    detection_confidence: float = 0.80
    satellite_zoom: int = 19
    satellite_source: str = "Satellite"   # leafmap-Quelle, z.B. "Esri.WorldImagery"

    # DLR Solar-Potenzialatlas Deutschland
    dlr_wmts_url: str = "https://geoservice.dlr.de/eoc/gwc/service/wmts"
    dlr_layer: str = "solarde:SDE_BUILDINGS"
    dlr_zoom: int = 21

    # Geocoding
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "solar-sites/2.0"
    nominatim_delay_s: float = 1.1          # Rate-Limit: 1 Anfrage/Sekunde

    # PVGIS
    pvgis_url: str = "https://re.jrc.ec.europa.eu/api/v5_2"
    pvgis_system_loss: float = 14.0         # Systemverluste in %
    pvgis_mounting: str = "free"            # "free" = Aufdach, "building" = BIPV

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
