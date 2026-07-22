from pathlib import Path

from typer.testing import CliRunner

from lineageguard import cli as cli_module
from lineageguard.providers import FixtureContextProvider


FIXTURE = Path(__file__).parents[1] / "examples" / "datahub_context.json"
URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_orders,PROD)"
RUNNER = CliRunner()


def test_review_uses_mcp_url_and_token_environment(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeMCPProvider:
        metadata_gaps = ["lineage result was truncated"]

        def __init__(self, url: str, token: str | None = None) -> None:
            captured["url"] = url
            captured["token"] = token

        def get_dataset_context(self, urn: str | None, columns: set[str]):
            captured["urn"] = urn
            captured["columns"] = columns
            return FixtureContextProvider(FIXTURE).get_dataset_context()

    monkeypatch.setattr(cli_module, "DataHubMCPContextProvider", FakeMCPProvider)
    monkeypatch.setenv("DATAHUB_MCP_URL", "https://example.acryl.io/integrations/ai/mcp/")
    monkeypatch.setenv("DATAHUB_MCP_TOKEN", "secret-from-environment")

    sql_file = tmp_path / "migration.sql"
    out = tmp_path / "review.md"
    sql_file.write_text(
        "ALTER TABLE customer_orders DROP COLUMN email;\n",
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        cli_module.app,
        ["review", "--sql", str(sql_file), "--urn", URN, "--out", str(out)],
    )

    assert result.exit_code == 0
    assert captured == {
        "url": "https://example.acryl.io/integrations/ai/mcp/",
        "token": "secret-from-environment",
        "urn": URN,
        "columns": {"email"},
    }
    assert "Metadata warning: lineage result was truncated" in result.output
    assert out.exists()
