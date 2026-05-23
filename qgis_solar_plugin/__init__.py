"""Solar Sites QGIS Plugin – path bootstrap.

Two modes:
  ZIP install   solar_sites/ is bundled inside this directory
  Development   solar_sites/ lives one level up (repo root)
"""

import sys
from pathlib import Path

_plugin_dir = Path(__file__).resolve().parent

if (_plugin_dir / "solar_sites").is_dir():
    # Installed from ZIP: solar_sites is bundled next to this file
    _lib_path = str(_plugin_dir)
else:
    # Development checkout: solar_sites is in the repo root
    _lib_path = str(_plugin_dir.parent)

if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)


def classFactory(iface):
    from .solar_plugin import SolarPlugin
    return SolarPlugin(iface)
