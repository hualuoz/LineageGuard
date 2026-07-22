import asyncio
from types import SimpleNamespace

import pytest

from lineageguard.mcp_client import CORE_DATAHUB_TOOLS, connect_datahub_mcp, decode_tool_result


def test_decode_tool_result_prefers_structured_content() -> None:
    result = SimpleNamespace(
        isError=False,
        structuredContent={"urn": "urn:li:dataset:test"},
        content=[SimpleNamespace(text='{"ignored": true}')],
    )

    assert decode_tool_result(result) == {"urn": "urn:li:dataset:test"}


def test_decode_tool_result_unwraps_fastmcp_collection() -> None:
    result = SimpleNamespace(
        isError=False,
        structuredContent={"result": [{"urn": "urn:li:dataset:test"}]},
        content=[],
    )

    assert decode_tool_result(result) == [{"urn": "urn:li:dataset:test"}]


def test_decode_tool_result_falls_back_to_text_json() -> None:
    result = SimpleNamespace(
        isError=False,
        structuredContent=None,
        content=[SimpleNamespace(text='{"totalFields": 0, "fields": []}')],
    )

    assert decode_tool_result(result) == {"totalFields": 0, "fields": []}


def test_decode_tool_result_raises_mcp_error_text() -> None:
    result = SimpleNamespace(
        isError=True,
        structuredContent=None,
        content=[SimpleNamespace(text="permission denied")],
    )

    with pytest.raises(RuntimeError, match="permission denied"):
        decode_tool_result(result)


def test_connect_datahub_mcp_initializes_and_calls_tool(monkeypatch) -> None:
    import httpx
    import mcp
    import mcp.client.streamable_http as streamable_http_module

    observed: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, **kwargs) -> None:
            observed["http_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

    class AsyncContext:
        def __init__(self, value) -> None:
            self.value = value

        async def __aenter__(self):
            return self.value

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

    class FakeSession:
        def __init__(self, read_stream, write_stream) -> None:
            observed["streams"] = (read_stream, write_stream)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def initialize(self) -> None:
            observed["initialized"] = True

        async def list_tools(self):
            return SimpleNamespace(
                tools=[SimpleNamespace(name=name) for name in sorted(CORE_DATAHUB_TOOLS)]
            )

        async def call_tool(self, name: str, arguments: dict[str, object]):
            observed["call"] = (name, arguments)
            return SimpleNamespace(
                isError=False,
                structuredContent={"urn": "urn:li:dataset:test"},
                content=[],
            )

    def fake_streamable_http_client(url: str, *, http_client):
        observed["url"] = url
        observed["http_client"] = http_client
        return AsyncContext(("read", "write", lambda: None))

    monkeypatch.setattr(httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(mcp, "ClientSession", FakeSession)
    monkeypatch.setattr(
        streamable_http_module,
        "streamable_http_client",
        fake_streamable_http_client,
    )

    async def exercise() -> dict[str, str]:
        async with connect_datahub_mcp("https://mcp.example.test/mcp", "secret") as call:
            return await call("get_entities", {"urns": "urn:li:dataset:test"})

    assert asyncio.run(exercise()) == {"urn": "urn:li:dataset:test"}
    assert observed["url"] == "https://mcp.example.test/mcp"
    assert observed["streams"] == ("read", "write")
    assert observed["initialized"] is True
    assert observed["call"] == ("get_entities", {"urns": "urn:li:dataset:test"})
    assert observed["http_kwargs"]["headers"] == {"Authorization": "Bearer secret"}
