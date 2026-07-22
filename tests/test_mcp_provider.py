from __future__ import annotations

from typing import Any

import pytest

from lineageguard.providers import DataHubMCPContextProvider


URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_orders,PROD)"


class FakeToolCall:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        if name == "get_entities":
            return {
                "urn": URN,
                "type": "DATASET",
                "name": "customer_orders_raw",
                "editableProperties": {
                    "name": "customer_orders",
                    "description": "Curated order contracts.",
                },
                "ownership": {"owners": [{"owner": {"urn": "urn:li:corpuser:data-platform"}}]},
                "tags": {
                    "tags": [
                        {
                            "tag": {
                                "urn": "urn:li:tag:PII",
                                "properties": {"name": "PII"},
                            }
                        }
                    ]
                },
                "glossaryTerms": {
                    "terms": [
                        {
                            "term": {
                                "urn": "urn:li:glossaryTerm:CustomerData",
                                "properties": {"name": "Customer Data"},
                            }
                        }
                    ]
                },
            }

        if name == "list_schema_fields":
            if arguments["offset"] == 0:
                return {
                    "urn": URN,
                    "fields": [
                        {
                            "fieldPath": "email",
                            "nativeDataType": "VARCHAR",
                            "description": "System description",
                            "editedDescription": "Customer contact email",
                            "tags": {
                                "tags": [
                                    {
                                        "tag": {
                                            "urn": "urn:li:tag:PII",
                                            "properties": {"name": "PII"},
                                        }
                                    }
                                ]
                            },
                            "editedTags": ["Sensitive"],
                            "glossaryTerms": {
                                "terms": [
                                    {
                                        "term": {
                                            "urn": "urn:li:glossaryTerm:EmailAddress",
                                            "properties": {"name": "Email Address"},
                                        }
                                    }
                                ]
                            },
                        }
                    ],
                    "totalFields": 2,
                    "returned": 1,
                    "remainingCount": 1,
                    "matchingCount": None,
                    "offset": 0,
                }
            return {
                "urn": URN,
                "fields": [{"fieldPath": "status", "type": "STRING"}],
                "totalFields": 2,
                "returned": 1,
                "remainingCount": 0,
                "matchingCount": None,
                "offset": 1,
            }

        if name == "get_lineage" and arguments["column"] is None:
            return {
                "downstreams": {
                    "total": 2,
                    "returned": 2,
                    "searchResults": [
                        {
                            "entity": {
                                "urn": "urn:li:dataset:warehouse_orders",
                                "type": "DATASET",
                                "properties": {"name": "warehouse.orders"},
                            },
                            "degree": 1,
                        },
                        {
                            "entity": {
                                "urn": "urn:li:dashboard:revenue",
                                "type": "DASHBOARD",
                                "properties": {"name": "Revenue dashboard"},
                            },
                            "degree": 2,
                        },
                    ],
                }
            }

        if name == "get_lineage" and arguments["column"] == "email":
            return {
                "downstreams": {
                    "total": 3,
                    "returned": 1,
                    "truncatedDueToTokenBudget": True,
                    "searchResults": [
                        {
                            "entity": {
                                "urn": "urn:li:dataset:churn_features",
                                "type": "DATASET",
                                "name": "ml.churn_features",
                            },
                            "degree": 1,
                            "lineageColumns": ["contact_email"],
                        }
                    ],
                }
            }

        raise AssertionError(f"Unexpected tool call: {name} {arguments}")


def test_mcp_provider_maps_context_and_exposes_lineage_gap() -> None:
    fake = FakeToolCall()
    provider = DataHubMCPContextProvider(
        url="https://example.acryl.io/integrations/ai/mcp/",
        token="not-used-by-fake",
        tool_call=fake,
    )

    context = provider.get_dataset_context(URN, columns={"EMAIL"})

    assert context.source == "datahub-mcp"
    assert context.name == "customer_orders"
    assert context.description == "Curated order contracts."
    assert context.owners == ["urn:li:corpuser:data-platform"]
    assert context.tags == ["PII", "Customer Data"]
    assert [column.name for column in context.columns] == ["email", "status"]
    email = context.column("email")
    assert email is not None
    assert email.native_type == "VARCHAR"
    assert email.description == "Customer contact email"
    assert email.tags == ["PII", "Sensitive"]
    assert email.downstream_assets[0].name == "ml.churn_features"
    assert [asset.name for asset in context.downstream_assets] == [
        "warehouse.orders",
        "Revenue dashboard",
    ]

    assert provider.lineage_metadata["dataset"] == {
        "total": 2,
        "reportedReturned": 2,
        "observedResults": 2,
        "hasMore": False,
        "truncated": False,
        "metadataGap": False,
        "pagination": "single-request",
    }
    assert provider.lineage_metadata["column:email"]["truncated"] is True
    assert any("column:email is incomplete" in gap for gap in provider.metadata_gaps)
    assert context.metadata_gaps == provider.metadata_gaps

    assert fake.calls == [
        ("get_entities", {"urns": URN}),
        (
            "list_schema_fields",
            {"urn": URN, "keywords": ["email"], "limit": 100, "offset": 0},
        ),
        (
            "list_schema_fields",
            {"urn": URN, "keywords": ["email"], "limit": 100, "offset": 1},
        ),
        (
            "get_lineage",
            {
                "urn": URN,
                "column": None,
                "upstream": False,
                "max_hops": 2,
                "max_results": 100,
                "offset": 0,
            },
        ),
        (
            "get_lineage",
            {
                "urn": URN,
                "column": "email",
                "upstream": False,
                "max_hops": 2,
                "max_results": 100,
                "offset": 0,
            },
        ),
    ]


