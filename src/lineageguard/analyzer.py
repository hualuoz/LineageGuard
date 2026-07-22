from __future__ import annotations

import re

import sqlglot
from sqlglot import expressions as exp

from lineageguard.models import DatasetContext, Finding, ReviewReport


DROP_COLUMN = re.compile(
    r"\bDROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?(?P<column>[`\"\w]+)", re.IGNORECASE
)
RENAME_COLUMN = re.compile(
    r"\bRENAME\s+COLUMN\s+(?P<old>[`\"\w]+)\s+TO\s+(?P<new>[`\"\w]+)", re.IGNORECASE
)
ALTER_TYPE = re.compile(
    r"\bALTER\s+COLUMN\s+(?P<column>[`\"\w]+)\s+(?:SET\s+DATA\s+)?TYPE\b",
    re.IGNORECASE,
)
ADD_NOT_NULL = re.compile(
    r"\bADD\s+COLUMN\s+(?P<column>[`\"\w]+)\s+[^;]+?\bNOT\s+NULL\b(?![^;]*\bDEFAULT\b)",
    re.IGNORECASE,
)

WEIGHTS = {"critical": 40, "high": 25, "medium": 10, "low": 5}


def targeted_columns(sql: str) -> set[str]:
    """Return existing columns whose contracts are changed by the SQL."""
    columns = {match.group("column").strip('`"').lower() for match in DROP_COLUMN.finditer(sql)}
    columns.update(match.group("old").strip('`"').lower() for match in RENAME_COLUMN.finditer(sql))
    columns.update(match.group("column").strip('`"').lower() for match in ALTER_TYPE.finditer(sql))
    return columns


def _column_assets(context: DatasetContext, column_name: str) -> list:
    column = context.column(column_name)
    return (
        column.downstream_assets
        if column and column.downstream_assets
        else context.downstream_assets
    )


def _destructive_finding(
    context: DatasetContext, operation: str, column_name: str, replacement: str | None = None
) -> Finding:
    column = context.column(column_name)
    assets = _column_assets(context, column_name)
    sensitive = bool(column and column.sensitive)
    severity = "critical" if sensitive or assets else "high"
    evidence_parts = [f"Column `{column_name}` is targeted by `{operation}`."]
    if sensitive:
        evidence_parts.append(
            f"DataHub classifies it with {', '.join(column.tags + column.glossary_terms)}."
        )
    if assets:
        evidence_parts.append(
            f"DataHub lineage shows {len(assets)} downstream asset(s): "
            + ", ".join(asset.name for asset in assets[:5])
            + "."
        )
    if replacement:
        evidence_parts.append(f"The proposed replacement name is `{replacement}`.")

    return Finding(
        severity=severity,
        code=f"destructive_{operation.lower().replace(' ', '_')}",
        title=f"{operation.title()} can break downstream consumers",
        evidence=" ".join(evidence_parts),
        recommendation=(
            "Use an expand-and-contract migration: add the replacement, backfill it, dual-write, "
            "migrate every downstream consumer, and remove the old column only after DataHub lineage "
            "and usage checks are clean."
        ),
        affected_assets=assets,
    )


def review_sql(sql: str, context: DatasetContext, dialect: str | None = None) -> ReviewReport:
    findings: list[Finding] = []
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.ParseError as exc:
        statements = []
        findings.append(
            Finding(
                severity="high",
                code="sql_parse_error",
                title="SQL could not be parsed safely",
                evidence=str(exc),
                recommendation="Fix the SQL syntax or select the correct dialect before review.",
            )
        )

    for match in DROP_COLUMN.finditer(sql):
        findings.append(_destructive_finding(context, "drop column", match.group("column")))

    for match in RENAME_COLUMN.finditer(sql):
        findings.append(
            _destructive_finding(
                context, "rename column", match.group("old"), replacement=match.group("new")
            )
        )

    for match in ALTER_TYPE.finditer(sql):
        findings.append(_destructive_finding(context, "alter column type", match.group("column")))

    for match in ADD_NOT_NULL.finditer(sql):
        findings.append(
            Finding(
                severity="high",
                code="not_null_without_default",
                title="Non-null column is added without a default",
                evidence=f"New column `{match.group('column')}` is `NOT NULL` without a default.",
                recommendation=(
                    "Add the column as nullable, backfill existing rows, validate completeness, "
                    "then add the non-null constraint in a later deployment."
                ),
            )
        )

    if any(statement.find(exp.Star) for statement in statements):
        findings.append(
            Finding(
                severity="medium",
                code="select_star",
                title="Wildcard projection hides schema coupling",
                evidence="The SQL contains `SELECT *`, so new or reordered columns can leak downstream.",
                recommendation="List the required columns explicitly and preserve stable output names.",
            )
        )

    if not context.owners:
        findings.append(
            Finding(
                severity="medium",
                code="missing_owner",
                title="No accountable DataHub owner",
                evidence=f"Dataset `{context.name}` has no owner in DataHub.",
                recommendation="Assign a technical or data owner before approving a breaking change.",
            )
        )

    risk_score = min(100, sum(WEIGHTS[finding.severity] for finding in findings))
    if any(finding.severity == "critical" for finding in findings) or risk_score >= 50:
        verdict = "block"
    elif risk_score >= 25:
        verdict = "manual_review"
    else:
        verdict = "pass_with_checks"

    summary = (
        f"{len(findings)} finding(s) across {len(statements)} parsed statement(s); "
        f"DataHub reports {len(context.downstream_assets)} downstream asset(s)."
    )
    plan = [
        "Create an additive schema change and keep the current contract intact.",
        "Backfill and validate the replacement using explicit row-count and null checks.",
        "Notify DataHub owners and migrate the listed downstream assets.",
        "Run the review again after DataHub lineage and usage metadata refresh.",
        "Remove the old field only after a monitored compatibility window and rollback checkpoint.",
    ]
    return ReviewReport(
        dataset=context,
        risk_score=risk_score,
        verdict=verdict,
        summary=summary,
        findings=findings,
        safe_migration_plan=plan,
        analyzed_statements=len(statements),
    )
