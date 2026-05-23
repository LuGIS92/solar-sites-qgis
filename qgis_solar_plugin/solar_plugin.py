"""Hauptklasse des QGIS Plugins."""

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction

_ICON = str(Path(__file__).resolve().parent / "icon.svg")


class SolarPlugin:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.action: QAction | None = None
        self.dock = None

    def initGui(self) -> None:
        from .solar_dock import SolarDockWidget

        self.action = QAction(QIcon(_ICON), "Solar Sites PV-Analyse", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.setToolTip("PV-Potenzialanalyse (Solar Sites)")
        self.action.triggered.connect(self._toggle_dock)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Solar Sites", self.action)

        self.dock = SolarDockWidget(self.iface, self.iface.mainWindow())
        self.iface.mainWindow().addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.visibilityChanged.connect(self.action.setChecked)
        self.dock.hide()

    def unload(self) -> None:
        self.iface.removePluginMenu("&Solar Sites", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dock:
            self.iface.mainWindow().removeDockWidget(self.dock)
            self.dock.setParent(None)   # sofortiges Loslösen, kein "duplicate widget"
            self.dock = None

    def _toggle_dock(self) -> None:
        if self.dock is None:
            return
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.dock.show()
            self.dock.raise_()
