"""pytest-Konfiguration: Repo-Root auf sys.path setzen."""

import sys
from pathlib import Path

# Repo-Root → solar_sites und qgis_solar_plugin importierbar machen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
