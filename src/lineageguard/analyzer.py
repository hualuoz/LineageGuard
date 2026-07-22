from __future__ import annotations

import sqlglot
from sqlglot import expressions as exp

from lineageguard.models import DatasetContext, Finding, ReviewReport


WEIGHTS = {"critical": 40, "high": 25, "medium": 10, "low": 5}


def targeted_columns(sql: str, dialect: str | None = None) -> set[str]:
    """Return existing columns whose contracts are changed by the SQL."""
    try:
        statements = [
            statement for statement in sqlglot.parse(sql, read=dialect) if statement is not None
        ]
    except sqlglot.errors.ParseError:
        return set()

    columns = set()
    for alter in _alter_statements(statements):
        for action in alter.args.get("actions") or []:
            if (
                isinstance(action, exp.Drop)
                and str(action.args.get("kind", "")).upper() == "COLUMN"
            ):
                columns.add(_column_name(action.this))
            elif isinstance(action, exp.RenameColumn):
                columns.add(_column_name(action.this))
            elif isinstance(action, exp.AlterColumn) and action.args.get("dtype") is not None:
                columns.add(_column_name(action.this))
            elif isinstance(action, exp.ModifyColumn):
                columns.add(_modify_column_names(action)[0])
    return columns


def _alter_statements(statements: list[exp.Expression]) -> list[exp.Alter]:
    return [alter for statement in statements for alter in statement.find_all(exp.Alter)]


def _column_name(expression: exp.Expression) -> str:
    return expression.name.strip('`"').lower()


def _modify_column_names(action: exp.ModifyColumn) -> tuple[str, str | None]:
    new_name = _column_name(action.this)
    old_expression = action.args.get("rename_from")
    old_name = _column_name(old_expression) if old_expression is not None else new_name
    return old_name, new_name if new_name != old_name else None


def _normalized_name_parts(value: str) -> tuple[str, ...]:
    return tuple(part.strip().strip('`"[]').lower() for part in value.split(".") if part.strip())


def _context_table_names(context: DatasetContext) -> list[tuple[str, ...]]:
    candidates = [context.name]
    prefix = "urn:li:dataset:("
    if context.urn.startswith(prefix) and context.urn.endswith(")"):
        urn_parts = context.urn[len(prefix) : -1].rsplit(",", 2)
        if len(urn_parts) == 3:
            candidates.append(urn_parts[1])
    names = [parts for candidate in candidates if (parts := _normalized_name_parts(candidate))]
    return sorted(set(names), key=len, reverse=True)


def _table_matches_context(table: exp.Expression, context: DatasetContext) -> bool:
    if not isinstance(table, exp.Table):
        return False

    table_parts = tuple(part.name.lower() for part in table.parts)
    context_names = _context_table_names(context)
    qualified_names = [parts for parts in context_names if len(parts) > 1]
    candidates = qualified_names or context_names
    for context_parts in candidates:
        if len(table_parts) == 1 and table_parts[-1] == context_parts[-1]:
            return True
        if (
            len(table_parts) <= len(context_parts)
            and table_parts == context_parts[-len(table_parts) :]
        ):
            return True
        if (
            len(context_parts) < len(table_parts)
            and context_parts == table_parts[-len(context_parts) :]
        ):
            return True
    return False


def _statement_references_context(statement: exp.Expression, context: DatasetContext) -> bool:
    return any(_table_matches_context(table, context) for table in statement.find_all(exp.Table))


def _create_target(statement: exp.Create) -> exp.Table | None:
    target = statement.this
    if isinstance(target, exp.Schema):
        target = target.this
    return target if isinstance(target, exp.Table) else None


def _table_ddl_targets(statements: list[exp.Expression]) -> list[exp.Table]:
    targets: list[exp.Table] = []
    for statement in statements:
        if (
            isinstance(statement, exp.Alter)
            and str(statement.args.get("kind", "")).upper() in {"TABLE", "VIEW"}
            and isinstance(statement.this, exp.Table)
        ):
            targets.append(statement.this)
        elif (
            isinstance(statement, exp.Drop)
            and str(statement.args.get("kind", "")).upper() in {"TABLE", "VIEW"}
            and isinstance(statement.this, exp.Table)
        ):
            targets.append(statement.this)
        elif (
            isinstance(statement, exp.Create)
            and statement.args.get("replace")
            and (target := _create_target(statement))
        ):
            targets.append(target)
        elif isinstance(statement, exp.TruncateTable):
            targets.extend(
                table
                for table in statement.args.get("expressions") or []
                if isinstance(table, exp.Table)
            )
    return targets


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


