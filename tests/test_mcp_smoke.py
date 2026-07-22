import os

import pytest

from lineageguard.providers import DataHubMCPContextProvider


MCP_URL = os.getenv("DATAHUB_MCP_URL")
MCP_TOKEN = os.getenv("DATAHUB_MCP_TOKEN")
TEST_URN = os.getenv("DATAHUB_MCP_TEST_URN")


@pytest.mark.skipif(
    not all((MCP_URL, MCP_TOKEN, TEST_URN)),
    reason=(
        "set DATAHUB_MCP_URL, DATAHUB_MCP_TOKEN, and DATAHUB_MCP_TEST_URN "
        "to run the live DataHub MCP smoke test"
    ),
)
def test_live_datahub_mcp_context_smoke() -> None:
    provider = DataHubMCPContextProvider(url=MCP_URL or "", token=MCP_TOKEN)

    context = provider.get_dataset_context(TEST_URN)

    assert context.urn == TEST_URN
    assert context.source == "datahub-mcp"
    assert context.columns
    assert provider.lineage_metadata["dataset"]["pagination"] == "single-request"
