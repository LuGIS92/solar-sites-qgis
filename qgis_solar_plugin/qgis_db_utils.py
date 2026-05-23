"""Liest QGIS-konfigurierte PostgreSQL-Verbindungen aus QgsSettings."""

from __future__ import annotations


def list_postgres_connections() -> list[str]:
    """Gibt alle in QGIS konfigurierten PostgreSQL-Verbindungsnamen zurück."""
    from qgis.core import QgsSettings
    s = QgsSettings()
    s.beginGroup("PostgreSQL/connections")
    names = s.childGroups()
    s.endGroup()
    return sorted(names)


def get_dsn(conn_name: str) -> str:
    """Baut einen psycopg2-DSN-String aus einer QGIS-Verbindung.

    Reihenfolge:
      1. QGIS Auth-Manager (authcfg) – wird von den meisten Verbindungen genutzt
      2. In QgsSettings gespeichertes Klartextpasswort (savePassword=true)
      3. Interaktiver QGIS-Passwort-Dialog als Fallback
    """
    from qgis.core import QgsApplication, QgsCredentials, QgsSettings

    s = QgsSettings()
    base = f"PostgreSQL/connections/{conn_name}"

    host     = s.value(f"{base}/host",     "localhost")
    port     = s.value(f"{base}/port",     "5432")
    database = s.value(f"{base}/database", "")
    username = s.value(f"{base}/username", "")
    authcfg  = s.value(f"{base}/authcfg",  "") or ""

    password = ""

    # 1. Auth-Manager via QgsAuthMethodConfig (unterstützt Basic, PKI, etc.)
    if authcfg:
        from qgis.core import QgsAuthMethodConfig
        config = QgsAuthMethodConfig()
        ok = QgsApplication.authManager().loadAuthenticationConfig(authcfg, config, True)
        if ok and config.isValid():
            cfg_map = config.configMap()
            username = cfg_map.get("username", username)
            password = cfg_map.get("password", "")

    # 2. Klartextpasswort aus Settings
    if not password:
        save_pwd = str(s.value(f"{base}/savePassword", "false")).lower() == "true"
        if save_pwd:
            password = s.value(f"{base}/password", "") or ""

    # 3. Interaktiver QGIS-Dialog (muss im Main-Thread aufgerufen werden)
    if not password:
        uri_key = f"host={host} dbname={database} port={port} user={username}"
        ok, username, password = QgsCredentials.instance().get(uri_key, username, "")
        if not ok or not password:
            raise RuntimeError(
                f"Kein Passwort für QGIS-Verbindung '{conn_name}' angegeben.\n"
                "Bitte das Passwort in den QGIS-Verbindungseinstellungen speichern."
            )
        QgsCredentials.instance().put(uri_key, username, password)

    return (
        f"host={host} port={port} dbname={database} "
        f"user={username} password={password}"
    )


def get_connection_info(conn_name: str) -> dict:
    """Gibt Verbindungsinfos als Dict zurück (für Anzeige im UI)."""
    from qgis.core import QgsSettings
    s = QgsSettings()
    base = f"PostgreSQL/connections/{conn_name}"
    return {
        "host":     s.value(f"{base}/host",     "localhost"),
        "port":     s.value(f"{base}/port",     "5432"),
        "database": s.value(f"{base}/database", ""),
        "username": s.value(f"{base}/username", ""),
    }
