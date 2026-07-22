# LineageGuard

LineageGuard is a DataHub-aware merge gate for SQL schema changes. It reads the target dataset's schema, governance metadata, owners, and downstream lineage, then turns a proposed migration into a reproducible risk report and a safe rollout plan.

The project targets the **Metadata-Aware Code Generation & Development** track of the 2026 DataHub Agent Hackathon.

## Why it exists

A syntactically valid migration can still break dashboards, models, and data contracts. Code review rarely has a current map of those consumers. LineageGuard brings DataHub context into the review before the change merges.

## What it checks

- dropped, renamed, and type-changed columns
- DataHub PII, sensitive, and glossary classifications
- table- and column-level downstream impact
- non-null additions without a safe backfill phase
- wildcard projections that create hidden schema coupling
- missing DataHub ownership

## Quick demo

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

lineageguard review \
  --sql examples/proposed_change.sql \
  --context examples/datahub_context.json \
  --out review-output/review.md \
  --json-out review-output/review.json
```

The bundled scenario tries to drop a PII-tagged email column used by a downstream churn feature table, adds a non-null column without a backfill, and creates a `SELECT *` view. LineageGuard blocks the change and identifies the affected DataHub assets.

See the committed [sample review](examples/sample_review.md) for the exact output.

## Interactive console

Run the local review console and open `http://127.0.0.1:8000`:

```bash
lineageguard serve
```

The console visualizes the DataHub blast radius from the changed field to downstream datasets and dashboards. Editing the migration and selecting **Trace impact** reruns the same analyzer used by the CLI.

## Connect to DataHub

Install the optional SDK and point the command at a DataHub dataset URN:

```bash
pip install -e ".[datahub,dev]"
export DATAHUB_TOKEN="<personal-access-token>"

lineageguard review \
  --sql migration.sql \
  --urn "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_orders,PROD)" \
  --server http://localhost:8080
```

The live provider uses the official DataHub Python SDK to retrieve schema, ownership, tags, glossary terms, and downstream lineage up to two hops. It requests column-level lineage only for fields changed by the proposed SQL, so wide schemas do not trigger a query for every field. The fixture mode exists so reviewers can reproduce the full decision path without credentials.

## Tests

```bash
pytest -q
ruff check .
ruff format --check .
```

## License

Apache License 2.0.
