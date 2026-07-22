# DataHub MCP contract

Use the live schemas exposed by the official DataHub MCP Server as authoritative. The
signatures below match the open-source server and define the fields LineageGuard needs.

## Read calls

`get_entities`

```json
{"urns": ["urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.orders,PROD)"]}
```

Use the entity name or properties name, description, ownership, tags, and glossary terms.
The tool accepts one URN string or an array; prefer an array.

`list_schema_fields`

```json
{
  "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.orders,PROD)",
  "keywords": ["email", "status"],
  "limit": 100,
  "offset": 0
}
```

The response contains `fields`, `totalFields`, `returned`, `remainingCount`, and
`offset`. Continue with a larger offset while `remainingCount` is positive. When the
changed-column list is empty, omit `keywords` and retrieve the schema page needed for the
review.

`get_lineage`

```json
{
  "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.orders,PROD)",
  "column": null,
  "upstream": false,
  "max_hops": 2,
  "max_results": 100,
  "offset": 0
}
```

For column lineage, replace `column` with one changed existing field name. Downstream
results are under `downstreams.searchResults`; each result contains an entity and degree.
Keep at most two hops. Use `max_results: 100` and `offset: 0` once. In the current official
server, lineage `offset` is applied after a GraphQL request that still starts at zero, so a
normal second-page loop is unreliable. Compare `downstreams.total` with `returned` and the
length of `searchResults`, and inspect `hasMore` plus `truncatedDueToTokenBudget`. If any
signal shows more results, report the evidence as truncated instead of pretending the graph
is complete.

## LineageGuard context

Build this shape:

```json
{
  "urn": "<target dataset URN>",
  "name": "<dataset display or qualified name>",
  "description": "<dataset description or empty string>",
  "owners": ["<owner URN or display name>"],
  "tags": ["<dataset tag or glossary term>"],
  "columns": [
    {
      "name": "<fieldPath>",
      "native_type": "<nativeDataType or type>",
      "description": "<field description or empty string>",
      "tags": ["<field tag>"],
      "glossary_terms": ["<field glossary term>"],
      "downstream_assets": [
        {
          "urn": "<entity URN>",
          "name": "<entity display name>",
          "type": "<entity type>",
          "hops": 1
        }
      ]
    }
  ],
  "downstream_assets": [
    {
      "urn": "<entity URN>",
      "name": "<entity display name>",
      "type": "<entity type>",
      "hops": 1
    }
  ],
  "metadata_gaps": ["<explicit missing or truncated evidence>"],
  "source": "datahub-mcp"
}
```

Normalize field names case-insensitively, preserve original display names, deduplicate assets
by URN, and convert lineage degree to integer `hops`. Include only MCP-returned values.
Tags and terms may be returned as strings or nested objects; preserve their display name
when present, otherwise their URN.

Use an empty `metadata_gaps` list only when the requested schema and lineage evidence is
complete. Record every omitted, inconsistent, or truncated response there; the deterministic
gate treats any such gap as requiring manual review.

If a changed field is absent from `list_schema_fields`, include no invented column context.
The deterministic analyzer will still report the SQL operation without false DataHub claims.

## Approved writeback

After explicit confirmation, call:

```json
{
  "document_type": "Decision",
  "title": "LineageGuard review: <dataset> - <verdict>",
  "content": "<complete Markdown report>",
  "topics": ["lineageguard", "schema-change", "<verdict>"],
  "related_assets": ["<target dataset URN>"]
}
```

Mutation tools must be enabled on the DataHub MCP server. A successful response contains
`success: true` and the created document `urn`. Do not retry a failed mutation blindly.
