from pathlib import Path

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
