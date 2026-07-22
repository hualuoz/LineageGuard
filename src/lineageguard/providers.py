from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from lineageguard.mcp_client import ToolCall, connect_datahub_mcp
from lineageguard.models import AssetReference, ColumnContext, DatasetContext


class ContextProvider(Protocol):
    def get_dataset_context(
        self, urn: str | None = None, columns: set[str] | None = None
    ) -> DatasetContext: ...


class FixtureContextProvider:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_dataset_context(
        self, urn: str | None = None, columns: set[str] | None = None
    ) -> DatasetContext:
        context = DatasetContext.model_validate_json(self.path.read_text(encoding="utf-8"))
        if urn and context.urn != urn:
            raise ValueError(f"fixture contains {context.urn!r}, not requested URN {urn!r}")
        return context


class DataHubContextProvider:
    """Read schema, governance, and downstream lineage from a DataHub instance."""

    def __init__(self, server: str, token: str | None = None, max_hops: int = 2) -> None:
        try:
            from datahub.ingestion.graph.client import DatahubClientConfig, DataHubGraph
            from datahub.sdk import DataHubClient
        except ImportError as exc:  # pragma: no cover - depends on optional package
            raise RuntimeError('Install DataHub support with: pip install -e ".[datahub]"') from exc

        self.graph = DataHubGraph(config=DatahubClientConfig(server=server, token=token))
        self.client = DataHubClient(server=server, token=token)
        self.max_hops = max_hops

    def get_dataset_context(
        self, urn: str | None = None, columns: set[str] | None = None
    ) -> DatasetContext:
        if not urn:
            raise ValueError("a DataHub dataset URN is required")

        from datahub.metadata.schema_classes import (
            DatasetPropertiesClass,
            GlobalTagsClass,
            GlossaryTermsClass,
            OwnershipClass,
            SchemaMetadataClass,
        )

        schema = self.graph.get_aspect(urn, SchemaMetadataClass)
        if schema is None:
            raise ValueError(f"DataHub returned no schema metadata for {urn}")

        properties = self.graph.get_aspect(urn, DatasetPropertiesClass)
        ownership = self.graph.get_aspect(urn, OwnershipClass)
        global_tags = self.graph.get_aspect(urn, GlobalTagsClass)
        glossary_terms = self.graph.get_aspect(urn, GlossaryTermsClass)

        def lineage_assets(source_column: str | None = None) -> list[AssetReference]:
            return [
                AssetReference(
                    urn=str(item.urn),
                    name=str(item.name or item.urn),
                    type=str(item.type or "UNKNOWN"),
                    hops=int(item.hops or 1),
                )
                for item in self.client.lineage.get_lineage(
                    source_urn=urn,
                    source_column=source_column,
                    direction="downstream",
                    max_hops=self.max_hops,
                )
            ]

        downstream = lineage_assets()

        columns = {column.lower() for column in (columns or set())}
        column_contexts = []
        for field in schema.fields:
            field_name = str(field.fieldPath)
            field_tags = getattr(getattr(field, "globalTags", None), "tags", None) or []
            field_terms = getattr(getattr(field, "glossaryTerms", None), "terms", None) or []
            column_contexts.append(
                ColumnContext(
                    name=field_name,
                    native_type=str(field.nativeDataType or "unknown"),
                    description=str(field.description or ""),
                    tags=[str(tag.tag) for tag in field_tags],
                    glossary_terms=[str(term.urn) for term in field_terms],
                    downstream_assets=(
                        lineage_assets(source_column=field_name)
                        if field_name.lower() in columns
                        else []
                    ),
                )
            )

        owners = [str(owner.owner) for owner in (getattr(ownership, "owners", None) or [])]
        tags = [str(tag.tag) for tag in (getattr(global_tags, "tags", None) or [])]
        terms = [str(term.urn) for term in (getattr(glossary_terms, "terms", None) or [])]
        tags.extend(terms)

        return DatasetContext(
            urn=urn,
            name=str(getattr(properties, "name", None) or urn),
            description=str(getattr(properties, "description", None) or ""),
            owners=owners,
            tags=tags,
            columns=column_contexts,
            downstream_assets=downstream,
            source="datahub",
        )


