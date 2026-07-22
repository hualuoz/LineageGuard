# LineageGuard review

**Verdict:** `block`  
**Risk score:** `75/100`  
**Dataset:** `analytics.customer_orders`  
**Context source:** `datahub-export`

3 finding(s) across 3 parsed statement(s); DataHub reports 2 downstream asset(s).

## Findings

### 1. [CRITICAL] Drop Column can break downstream consumers

- Code: `destructive_drop_column`
- Evidence: Column `email` is targeted by `drop column`. DataHub classifies it with urn:li:tag:PII, urn:li:tag:Sensitive, urn:li:glossaryTerm:PersonalEmail. DataHub lineage shows 1 downstream asset(s): ml.churn_features.
- Recommendation: Use an expand-and-contract migration: add the replacement, backfill it, dual-write, migrate every downstream consumer, and remove the old column only after DataHub lineage and usage checks are clean.
- Affected assets: `ml.churn_features` (1 hop)

### 2. [HIGH] Non-null column is added without a default

- Code: `not_null_without_default`
- Evidence: New column `lifecycle_status` is `NOT NULL` without a default.
- Recommendation: Add the column as nullable, backfill existing rows, validate completeness, then add the non-null constraint in a later deployment.

### 3. [MEDIUM] Wildcard projection hides schema coupling

- Code: `select_star`
- Evidence: The SQL contains `SELECT *`, so new or reordered columns can leak downstream.
- Recommendation: List the required columns explicitly and preserve stable output names.

## Safe migration plan

1. Create an additive schema change and keep the current contract intact.
2. Backfill and validate the replacement using explicit row-count and null checks.
3. Notify DataHub owners and migrate the listed downstream assets.
4. Run the review again after DataHub lineage and usage metadata refresh.
5. Remove the old field only after a monitored compatibility window and rollback checkpoint.

---
Generated from DataHub schema, governance, and downstream lineage context.
