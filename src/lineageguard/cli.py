from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from lineageguard.analyzer import review_sql, targeted_columns
from lineageguard.providers import DataHubContextProvider, FixtureContextProvider
from lineageguard.render import render_markdown


app = typer.Typer(help="Review SQL changes with DataHub schema and lineage context.")


@app.callback()
def main() -> None:
    """Review SQL schema changes before they break downstream assets."""


@app.command()
def review(
    sql_file: Path = typer.Option(..., "--sql", exists=True, dir_okay=False),
    context_file: Path | None = typer.Option(None, "--context", exists=True, dir_okay=False),
    urn: str | None = typer.Option(None, "--urn"),
    server: str = typer.Option("http://localhost:8080", "--server"),
    token: str | None = typer.Option(None, "--token", envvar="DATAHUB_TOKEN"),
    dialect: str | None = typer.Option(None, "--dialect"),
    out: Path = typer.Option(Path("review-output/review.md"), "--out"),
    json_out: Path | None = typer.Option(None, "--json-out"),
) -> None:
    """Generate a merge-gate report for a proposed SQL change."""
    if bool(context_file) == bool(urn):
        raise typer.BadParameter("provide exactly one of --context or --urn")

    provider = (
        FixtureContextProvider(context_file)
        if context_file
        else DataHubContextProvider(server=server, token=token or os.getenv("DATAHUB_TOKEN"))
    )
    sql = sql_file.read_text(encoding="utf-8")
    context = provider.get_dataset_context(urn, columns=targeted_columns(sql))
    report = review_sql(sql, context, dialect=dialect)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(report), encoding="utf-8")
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report.model_dump(), indent=2) + "\n", encoding="utf-8")

    typer.echo(f"{report.verdict.upper()} - risk {report.risk_score}/100")
    typer.echo(f"Report: {out}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port", min=1, max=65535),
) -> None:
    """Run the interactive review console."""
    import uvicorn

    uvicorn.run("lineageguard.webapp:app", host=host, port=port)


if __name__ == "__main__":
    app()
