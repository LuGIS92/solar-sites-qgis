# CLAUDE.md – Solar Sites QGIS Plugin

Dieses Dokument gibt Claude Code den nötigen Kontext, um sofort produktiv zu
arbeiten. Lies es vollständig bevor du Änderungen vornimmst.

---

## Projektüberblick

QGIS-Plugin für PV-Potenzialanalyse auf Gebäuden.  
Eingabe: Bounding-Box (oder Stadtname) + Filterparameter  
Ausgabe: QGIS-Vektorlayer + Excel-Export + optionaler GeoPackage-Export

**Datenquellen:**
- Gebäude: ALKIS via PostGIS **oder** lokale GeoPackage-Datei
- Solarstrahlung: PVGIS-API (EU JRC) und DLR-Gebäudeatlas (WMTS)
- Bestandsanlagen: Marktstammdatenregister (MaStR) – PostGIS-Tabelle oder lokales GPKG
- Optional: YOLO-Panel-Erkennung auf Satellitenbildern (leafmap)

---

## Repository-Struktur

```
qgis_solar_plugin/          ← QGIS-Plugin-Paket (wird als ZIP installiert)
│   __init__.py             ← classFactory() + sys.path-Bootstrap (dual-mode)
│   metadata.txt            ← Plugin-Metadaten für QGIS Plugin Manager
│   solar_plugin.py         ← Hauptklasse: initGui / unload / run
│   solar_dock.py           ← QDockWidget: 3-Seiten-Wizard (QStackedWidget)
│   worker.py               ← QThread für Hintergrundanalyse
│   data_sources.py         ← PostGISSource + GeoPackageSource
│   layer_builder.py        ← Ergebnisse → QgsVectorLayer + Zoom
│   qgis_db_utils.py        ← QGIS-Verbindungs-DSN lesen + ogr2ogr-Wrapper
│   icon.svg

solar_sites/                ← Business-Logik-Bibliothek (kein QGIS)
│   solar/
│   │   estimator.py        ← estimate(building) → SolarEstimate
│   │   dlr.py              ← DLR WMTS GetFeatureInfo
│   │   pvgis.py            ← PVGIS REST API
│   │   detection.py        ← YOLO-Panel-Erkennung
│   buildings/finder.py     ← Building-Dataclass
│   geocoding/nominatim.py  ← Reverse-Geocoding
│   export/excel.py         ← .xlsx-Export
│   config.py               ← pydantic-settings (liest .env)

data/
│   sample.gpkg             ← 20 synthetische Gebäude, Köln Hbf (Test)

scripts/
│   build_zip.sh            ← Baut dist/solar_sites_pv_analysis_vX.Y.Z.zip
│   create_sample_gpkg.py   ← Erstellt data/sample.gpkg (nur stdlib)

tests/                      ← pytest-Tests (kein QGIS erforderlich)

.github/workflows/
│   ci.yml                  ← ruff + compileall + pytest bei Push/PR
│   release.yml             ← ZIP bauen + GitHub Release bei v*.*.*-Tag
```

---

## Dual-Mode sys.path-Bootstrap (`__init__.py`)

Das Plugin muss in zwei Modi funktionieren:

| Modus | solar_sites liegt … | sys.path-Eintrag |
|---|---|---|
| **ZIP-Install** (QGIS Plugin Manager) | innerhalb `qgis_solar_plugin/solar_sites/` | `qgis_solar_plugin/` selbst |
| **Dev** (Symlink/Checkout) | Repo-Root `../solar_sites/` | ein Verzeichnis hoch |

```python
# __init__.py
_plugin_dir = Path(__file__).resolve().parent
if (_plugin_dir / "solar_sites").is_dir():
    _lib_path = str(_plugin_dir)      # ZIP-Install
else:
    _lib_path = str(_plugin_dir.parent)  # Dev
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)
```

**Nie** hartkodierte absolute Pfade verwenden.

---

## Kritische Bugs & ihre Fixes (damit du sie nicht wieder einführst)

### 1. DLR WMTS gibt leere Features zurück (zoom > 19)

