from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from lineageguard.analyzer import review_sql, targeted_columns
from lineageguard.providers import (
    DataHubContextProvider,
    DataHubMCPContextProvider,
    FixtureContextProvider,
)
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
    mcp_url: str | None = typer.Option(
        None,
        "--mcp-url",
        envvar="DATAHUB_MCP_URL",
        help="Tenant-specific DataHub Streamable HTTP MCP endpoint.",
    ),
    token: str | None = typer.Option(None, "--token", envvar="DATAHUB_TOKEN"),
    dialect: str | None = typer.Option(None, "--dialect"),
    out: Path = typer.Option(Path("review-output/review.md"), "--out"),
    json_out: Path | None = typer.Option(None, "--json-out"),
    fail_on_block: bool = typer.Option(
        False,
        "--fail-on-block",
        help="Exit with status 2 when the review verdict is block.",
    ),
    require_pass: bool = typer.Option(
        False,
        "--require-pass",
        help="Exit with status 2 unless the verdict is pass_with_checks.",
    ),
) -> None:
    """Generate a merge-gate report for a proposed SQL change."""
    if not context_file and not urn:
        raise typer.BadParameter("provide --context, or --urn for a live DataHub source")

    if context_file:
        provider = FixtureContextProvider(context_file)
    elif mcp_url:
        provider = DataHubMCPContextProvider(
            url=mcp_url,
            token=os.getenv("DATAHUB_MCP_TOKEN"),
        )
    else:
        provider = DataHubContextProvider(
            server=server,
            token=token or os.getenv("DATAHUB_TOKEN"),
        )
    sql = sql_file.read_text(encoding="utf-8")
    context = provider.get_dataset_context(urn, columns=targeted_columns(sql, dialect=dialect))
    for gap in getattr(provider, "metadata_gaps", []):
        typer.echo(f"Metadata warning: {gap}", err=True)
    report = review_sql(sql, context, dialect=dialect)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(report), encoding="utf-8")
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report.model_dump(), indent=2) + "\n", encoding="utf-8")

    typer.echo(f"{report.verdict.upper()} - risk {report.risk_score}/100")
    typer.echo(f"Report: {out}")
    if (fail_on_block and report.verdict == "block") or (
        require_pass and report.verdict != "pass_with_checks"
    ):
        raise typer.Exit(code=2)


@app.command("target-columns")
def target_columns(
    sql_file: Path = typer.Option(..., "--sql", exists=True, dir_okay=False),
    dialect: str | None = typer.Option(None, "--dialect"),
) -> None:
    """Print existing columns changed by a proposed SQL migration as JSON."""
    sql = sql_file.read_text(encoding="utf-8")
    typer.echo(json.dumps(sorted(targeted_columns(sql, dialect=dialect))))


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
