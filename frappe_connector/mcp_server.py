"""MCP server exposing a Frappe site's documents and API methods as tools.

Requires the optional dependency: ``pip install "frappe-connector[mcp]"``.
Connection settings come from the FRAPPE_* environment variables described in
:mod:`frappe_connector.config`. Run ``frappe-connector-mcp --help`` for options.
"""

import argparse
import functools
import json
import os
import sys
from typing import Any, Literal

import requests

try:
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations
except ImportError:  # pragma: no cover - exercised only without the extra
    sys.exit(
        'The MCP server needs the "mcp" extra: pip install "frappe-connector[mcp]"'
    )

from . import config
from .connector import FrappeConnector, FrappeException, ServerError

INSTRUCTIONS = """\
Tools for reading and changing data on a Frappe / ERPNext site.
Records are "documents" grouped by "doctype" (e.g. Customer, Sales Invoice).
Filters use Frappe syntax: {"status": "Active"} or [["grand_total", ">", 1000]].
Use list_documents with a small limit and explicit fields before fetching whole documents.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)


def _error_text(exc: Exception) -> str:
    if isinstance(exc, ServerError):
        # Frappe sends the whole server traceback; its last line is the useful part.
        lines = [line for line in str(exc).strip().splitlines() if line.strip()]
        last = lines[-1].strip(' "[]\\n') if lines else ""
        return f"Frappe server error ({exc.exc_type or 'unknown'}): {last}"
    if isinstance(exc, requests.RequestException):
        return f"Could not reach the Frappe server ({type(exc).__name__}): {exc}"
    return str(exc)


def _as_tool(fn):
    """Return results as one JSON text block (rather than one block per list
    item) and turn library errors into ToolErrors so the model sees them."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except (FrappeException, requests.RequestException, ValueError, KeyError) as exc:
            raise ToolError(_error_text(exc)) from exc
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    return wrapper


def build_server(connector_factory=config.connect, read_only: bool = False) -> MCPServer:
    """Create the MCP server. ``connector_factory`` is called lazily, once,
    the first time a tool needs to talk to Frappe."""
    server = MCPServer(name="frappe", instructions=INSTRUCTIONS)
    state: dict[str, FrappeConnector] = {}

    def client() -> FrappeConnector:
        if "client" not in state:
            state["client"] = connector_factory()
        return state["client"]

    def tool(annotations: ToolAnnotations):
        def register(fn):
            server.add_tool(_as_tool(fn), annotations=annotations)
            return fn

        return register

    @tool(READ_ONLY)
    def list_documents(
        doctype: str,
        fields: list[str] | None = None,
        filters: dict[str, Any] | list[Any] | None = None,
        order_by: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Any:
        """List documents of a doctype.

        Args:
            doctype: Doctype name, e.g. "Customer".
            fields: Fields to return; defaults to ["name"]. Use ["*"] for all fields.
            filters: Frappe filters as a dict or a list of [field, operator, value].
            order_by: Sort clause, e.g. "creation desc".
            offset: Number of records to skip.
            limit: Maximum number of records to return (0 returns all).
        """
        return client().get_list(
            doctype,
            fields=fields or ["name"],
            filters=filters,
            offset=offset,
            page_size=limit,
            order_by=order_by,
        )

    @tool(READ_ONLY)
    def get_document(
        doctype: str,
        name: str | None = None,
        filters: dict[str, Any] | list[Any] | None = None,
        fields: list[str] | None = None,
    ) -> Any:
        """Fetch one document by name, or the first document matching filters.

        Args:
            doctype: Doctype name, e.g. "Sales Invoice".
            name: Document name (ID). Either this or filters is required.
            filters: Frappe filters used when no name is given.
            fields: Only return these fields of the document.
        """
        return client().get_doc(doctype, name=name or "", filters=filters, fields=fields)

    if not read_only:

        @tool(WRITE)
        def create_document(doctype: str, data: dict[str, Any]) -> Any:
            """Create a new document.

            Args:
                doctype: Doctype name, e.g. "Customer".
                data: Field values for the new document (child tables as lists of dicts).
            """
            return client().create_doc({**data, "doctype": doctype})

        @tool(WRITE)
        def update_document(doctype: str, name: str, data: dict[str, Any]) -> Any:
            """Update fields on an existing document.

            Args:
                doctype: Doctype name.
                name: Name (ID) of the document to update.
                data: Field values to change.
            """
            return client().update_doc({**data, "doctype": doctype, "name": name})

        @tool(DESTRUCTIVE)
        def delete_document(doctype: str, name: str) -> Any:
            """Permanently delete a document.

            Args:
                doctype: Doctype name.
                name: Name (ID) of the document to delete.
            """
            client().delete_doc(doctype, name)
            return {"deleted": True, "doctype": doctype, "name": name}

        @tool(DESTRUCTIVE)
        def rename_document(doctype: str, old_name: str, new_name: str) -> Any:
            """Rename a document, updating links that point to it.

            Args:
                doctype: Doctype name.
                old_name: Current name (ID).
                new_name: New name (ID).
            """
            return client().rename_doc(doctype, old_name, new_name)

        @tool(DESTRUCTIVE)
        def submit_document(doctype: str, name: str) -> Any:
            """Submit a submittable document (e.g. a draft Sales Invoice).
            Submitted documents can no longer be edited, only cancelled.

            Args:
                doctype: Doctype name.
                name: Name (ID) of the draft document.
            """
            return client().submit_doc({"doctype": doctype, "name": name})

        @tool(DESTRUCTIVE)
        def call_method(
            method: str,
            params: dict[str, Any] | None = None,
            http_method: Literal["GET", "POST"] = "POST",
        ) -> Any:
            """Call a whitelisted server method, e.g. "frappe.client.get_count"
            or a custom app's "myapp.api.process_order".

            Args:
                method: Dotted path of the whitelisted method.
                params: Arguments passed to the method.
                http_method: GET for read-only methods, POST for methods that change data.
            """
            c = client()
            if http_method == "GET":
                return c.get_api(method, params=params)
            return c.post_api(method, params=params)

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="frappe-connector-mcp",
        description="Run an MCP server for a Frappe site. Connection settings "
        "are read from FRAPPE_URL, FRAPPE_API_KEY, FRAPPE_API_SECRET "
        "(or FRAPPE_USERNAME, FRAPPE_PASSWORD), FRAPPE_SSL_VERIFY and FRAPPE_TIMEOUT.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        default=config.env_flag("FRAPPE_MCP_READ_ONLY", False),
        help="Only expose list/get tools (or set FRAPPE_MCP_READ_ONLY=1).",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.environ.get("FRAPPE_MCP_TRANSPORT", "stdio"),
        help="MCP transport (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for streamable-http.")
    parser.add_argument("--port", type=int, default=8000, help="Port for streamable-http.")
    args = parser.parse_args(argv)

    if not os.environ.get("FRAPPE_URL"):
        parser.error("FRAPPE_URL is not set")

    server = build_server(read_only=args.read_only)
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