**Problem:** `dlr_zoom=21` übersteigt die Tile-Matrix des DLR-Dienstes.  
**Fix:** Multi-Zoom-Fallback in `dlr.py`:
```python
_ZOOM_FALLBACKS = [19, 18, 17, 16]
# Erst konfigurierten Zoom versuchen, dann Fallbacks, dann pixel-Jitter bei zoom 18
```
**Nie** einen Einzelzoom ohne Fallback verwenden. Zoom-Werte > 19 liefern bei DLR immer leere Feature-Listen.

### 2. DLR-Wert war in MWh, nicht kWh

**Problem:** Das Feld `pveppmwhrp` enthält MWh/Jahr (z.B. `311`).  
**Fix:** Multiplikation mit 1000 in `dlr.py`:
```python
annual_energy_kwh=float(mwh) * 1000,   # MWh → kWh
```

### 3. Karte zoomt nach Nigeria (CRS-Konflikt)

**Problem:** `layer.extent()` ist EPSG:4326, Canvas ist EPSG:3857 → direktes `setExtent()` interpretiert Lat/Lon als Meter.  
**Fix:** In `layer_builder.py` immer transformieren:
```python
xform = QgsCoordinateTransform(
    layer.crs(),
    canvas.mapSettings().destinationCrs(),
    QgsProject.instance(),
)
canvas.setExtent(xform.transformBoundingBox(layer.extent()))
```
Das funktioniert dynamisch für **jede** Canvas-CRS (auch EPSG:25832, EPSG:31468 etc.).

### 4. psycopg2 "argument formats can't be mixed"

**Problem:** SQL wie `AND col LIKE '31001_1%'` zusammen mit `%(param)s`-Platzhaltern.  
**Fix:** Prozentzeichen in Literals verdoppeln: `'31001_1%%'`

### 5. `clear_cache` ImportError

**Problem:** Ältere Deployments haben `dlr.py` ohne `clear_cache()`-Funktion.  
**Fix:** In `worker.py` immer mit try/except importieren:
```python
try:
    from solar_sites.solar.dlr import clear_cache as _dlr_clear
    _dlr_clear()
except ImportError:
    pass
```

### 6. ogr2ogr "Cannot find proj.db"

**Problem:** System-`ogr2ogr` kennt QGIS-Bundled PROJ-Daten nicht.  
**Fix:** In `qgis_db_utils.py` → `_qgis_env()` setzt `PROJ_DATA` und `GDAL_DATA`
aus QGIS-Bundle-Pfaden, bevor der Subprozess gestartet wird.

---

## Security-Regeln (zwingend einhalten)

### DB-Schema-Änderungen NIEMALS automatisch ausführen

Der App-User hat nur SELECT/INSERT/UPDATE auf vorhandene Tabellen.  
**DDL (CREATE TABLE, ALTER TABLE, DROP) muss als SQL-Statement ausgegeben werden,
damit der Admin es manuell ausführen kann.** Niemals `CREATE TABLE IF NOT EXISTS`
o.ä. aus Anwendungscode aufrufen.

### SQL-Injection verhindern

- Spaltennamen kommen durch `_safe()` in `data_sources.py`:
  ```python
  _SAFE_COL = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')
  ```
  Niemals Spaltennamen direkt aus User-Input ohne `_safe()` in SQL einbauen.
- Werte ausschließlich via psycopg2-Parameter (`%(name)s`) übergeben.

### Keine Secrets committen

- `.env` ist in `.gitignore` – niemals committen
- Verbindungs-DSN enthält Passwort → niemals loggen, niemals in Fehlermeldungen ausgeben

---

## Architektur-Entscheidungen

### QThread statt QgsTask

`AnalysisWorker(QThread)` in `worker.py` statt `QgsTask`, weil:
- psycopg2-Verbindungen dürfen nicht zwischen Threads geteilt werden
- PVGIS/DLR-HTTP-Calls blockieren; QThread gibt vollständige Kontrolle

### `_safe()` für Spalten-Mapping

Nutzer können PostGIS-Spaltennamen in der UI konfigurieren (z.B. `mastr_kw`,
`mastr_geom`). Diese Eingaben laufen durch `_safe()` bevor sie in SQL landen.

