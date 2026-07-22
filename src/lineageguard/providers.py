from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

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


def write_context_fixture(context: DatasetContext, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context.model_dump(), indent=2) + "\n", encoding="utf-8")