def _destructive_table_finding(
    context: DatasetContext,
    operation: str,
    table_name: str,
    replacement: str | None = None,
) -> Finding:
    evidence = f"Table `{table_name}` is targeted by `{operation}`."
    if context.downstream_assets:
        evidence += (
            f" DataHub lineage shows {len(context.downstream_assets)} downstream asset(s): "
            + ", ".join(asset.name for asset in context.downstream_assets[:5])
            + "."
        )
    if replacement:
        evidence += f" The proposed replacement name is `{replacement}`."
    return Finding(
        severity="critical",
        code=f"destructive_{operation.lower().replace(' ', '_')}",
        title=f"{operation.title()} can invalidate the entire data contract",
        evidence=evidence,
        recommendation=(
            "Preserve the current table contract, migrate every DataHub downstream consumer "
            "to a replacement, and perform the destructive operation only after an explicit "
            "owner-approved compatibility window."
        ),
        affected_assets=context.downstream_assets,
    )


def review_sql(sql: str, context: DatasetContext, dialect: str | None = None) -> ReviewReport:
    findings: list[Finding] = []
    try:
        statements = [
            statement for statement in sqlglot.parse(sql, read=dialect) if statement is not None
        ]
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

    unsupported_ddl = [
        statement
        for statement in statements
        if isinstance(statement, exp.Command)
        and str(statement.args.get("this", "")).upper()
        in {"ALTER", "CREATE", "DROP", "RENAME", "TRUNCATE"}
    ]
    if unsupported_ddl:
        findings.append(
            Finding(
                severity="high",
                code="unsupported_sql_statement",
                title="DDL could not be analyzed safely",
                evidence=(
                    "SQLGlot treated the following DDL as an unsupported command: "
                    + "; ".join(statement.sql() for statement in unsupported_ddl)
                    + "."
                ),
                recommendation=(
                    "Select the correct SQL dialect and rerun the review; do not merge a "
                    "schema change whose operations were not parsed into a structured AST."
                ),
            )
        )

    for statement in statements:
        if not isinstance(statement, exp.Drop):
            continue
        kind = str(statement.args.get("kind", "object")).upper()
        if kind in {"SCHEMA", "DATABASE"}:
            findings.append(
                Finding(
                    severity="critical",
                    code=f"destructive_drop_{kind.lower()}",
                    title=f"Drop {kind.title()} can remove the selected dataset",
                    evidence=(
                        f"The migration contains `{statement.sql()}`, which can remove "
                        f"`{context.name}` and invalidate its DataHub lineage."
                    ),
                    recommendation=(
                        "Remove the container-level drop from this migration and require a "
                        "separate, owner-approved decommission plan with a complete asset inventory."
                    ),
                    affected_assets=context.downstream_assets,
                )
            )
        elif kind not in {"TABLE", "VIEW"}:
            findings.append(
                Finding(
                    severity="high",
                    code="unsupported_drop_operation",
                    title="Drop operation requires human review",
                    evidence=f"LineageGuard does not classify `{statement.sql()}` automatically.",
                    recommendation=(
                        "Verify the dropped object's relationship to the selected dataset and add "
                        "a dedicated policy before allowing automatic merge."
                    ),
                )
            )

    relevant_statements = [
        statement for statement in statements if _statement_references_context(statement, context)
    ]
    mismatched_tables = {
        table.sql()
        for table in _table_ddl_targets(statements)
        if not _table_matches_context(table, context)
    }
    mismatched_tables.update(
        target.sql()
        for statement in statements
        if isinstance(statement, exp.Create)
        and not statement.args.get("replace")
        and (target := _create_target(statement)) is not None
        and not _table_matches_context(target, context)
        and not _statement_references_context(statement, context)
    )
    mismatched_tables = sorted(mismatched_tables)
    if mismatched_tables:
        findings.append(
            Finding(
                severity="critical",
                code="target_dataset_mismatch",
                title="Migration target does not match the DataHub dataset",
                evidence=(
                    "The migration alters "
                    + ", ".join(f"`{table}`" for table in mismatched_tables)
                    + f", but the selected DataHub context is `{context.name}` ({context.urn})."
                ),
                recommendation=(
                    "Select the matching DataHub dataset URN or split the migration so every "
                    "altered table is reviewed against its own metadata context."
                ),
            )
        )

    for statement in relevant_statements:
        if (
            isinstance(statement, exp.Drop)
            and str(statement.args.get("kind", "")).upper() in {"TABLE", "VIEW"}
            and _table_matches_context(statement.this, context)
        ):
            kind = str(statement.args.get("kind", "table")).lower()
            findings.append(
                _destructive_table_finding(context, f"drop {kind}", statement.this.sql())
            )
        elif isinstance(statement, exp.TruncateTable):
            for table in statement.args.get("expressions") or []:
                if _table_matches_context(table, context):
                    findings.append(
                        _destructive_table_finding(context, "truncate table", table.sql())
                    )
        elif isinstance(statement, exp.Create):
            target = _create_target(statement)
            if target is not None and _table_matches_context(target, context):
                kind = str(statement.args.get("kind", "dataset")).lower()
                if statement.args.get("replace"):
                    findings.append(
                        _destructive_table_finding(
                            context,
                            f"replace {kind}",
                            target.sql(),
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            severity="high",
                            code="create_existing_dataset_definition",
                            title="Dataset definition requires human review",
                            evidence=(
                                f"The migration creates {kind} `{target.sql()}` using the "
                                "selected existing DataHub dataset context."
                            ),
                            recommendation=(
                                "Confirm whether this is a new asset or a replacement. Use a new "
                                "URN for a new asset, or an explicit owner-approved replacement "
                                "plan for an existing contract."
                            ),
                        )
                    )

    for alter in _alter_statements(relevant_statements):
        if not _table_matches_context(alter.this, context):
            continue
        for action in alter.args.get("actions") or []:
            if (
                isinstance(action, exp.Drop)
                and str(action.args.get("kind", "")).upper() == "COLUMN"
            ):
                findings.append(
                    _destructive_finding(context, "drop column", _column_name(action.this))
                )
            elif isinstance(action, exp.RenameColumn):
                findings.append(
                    _destructive_finding(
                        context,
                        "rename column",
                        _column_name(action.this),
                        replacement=_column_name(action.args["to"]),
                    )
                )
            elif isinstance(action, exp.AlterColumn) and action.args.get("dtype") is not None:
                findings.append(
                    _destructive_finding(context, "alter column type", _column_name(action.this))
                )
            elif isinstance(action, exp.ModifyColumn):
                old_name, replacement = _modify_column_names(action)
                findings.append(
                    _destructive_finding(
                        context,
                        "alter column type",
                        old_name,
                        replacement=replacement,
                    )
                )
            elif isinstance(action, exp.AlterRename):
                findings.append(
                    _destructive_table_finding(
                        context,
                        "rename table",
                        alter.this.sql(),
                        replacement=action.this.sql(),
                    )
                )
            elif (
                isinstance(action, exp.ColumnDef)
                and action.find(exp.NotNullColumnConstraint)
                and not action.find(exp.DefaultColumnConstraint)
            ):
                column_name = _column_name(action.this)
                findings.append(
                    Finding(
                        severity="high",
                        code="not_null_without_default",
                        title="Non-null column is added without a default",
                        evidence=f"New column `{column_name}` is `NOT NULL` without a default.",
                        recommendation=(
                            "Add the column as nullable, backfill existing rows, validate completeness, "
                            "then add the non-null constraint in a later deployment."
                        ),
                    )
                )
            elif not isinstance(action, exp.ColumnDef):
                findings.append(
                    Finding(
                        severity="high",
                        code="unsupported_table_alteration",
                        title="Table alteration requires human review",
                        evidence=(
                            f"LineageGuard parsed but does not classify `{action.sql()}` "
                            f"on `{alter.this.sql()}`."
                        ),
                        recommendation=(
                            "Review the structured operation against the selected DataHub context "
                            "and add a dedicated policy before allowing automatic merge."
                        ),
                    )
                )

    if any(statement.find(exp.Star) for statement in relevant_statements):
        findings.append(
            Finding(
                severity="medium",
                code="select_star",
                title="Wildcard projection hides schema coupling",
                evidence="The SQL contains `SELECT *`, so new or reordered columns can leak downstream.",
                recommendation="List the required columns explicitly and preserve stable output names.",
            )
        )

    if relevant_statements and not context.owners:
        findings.append(
            Finding(
                severity="medium",
                code="missing_owner",
                title="No accountable DataHub owner",
                evidence=f"Dataset `{context.name}` has no owner in DataHub.",
                recommendation="Assign a technical or data owner before approving a breaking change.",
            )
        )

    if relevant_statements and context.metadata_gaps:
        findings.append(
            Finding(
                severity="high",
                code="incomplete_datahub_metadata",
                title="DataHub evidence is incomplete",
                evidence=" ".join(context.metadata_gaps),
                recommendation=(
                    "Resolve the metadata gap and rerun the review before approving the change; "
                    "do not treat missing lineage or schema evidence as proof of safety."
                ),
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