### Gebäudetyp-Filter

4-stufiges System in `solar_dock.py`:

| Index | Wert | SQL-Effekt |
|---|---|---|
| 0 | Alle | kein Filter |
| 1 | Wohngebäude | `LIKE '31001_1%%'` |
| 2 | Gewerbe/Industrie | `~ '^31001_[23]'` |
| 3 | Eigener Filter | `ILIKE '%<freitext>%'` |

### BBox-Eingabe (Seite 2 des Wizards)

Drei Quellen für die Bounding Box:
1. Manuelle Koordinaten-Eingabe
2. `_bbox_from_canvas()`: aktueller Kartenausschnitt
3. `_bbox_from_layer()`: Extent eines ausgewählten Layers

Beide automatischen Methoden transformieren in EPSG:4326 bevor sie die
Koordinatenfelder befüllen.

---

## Entwicklungs-Workflow

### Plugin in QGIS testen (Dev-Mode)

```bash
# Im QGIS Plugin-Verzeichnis (macOS)
ln -sf /pfad/zum/repo/qgis_solar_plugin \
    ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_solar_plugin
```

QGIS: **Erweiterungen → Erweiterungen verwalten → Installiert → Reload**  
(oder Plugin Reloader installieren für schnelleres Iterieren)

### ZIP für Weitergabe bauen

```bash
bash scripts/build_zip.sh
# → dist/solar_sites_pv_analysis_vX.Y.Z.zip
```

Der ZIP enthält `solar_sites/` eingebettet – keine separate Installation nötig.

### Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest tests/
```

Tests in `tests/` dürfen kein `qgis.core` importieren (CI hat kein QGIS).
QGIS-abhängiger Code gehört in `qgis_solar_plugin/`.

### Linter

```bash
ruff check .      # Fehler prüfen
ruff check --fix . # Auto-Fix
```

Konfiguration in `ruff.toml`: Python 3.9 (QGIS-Standard), line-length 100.

### Release erstellen

```bash
# metadata.txt version= hochsetzen, dann:
git tag v1.0.1
git push origin v1.0.1
# → GitHub Actions baut ZIP + erstellt Release automatisch
```

---

## Bekannte Einschränkungen

- **pydantic-settings** ist in QGIS-Python nicht vorinstalliert.  
  Installationshinweis in README für Nutzer, falls `config.py` ImportError wirft.

- **psycopg2** muss in QGIS-Python vorhanden sein (`python-qgis -m pip install psycopg2-binary`).

- **leafmap** für YOLO-Panel-Erkennung ist optional; fehlt es, deaktiviert `worker.py`
  die Funktion mit einem Hinweistext.

- **DLR-Atlas** deckt nur Deutschland ab. Bei anderen Koordinaten ist Fallback PVGIS aktiv.

---

## Konfiguration (`.env`)

Alle Einstellungen werden aus `.env` im Repo-Root geladen (via `solar_sites/config.py`).  
Im Plugin-Kontext muss der Pfad explizit gesetzt werden (passiert in `__init__.py`).  
Vorlage: `.env.example`

Wichtige Variablen:

| Variable | Bedeutung |
|---|---|
| `DLR_WMTS_URL` | DLR Gebäudeatlas WMTS-Endpoint |
| `DLR_LAYER` | Layer-Name (Standard: `SDE_BUILDINGS`) |
| `DLR_ZOOM` | Startzoom (19 empfohlen; > 19 hat keinen Effekt) |
| `PVGIS_BASE_URL` | PVGIS-API-URL |
| `NOMINATIM_URL` | Nominatim-Instanz (Standard: OSM public) |

---

## Datei-Checkliste vor erstem Push

- [ ] `metadata.txt`: `tracker`, `repository`, `homepage` zeigen auf dieses Repo
- [ ] `.env` ist **nicht** committed (steht in `.gitignore`)
- [ ] `data/sample.gpkg` ist committed (synthetische Daten, keine echten)
- [ ] `dist/` ist **nicht** committed (steht in `.gitignore`)