def test_mcp_provider_reports_missing_targeted_column() -> None:
    fake = FakeToolCall()
    provider = DataHubMCPContextProvider(
        url="https://example.acryl.io/integrations/ai/mcp/",
        tool_call=fake,
    )

    context = provider.get_dataset_context(URN, columns={"missing_column"})

    assert context.column("missing_column") is None
    assert any("missing_column" in gap for gap in provider.metadata_gaps)
    assert all(
        arguments.get("column") != "missing_column"
        for name, arguments in fake.calls
        if name == "get_lineage"
    )


def test_empty_lineage_is_complete_without_pagination_warning() -> None:
    async def call(name: str, arguments: dict[str, Any]) -> Any:
        if name == "get_entities":
            return {"urn": URN, "type": "DATASET", "name": "customer_orders"}
        if name == "list_schema_fields":
            return {
                "urn": URN,
                "fields": [],
                "totalFields": 0,
                "returned": 0,
                "remainingCount": 0,
                "matchingCount": None,
                "offset": arguments["offset"],
            }
        if name == "get_lineage":
            return {"downstreams": {"total": 0}}
        raise AssertionError(name)

    provider = DataHubMCPContextProvider(
        url="https://example.acryl.io/integrations/ai/mcp/",
        tool_call=call,
    )

    context = provider.get_dataset_context(URN)

    assert context.downstream_assets == []
    assert provider.lineage_metadata["dataset"]["reportedReturned"] == 0
    assert provider.metadata_gaps == []


def test_has_more_marks_lineage_as_truncated() -> None:
    async def call(name: str, arguments: dict[str, Any]) -> Any:
        if name == "get_entities":
            return {"urn": URN, "type": "DATASET", "name": "customer_orders"}
        if name == "list_schema_fields":
            return {
                "urn": URN,
                "fields": [],
                "totalFields": 0,
                "returned": 0,
                "remainingCount": 0,
                "offset": arguments["offset"],
            }
        if name == "get_lineage":
            return {
                "downstreams": {
                    "total": 1,
                    "returned": 1,
                    "hasMore": True,
                    "searchResults": [
                        {
                            "entity": {
                                "urn": "urn:li:dashboard:revenue",
                                "type": "DASHBOARD",
                                "name": "Revenue",
                            },
                            "degree": 1,
                        }
                    ],
                }
            }
        raise AssertionError(name)

    provider = DataHubMCPContextProvider(
        url="https://example.acryl.io/integrations/ai/mcp/",
        tool_call=call,
    )

    context = provider.get_dataset_context(URN)

    assert context.downstream_assets[0].name == "Revenue"
    assert provider.lineage_metadata["dataset"]["hasMore"] is True
    assert provider.lineage_metadata["dataset"]["truncated"] is True
    assert any("dataset is incomplete" in gap for gap in provider.metadata_gaps)


@pytest.mark.parametrize(
    "entity",
    [
        {"urn": "urn:li:dashboard:wrong", "type": "DASHBOARD"},
        {"urn": URN, "type": "DASHBOARD"},
    ],
)
def test_mcp_provider_rejects_wrong_entity_identity(entity: dict[str, str]) -> None:
    async def call(name: str, arguments: dict[str, Any]) -> Any:
        assert name == "get_entities"
        return entity

    provider = DataHubMCPContextProvider(
        url="https://example.acryl.io/integrations/ai/mcp/",
        tool_call=call,
    )

    with pytest.raises(RuntimeError):
        provider.get_dataset_context(URN)
