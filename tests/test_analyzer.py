from pathlib import Path

import pytest

from lineageguard.analyzer import review_sql, targeted_columns
from lineageguard.providers import FixtureContextProvider
from lineageguard.render import render_markdown
from lineageguard.webapp import ReviewRequest, create_app


FIXTURE = Path(__file__).parents[1] / "examples" / "datahub_context.json"


def context():
    return FixtureContextProvider(FIXTURE).get_dataset_context()


def test_sensitive_drop_blocks_change() -> None:
    report = review_sql("ALTER TABLE customer_orders DROP COLUMN email", context())

    assert report.verdict == "block"
    assert report.risk_score >= 40
    finding = next(item for item in report.findings if item.code == "destructive_drop_column")
    assert finding.severity == "critical"
    assert finding.affected_assets[0].name == "ml.churn_features"


def test_not_null_and_select_star_are_flagged() -> None:
    sql = """
    ALTER TABLE customer_orders ADD COLUMN status VARCHAR NOT NULL;
    SELECT * FROM customer_orders;
    """
    report = review_sql(sql, context())

    assert {item.code for item in report.findings} >= {
        "not_null_without_default",
        "select_star",
    }
    assert report.verdict == "manual_review"


def test_markdown_contains_datahub_evidence_and_plan() -> None:
    report = review_sql(
        "ALTER TABLE customer_orders RENAME COLUMN email TO contact_email", context()
    )
    markdown = render_markdown(report)

    assert "DataHub lineage shows" in markdown
    assert "ml.churn_features" in markdown
    assert "Safe migration plan" in markdown


def test_additive_change_passes_with_checks() -> None:
    report = review_sql("ALTER TABLE customer_orders ADD COLUMN note VARCHAR", context())

    assert report.verdict == "pass_with_checks"
    assert report.risk_score == 0


def test_web_review_contract_uses_same_analyzer() -> None:
    request = ReviewRequest(sql="ALTER TABLE customer_orders DROP COLUMN email", context=context())
    route = next(route for route in create_app().routes if route.path == "/api/review")
    report = route.endpoint(request)

    assert report.verdict == "block"
    assert report.dataset.source == "datahub-export"


def test_only_existing_changed_columns_are_targeted_for_live_lineage() -> None:
    sql = """
    ALTER TABLE orders DROP COLUMN email;
    ALTER TABLE orders RENAME COLUMN status TO lifecycle_status;
    ALTER TABLE orders ADD COLUMN note VARCHAR;
    """

    assert targeted_columns(sql) == {"email", "status"}


@pytest.mark.parametrize("sql", ["", "-- no schema change here"])
def test_empty_or_comment_only_sql_does_not_crash(sql: str) -> None:
    report = review_sql(sql, context())

    assert report.analyzed_statements == 0
    assert report.findings == []
    assert report.verdict == "pass_with_checks"


@pytest.mark.parametrize(
    "sql",
    [
        "ALTER TABLE unrelated DROP COLUMN email",
        "ALTER TABLE another_schema.customer_orders DROP COLUMN email",
    ],
)
def test_unrelated_table_is_blocked_without_false_dataset_attribution(sql: str) -> None:
    report = review_sql(sql, context())

    assert report.verdict == "block"
    assert [finding.code for finding in report.findings] == ["target_dataset_mismatch"]
    assert report.findings[0].affected_assets == []


@pytest.mark.parametrize(
    "sql",
    [
        "-- ALTER TABLE customer_orders DROP COLUMN email\nSELECT 1",
        "SELECT 'ALTER TABLE customer_orders DROP COLUMN email' AS note",
    ],
)
def test_comments_and_strings_do_not_trigger_drop_detection(sql: str) -> None:
    report = review_sql(sql, context())

    assert targeted_columns(sql) == set()
    assert all(finding.code != "destructive_drop_column" for finding in report.findings)
    assert report.verdict == "pass_with_checks"


def test_qualified_urn_prevents_same_table_name_false_attribution() -> None:
    dataset = context().model_copy(update={"name": "customer_orders", "metadata_gaps": []})

    report = review_sql(
        "ALTER TABLE another_schema.customer_orders DROP COLUMN email",
        dataset,
    )

    assert [finding.code for finding in report.findings] == ["target_dataset_mismatch"]


