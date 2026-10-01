import json
from urllib.parse import parse_qs

import anyio
import pytest

pytest.importorskip("mcp")

from mcp import Client  # noqa: E402

from frappe_connector import FrappeConnector  # noqa: E402
from frappe_connector.mcp_server import build_server  # noqa: E402

from .conftest import BASE  # noqa: E402

WRITE_TOOLS = {
    "create_document",
    "update_document",
    "delete_document",
    "rename_document",
    "submit_document",
    "call_method",
}


def factory():
    return FrappeConnector(BASE, api_key="k", api_secret="s")


def call(server, name, arguments):
    async def go():
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    return anyio.run(go)


def list_tools(server):
    async def go():
        async with Client(server) as client:
            return (await client.list_tools()).tools

    return anyio.run(go)


def text(result):
    return result.content[0].text


def test_tools_and_annotations():
    tools = {t.name: t for t in list_tools(build_server(factory))}
    assert set(tools) == {"list_documents", "get_document"} | WRITE_TOOLS
    assert tools["list_documents"].annotations.read_only_hint is True
    assert tools["delete_document"].annotations.destructive_hint is True


def test_read_only_mode_hides_write_tools():
    names = {t.name for t in list_tools(build_server(factory, read_only=True))}
    assert names == {"list_documents", "get_document"}


def test_list_documents(mocked):
    mocked.get(f"{BASE}/api/resource/Customer", json={"data": [{"name": "C1"}]})
    result = call(build_server(factory), "list_documents", {"doctype": "Customer", "limit": 5})
    assert not result.is_error
    assert json.loads(text(result)) == [{"name": "C1"}]


def test_create_document_sets_doctype(mocked):
    mocked.post(f"{BASE}/api/resource/Customer", json={"data": {"name": "C1"}})
    result = call(
        build_server(factory),
        "create_document",
        {"doctype": "Customer", "data": {"customer_name": "Acme"}},
    )
    assert not result.is_error
    sent = json.loads(parse_qs(mocked.calls[0].request.body)["data"][0])
    assert sent == {"customer_name": "Acme", "doctype": "Customer"}


def test_server_error_is_reported_to_model(mocked):
    mocked.get(
        f"{BASE}/api/resource/Customer/X",
        json={
            "exc": '["Traceback (most recent call last):\\n  ...\\nfrappe.exceptions.DoesNotExistError: Customer X not found\\n"]',
            "exc_type": "DoesNotExistError",
        },
        status=404,
    )
    result = call(build_server(factory), "get_document", {"doctype": "Customer", "name": "X"})
    assert result.is_error
    assert "DoesNotExistError" in text(result)
    assert "Customer X not found" in text(result)


def test_connector_created_once_and_lazily(mocked):
    created = []

    def counting_factory():
        created.append(1)
        return factory()

    server = build_server(counting_factory)
    assert created == []
    mocked.get(f"{BASE}/api/resource/Customer", json={"data": []})

    async def go():
        async with Client(server) as client:
            await client.call_tool("list_documents", {"doctype": "Customer"})
            await client.call_tool("list_documents", {"doctype": "Customer"})

    anyio.run(go)
    assert created == [1]


def test_network_error_is_reported_to_model(mocked):
    import requests

    mocked.get(f"{BASE}/api/resource/Customer", body=requests.ConnectionError("refused"))
    result = call(build_server(factory), "list_documents", {"doctype": "Customer"})
    assert result.is_error
    assert "Could not reach the Frappe server" in text(result)
