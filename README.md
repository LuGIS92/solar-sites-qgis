# Solar Sites – PV-Potenzialanalyse für QGIS

[![CI](https://github.com/LuGIS92/solar-sites-qgis/actions/workflows/ci.yml/badge.svg)](https://github.com/LuGIS92/solar-sites-qgis/actions/workflows/ci.yml)
[![Lizenz: GPL v3](https://img.shields.io/badge/Lizenz-GPL%20v3-blue.svg)](LICENSE)

Dieses Plugin ist aus einer praktischen Notwendigkeit entstanden: Hunderte von Gebäuden
auf Solarpotenzial zu prüfen, ohne jedes einzeln manuell in PVGIS oder den DLR-Atlas
einzugeben. Es lädt Gebäudegrundrisse, fragt Strahlungsdaten ab, gleicht mit dem
Marktstammdatenregister ab – und gibt am Ende einen farbcodierten Layer und eine
Excel-Tabelle aus.

Entwickelt für Deutschland (ALKIS, DLR-Atlas, MaStR), aber der OSM-Modus funktioniert
weltweit.

**Status:** aktiv in Nutzung, kein poliertes Endprodukt. Feedback und PRs willkommen.

---

## Was das Plugin macht

Du gibst eine Bounding-Box oder einen Stadtnamen an. Das Plugin:

1. Lädt Gebäude aus PostGIS (ALKIS), einer GeoPackage-Datei oder OpenStreetMap
2. Fragt für jedes Gebäude Strahlungsdaten ab – zuerst den DLR-Gebäudeatlas, falls
   der nichts liefert PVGIS als Fallback
3. Prüft optional, ob bereits eine PV-Anlage im Marktstammdatenregister eingetragen ist
4. Erstellt einen Punkt-Layer in QGIS mit Farbverlauf (rot = wenig, grün = viel Potenzial)
5. Exportiert die Ergebnisse als Excel-Datei und optional als GeoPackage

Die Analyse läuft im Hintergrund – QGIS bleibt während der ganzen Zeit bedienbar.

---

## Voraussetzungen

- QGIS 3.16 oder neuer
- Python 3.9+ (kommt mit QGIS)

Je nach Modus brauchst du noch ein paar Python-Pakete. Am einfachsten über die
QGIS Python-Konsole installieren:

```python
import pip

# Immer nötig (Excel-Export):
pip.main(['install', 'pandas', 'openpyxl', 'pydantic-settings'])

# Nur für PostGIS-Modus:
pip.main(['install', 'psycopg2-binary'])

# Optional – YOLO-Panel-Erkennung auf Satellitenbildern:
pip.main(['install', 'leafmap', 'ultralytics'])
```

Der OSM/Overpass-Modus braucht nichts Zusätzliches, das läuft mit der Python-Standardbibliothek.

---

## Installation

Es gibt noch keinen offiziellen Release-ZIP. Du hast zwei Optionen:

### Als Entwickler (empfohlen fürs Ausprobieren)

```bash
git clone https://github.com/LuGIS92/solar-sites-qgis.git
cd solar-sites-qgis

# Symlink setzen – einmalig, bleibt dauerhaft erhalten:
# macOS:
ln -sfn "$(pwd)/qgis_solar_plugin" \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_solar_plugin

# Linux:
ln -sfn "$(pwd)/qgis_solar_plugin" \
  ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/qgis_solar_plugin
```

Nach Code-Änderungen reicht der [Plugin Reloader](https://plugins.qgis.org/plugins/plugin_reloader/)
in QGIS – kein Neustart nötig. Ausnahme: Änderungen in `solar_sites/` brauchen einen
QGIS-Neustart wegen des Python-Modul-Caches.

### Als ZIP

```bash
bash scripts/build_zip.sh
# → dist/solar_sites_pv_analysis_v2.0.0.zip
```

Dann in QGIS: **Erweiterungen → Erweiterungen verwalten → Aus ZIP installieren**.

---

## Schnellstart

Für einen ersten Test liegt in `data/sample.gpkg` ein kleines GeoPackage mit
20 synthetischen Gebäuden im Kölner Raum.

1. QGIS öffnen, irgendeine Hintergrundkarte laden
2. Solar Sites Panel öffnen (Toolbar oder **Erweiterungen → Solar Sites**)
3. **Seite 1:** GeoPackage wählen → `data/sample.gpkg`, Layer `buildings`
4. **Seite 2:** „Spalten laden" klicken, dann Weiter (funktioniert automatisch)
5. **Seite 3:** „Aktuelle Kartenansicht übernehmen" oder eine Stadt eingeben
6. **Seite 4:** Standardwerte lassen → **Analyse starten**

Ein paar Sekunden später erscheint ein Punkt-Layer auf der Karte.

### Ohne eigene Gebäudedaten – OSM-Modus

Wenn du keine PostGIS-Datenbank oder kein eigenes GeoPackage hast, nimm einfach
OpenStreetMap als Datenquelle. Auf **Seite 1** „OpenStreetMap (Overpass)" wählen –
die Spalten-Seite wird übersprungen, der Rest bleibt gleich.

Für größere Städte empfiehlt sich ein Gebäude-Limit von 100–200 beim ersten Test,
sonst kann die Overpass-Abfrage ein paar Minuten dauern.

---

## Datenquellen

### PostGIS / ALKIS

Standard für Deutschland, wenn eine aufbereitete Datenbank vorhanden ist. Das Plugin
erwartet eine PostgreSQL-Verbindung, die bereits in QGIS eingerichtet ist.

Standardmäßige Tabellennamen: `deutschland.gebaeude_deutschland_tbl` für Gebäude,
`deutschland.mastr_solar` für MaStR-Daten. Beides konfigurierbar, abweichende
Spaltennamen lassen sich auf Seite 2 mappen.

### GeoPackage

Funktioniert mit jeder Polygon-Datei. Das Plugin versucht gängige Spaltennamen
automatisch zu erkennen. MaStR-Daten können als zweite GeoPackage-Datei dazugeladen
werden – am einfachsten erstellt via [open-mastr](https://open-mastr.readthedocs.io/en/latest/advanced/).

### OpenStreetMap (Overpass-API)

Kein lokaler Datensatz nötig, funktioniert weltweit. Der Gebäudetyp-Filter
arbeitet mit OSM-Tags (`house`, `industrial`, `warehouse`, …) statt ALKIS-Codes.
Standard-Endpunkt ist `overpass-api.de`, lässt sich in der UI auf eine eigene
Instanz umstellen.

---

## Was rauskommt

Der Ergebnis-Layer enthält pro Gebäude:

| Feld | Bedeutung |
|---|---|
| `annual_energy_kwh` | Geschätzter Jahresertrag in kWh |
| `installable_kwp` | Installierbare Leistung in kWp |
| `usable_area_sqm` | Nutzbare Dachfläche in m² |
| `pvgis_irradiation` | Globalstrahlung laut PVGIS (kWh/kWp/Jahr) |
| `dlr_annual_kwh` | Rohwert aus dem DLR-Atlas (falls verfügbar) |
| `data_source` | `dlr` oder `pvgis` – welche Quelle genutzt wurde |
| `mastr_registered` | 1 wenn im MaStR gefunden, sonst 0 |
| `mastr_capacity_kw` | Registrierte Leistung in der Nähe (kW) |
| `panels_detected` | 1 wenn YOLO Panels erkannt hat |
| `building_type` | ALKIS-Code oder OSM-Tag |
| `area_sqm` | Grundfläche des Gebäudes |

Dazu gibt es einen Excel-Export mit denselben Feldern plus Adressdaten (falls Nominatim-Geocoding aktiviert).

---

## Gebäudetyp-Filter

Der Filter auf Seite 4 macht je nach Datenquelle etwas Unterschiedliches:

- **Leer:** alle Gebäude
- **Wohngebäude:** ALKIS `31001_1xxx` bzw. OSM `house`, `apartments`, `detached`, …
- **Gewerbe/Industrie:** ALKIS `31001_2/3xxx` bzw. OSM `industrial`, `warehouse`, `commercial`, …
- **Eigener Filter:** Freitext, funktioniert mit beiden Quellen (Groß-/Kleinschreibung egal)

---

## Konfiguration

Das Plugin läuft auch ohne `.env`-Datei mit sinnvollen Standardwerten. Wer etwas
anpassen will: `.env.example` nach `.env` kopieren und bearbeiten.

Die wichtigsten Stellschrauben:

```ini
DLR_ZOOM=19              # Tile-Zoom für den DLR-Atlas (17–19, höher bringt nichts)
PVGIS_SYSTEM_LOSS=14.0   # Systemverluste in %
PANEL_POWER_PER_SQM=0.175  # kWp pro m² Modulfläche
ROOF_COVERAGE_FLAT=0.65    # Anteil nutzbarer Fläche bei Flachdächern
ROOF_COVERAGE_PITCHED=0.55 # Anteil nutzbarer Fläche bei Schrägdächern
```

---

## Bekannte Einschränkungen

- Der DLR-Atlas deckt nur Deutschland ab. Außerhalb springt das Plugin automatisch auf PVGIS um.
- Der OSM-Modus hat keine MaStR-Anbindung.
- `pydantic-settings` und `psycopg2` sind in QGIS-Python nicht vorinstalliert und müssen einmalig nachinstalliert werden.
- YOLO-Panel-Erkennung ist experimentell und braucht `leafmap` + `ultralytics` in QGIS-Python.

---

## Entwicklung

```bash
pip install -r requirements-dev.txt
pytest tests/          # Tests laufen ohne QGIS und ohne DB
ruff check .           # Linter
```

Für einen neuen Release: `version=` in `metadata.txt` hochsetzen, dann Tag pushen –
GitHub Actions baut den ZIP und veröffentlicht automatisch einen Release.

---

## Lizenz

[GPL v3](LICENSE) – freie Software, Weitergabe und Modifikation erwünscht.
