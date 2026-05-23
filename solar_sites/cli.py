"""CLI-Einstiegspunkt für Solar Sites."""

from __future__ import annotations

import logging
from pathlib import Path

import click


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s [%(name)s] %(message)s",
    )


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Zeige Debug-Logs (PVGIS, MaStR, etc.)")
@click.version_option()
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Solar Sites – PV-Potenzialanalyse für Gewerbeimmobilien."""
    _setup_logging(verbose)


@cli.command("process-list")
@click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True, path_type=Path), help="CSV/Excel mit Adressen (Spalten: street, house_nr, city, postal_code)")
@click.option("--output", "-o", "output_path", type=click.Path(path_type=Path), default=None, help="Ausgabe-Excel (Standard: exports/solar_potenzial_<job>_<ts>.xlsx)")
@click.option("--job-id", default=None, help="Job-ID (wird generiert wenn leer)")
def process_list(input_path: Path, output_path: Path | None, job_id: str | None) -> None:
    """Verarbeitet eine Adressliste (Kundenliste) und exportiert Solarpotenziale."""
    from solar_sites.db.queries import get_analyses_for_job
    from solar_sites.export.excel import export_to_excel
    from solar_sites.workflows.customer_list import run

    job = run(input_path, job_id=job_id)
    analyses = get_analyses_for_job(job)
    path = export_to_excel(analyses, job, output_path)
    click.echo(f"Export: {path}")
    click.echo(f"Job-ID: {job}  |  Analysiert: {len(analyses)} Gebäude")


@cli.command("search-area")
@click.option("--city", default=None, help="Stadt oder PLZ+Stadt")
@click.option("--plz", default="", help="Postleitzahl (optional, kombiniert mit --city)")
@click.option("--bbox", nargs=4, type=float, default=None, metavar="MIN_LAT MIN_LON MAX_LAT MAX_LON", help="Bounding-Box statt Stadt")
@click.option("--min-area", default=None, type=float,
              help="Mindest-Grundfläche in m²  [Standard: 100]  "
                   "Richtwerte: 200=Wohnhaus, 500=kleines Gewerbe, 1000=Lager/Supermarkt, 2000=Logistik/Fabrik")
@click.option("--limit", default=None, type=int,
              help="Maximale Anzahl Gebäude (nach Größe sortiert, größte zuerst)")
@click.option("--no-mastr", is_flag=True, default=False,
              help="MaStR-Abfrage überspringen (schneller, kein registriert/nicht-registriert)")
@click.option("--use", "building_use", default=None,
              type=click.Choice(["wohnen", "gewerbe"], case_sensitive=False),
              help="Nutzungsart: wohnen=nur Wohngebäude (ALKIS 1xxx), gewerbe=nur Gewerbe/Industrie (2xxx–3xxx)  [Standard: alle]")
@click.option("--output", "-o", "output_path", type=click.Path(path_type=Path), default=None,
              help="Ausgabe-Excel  [Standard: exports/solar_potenzial_<job>_<ts>.xlsx]")
@click.option("--job-id", default=None, help="Job-ID (wird generiert wenn leer)")
def search_area(
    city: str | None,
    plz: str,
    bbox: tuple | None,
    min_area: float | None,
    limit: int | None,
    no_mastr: bool,
    building_use: str | None,
    output_path: Path | None,
    job_id: str | None,
) -> None:
    """Sucht Gebäude in einem Gebiet und schätzt deren Solarpotenzial.

    \b
    Beispiele:
      solar-sites search-area --city München --min-area 1000
      solar-sites search-area --city Köln --plz 50667 --min-area 500 --limit 200 --use gewerbe
      solar-sites search-area --bbox 48.10 11.50 48.20 11.65 --min-area 2000 --use wohnen
    """
    from solar_sites.db.queries import get_analyses_for_job
    from solar_sites.export.excel import export_to_excel
    from solar_sites.workflows.area_search import run_by_bbox, run_by_city

    if bbox:
        job = run_by_bbox(*bbox, min_area_sqm=min_area, limit=limit, skip_mastr=no_mastr, building_use=building_use, job_id=job_id)
    elif city:
        job = run_by_city(city, postal_code=plz, min_area_sqm=min_area, limit=limit, skip_mastr=no_mastr, building_use=building_use, job_id=job_id)
    else:
        raise click.UsageError("Entweder --city oder --bbox angeben.")

    analyses = get_analyses_for_job(job)
    path = export_to_excel(analyses, job, output_path)
    click.echo(f"Export: {path}")
    click.echo(f"Job-ID: {job}  |  Analysiert: {len(analyses)} Gebäude")


@cli.command("export")
@click.argument("job_id")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
def export_job(job_id: str, output: Path | None) -> None:
    """Exportiert einen bereits berechneten Job als Excel."""
    from solar_sites.db.queries import get_analyses_for_job
    from solar_sites.export.excel import export_to_excel

    analyses = get_analyses_for_job(job_id)
    if not analyses:
        raise click.ClickException(f"Keine Ergebnisse für Job '{job_id}' gefunden.")
    path = export_to_excel(analyses, job_id, output)
    click.echo(f"Export: {path}  ({len(analyses)} Einträge)")


@cli.command("db-init")
def db_init() -> None:
    """Erstellt das solar_sites-Schema und alle benötigten Tabellen."""
    from solar_sites.db.queries import ensure_schema
    ensure_schema()
    click.echo("Datenbank-Schema erstellt.")


@cli.command("dashboard")
@click.option("--port", default=8501, show_default=True)
def dashboard(port: int) -> None:
    """Startet das Streamlit-Dashboard."""
    import subprocess
    import sys
    from pathlib import Path

    app_path = Path(__file__).parent.parent / "app" / "main.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)],
        check=True,
    )