class DataHubMCPContextProvider:
    """Read schema and downstream lineage through the official DataHub MCP server."""

    def __init__(
        self,
        url: str,
        token: str | None = None,
        max_hops: int = 2,
        tool_call: ToolCall | None = None,
    ) -> None:
        if max_hops < 1:
            raise ValueError("max_hops must be at least 1")
        self.url = url
        self.token = token
        self.max_hops = max_hops
        self._tool_call = tool_call
        self.lineage_metadata: dict[str, dict[str, object]] = {}
        self.metadata_gaps: list[str] = []

    def get_dataset_context(
        self, urn: str | None = None, columns: set[str] | None = None
    ) -> DatasetContext:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aget_dataset_context(urn, columns))
        raise RuntimeError(
            "get_dataset_context cannot run inside an event loop; use aget_dataset_context instead"
        )

    async def aget_dataset_context(
        self, urn: str | None = None, columns: set[str] | None = None
    ) -> DatasetContext:
        if not urn:
            raise ValueError("a DataHub dataset URN is required")

        self.lineage_metadata.clear()
        self.metadata_gaps.clear()
        if self._tool_call is not None:
            return await self._load_context(self._tool_call, urn, columns or set())

        async with connect_datahub_mcp(self.url, self.token) as tool_call:
            return await self._load_context(tool_call, urn, columns or set())

    async def _load_context(
        self, tool_call: ToolCall, urn: str, columns: set[str]
    ) -> DatasetContext:
        entity = await tool_call("get_entities", {"urns": urn})
        if not isinstance(entity, dict):
            raise RuntimeError("DataHub MCP get_entities returned a non-object payload")
        if error := entity.get("error"):
            raise RuntimeError(f"DataHub MCP get_entities failed: {error}")
        if entity.get("urn") != urn:
            raise RuntimeError(
                f"DataHub MCP get_entities returned an unexpected entity URN: {entity.get('urn')!r}"
            )
        if str(entity.get("type") or "").upper() != "DATASET":
            raise RuntimeError(
                f"DataHub MCP get_entities must return a DATASET, not {entity.get('type')!r}"
            )

        targeted = {column.lower() for column in columns}
        fields = await self._load_schema_fields(tool_call, urn, targeted)
        downstream = await self._load_downstream_assets(tool_call, urn, column=None)

        found_targeted: set[str] = set()
        column_contexts: list[ColumnContext] = []
        for field in fields:
            field_path = field.get("fieldPath")
            if not field_path:
                self._add_gap("DataHub MCP returned a schema field without fieldPath")
                continue

            name = str(field_path)
            normalized_name = name.lower()
            column_downstream: list[AssetReference] = []
            if normalized_name in targeted:
                found_targeted.add(normalized_name)
                column_downstream = await self._load_downstream_assets(tool_call, urn, column=name)

            column_contexts.append(
                ColumnContext(
                    name=name,
                    native_type=str(field.get("nativeDataType") or field.get("type") or "unknown"),
                    description=str(
                        field.get("editedDescription") or field.get("description") or ""
                    ),
                    tags=_unique_strings(
                        _tag_names(field) + _tag_names({"tags": field.get("editedTags")})
                    ),
                    glossary_terms=_unique_strings(
                        _glossary_term_names(field)
                        + _glossary_term_names({"glossaryTerms": field.get("editedGlossaryTerms")})
                    ),
                    downstream_assets=column_downstream,
                )
            )

        if missing_columns := sorted(targeted - found_targeted):
            self._add_gap(
                "DataHub MCP schema did not contain targeted column(s): "
                + ", ".join(missing_columns)
            )

        return DatasetContext(
            urn=urn,
            name=_entity_name(entity, urn),
            description=_entity_description(entity),
            owners=_owner_urns(entity),
            tags=_unique_strings(_tag_names(entity) + _glossary_term_names(entity)),
            columns=column_contexts,
            downstream_assets=downstream,
            metadata_gaps=list(self.metadata_gaps),
            source="datahub-mcp",
        )

    async def _load_schema_fields(
        self, tool_call: ToolCall, urn: str, columns: set[str]
    ) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        offset = 0
        limit = 100

        while True:
            page = await tool_call(
                "list_schema_fields",
                {
                    "urn": urn,
                    "keywords": sorted(columns) or None,
                    "limit": limit,
                    "offset": offset,
                },
            )
            if not isinstance(page, dict):
                raise RuntimeError("DataHub MCP list_schema_fields returned a non-object payload")

            page_fields = page.get("fields") or []
            if not isinstance(page_fields, list):
                raise RuntimeError("DataHub MCP schema fields payload is not a list")
            valid_fields = [field for field in page_fields if isinstance(field, dict)]
            fields.extend(valid_fields)

            observed = len(page_fields)
            if len(valid_fields) != observed:
                self._add_gap(
                    "DataHub MCP schema response contained "
                    f"{observed - len(valid_fields)} invalid field item(s) at offset {offset}"
                )
            returned = _optional_int(page.get("returned"))
            remaining = _optional_int(page.get("remainingCount"))
            total = _optional_int(page.get("totalFields"))
            if returned is None:
                self._add_gap(f"DataHub MCP schema response omitted returned at offset {offset}")
            elif returned != observed:
                self._add_gap(
                    "DataHub MCP schema metadata reported "
                    f"returned={returned}, but supplied {observed} field(s) at offset {offset}"
                )

            if remaining is not None and remaining <= 0:
                break

            next_offset = offset + observed
            if total is not None and next_offset >= total:
                break
            if observed == 0:
                if (remaining or 0) > 0 or (total or 0) > offset:
                    self._add_gap(
                        "DataHub MCP schema pagination stopped after an empty page "
                        f"at offset {offset}"
                    )
                break
            if remaining is None and total is None:
                self._add_gap(
                    "DataHub MCP schema response omitted both remainingCount and totalFields; "
                    "only the first page is available"
                )
                break
            offset = next_offset

        return fields

    async def _load_downstream_assets(
        self, tool_call: ToolCall, urn: str, column: str | None
    ) -> list[AssetReference]:
        response = await tool_call(
            "get_lineage",
            {
                "urn": urn,
                "column": column,
                "upstream": False,
                "max_hops": self.max_hops,
                "max_results": 100,
                "offset": 0,
            },
        )
        if not isinstance(response, dict):
            raise RuntimeError("DataHub MCP get_lineage returned a non-object payload")

        label = f"column:{column}" if column else "dataset"
        downstream = response.get("downstreams")
        if not isinstance(downstream, dict):
            self.lineage_metadata[label] = {
                "total": None,
                "reportedReturned": None,
                "observedResults": 0,
                "truncated": False,
                "metadataGap": True,
                "pagination": "single-request",
            }
            self._add_gap(f"DataHub MCP lineage response omitted downstream metadata for {label}")
            return []

        raw_results = downstream.get("searchResults") or []
        if not isinstance(raw_results, list):
            raise RuntimeError("DataHub MCP downstream searchResults is not a list")
        results = [item for item in raw_results if isinstance(item, dict)]
        observed = len(raw_results)
        if len(results) != observed:
            self._add_gap(
                f"DataHub MCP lineage for {label} contained "
                f"{observed - len(results)} invalid result item(s)"
            )
        total = _optional_int(downstream.get("total"))
        reported_returned = _optional_int(downstream.get("returned"))
        if reported_returned is None and total == 0 and observed == 0:
            # The DataHub server omits pagination fields when searchResults is empty.
            reported_returned = 0
        token_truncated = bool(downstream.get("truncatedDueToTokenBudget"))
        has_more = bool(downstream.get("hasMore"))
        truncated = token_truncated or has_more or (total is not None and total > observed)
        metadata_gap = total is None or reported_returned is None

        self.lineage_metadata[label] = {
            "total": total,
            "reportedReturned": reported_returned,
            "observedResults": observed,
            "hasMore": has_more,
            "truncated": truncated,
            "metadataGap": metadata_gap,
            "pagination": "single-request",
        }

        if total is None:
            self._add_gap(f"DataHub MCP lineage response omitted total for {label}")
        if reported_returned is None:
            self._add_gap(f"DataHub MCP lineage response omitted returned for {label}")
        elif reported_returned != observed:
            self._add_gap(
                f"DataHub MCP lineage metadata for {label} reported "
                f"returned={reported_returned}, but supplied {observed} result(s)"
            )
        if truncated:
            reason = "token budget" if token_truncated else "server result limit"
            self._add_gap(
                f"DataHub MCP lineage for {label} is incomplete ({observed} of "
                f"{total if total is not None else 'unknown'} result(s), {reason}); "
                "offset pagination is not used because the current server implementation "
                "does not reliably page lineage"
            )

        return _dedupe_assets(_asset_from_lineage_result(item) for item in results)

    def _add_gap(self, message: str) -> None:
        if message not in self.metadata_gaps:
            self.metadata_gaps.append(message)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _entity_name(entity: dict[str, Any], fallback: str) -> str:
    editable = entity.get("editableProperties") or {}
    properties = entity.get("properties") or {}
    return str(editable.get("name") or properties.get("name") or entity.get("name") or fallback)


