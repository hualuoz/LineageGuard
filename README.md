# LineageGuard

LineageGuard is a DataHub-powered agent and merge gate for SQL schema changes. It retrieves
catalog context through the official DataHub MCP Server, traces downstream blast radius, and
turns a proposed migration into a reproducible merge verdict. A blocking verdict can fail a
GitHub check; after explicit approval, the agent can save the review decision back to DataHub.

The project targets **Agents That Do Real Work** in the 2026 DataHub Agent Hackathon.

## Read, decide, act

1. The bundled Agent Skill calls DataHub MCP `get_entities`, `list_schema_fields`, and
   table- and column-level `get_lineage`.
2. The deterministic Python policy engine parses the SQL and scores only evidence tied to
   the target dataset.
3. The composite GitHub Action exits nonzero for a blocking verdict, preventing an unsafe
   migration from merging.
4. With explicit user approval, the Skill calls DataHub MCP `save_document` so the decision
   and its evidence remain attached to the affected asset.

This separation keeps catalog access agentic while making the final policy decision
reproducible in local development and CI.

## What it checks

- dropped, renamed, and type-changed columns;
- dropped, renamed, truncated, or replaced tables and views;
- container-level schema or database drops;
- DataHub PII, sensitive, and glossary classifications;
- table- and column-level downstream impact;
- non-null additions without a safe backfill phase;
- wildcard projections that create hidden schema coupling;
- missing DataHub ownership;
- SQL that targets a different table than the selected DataHub dataset.

SQL comments and string literals are not treated as migrations, and empty input does not
crash the reviewer.

## Reproduce the demo locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

lineageguard review \
  --sql examples/proposed_change.sql \
  --context examples/datahub_context.json \
  --urn "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_orders,PROD)" \
  --out review-output/review.md \
  --json-out review-output/review.json \
  --require-pass
```

The command intentionally exits with status 2. The bundled scenario tries to drop a
PII-tagged email column used by a downstream churn feature table, adds a non-null column
without a backfill, and creates a `SELECT *` view. See the committed
[sample review](examples/sample_review.md) and
[machine-readable report](examples/sample_review.json) for the expected evidence.

Fixture mode is a credential-free replay for judges. It is not presented as a live DataHub
connection.

## Run the DataHub Agent Skill

The installable project Skill is at
[.agents/skills/lineageguard-review](.agents/skills/lineageguard-review/SKILL.md). Its metadata
declares the official universal DataHub MCP Server at `https://mcp.datahub.com/mcp`; an
OAuth-capable agent host performs the interactive authorization flow.

After connecting an MCP-compatible agent to DataHub, ask:

```text
Use $lineageguard-review to review migration.sql against
urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_orders,PROD).
```

The Skill gathers the changed fields, paginates schema responses, writes a temporary
context file, runs the deterministic gate, and returns one of `block`, `manual_review`, or
`pass_with_checks`. DataHub writeback is deliberately confirmation-gated because it changes
catalog state.

The same official MCP path can run directly from the CLI:

```bash
pip install -e ".[mcp,dev]"
export DATAHUB_MCP_URL="https://<tenant>.acryl.io/integrations/ai/mcp/"
export DATAHUB_MCP_TOKEN="<personal-access-token>"

lineageguard review \
  --sql migration.sql \
  --urn "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_orders,PROD)" \
  --require-pass
```

The standalone CLI uses the tenant-specific MCP endpoint with a static Bearer token, read
only from the environment; it does not implement the universal endpoint's browser OAuth
flow. If DataHub truncates lineage or omits schema evidence, LineageGuard records the gap in
the report and requires manual review.

## Block a pull request

The repository is also a composite GitHub Action:

```yaml
- uses: hualuoz/LineageGuard@main
  with:
    sql-file: migrations/proposed_change.sql
    context-file: .lineageguard/datahub-context.json
    dialect: snowflake

- name: Upload review evidence
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: lineageguard-review
    path: review-output/
```

The complete consumer workflow is in
[examples/github-actions/lineageguard.yml](examples/github-actions/lineageguard.yml). In a live
setup, generate the short-lived context file with the Agent Skill before invoking the action;
do not commit private catalog metadata.

## Interactive console

Run the local review console and open `http://127.0.0.1:8000`:

```bash
lineageguard serve
```

Editing the migration and selecting **Trace impact** reruns the same analyzer used by the CLI
and GitHub Action.

## Direct DataHub SDK provider

For non-agent automation, LineageGuard retains a direct provider based on the official
DataHub Python SDK:

```bash
pip install -e ".[datahub,dev]"
export DATAHUB_TOKEN="<personal-access-token>"

lineageguard review \
  --sql migration.sql \
  --urn "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_orders,PROD)" \
  --server http://localhost:8080
```

The SDK provider retrieves schema, ownership, tags, glossary terms, and downstream lineage
up to two hops. The DataHub MCP Agent Skill is the hackathon integration and the recommended
interactive path.

## Demo video

The repository includes the complete [Remotion source](demo-video/README.md) for a 66-second,
1080p walkthrough. The final submission video also includes a real console run so reviewers
can see the project functioning, not only animated product frames.

## Verify

```bash
pytest -q
ruff check .
ruff format --check .
python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .agents/skills/lineageguard-review
```

CI runs the tests, lint checks, fixture replay, and the composite merge-gate action.

## License

Apache License 2.0.
