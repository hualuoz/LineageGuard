from pathlib import Path

from typer.testing import CliRunner

from lineageguard.cli import app


FIXTURE = Path(__file__).parents[1] / "examples" / "datahub_context.json"
RUNNER = CliRunner()


def test_target_columns_prints_json(tmp_path: Path) -> None:
    sql_file = tmp_path / "migration.sql"
    sql_file.write_text(
        "ALTER TABLE customer_orders DROP COLUMN email;\n"
        "ALTER TABLE customer_orders RENAME COLUMN status TO lifecycle_status;\n",
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["target-columns", "--sql", str(sql_file)])

    assert result.exit_code == 0
    assert result.stdout.strip() == '["email", "status"]'


def test_fixture_context_can_validate_requested_urn(tmp_path: Path) -> None:
    sql_file = tmp_path / "migration.sql"
    out = tmp_path / "review.md"
    sql_file.write_text(
        "ALTER TABLE customer_orders ADD COLUMN note VARCHAR;\n",
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        [
            "review",
            "--sql",
            str(sql_file),
            "--context",
            str(FIXTURE),
            "--urn",
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_orders,PROD)",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    assert out.exists()


def test_fail_on_block_preserves_reports_and_returns_two(tmp_path: Path) -> None:
    sql_file = tmp_path / "migration.sql"
    markdown_file = tmp_path / "review.md"
    json_file = tmp_path / "review.json"
    sql_file.write_text(
        "ALTER TABLE customer_orders DROP COLUMN email;\n",
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        [
            "review",
            "--sql",
            str(sql_file),
            "--context",
            str(FIXTURE),
            "--out",
            str(markdown_file),
            "--json-out",
            str(json_file),
            "--fail-on-block",
        ],
    )

    assert result.exit_code == 2
    assert "BLOCK - risk" in result.stdout
    assert markdown_file.exists()
    assert json_file.exists()


def test_require_pass_fails_manual_review(tmp_path: Path) -> None:
    sql_file = tmp_path / "migration.sql"
    markdown_file = tmp_path / "review.md"
    sql_file.write_text(
        "ALTER TABLE customer_orders ADD COLUMN required_flag BOOLEAN NOT NULL;\n",
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        [
            "review",
            "--sql",
            str(sql_file),
            "--context",
            str(FIXTURE),
            "--out",
            str(markdown_file),
            "--require-pass",
        ],
    )

    assert result.exit_code == 2
    assert "MANUAL_REVIEW - risk 25/100" in result.stdout
    assert "not_null_without_default" in markdown_file.read_text(encoding="utf-8")


def test_require_pass_fails_unparseable_sql(tmp_path: Path) -> None:
    sql_file = tmp_path / "migration.sql"
    markdown_file = tmp_path / "review.md"
    sql_file.write_text("ALTER TABLE", encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "review",
            "--sql",
            str(sql_file),
            "--context",
            str(FIXTURE),
            "--out",
            str(markdown_file),
            "--require-pass",
        ],
    )

    assert result.exit_code == 2
    assert "MANUAL_REVIEW - risk 25/100" in result.stdout
    assert "sql_parse_error" in markdown_file.read_text(encoding="utf-8")