def _entity_description(entity: dict[str, Any]) -> str:
    editable = entity.get("editableProperties") or {}
    properties = entity.get("properties") or {}
    return str(
        editable.get("description")
        or properties.get("description")
        or entity.get("description")
        or ""
    )


def _owner_urns(entity: dict[str, Any]) -> list[str]:
    ownership = entity.get("ownership") or {}
    owners = ownership.get("owners") or []
    return _unique_strings(
        [
            str(owner_urn)
            for entry in owners
            if isinstance(entry, dict)
            and isinstance(entry.get("owner"), dict)
            and (owner_urn := entry["owner"].get("urn"))
        ]
    )


def _tag_names(entity: dict[str, Any]) -> list[str]:
    raw_tags = entity.get("tags") or []
    tags = raw_tags.get("tags") or [] if isinstance(raw_tags, dict) else raw_tags
    names: list[str] = []
    for entry in tags:
        if isinstance(entry, str):
            names.append(entry)
            continue
        tag = entry.get("tag") if isinstance(entry, dict) else None
        if isinstance(tag, str):
            names.append(tag)
            continue
        if not isinstance(tag, dict):
            tag = entry if isinstance(entry, dict) else None
        if not isinstance(tag, dict):
            continue
        properties = tag.get("properties") or {}
        if value := properties.get("name") or tag.get("name") or tag.get("urn"):
            names.append(str(value))
    return names