def test_mixed_table_migration_blocks_mismatch_and_reviews_matching_table() -> None:
    report = review_sql(
        """
        ALTER TABLE analytics.customer_orders DROP COLUMN email;
        ALTER TABLE analytics.unrelated DROP COLUMN email;
        """,
        context(),
    )

    codes = {finding.code for finding in report.findings}
    assert report.verdict == "block"
    assert codes == {"target_dataset_mismatch", "destructive_drop_column"}


def test_more_qualified_matching_table_is_accepted() -> None:
    report = review_sql(
        "ALTER TABLE warehouse.analytics.customer_orders ADD COLUMN note VARCHAR",
        context(),
    )

    assert all(finding.code != "target_dataset_mismatch" for finding in report.findings)


def test_mysql_modify_column_is_treated_as_type_change() -> None:
    sql = "ALTER TABLE analytics.customer_orders MODIFY COLUMN email BIGINT"

    report = review_sql(sql, context(), dialect="mysql")

    assert targeted_columns(sql, dialect="mysql") == {"email"}
    assert report.verdict == "block"
    assert report.findings[0].code == "destructive_alter_column_type"


def test_unsupported_ddl_fails_closed_without_dialect() -> None:
    sql = "ALTER TABLE analytics.customer_orders MODIFY COLUMN email BIGINT"

    report = review_sql(sql, context())

    assert report.verdict == "manual_review"
    assert report.findings[0].code == "unsupported_sql_statement"


def test_mysql_change_column_uses_old_name_for_lineage() -> None:
    sql = "ALTER TABLE analytics.customer_orders CHANGE COLUMN email contact_email BIGINT"

    report = review_sql(sql, context(), dialect="mysql")

    assert targeted_columns(sql, dialect="mysql") == {"email"}
    assert report.verdict == "block"
    assert "`email`" in report.findings[0].evidence
    assert "`contact_email`" in report.findings[0].evidence
    assert report.findings[0].affected_assets[0].name == "ml.churn_features"


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("DROP TABLE analytics.customer_orders", "destructive_drop_table"),
        ("DROP VIEW analytics.customer_orders", "destructive_drop_view"),
        (
            "ALTER TABLE analytics.customer_orders RENAME TO old_orders",
            "destructive_rename_table",
        ),
        ("TRUNCATE TABLE analytics.customer_orders", "destructive_truncate_table"),
        (
            "CREATE OR REPLACE TABLE analytics.customer_orders (id BIGINT)",
            "destructive_replace_table",
        ),
        (
            "CREATE OR REPLACE VIEW analytics.customer_orders AS SELECT 1 AS id",
            "destructive_replace_view",
        ),
    ],
)
def test_destructive_table_ddl_is_blocked(sql: str, code: str) -> None:
    report = review_sql(sql, context())

    assert report.verdict == "block"
    assert report.findings[0].code == code
    assert report.findings[0].affected_assets


def test_unclassified_table_alteration_fails_closed() -> None:
    report = review_sql(
        "ALTER TABLE analytics.customer_orders ADD CONSTRAINT positive_total "
        "CHECK (order_total >= 0)",
        context(),
    )

    assert report.verdict == "manual_review"
    assert report.findings[0].code == "unsupported_table_alteration"


def test_plain_create_for_existing_context_requires_review() -> None:
    report = review_sql(
        "CREATE TABLE analytics.customer_orders (id BIGINT)",
        context(),
    )

    assert report.verdict == "manual_review"
    assert report.findings[0].code == "create_existing_dataset_definition"


def test_new_downstream_view_is_reviewed_as_a_consumer_not_a_target_mismatch() -> None:
    report = review_sql(
        "CREATE VIEW analytics.customer_order_rollup AS SELECT * FROM analytics.customer_orders",
        context(),
    )

    assert {finding.code for finding in report.findings} == {"select_star"}


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("DROP SCHEMA analytics CASCADE", "destructive_drop_schema"),
        ("DROP DATABASE analytics CASCADE", "destructive_drop_database"),
    ],
)
def test_container_level_drop_is_blocked(sql: str, code: str) -> None:
    report = review_sql(sql, context())

    assert report.verdict == "block"
    assert report.findings[0].code == code


def test_incomplete_metadata_requires_manual_review() -> None:
    dataset = context().model_copy(update={"metadata_gaps": ["Column lineage was truncated."]})

    report = review_sql(
        "ALTER TABLE analytics.customer_orders ADD COLUMN delivery_note VARCHAR",
        dataset,
    )

    assert report.verdict == "manual_review"
    assert report.risk_score == 25
    assert report.findings[0].code == "incomplete_datahub_metadata"
