# frappe-connector

A lightweight Python client for connecting and interacting with Frappe instances.

## Installation

```bash
pip install frappe-connector
```

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
    page_size=20,
    order_by="creation desc",
)
```

### `get_doc` — fetch a single document

```python
# by name
customer = client.get_doc("Customer", name="CUST-00001")

# by filter
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
client.submit_doc([{"doctype": "Sales Invoice", "name": "SINV-00001"}])
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

---

## Closing the session

```python
client.close()  # logs out from the server
```
