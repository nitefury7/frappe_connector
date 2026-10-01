# frappe-connector

A lightweight Python client for connecting and interacting with Frappe instances.

## Installation

```bash
pip install frappe-connector          # library + CLI
pip install "frappe-connector[mcp]"   # also the MCP server
```

The package ships three ways to use it:

- a **Python library** (`FrappeConnector`, below)
- a **command-line tool**, `frappe-connector` (see [CLI](#cli))
- an **MCP server**, `frappe-connector-mcp`, that gives AI assistants access to your site (see [MCP server](#mcp-server))

## Authentication

### Session login (username + password)

```python
from frappe_connector import FrappeConnector

client = FrappeConnector(
    "https://erp.example.com",
    username="admin",
    password="secret",
)
```

### Token login (API key + secret)

```python
client = FrappeConnector(
    "https://erp.example.com",
    api_key="your_api_key",
    api_secret="your_api_secret",
)
```

### Connection options

```python
client = FrappeConnector(
    "https://erp.example.com",
    api_key="...",
    api_secret="...",
    ssl_verify=False,  # skip TLS certificate checks (self-signed certs)
    timeout=60,        # seconds per request (default 30)
)
```

### Context manager (auto-logout)

```python
with FrappeConnector("https://erp.example.com", username="admin", password="secret") as client:
    records = client.get_list("Customer")
```

---

## CRUD Operations

### `get_list` — fetch multiple records

```python
customers = client.get_list(
    "Customer",
    fields=["name", "customer_name", "email_id"],
    filters={"status": "Active"},
    offset=0,
    page_size=20,       # omit for the server default (20), 0 for all records
    order_by="creation desc",
)
```

### `get_doc` — fetch a single document

```python
# by name
customer = client.get_doc("Customer", name="CUST-00001")

# by filter: returns the first matching document
customer = client.get_doc(
    "Customer",
    filters={"customer_name": "Acme Corp"},
    fields=["name", "customer_name", "email_id"],
)
```

### `create_doc` — insert a new document

```python
new_customer = client.create_doc({
    "doctype": "Customer",
    "customer_name": "Globex Corporation",
    "customer_type": "Company",
    "customer_group": "Commercial",
    "territory": "All Territories",
})
```

### `update_doc` — update an existing document

```python
updated = client.update_doc({
    "doctype": "Customer",
    "name": "CUST-00001",
    "phone": "+977-9800000000",
})
```

### `delete_doc` — delete a document

```python
client.delete_doc("Customer", "CUST-99999")
```

### `rename_doc` — rename a document

```python
client.rename_doc("Customer", old_name="CUST-OLD", new_name="CUST-NEW")
```

### `submit_doc` — submit a document

```python
client.submit_doc({"doctype": "Sales Invoice", "name": "SINV-00001"})

# or several at once (returns a list of results)
client.submit_doc([
    {"doctype": "Sales Invoice", "name": "SINV-00001"},
    {"doctype": "Sales Invoice", "name": "SINV-00002"},
])
```

---

## API Method Calls

### `get_api` — call a whitelisted GET method

```python
result = client.get_api("myapp.api.get_summary", params={"year": 2025})
```

### `post_api` — call a whitelisted POST method

```python
result = client.post_api("myapp.api.process_order", params={"order_id": "ORD-001"})
```

---

## Error Handling

All exceptions inherit from `FrappeException`, so you can catch broadly or specifically.

```python
from frappe_connector import FrappeConnector, LoginFailedError, ServerError, FrappeException

try:
    client = FrappeConnector("https://erp.example.com", username="admin", password="wrong")
except LoginFailedError as e:
    print(e)  # "Invalid credentials or login rejected by server."

try:
    client.get_doc("Customer", "CUST-001")
except ServerError as e:
    print(e.exc_type)          # e.g. "DoesNotExistError"
    print(e.server_traceback)  # full traceback from Frappe
    print(e.response)          # raw requests.Response object
except FrappeException as e:
    print(e)
```

| Exception          | When raised                                       |
| ------------------ | ------------------------------------------------- |
| `FrappeException`  | Base class for all library errors                 |
| `LoginFailedError` | Credentials rejected by the server                |
| `ServerError`      | Server returned an exception in the response body |

Other HTTP errors (e.g. 403 permission denied) and non-JSON responses raise
`FrappeException` with the server's message. Network failures raise the usual
`requests` exceptions.

---

## Closing the session

```python
client.close()  # logs out (session login) and closes the HTTP connection
```

---

## Configuration via environment variables

The CLI and MCP server read their connection settings from these variables
(the CLI also accepts matching `--url`, `--api-key`, … flags):

| Variable            | Meaning                                         |
| ------------------- | ----------------------------------------------- |
| `FRAPPE_URL`        | Base URL of the site (required)                 |
| `FRAPPE_API_KEY`    | API key (token auth)                            |
| `FRAPPE_API_SECRET` | API secret (token auth)                         |
| `FRAPPE_USERNAME`   | Username (session auth)                         |
| `FRAPPE_PASSWORD`   | Password (session auth)                         |
| `FRAPPE_SSL_VERIFY` | `0` / `false` to skip TLS certificate checks    |
| `FRAPPE_TIMEOUT`    | Request timeout in seconds (default 30)         |

---

## CLI

```bash
export FRAPPE_URL=https://erp.example.com
export FRAPPE_API_KEY=your_api_key FRAPPE_API_SECRET=your_api_secret

frappe-connector list Customer --fields name,customer_name --filters '{"disabled": 0}' --limit 50
frappe-connector get Customer CUST-00001
frappe-connector get Customer --filters '{"customer_name": "Acme Corp"}' --fields name,email_id
frappe-connector create Customer '{"customer_name": "Globex", "customer_group": "Commercial"}'
frappe-connector update Customer CUST-00001 @changes.json     # JSON from a file
cat doc.json | frappe-connector create Customer -              # JSON from stdin
frappe-connector rename Customer CUST-OLD CUST-NEW
frappe-connector submit "Sales Invoice" SINV-00001 --yes
frappe-connector delete Customer CUST-99999 --yes
frappe-connector call frappe.client.get_count --get --params '{"doctype": "Customer"}'
```

Results are printed as JSON (`--compact` for one line), so they pipe nicely
into `jq`. `delete` and `submit` ask for confirmation unless `--yes` is given.
Errors go to stderr with exit code 1. Run `frappe-connector COMMAND --help` for
all options; `python -m frappe_connector` works too.

---

## MCP server

`frappe-connector-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io)
server that lets AI assistants (Claude Desktop, Claude Code, …) work with your
Frappe site. Install the extra first: `pip install "frappe-connector[mcp]"`.

Tools:

| Tool              | Does                                             |
| ----------------- | ------------------------------------------------ |
| `list_documents`  | List documents with fields, filters, sorting, paging |
| `get_document`    | Fetch one document by name or filters            |
| `create_document` | Create a document                                |
| `update_document` | Update fields on a document                      |
| `delete_document` | Delete a document                                |
| `rename_document` | Rename a document                                |
| `submit_document` | Submit a draft document                          |
| `call_method`     | Call a whitelisted server method                 |

Start it with `--read-only` (or `FRAPPE_MCP_READ_ONLY=1`) to expose only
`list_documents` and `get_document`.

Claude Code:

```bash
claude mcp add frappe \
  -e FRAPPE_URL=https://erp.example.com \
  -e FRAPPE_API_KEY=your_api_key \
  -e FRAPPE_API_SECRET=your_api_secret \
  -- frappe-connector-mcp --read-only
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "frappe": {
      "command": "uvx",
      "args": ["--from", "frappe-connector[mcp]", "frappe-connector-mcp"],
      "env": {
        "FRAPPE_URL": "https://erp.example.com",
        "FRAPPE_API_KEY": "your_api_key",
        "FRAPPE_API_SECRET": "your_api_secret"
      }
    }
  }
}
```

The server uses stdio by default; `--transport streamable-http --host 127.0.0.1 --port 8000`
serves it over HTTP instead. The tools act with the permissions of the
configured Frappe user, so a dedicated user with limited roles is a good idea.

---

## Development

```bash
uv sync --all-extras
uv run pytest
```
