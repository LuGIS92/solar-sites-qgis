# Solar Sites – QGIS PV-Analyse-Plugin

[![CI](https://github.com/LuGIS92/solar-sites-qgis/actions/workflows/ci.yml/badge.svg)](https://github.com/LuGIS92/solar-sites-qgis/actions/workflows/ci.yml)
[![Lizenz: GPL v3](https://img.shields.io/badge/Lizenz-GPL%20v3-blue.svg)](LICENSE)
[![QGIS ≥ 3.16](https://img.shields.io/badge/QGIS-%E2%89%A53.16-green)](https://qgis.org)

QGIS-Plugin zur automatisierten PV-Potenzialanalyse auf Gebäudedächern.  
Gebäude werden aus **ALKIS/PostGIS**, einer **GeoPackage-Datei** oder direkt aus
**OpenStreetMap** geladen. Strahlungsdaten kommen von **PVGIS** (EU JRC) und dem
**DLR-Gebäudeatlas**, PV-Bestandsanlagen werden im **Marktstammdatenregister (MaStR)**
geprüft – alles ohne QGIS zu verlassen.

> Schwerpunkt Deutschland, funktioniert aber mit jedem Gebäudedatensatz der in QGIS
> geladen werden kann. OSM-Modus ist weltweit einsetzbar.

---

## Funktionen

| Funktion | Details |
|---|---|
| **Drei Datenquellen** | QGIS-PostgreSQL-Verbindung (ALKIS/PostGIS) · GeoPackage · OpenStreetMap via Overpass-API |
| **Solarschätzung** | DLR-Gebäudeatlas (primär) · PVGIS REST-API (Fallback) |
| **MaStR-Abgleich** | Kennzeichnet Gebäude mit bereits registrierten PV-Anlagen |
| **Panel-Erkennung** | Optionale YOLO-basierte Erkennung auf Satellitenbildern (erfordert `leafmap`) |
| **Flexible Filter** | Mindestdachfläche · Gebäudetyp-Voreinstellungen · Freitext-Filter |
| **Suchgebiet** | Aktuelle Kartenansicht · Extent eines Layers · Stadt/PLZ-Geocoding |
| **Spalten-Zuordnung** | Beliebige Spaltennamen auf Pflichtfelder mappen (Wizard Seite 2) |
| **Exporte** | QGIS-Vektorlayer (Farbverlauf) · Excel (.xlsx) · GeoPackage |
| **Nicht-blockierend** | Analyse läuft im Hintergrund-Thread; QGIS bleibt bedienbar |

---

## Voraussetzungen

| Anforderung | Version |
|---|---|
| QGIS | ≥ 3.16 |
| Python | ≥ 3.9 (wird mit QGIS mitgeliefert) |

### Python-Pakete (einmalig in QGIS-Python installieren)

**QGIS → Erweiterungen → Python-Konsole** öffnen und ausführen:

```python
import pip

# Minimum (Excel-Export + Konfiguration):
pip.main(['install', 'pandas', 'openpyxl', 'pydantic-settings'])

# Nur für PostGIS-Modus:
pip.main(['install', 'psycopg2-binary'])

# Optional – YOLO-Panel-Erkennung:
pip.main(['install', 'leafmap', 'ultralytics'])
```

> OSM/Overpass-Modus benötigt keine zusätzlichen Pakete – nur Python-Stdlib.

---

## Installation

### Aus dem ZIP (empfohlen)

Noch kein offizieller Release vorhanden. ZIP selbst bauen:

```bash
git clone https://github.com/LuGIS92/solar-sites-qgis.git
cd solar-sites-qgis
bash scripts/build_zip.sh
# → dist/solar_sites_pv_analysis_v2.0.0.zip
```

Dann in QGIS: **Erweiterungen → Erweiterungen verwalten → Aus ZIP installieren**.

### Entwickler-Installation (Symlink)

```bash
git clone https://github.com/LuGIS92/solar-sites-qgis.git
cd solar-sites-qgis

# macOS:
ln -sfn "$(pwd)/qgis_solar_plugin" \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_solar_plugin

# Linux:
ln -sfn "$(pwd)/qgis_solar_plugin" \
  ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/qgis_solar_plugin
```

Den Symlink **nur einmal** setzen – er bleibt dauerhaft erhalten.  
Änderungen im Repository sind sofort aktiv; nur Plugin Reloader (F5) drücken.

---

## Schnellstart (mit Beispieldaten)

Im Ordner `data/sample.gpkg` liegen 20 synthetische Gebäude im Kölner Raum.

1. QGIS öffnen, Hintergrundkarte laden (z.B. OpenStreetMap via QuickMapServices).
2. Solar Sites Panel öffnen (Toolbar oder **Erweiterungen → Solar Sites**).
3. **Seite 1 – Datenquelle:** *GeoPackage* wählen, `data/sample.gpkg`, Layer `buildings`.
4. **Seite 2 – Spalten:** *Spalten laden* klicken, dann *Weiter* (automatische Erkennung).
5. **Seite 3 – Suchgebiet:** *Aktuelle Kartenansicht übernehmen* oder `Köln` eingeben.
6. **Seite 4 – Filter:** Standardwerte lassen, **Analyse starten** klicken.
7. Ein neuer Punkt-Layer *Solar XXXX* erscheint – farbcodiert nach Jahresertrag (grün = hohes Potenzial).

### Ohne eigene Gebäudedaten – OSM-Modus

1. **Seite 1 – Datenquelle:** *OpenStreetMap (Overpass)* wählen.
2. Seite 2 (Spalten) wird automatisch übersprungen.
3. **Seite 3 – Suchgebiet:** Stadt eingeben oder Kartenausschnitt übernehmen.
4. **Seite 4 – Filter:** Gebäude-Limit setzen (Empfehlung: 100–200 für erste Tests).
5. Analyse starten – Gebäude werden live aus OpenStreetMap geladen.

> **Hinweis OSM-Modus:** Für große Gebiete (> 5 km²) kann die Overpass-Abfrage mehrere
> Minuten dauern. Gebäudetyp-Filter nutzt OSM-Tags (`house`, `industrial`, …) statt ALKIS-Codes.

---

## Datenquellen

### Option A – PostGIS (ALKIS)

Erfordert eine PostgreSQL/PostGIS-Datenbank mit ALKIS-Gebäudedaten.

| Einstellung | Standard | Beschreibung |
|---|---|---|
| Verbindung | — | In QGIS gespeicherte PostgreSQL-Verbindung |
| Gebäude-Tabelle | `deutschland.gebaeude_deutschland_tbl` | ALKIS-Polygon-Tabelle (SRID 3035) |
| MaStR-Tabelle | `deutschland.mastr_solar` | Punkt-Tabelle mit PV-Registrierungen (optional) |

**Erwartete Spalten (ALKIS-Standard):**

| Spalte | Typ | Hinweis |
|---|---|---|
| `gml_id` | TEXT | Eindeutige Gebäude-ID |
| `geom` | GEOMETRY(Polygon, 3035) | Grundriss |
| `area` | DOUBLE PRECISION | Dachfläche m² (oder via ST_Area berechnet) |
| `gebaeudefunktion` | TEXT | ALKIS-Gebäudefunktionscode |
| `roof_type` | TEXT | Dachform (optional) |

Abweichende Spaltennamen können auf Wizard-Seite 2 zugeordnet werden.

### Option B – GeoPackage

Jede Polygon-Layer-Datei funktioniert. Das Plugin erkennt gängige Spaltennamen
automatisch und fällt graceful zurück wenn Felder fehlen.

**MaStR als GeoPackage** – am einfachsten via [open-mastr](https://open-mastr.readthedocs.io/en/latest/advanced/):

```bash
pip install open-mastr
python -c "
from open_mastr import Mastr
db = Mastr()
db.download(date='today')
db.to_csv()
# Solar-CSV in QGIS importieren → Als GeoPackage speichern
"
```

### Option C – OpenStreetMap (Overpass-API)

Keine lokalen Daten nötig. Gebäude werden live aus OSM geladen.

- Weltweit einsetzbar
- Keine zusätzliche Installation
- Standard-Overpass-Endpunkt: `https://overpass-api.de/api/interpreter`
- Alternative Instanzen können in der UI konfiguriert werden
- Gebäudetyp-Filter nutzt OSM-Tags: `house`, `apartments`, `industrial`, `warehouse`, …

---

## Ausgabe-Felder

| Feld | Einheit | Quelle |
|---|---|---|
| `annual_energy_kwh` | kWh/Jahr | DLR oder PVGIS |
| `installable_kwp` | kWp | DLR-Modulfläche oder Schätzung |
| `usable_area_sqm` | m² | DLR oder Schätzung |
| `pvgis_irradiation` | kWh/kWp/Jahr | PVGIS-API |
| `dlr_annual_kwh` | kWh/Jahr | DLR-Gebäudeatlas (Rohwert) |
| `data_source` | `dlr` / `pvgis` | Verwendete Quelle |
| `mastr_registered` | 0 / 1 | Im MaStR gefunden |
| `mastr_capacity_kw` | kW | Registrierte Gesamtleistung in der Nähe |
| `panels_detected` | 0 / 1 | YOLO-Erkennungsergebnis |
| `building_type` | Text | ALKIS-Code oder OSM-Tag |
| `building_source` | Text | `alkis`, `osm`, … |
| `area_sqm` | m² | Grundfläche |

---

## Gebäudetyp-Filter

| Eingabe | Wirkung |
|---|---|
| *(leer)* | Alle Gebäude |
| Voreinstellung *Wohngebäude* | ALKIS `31001_1xxx` / OSM: `house`, `apartments`, … |
| Voreinstellung *Gewerbe/Industrie* | ALKIS `31001_2xxx`/`31001_3xxx` / OSM: `industrial`, `warehouse`, … |
| `31001_2620` | Genau ein ALKIS-Typ (z.B. Lagerhalle) |
| `industrial` | Freitext – enthält diesen String (Groß-/Kleinschreibung egal) |

---

## Konfiguration (`.env`)

`.env.example` nach `.env` kopieren und anpassen.  
Das Plugin funktioniert auch ohne `.env`-Datei mit sinnvollen Standardwerten.

```ini
# DLR-Gebäudeatlas (öffentlicher Dienst, kein API-Key)
DLR_ZOOM=19                  # Tile-Zoom (17–19 empfohlen)

# PVGIS (EU JRC, kein Key)
PVGIS_SYSTEM_LOSS=14.0       # Systemverluste in %

# Solarmodul-Parameter
PANEL_EFFICIENCY=0.20        # Modulwirkungsgrad (20 %)
PANEL_POWER_PER_SQM=0.175    # kWp pro m²
ROOF_COVERAGE_FLAT=0.65      # Nutzbare Fläche Flachdach
ROOF_COVERAGE_PITCHED=0.55   # Nutzbare Fläche Schrägdach
```

---

## Repository-Struktur

```
solar-sites-qgis/
├── qgis_solar_plugin/       ← QGIS-Plugin (UI-Schicht)
│   ├── solar_dock.py        ← 5-seitiger Wizard (QStackedWidget)
│   ├── worker.py            ← Hintergrund-Analyse-Thread
│   ├── data_sources.py      ← PostGIS + GeoPackage + Overpass
│   ├── layer_builder.py     ← Ergebnisse → QGIS-Vektorlayer
│   └── qgis_db_utils.py     ← QGIS-Auth-Manager-Integration
├── solar_sites/             ← Reine Python-Analysebibliothek (kein QGIS)
│   ├── solar/               ← estimator, DLR, PVGIS, YOLO-Erkennung
│   ├── buildings/           ← Gebäude-Finder, Overpass-Client
│   ├── geocoding/           ← Nominatim-Reverse-Geocoding
│   └── export/              ← Excel-Export
├── tests/                   ← pytest-Tests (kein QGIS/DB erforderlich)
├── data/
│   └── sample.gpkg          ← 20 Beispielgebäude (Kölner Raum, WGS84)
└── scripts/
    ├── build_zip.sh         ← Installierbares Plugin-ZIP bauen
    └── create_sample_gpkg.py← sample.gpkg erzeugen (einmalig)
```

---

## Entwicklung

### Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Tests in `tests/` benötigen kein QGIS und keine Datenbankverbindung.  
QGIS-abhängiger Code wird manuell im Plugin getestet.

### Linter

```bash
ruff check .        # Fehler prüfen
ruff check --fix .  # Auto-Fix
```

### Release erstellen

```bash
# version= in metadata.txt hochsetzen, dann:
git tag v2.0.1
git push origin v2.0.1
# → GitHub Actions baut ZIP und erstellt GitHub Release automatisch
```

---

## Lizenz

[GNU General Public License v3.0](LICENSE)

Dieses Plugin ist freie Software: du kannst es unter den Bedingungen der
GNU General Public License, Version 3 oder höher, weitergeben und/oder
modifizieren.