def _glossary_term_names(entity: dict[str, Any]) -> list[str]:
    raw_terms = entity.get("glossaryTerms") or []
    terms = raw_terms.get("terms") or [] if isinstance(raw_terms, dict) else raw_terms
    names: list[str] = []
    for entry in terms:
        if isinstance(entry, str):
            names.append(entry)
            continue
        term = entry.get("term") if isinstance(entry, dict) else None
        if isinstance(term, str):
            names.append(term)
            continue
        if not isinstance(term, dict):
            term = entry if isinstance(entry, dict) else None
        if not isinstance(term, dict):
            continue
        properties = term.get("properties") or {}
        if value := properties.get("name") or term.get("hierarchicalName") or term.get("urn"):
            names.append(str(value))
    return names


def _asset_from_lineage_result(result: dict[str, Any]) -> AssetReference | None:
    entity = result.get("entity")
    if not isinstance(entity, dict) or not entity.get("urn"):
        return None
    hops = _optional_int(result.get("degree")) or 1
    return AssetReference(
        urn=str(entity["urn"]),
        name=_entity_name(entity, str(entity["urn"])),
        type=str(entity.get("type") or "UNKNOWN"),
        hops=max(1, hops),
    )


def _dedupe_assets(
    assets: Iterable[AssetReference | None],
) -> list[AssetReference]:
    unique: dict[str, AssetReference] = {}
    for asset in assets:
        if asset is not None:
            unique.setdefault(asset.urn, asset)
    return list(unique.values())


def write_context_fixture(context: DatasetContext, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context.model_dump(), indent=2) + "\n", encoding="utf-8")
