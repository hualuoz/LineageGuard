from __future__ import annotations

from lineageguard.models import ReviewReport


def render_markdown(report: ReviewReport) -> str:
    lines = [
        "# LineageGuard review",
        "",
        f"**Verdict:** `{report.verdict}`  ",
        f"**Risk score:** `{report.risk_score}/100`  ",
        f"**Dataset:** `{report.dataset.name}`  ",
        f"**Context source:** `{report.dataset.source}`",
        "",
        report.summary,
        "",
        "## Findings",
        "",
    ]
    if not report.findings:
        lines.append("No blocking patterns were detected.")
    for index, finding in enumerate(report.findings, 1):
        lines.extend(
            [
                f"### {index}. [{finding.severity.upper()}] {finding.title}",
                "",
                f"- Code: `{finding.code}`",
                f"- Evidence: {finding.evidence}",
                f"- Recommendation: {finding.recommendation}",
            ]
        )
        if finding.affected_assets:
            lines.append(
                "- Affected assets: "
                + ", ".join(
                    f"`{asset.name}` ({asset.hops} hop)" for asset in finding.affected_assets
                )
            )
        lines.append("")

    lines.extend(["## Safe migration plan", ""])
    lines.extend(f"{index}. {step}" for index, step in enumerate(report.safe_migration_plan, 1))
    lines.extend(
        [
            "",
            "---",
            "Generated from DataHub schema, governance, and downstream lineage context.",
            "",
        ]
    )
    return "\n".join(lines)
