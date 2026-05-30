"""Haupt-UI des Plugins – Schritt-für-Schritt-Assistent (QStackedWidget)."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# ── Tooltips ──────────────────────────────────────────────────────────────────

_TIP_PG_TABLE = (
    "ALKIS-Gebäudetabelle (PostGIS, SRID 3035).\n"
    "Benötigte Spalten:\n"
    "  gml_id          – eindeutige Gebäude-ID\n"
    "  geom            – Polygon-Geometrie (SRID 3035)\n"
    "  area            – Dachfläche m² (optional, sonst ST_Area)\n"
    "  roof_type       – Dachform (optional)\n"
    "  gebaeudefunktion – ALKIS-Nutzungscode, z.B. '31001_1000'"
)
_TIP_MASTR_TABLE = (
    "MaStR-Tabelle (PostGIS, SRID 3035 oder 4326).\n"
    "Standard-Spalten:\n"
    "  geom          – Punkt-Geometrie\n"
    "  bruttoleistung – Leistung in kW als TEXT\n\n"
    "Abweichende Spaltennamen → Seite 2 'Spalten-Zuordnung'.\n"
    "Leer lassen → MaStR deaktiviert."
)
_TIP_GPKG_LAYER = (
    "Layer-Name in der GeoPackage-Datei.\n"
    "Erkannte Spaltenbezeichnungen (automatisch):\n"
    "  Gebäude-ID:   gml_id | fid | id | ogc_fid\n"
    "  Gebäudetyp:   gebaeudefunktion | building_type | type | nutzung\n"
    "  Dachform:     roof_type | dachform | dachtyp\n\n"
    "MaStR-Abfragen: optionale zweite GeoPackage-Datei (Seite 1)."
)
_TIP_MIN_AREA = (
    "Nur Gebäude mit mindestens dieser Dachfläche analysieren.\n"
    "Empfehlung:\n"
    "  300 m²  – typische Gewerbegebäude\n"
    " 1000 m²  – große Industriehallen\n"
    "  100 m²  – alle Wohngebäude"
)
_TIP_LIMIT = (
    "Maximale Anzahl zu analysierender Gebäude (nach Fläche sortiert).\n"
    "0 = alle Gebäude in der BBox (kann sehr lange dauern!)"
)
_TIP_GEOCODE = (
    "Für jedes Gebäude die Postanschrift via Nominatim nachschlagen.\n"
    "Ca. 1 Sekunde pro Gebäude (Rate-Limit OSM).\n"
    "Füllt Adress-Spalten in der Excel-Tabelle."
)


class SolarDockWidget(QDockWidget):

    _STEP_LABELS = ["Datenquelle", "Spalten", "Suchgebiet", "Filter"]
    _LAST_SETUP_PAGE = 3   # letzter Konfigurations-Schritt (0-basiert)
    _ANALYSE_PAGE    = 4   # Ergebnisse-Seite

    def __init__(self, iface, parent=None) -> None:
        super().__init__("Solar Sites PV-Analyse", parent)
        self.iface = iface
        self.worker = None
        self._analyses: list[dict] = []
        self._job_id: str = ""
        self._result_layer = None
        self._current_page = 0

        self._build_ui()
        self.setMinimumWidth(360)
        self.setObjectName("SolarSitesDock")

    # =========================================================================
    # UI-Aufbau
    # =========================================================================

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Schritt-Indikator
        self._step_bar = self._build_step_bar()
        outer.addWidget(self._step_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        outer.addWidget(sep)

        # Haupt-Stack (5 Seiten)
        self._pages = QStackedWidget()
        scroll = QScrollArea()
        scroll.setWidget(self._pages)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll, 1)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        outer.addWidget(sep2)

        # Navigationsleiste
        nav = self._build_nav_bar()
        outer.addWidget(nav)

        # Seiten befüllen
        for builder in [
            self._build_page_datasource,
            self._build_page_columns,
            self._build_page_area,
            self._build_page_filter,
            self._build_page_results,
        ]:
            w = QWidget()
            vbox = QVBoxLayout(w)
            vbox.setContentsMargins(8, 8, 8, 8)
            vbox.setSpacing(6)
            builder(vbox)
            vbox.addStretch()
            self._pages.addWidget(w)

        self._update_nav()

        scroll_root = QScrollArea()
        scroll_root.setWidget(root)
        scroll_root.setWidgetResizable(True)
        scroll_root.setFrameShape(QFrame.NoFrame)
        self.setWidget(root)

    def _build_step_bar(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(38)
        w.setStyleSheet("background:#f5f5f5;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(8, 4, 8, 4)
        self._step_labels: list[QLabel] = []
        for i, name in enumerate(self._STEP_LABELS):
            if i:
                sep = QLabel("›")
                sep.setStyleSheet("color:#aaa; margin:0 2px;")
                layout.addWidget(sep)
            lbl = QLabel(f"{i+1}. {name}")
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)
            self._step_labels.append(lbl)
        layout.addStretch()
        return w

    def _update_step_bar(self) -> None:
        page = self._current_page
        for i, lbl in enumerate(self._step_labels):
            if i < page:
                lbl.setStyleSheet("color:#27ae60; font-weight:bold;")
            elif i == page:
                lbl.setStyleSheet(
                    "color:white; background:#2980b9; border-radius:3px;"
                    "padding:1px 4px; font-weight:bold;"
                )
            else:
                lbl.setStyleSheet("color:#aaa;")

    def _build_nav_bar(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(8, 6, 8, 6)

        self._back_btn = QPushButton("← Zurück")
        self._back_btn.clicked.connect(self._prev_page)
        row.addWidget(self._back_btn)

        row.addStretch()

        self._page_lbl = QLabel("")
        self._page_lbl.setStyleSheet("color:#666;")
        row.addWidget(self._page_lbl)

        row.addStretch()

        self._next_btn = QPushButton("Weiter →")
        self._next_btn.setDefault(True)
        self._next_btn.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;font-weight:bold;"
            "padding:5px 14px;border-radius:3px;}"
            "QPushButton:disabled{background:#95a5a6;}"
        )
        self._next_btn.clicked.connect(self._next_page)
        row.addWidget(self._next_btn)
        return w

    def _update_nav(self) -> None:
        p = self._current_page
        is_analyse = p == self._ANALYSE_PAGE
        self._back_btn.setVisible(not is_analyse)
        self._back_btn.setEnabled(p > 0)

        if is_analyse:
            self._next_btn.setVisible(False)
            self._page_lbl.setText("")
        elif p == self._LAST_SETUP_PAGE:
            self._next_btn.setVisible(True)
            self._next_btn.setText("▶  Analyse starten")
            self._next_btn.setStyleSheet(
                "QPushButton{background:#27ae60;color:white;font-weight:bold;"
                "padding:5px 14px;border-radius:3px;}"
            )
            self._page_lbl.setText(f"{p+1} / {len(self._STEP_LABELS)}")
        else:
            self._next_btn.setVisible(True)
            self._next_btn.setText("Weiter →")
            self._next_btn.setStyleSheet(
                "QPushButton{background:#2980b9;color:white;font-weight:bold;"
                "padding:5px 14px;border-radius:3px;}"
                "QPushButton:disabled{background:#95a5a6;}"
            )
            self._page_lbl.setText(f"{p+1} / {len(self._STEP_LABELS)}")

        self._update_step_bar()

    # =========================================================================
    # Seiten
    # =========================================================================

    def _build_page_datasource(self, layout: QVBoxLayout) -> None:
        """Seite 0 – Datenquelle."""
        layout.addWidget(QLabel("<b>Datenquelle wählen</b>"))

        mode_row = QHBoxLayout()
        self._ds_postgis = QRadioButton("QGIS PostgreSQL-Verbindung")
        self._ds_gpkg    = QRadioButton("GeoPackage-Datei (.gpkg)")
        self._ds_osm     = QRadioButton("OpenStreetMap (Overpass)")
        self._ds_postgis.setChecked(True)
        mode_row.addWidget(self._ds_postgis)
        mode_row.addWidget(self._ds_gpkg)
        mode_row.addWidget(self._ds_osm)
        layout.addLayout(mode_row)

        self._ds_stack = QStackedWidget()

        # ── PostGIS ──────────────────────────────────────────────────────────
        pg = QWidget()
        pgl = QVBoxLayout(pg)
        pgl.setContentsMargins(0, 4, 0, 0)

        conn_row = QHBoxLayout()
        conn_row.addWidget(QLabel("Verbindung:"))
        self._pg_conn = QComboBox()
        self._pg_conn.setToolTip(
            "In QGIS gespeicherte PostgreSQL-Verbindung\n"
            "(Einstellungen → Datenquellen verwalten → PostgreSQL)."
        )
        self._refresh_connections()
        conn_row.addWidget(self._pg_conn)
        ref_btn = QPushButton("↻")
        ref_btn.setFixedWidth(26)
        ref_btn.setToolTip("Liste aktualisieren")
        ref_btn.clicked.connect(self._refresh_connections)
        conn_row.addWidget(ref_btn)
        pgl.addLayout(conn_row)

        def _pg_row(label, attr, default, tip):
            r = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setToolTip(tip)
            r.addWidget(lbl)
            le = QLineEdit(default)
            le.setToolTip(tip)
            setattr(self, attr, le)
            r.addWidget(le)
            pgl.addLayout(r)

        _pg_row("Gebäude-Tabelle:", "_pg_table",
                "deutschland.gebaeude_deutschland_tbl", _TIP_PG_TABLE)
        _pg_row("MaStR-Tabelle:",   "_pg_mastr",
                "deutschland.mastr_solar",              _TIP_MASTR_TABLE)
        self._ds_stack.addWidget(pg)

        # ── GeoPackage ───────────────────────────────────────────────────────
        gp = QWidget()
        gpl = QVBoxLayout(gp)
        gpl.setContentsMargins(0, 4, 0, 0)

        def _file_row(label, attr_path, placeholder, browse_slot):
            r = QHBoxLayout()
            le = QLineEdit()
            le.setPlaceholderText(placeholder)
            setattr(self, attr_path, le)
            r.addWidget(le)
            btn = QPushButton("…")
            btn.setFixedWidth(26)
            btn.clicked.connect(browse_slot)
            r.addWidget(btn)
            outer_r = QVBoxLayout()
            outer_r.addWidget(QLabel(label))
            outer_r.addLayout(r)
            gpl.addLayout(outer_r)

        _file_row("Gebäude-GeoPackage:", "_gpkg_path",
                  "Pfad zur .gpkg-Datei …",
                  lambda: self._browse_file(self._gpkg_path, "Gebäude-GeoPackage"))

        lyr_r = QHBoxLayout()
        lyr_r.addWidget(QLabel("Layer-Name:"))
        self._gpkg_layer = QLineEdit("buildings")
        self._gpkg_layer.setToolTip(_TIP_GPKG_LAYER)
        lyr_r.addWidget(self._gpkg_layer)
        gpl.addLayout(lyr_r)

        _file_row("MaStR-GeoPackage (optional):", "_gpkg_mastr_path",
                  "Pfad zur MaStR .gpkg (optional) …",
                  lambda: self._browse_file(self._gpkg_mastr_path, "MaStR-GeoPackage"))

        mastr_lyr_r = QHBoxLayout()
        mastr_lyr_r.addWidget(QLabel("MaStR-Layer:"))
        self._gpkg_mastr_layer = QLineEdit("mastr_solar")
        mastr_lyr_r.addWidget(self._gpkg_mastr_layer)
        gpl.addLayout(mastr_lyr_r)

        note = QLabel(
            "ℹ MaStR-GeoPackage aus BNetzA-CSV erstellen:\n"
            "  QGIS → Layer → Delimited Text → CSV → Als GeoPackage speichern\n"
            "  Benötigte Spalten: geom (Punkt WGS84), bruttoleistung (TEXT kW)\n\n"
            "💡 Tipp: open-mastr-Package lädt MaStR-Daten direkt herunter\n"
            "  und kann als GeoPackage exportieren:\n"
            "  pip install open-mastr\n"
            "  Doku: open-mastr.readthedocs.io/en/latest/advanced/"
        )
        note.setStyleSheet("color:#555; font-size:10px;")
        note.setWordWrap(True)
        gpl.addWidget(note)

        self._ds_stack.addWidget(gp)

        # ── OpenStreetMap / Overpass ──────────────────────────────────────────
        osm = QWidget()
        osml = QVBoxLayout(osm)
        osml.setContentsMargins(0, 4, 0, 0)

        osm_info = QLabel(
            "Gebäude werden live aus OpenStreetMap via Overpass-API geladen.\n"
            "Keine lokalen Daten erforderlich – funktioniert weltweit.\n\n"
            "⚠ Für große Gebiete (> 5 km²) kann die Abfrage mehrere Minuten\n"
            "  dauern. Bitte Gebäude-Limit auf Seite 4 setzen."
        )
        osm_info.setWordWrap(True)
        osm_info.setStyleSheet("color:#555; font-size:10px;")
        osml.addWidget(osm_info)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Overpass-URL:"))
        self._osm_url = QLineEdit("https://overpass-api.de/api/interpreter")
        self._osm_url.setToolTip(
            "Overpass-API-Endpunkt.\n"
            "Alternative Instanzen: overpass.kumi.systems, z.overpass.de"
        )
        url_row.addWidget(self._osm_url)
        osml.addLayout(url_row)

        timeout_row = QHBoxLayout()
        timeout_row.addWidget(QLabel("Timeout (s):"))
        self._osm_timeout = QSpinBox()
        self._osm_timeout.setRange(10, 300)
        self._osm_timeout.setValue(60)
        self._osm_timeout.setToolTip("Maximale Wartezeit für die Overpass-Abfrage.")
        timeout_row.addWidget(self._osm_timeout)
        timeout_row.addStretch()
        osml.addLayout(timeout_row)

        self._ds_stack.addWidget(osm)

        layout.addWidget(self._ds_stack)

        def _update_stack() -> None:
            if self._ds_postgis.isChecked():
                self._ds_stack.setCurrentIndex(0)
            elif self._ds_gpkg.isChecked():
                self._ds_stack.setCurrentIndex(1)
            else:
                self._ds_stack.setCurrentIndex(2)

        self._ds_postgis.toggled.connect(lambda _: _update_stack())
        self._ds_gpkg.toggled.connect(lambda _: _update_stack())
        self._ds_osm.toggled.connect(lambda _: _update_stack())

    def _build_page_columns(self, layout: QVBoxLayout) -> None:
        """Seite 1 – Spalten-Zuordnung."""
        layout.addWidget(QLabel("<b>Spalten-Zuordnung</b>"))
        layout.addWidget(QLabel(
            "Spalten automatisch erkennen oder manuell zuordnen.\n"
            "Felder leer lassen = automatische Erkennung."
        ))

        load_btn = QPushButton("↻  Spalten aus gewählter Quelle laden")
        load_btn.clicked.connect(self._load_columns_into_mapping)
        layout.addWidget(load_btn)

        self._map_inputs: dict[str, QComboBox] = {}
        defs = [
            ("id",            "Gebäude-ID",   "Standard PostGIS: gml_id"),
            ("geom",          "Geometrie",    "Standard PostGIS: geom"),
            ("area",          "Fläche (m²)",  "Standard: area / ST_Area"),
            ("building_type", "Gebäudetyp",   "Standard PostGIS: gebaeudefunktion"),
            ("roof_type",     "Dachform",     "Standard: roof_type"),
        ]
        for key, label, tip in defs:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(110)
            lbl.setToolTip(tip)
            row.addWidget(lbl)
            cb = QComboBox()
            cb.setEditable(True)
            cb.setToolTip(tip)
            cb.addItem("-- automatisch --")
            row.addWidget(cb)
            layout.addLayout(row)
            self._map_inputs[key] = cb

        # MaStR-spezifische Spalten
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)
        layout.addWidget(QLabel("<b>MaStR-Tabelle / -Layer</b> (optional)"))

        mastr_defs = [
            ("mastr_kw",   "Leistungs-Spalte", "Standard PostGIS: bruttoleistung"),
            ("mastr_geom", "Geometrie-Spalte",  "Standard PostGIS: geom"),
        ]
        for key, label, tip in mastr_defs:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(130)
            lbl.setToolTip(tip)
            row.addWidget(lbl)
            cb = QComboBox()
            cb.setEditable(True)
            cb.setToolTip(tip)
            cb.addItem("-- automatisch --")
            row.addWidget(cb)
            layout.addLayout(row)
            self._map_inputs[key] = cb

        skip_btn = QPushButton("Automatik verwenden (überspringen)")
        skip_btn.setStyleSheet("color:#666;")
        skip_btn.clicked.connect(self._skip_column_page)
        layout.addWidget(skip_btn)

    def _build_page_area(self, layout: QVBoxLayout) -> None:
        """Seite 2 – Suchgebiet."""
        layout.addWidget(QLabel("<b>Suchgebiet festlegen</b>"))

        mode_row = QHBoxLayout()
        self._srch_city = QRadioButton("Stadt / PLZ / Adresse")
        self._srch_bbox = QRadioButton("Bounding-Box (Koordinaten)")
        self._srch_city.setChecked(True)
        mode_row.addWidget(self._srch_city)
        mode_row.addWidget(self._srch_bbox)
        layout.addLayout(mode_row)

        self._srch_stack = QStackedWidget()

        # Stadt
        city_w = QWidget()
        city_l = QVBoxLayout(city_w)
        city_l.setContentsMargins(0, 4, 0, 0)
        for label, attr, ph in [
            ("Stadt / Adresse:", "_city", "z.B. Köln, München Schwabing"),
            ("PLZ (optional):", "_plz",  "z.B. 50667"),
        ]:
            r = QHBoxLayout()
            r.addWidget(QLabel(label))
            le = QLineEdit()
            le.setPlaceholderText(ph)
            setattr(self, attr, le)
            r.addWidget(le)
            city_l.addLayout(r)
        city_l.addWidget(QLabel(
            "ℹ Die BBox wird automatisch aus OpenStreetMap ermittelt."
        ))
        self._srch_stack.addWidget(city_w)

        # BBox
        bbox_w = QWidget()
        bbox_l = QVBoxLayout(bbox_w)
        bbox_l.setContentsMargins(0, 4, 0, 0)
        for label, attr, default, lo, hi in [
            ("Min Lat:", "_min_lat", 50.0, -90,  90),
            ("Min Lon:", "_min_lon",  7.0,-180, 180),
            ("Max Lat:", "_max_lat", 51.0, -90,  90),
            ("Max Lon:", "_max_lon",  8.0,-180, 180),
        ]:
            r = QHBoxLayout()
            r.addWidget(QLabel(label))
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setDecimals(5)
            sb.setValue(default)
            setattr(self, attr, sb)
            r.addWidget(sb)
            bbox_l.addLayout(r)
        self._srch_stack.addWidget(bbox_w)

        layout.addWidget(self._srch_stack)
        self._srch_city.toggled.connect(
            lambda on: self._srch_stack.setCurrentIndex(0 if on else 1)
        )

        # ── Schnellauswahl ────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)
        layout.addWidget(QLabel("Schnellauswahl:"))

        canvas_btn = QPushButton("🗺  Aktuelle Kartenansicht übernehmen")
        canvas_btn.setToolTip(
            "Übernimmt den aktuellen QGIS-Kartenausschnitt als Suchgebiet\n"
            "und wechselt automatisch in den Bounding-Box-Modus."
        )
        canvas_btn.clicked.connect(self._bbox_from_canvas)
        layout.addWidget(canvas_btn)

        layer_row = QHBoxLayout()
        self._layer_combo = QComboBox()
        self._layer_combo.setToolTip("Geladenen Layer als Extent-Quelle wählen")
        layer_row.addWidget(self._layer_combo)
        ref_lyr = QPushButton("↻")
        ref_lyr.setFixedWidth(26)
        ref_lyr.setToolTip("Layer-Liste aktualisieren")
        ref_lyr.clicked.connect(self._refresh_layers)
        layer_row.addWidget(ref_lyr)
        ext_btn = QPushButton("Extent übernehmen →")
        ext_btn.setToolTip("Extent des gewählten Layers als Suchgebiet setzen")
        ext_btn.clicked.connect(self._bbox_from_layer)
        layer_row.addWidget(ext_btn)
        layout.addLayout(layer_row)
        self._refresh_layers()

    def _build_page_filter(self, layout: QVBoxLayout) -> None:
        """Seite 3 – Filter & Optionen."""
        layout.addWidget(QLabel("<b>Filter & Optionen</b>"))

        for label, attr, lo, hi, val, step, tip in [
            ("Min. Dachfläche (m²):", "_min_area", 50,  10000, 300,  50,  _TIP_MIN_AREA),
            ("Max. Gebäude:",         "_limit",      0,   5000, 100,  50,  _TIP_LIMIT),
        ]:
            r = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setToolTip(tip)
            r.addWidget(lbl)
            sb = QSpinBox()
            sb.setRange(lo, hi)
            sb.setValue(val)
            sb.setSingleStep(step)
            sb.setToolTip(tip)
            if attr == "_limit":
                sb.setSpecialValueText("unbegrenzt")
            setattr(self, attr, sb)
            r.addWidget(sb)
            layout.addLayout(r)

        # ── Gebäudetyp-Filter ────────────────────────────────────────────────
        layout.addWidget(QLabel("Gebäudetyp:"))

        self._building_use = QComboBox()
        self._building_use.addItems([
            "Alle Gebäude",
            "Wohngebäude  (ALKIS 31001_1…)",
            "Gewerbe / Industrie  (ALKIS 31001_2… / 31001_3…)",
            "Eigener Filter …",
        ])
        self._building_use.setToolTip(
            "Vorauswahl für ALKIS-Gebäudedaten (PostGIS/GeoPackage aus ALKIS).\n"
            "'Eigener Filter' → Text wird im Gebäudetyp-Feld gesucht (enthält).\n\n"
            "Beispiele für eigenen Filter:\n"
            "  31001_1       – alle ALKIS-Wohngebäude\n"
            "  31001_2620    – nur Lagerhallen (ALKIS)\n"
            "  industrial    – OSM-Gebäude mit building=industrial\n"
            "  Lager         – freie Textsuche im Typ-Feld"
        )
        layout.addWidget(self._building_use)

        self._custom_type_row = QHBoxLayout()
        custom_lbl = QLabel("Filter-Text:")
        custom_lbl.setFixedWidth(80)
        self._custom_type_row.addWidget(custom_lbl)
        self._custom_type_filter = QLineEdit()
        self._custom_type_filter.setPlaceholderText(
            "z.B. 31001_2620  oder  industrial  oder  Lager"
        )
        self._custom_type_filter.setToolTip(
            "Freitext – Gebäude werden eingeschlossen wenn ihr Typ-Feld\n"
            "diesen Text enthält (Groß-/Kleinschreibung egal)."
        )
        self._custom_type_row.addWidget(self._custom_type_filter)
        custom_widget = QWidget()
        custom_widget.setLayout(self._custom_type_row)
        custom_widget.setVisible(False)
        self._custom_type_widget = custom_widget
        layout.addWidget(custom_widget)

        self._building_use.currentIndexChanged.connect(
            lambda i: self._custom_type_widget.setVisible(i == 3)
        )

        self._skip_mastr = QCheckBox("MaStR-Abfrage überspringen")
        self._skip_mastr.setToolTip("Deaktiviert die Abfrage im Marktstammdatenregister.")
        layout.addWidget(self._skip_mastr)

        self._geocode = QCheckBox("Adressen via Nominatim nachschlagen (~1 s/Gebäude)")
        self._geocode.setToolTip(_TIP_GEOCODE)
        layout.addWidget(self._geocode)

        layout.addWidget(QLabel(
            "ℹ Klicke 'Analyse starten' um den Workflow\n"
            "  für alle gefundenen Gebäude auszuführen.\n"
            "  Das Ergebnis erscheint als neuer QGIS-Layer."
        ))

    def _build_page_results(self, layout: QVBoxLayout) -> None:
        """Seite 4 – Analyse & Ergebnisse."""
        layout.addWidget(QLabel("<b>Analyse läuft …</b>"))

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(1000)
        self._log.setMinimumHeight(220)
        mono = QFont("Courier")
        mono.setPointSize(9)
        self._log.setFont(mono)
        layout.addWidget(self._log)

        btn_row = QHBoxLayout()
        self._excel_btn = QPushButton("⬇  Excel-Export")
        self._excel_btn.setEnabled(False)
        self._excel_btn.clicked.connect(self._export_excel)
        self._gpkg_btn = QPushButton("⬇  GeoPackage")
        self._gpkg_btn.setEnabled(False)
        self._gpkg_btn.clicked.connect(self._export_gpkg)
        btn_row.addWidget(self._excel_btn)
        btn_row.addWidget(self._gpkg_btn)
        layout.addLayout(btn_row)

        new_btn = QPushButton("← Neue Suche")
        new_btn.clicked.connect(self._reset_to_start)
        layout.addWidget(new_btn)

    # =========================================================================
    # Navigation
    # =========================================================================

    def _next_page(self) -> None:
        if not self._validate_page(self._current_page):
            return
        if self._current_page == self._LAST_SETUP_PAGE:
            self._start_analysis()
        elif self._current_page == 0 and self._ds_osm.isChecked():
            self._go_to(2)  # Spalten-Zuordnung für OSM irrelevant
        else:
            self._go_to(self._current_page + 1)

    def _prev_page(self) -> None:
        if self._current_page == 2 and self._ds_osm.isChecked():
            self._go_to(0)  # Spalten-Seite rückwärts überspringen
        else:
            self._go_to(self._current_page - 1)

    def _go_to(self, page: int) -> None:
        self._current_page = page
        self._pages.setCurrentIndex(page)
        self._update_nav()

    def _skip_column_page(self) -> None:
        for cb in self._map_inputs.values():
            cb.setCurrentIndex(0)
        self._go_to(2)

    def _reset_to_start(self) -> None:
        self._analyses = []
        self._job_id   = ""
        self._result_layer = None
        self._excel_btn.setEnabled(False)
        self._gpkg_btn.setEnabled(False)
        self._log.clear()
        self._go_to(0)

    def _validate_page(self, page: int) -> bool:
        if page == 0:
            if self._ds_postgis.isChecked() and not self._pg_conn.currentText():
                QMessageBox.warning(self, "Eingabe", "Keine PostgreSQL-Verbindung ausgewählt.")
                return False
            if self._ds_gpkg.isChecked() and not self._gpkg_path.text().strip():
                QMessageBox.warning(self, "Eingabe", "Kein GeoPackage-Pfad angegeben.")
                return False
            if self._ds_osm.isChecked() and not self._osm_url.text().strip():
                QMessageBox.warning(self, "Eingabe", "Bitte Overpass-URL angeben.")
                return False
        if page == 2 and self._srch_city.isChecked():
            if not self._city.text().strip():
                QMessageBox.warning(self, "Eingabe", "Bitte Stadt oder Adresse eingeben.")
                return False
        return True

    # =========================================================================
    # Hilfsmethoden Datenquelle
    # =========================================================================

    def _refresh_connections(self) -> None:
        from .qgis_db_utils import list_postgres_connections
        cur = self._pg_conn.currentText() if hasattr(self, "_pg_conn") else ""
        self._pg_conn.clear()
        conns = list_postgres_connections()
        self._pg_conn.addItems(conns)
        if cur in conns:
            self._pg_conn.setCurrentText(cur)

    def _browse_file(self, line_edit: QLineEdit, title: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f"{title} auswählen", "", "GeoPackage (*.gpkg)")
        if path:
            line_edit.setText(path)

    def _load_columns_into_mapping(self) -> None:
        try:
            cols = self._fetch_source_columns()
        except Exception as e:
            QMessageBox.warning(self, "Spalten laden", f"Fehler: {e}")
            return
        if not cols:
            QMessageBox.information(self, "Spalten laden", "Keine Spalten gefunden.")
            return
        for cb in self._map_inputs.values():
            cur = cb.currentText()
            cb.clear()
            cb.addItem("-- automatisch --")
            cb.addItems(cols)
            idx = cb.findText(cur)
            cb.setCurrentIndex(idx if idx >= 0 else 0)

    def _fetch_source_columns(self) -> list[str]:
        if self._ds_postgis.isChecked():
            from .data_sources import PostGISSource
            from .qgis_db_utils import get_dsn
            dsn = get_dsn(self._pg_conn.currentText())
            return PostGISSource.load_columns(dsn, self._pg_table.text().strip())
        if self._ds_osm.isChecked():
            return []  # OSM-Tags sind fest; Spalten-Mapping nicht anwendbar
        from .data_sources import GeoPackageSource
        return GeoPackageSource.load_columns(
            self._gpkg_path.text().strip(),
            self._gpkg_layer.text().strip() or "buildings",
        )

    def _get_column_map(self) -> dict:
        return {
            k: cb.currentText().strip()
            for k, cb in self._map_inputs.items()
            if cb.currentText().strip() not in ("", "-- automatisch --")
        }

    def _build_source(self):
        col_map = self._get_column_map()
        if self._ds_postgis.isChecked():
            from .data_sources import PostGISSource
            from .qgis_db_utils import get_dsn
            conn_name = self._pg_conn.currentText()
            if not conn_name:
                raise ValueError("Keine PostgreSQL-Verbindung ausgewählt.")
            dsn   = get_dsn(conn_name)
            mastr = self._pg_mastr.text().strip() or None
            return PostGISSource(dsn, self._pg_table.text().strip(), mastr, column_map=col_map)
        if self._ds_osm.isChecked():
            from .data_sources import OverpassSource
            return OverpassSource(
                overpass_url=self._osm_url.text().strip(),
                timeout=self._osm_timeout.value(),
            )
        from .data_sources import GeoPackageSource
        path = self._gpkg_path.text().strip()
        if not path:
            raise ValueError("Kein GeoPackage-Pfad angegeben.")
        mastr_path = self._gpkg_mastr_path.text().strip() or None
        mastr_lyr  = self._gpkg_mastr_layer.text().strip() or "mastr_solar"
        return GeoPackageSource(
            path, self._gpkg_layer.text().strip() or "buildings",
            mastr_gpkg_path=mastr_path, mastr_layer=mastr_lyr,
            column_map=col_map,
        )

    def _get_bbox(self) -> dict | None:
        if self._srch_city.isChecked():
            return self._geocode_city()
        return {
            "min_lat": self._min_lat.value(), "min_lon": self._min_lon.value(),
            "max_lat": self._max_lat.value(), "max_lon": self._max_lon.value(),
        }

    def _bbox_from_canvas(self) -> None:
        """Aktuelle QGIS-Kartenansicht → BBox-Felder (WGS84)."""
        try:
            from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
            canvas = self.iface.mapCanvas()
            extent = canvas.extent()
            crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
            xform = QgsCoordinateTransform(
                canvas.mapSettings().destinationCrs(), crs_4326, QgsProject.instance()
            )
            ext_wgs = xform.transformBoundingBox(extent)
            self._fill_bbox(
                ext_wgs.yMinimum(), ext_wgs.xMinimum(),
                ext_wgs.yMaximum(), ext_wgs.xMaximum(),
            )
            self._srch_bbox.setChecked(True)
        except Exception as e:
            QMessageBox.warning(self, "Kartenansicht", f"Fehler: {e}")

    def _bbox_from_layer(self) -> None:
        """Extent des gewählten Layers → BBox-Felder (WGS84)."""
        try:
            layer = self._layer_combo.currentData()
            if layer is None:
                return
            from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
            crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
            xform = QgsCoordinateTransform(layer.crs(), crs_4326, QgsProject.instance())
            ext_wgs = xform.transformBoundingBox(layer.extent())
            self._fill_bbox(
                ext_wgs.yMinimum(), ext_wgs.xMinimum(),
                ext_wgs.yMaximum(), ext_wgs.xMaximum(),
            )
            self._srch_bbox.setChecked(True)
        except Exception as e:
            QMessageBox.warning(self, "Layer-Extent", f"Fehler: {e}")

    def _fill_bbox(self, min_lat: float, min_lon: float,
                   max_lat: float, max_lon: float) -> None:
        self._min_lat.setValue(min_lat)
        self._min_lon.setValue(min_lon)
        self._max_lat.setValue(max_lat)
        self._max_lon.setValue(max_lon)

    def _refresh_layers(self) -> None:
        """Füllt die Layer-ComboBox mit allen geladenen QGIS-Layern."""
        try:
            from qgis.core import QgsProject
            cur = self._layer_combo.currentData()
            self._layer_combo.clear()
            for lyr in QgsProject.instance().mapLayers().values():
                self._layer_combo.addItem(lyr.name(), lyr)
            if cur is not None:
                for i in range(self._layer_combo.count()):
                    if self._layer_combo.itemData(i) is cur:
                        self._layer_combo.setCurrentIndex(i)
                        break
        except Exception:
            pass

    def _geocode_city(self) -> dict | None:
        try:
            from solar_sites.geocoding.nominatim import NominatimGeocoder
            g = NominatimGeocoder()
            city = self._city.text().strip()
            plz  = self._plz.text().strip()
            query = f"{plz} {city}".strip() if plz else city
            geo = g.geocode_raw(query)
            if geo is None:
                QMessageBox.warning(self, "Geocoding", f"'{query}' nicht gefunden.")
                return None
            self._log_line(f"Geocoding: {geo.display_name}")
            if geo.bbox:
                mn_lat, mn_lon, mx_lat, mx_lon = geo.bbox
            else:
                d = 0.045
                mn_lat, mn_lon = geo.lat - d, geo.lon - d
                mx_lat, mx_lon = geo.lat + d, geo.lon + d
            self._log_line(f"BBox: {mn_lat:.4f},{mn_lon:.4f} → {mx_lat:.4f},{mx_lon:.4f}")
            return {"min_lat": mn_lat, "min_lon": mn_lon, "max_lat": mx_lat, "max_lon": mx_lon}
        except Exception as e:
            QMessageBox.critical(self, "Geocoding-Fehler", str(e))
            return None

    # =========================================================================
    # Analyse
    # =========================================================================

    def _start_analysis(self) -> None:
        self._log.clear()
        self._excel_btn.setEnabled(False)
        self._gpkg_btn.setEnabled(False)
        self._analyses = []

        bbox = self._get_bbox()
        if bbox is None:
            return

        _USE_MAP = {
            0: None,       # Alle
            1: "wohnen",
            2: "gewerbe",
            3: None,       # Eigener Filter → building_type_filter
        }
        use_idx = self._building_use.currentIndex()
        custom_filter = (
            self._custom_type_filter.text().strip()
            if use_idx == 3 else None
        )
        params = {
            **bbox,
            "min_area":            self._min_area.value(),
            "building_use":        _USE_MAP[use_idx],
            "building_type_filter":custom_filter,
            "limit":               self._limit.value() or None,
            "skip_mastr":          self._skip_mastr.isChecked(),
            "geocode_addresses":   self._geocode.isChecked(),
        }

        try:
            source = self._build_source()
        except Exception as e:
            QMessageBox.critical(self, "Verbindungsfehler", str(e))
            return

        import uuid
        self._job_id = str(uuid.uuid4())[:8]

        self._go_to(self._ANALYSE_PAGE)
        self._next_btn.setEnabled(False)

        from .worker import AnalysisWorker
        self.worker = AnalysisWorker(source, params)
        self.worker.progress.connect(self._log_line)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _log_line(self, msg: str) -> None:
        self._log.appendPlainText(msg)

    def _on_finished(self, analyses: list) -> None:
        self._next_btn.setEnabled(True)
        self._analyses = analyses
        self._log_line(f"\n✓ {len(analyses)} Gebäude analysiert (Job: {self._job_id})")

        if not analyses:
            return

        self._excel_btn.setEnabled(True)
        self._gpkg_btn.setEnabled(True)

        from .layer_builder import add_to_project, build_memory_layer
        self._result_layer = build_memory_layer(analyses, self._job_id)
        add_to_project(self._result_layer, self.iface)

    def _on_error(self, msg: str) -> None:
        self._next_btn.setEnabled(True)
        self._log_line(f"\nFEHLER:\n{msg}")
        QMessageBox.critical(self, "Analyse fehlgeschlagen", msg[:500])

    # =========================================================================
    # Export
    # =========================================================================

    def _export_excel(self) -> None:
        if not self._analyses:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Excel speichern", f"solar_{self._job_id}.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            from pathlib import Path

            from solar_sites.export.excel import export_to_excel
            out = export_to_excel(self._analyses, self._job_id, Path(path))
            QMessageBox.information(self, "Export", f"Gespeichert:\n{out}")
        except Exception as e:
            QMessageBox.critical(self, "Export-Fehler", str(e))

    def _export_gpkg(self) -> None:
        if not self._result_layer:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "GeoPackage speichern", f"solar_{self._job_id}.gpkg", "GeoPackage (*.gpkg)"
        )
        if not path:
            return
        try:
            from .layer_builder import save_to_gpkg
            save_to_gpkg(self._result_layer, path)
            QMessageBox.information(self, "Export", f"Gespeichert:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export-Fehler", str(e))
