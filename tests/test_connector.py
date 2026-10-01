import json
from urllib.parse import parse_qs, urlparse

import pytest
from responses import matchers

from frappe_connector import FrappeConnector, FrappeException, LoginFailedError, ServerError

from .conftest import BASE


def query(call):
    return {k: v[0] for k, v in parse_qs(urlparse(call.request.url).query).items()}


def form(call):
    return {k: v[0] for k, v in parse_qs(call.request.body).items()}


def test_token_auth_header_and_trailing_slash(mocked, client):
    mocked.get(f"{BASE}/api/resource/Customer", json={"data": []})
    assert client.get_list("Customer") == []
    request = mocked.calls[0].request
    assert request.headers["Authorization"] == "Basic a2V5OnNlY3JldA=="
    assert request.headers["Accept"] == "application/json"


def test_ssl_verify_and_timeout_apply_to_every_request(mocked):
    client = FrappeConnector(BASE, api_key="k", api_secret="s", ssl_verify=False, timeout=5)
    mocked.get(f"{BASE}/api/resource/Customer/C1", json={"data": {"name": "C1"}})
    mocked.post(f"{BASE}/api/method/my.method", json={"message": 1})
    client.get_doc("Customer", "C1")
    client.post_api("my.method")
    for call in mocked.calls:
        assert call.request.req_kwargs["verify"] is False
        assert call.request.req_kwargs["timeout"] == 5


def test_session_login_and_logout(mocked):
    mocked.post(BASE, json={"message": "Logged In"})
    mocked.get(BASE, json={})
    with FrappeConnector(BASE, username="admin", password="pw"):
        pass
    assert form(mocked.calls[0]) == {"cmd": "login", "usr": "admin", "pwd": "pw"}
    assert query(mocked.calls[1]) == {"cmd": "logout"}


def test_token_client_close_does_not_log_out(mocked, client):
    client.close()
    assert len(mocked.calls) == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"json": {"message": "Incorrect password"}, "status": 401},
        {"body": "<html>Bad gateway</html>", "status": 502},
    ],
)
def test_login_failure(mocked, kwargs):
    mocked.post(BASE, **kwargs)
    with pytest.raises(LoginFailedError):
        FrappeConnector(BASE, username="admin", password="bad")


def test_missing_base_url():
    with pytest.raises(ValueError):
        FrappeConnector(api_key="k", api_secret="s")


def test_non_json_response_raises_without_printing(mocked, client, capsys):
    mocked.get(f"{BASE}/api/resource/Customer", body="<html>oops</html>", status=500)
    with pytest.raises(FrappeException, match="HTTP 500: <html>oops"):
        client.get_list("Customer")
    assert capsys.readouterr().out == ""


def test_server_error_carries_traceback_and_type(mocked, client):
    mocked.get(
        f"{BASE}/api/resource/Customer/X",
        json={"exc": "Traceback...\nDoesNotExistError", "exc_type": "DoesNotExistError"},
        status=404,
    )
    with pytest.raises(ServerError) as info:
        client.get_doc("Customer", "X")
    assert info.value.exc_type == "DoesNotExistError"
    assert "Traceback" in info.value.server_traceback


def test_http_error_without_exc_uses_server_messages(mocked, client):
    messages = json.dumps([json.dumps({"message": "Not permitted"})])
    mocked.get(
        f"{BASE}/api/resource/Customer",
        json={"exc_type": "PermissionError", "_server_messages": messages},
        status=403,
    )
    with pytest.raises(FrappeException, match="PermissionError: Not permitted"):
        client.get_list("Customer")


@pytest.mark.parametrize("value", [[], 0, False, ""])
def test_falsy_message_is_returned_as_is(mocked, client, value):
    mocked.get(f"{BASE}/api/method/my.method", json={"message": value})
    assert client.get_api("my.method") == value


def test_get_list_params(mocked, client):
    mocked.get(f"{BASE}/api/resource/Sales%20Invoice", json={"data": [{"name": "S1"}]})
    client.get_list(
        "Sales Invoice",
        fields=["name"],
        filters={"status": "Paid"},
        offset=10,
        page_size=5,
        order_by="creation desc",
    )
    assert query(mocked.calls[0]) == {
        "fields": '["name"]',
        "filters": '{"status": "Paid"}',
        "limit_start": "10",
        "limit_page_length": "5",
        "order_by": "creation desc",
    }


def test_get_list_page_size_zero_means_all(mocked, client):
    mocked.get(f"{BASE}/api/resource/Customer", json={"data": []})
    client.get_list("Customer", page_size=0)
    client.get_list("Customer")
    assert query(mocked.calls[0])["limit_page_length"] == "0"
    assert "limit_page_length" not in query(mocked.calls[1])


def test_get_doc_quotes_name(mocked, client):
    mocked.get(f"{BASE}/api/resource/Item/A%2FB%20C", json={"data": {"name": "A/B C"}})
    assert client.get_doc("Item", "A/B C") == {"name": "A/B C"}


def test_get_doc_by_filters_returns_single_doc(mocked, client):
    mocked.get(
        f"{BASE}/api/method/frappe.client.get",
        json={"message": {"name": "C1", "customer_name": "Acme", "email_id": "a@x"}},
    )
    doc = client.get_doc(
        "Customer", filters={"customer_name": "Acme"}, fields=["name", "customer_name"]
    )
    assert doc == {"name": "C1", "customer_name": "Acme"}
    assert query(mocked.calls[0]) == {
        "doctype": "Customer",
        "filters": '{"customer_name": "Acme"}',
    }


def test_get_doc_requires_name_or_filters(client):
    with pytest.raises(ValueError):
        client.get_doc("Customer")


def test_create_and_update(mocked, client):
    mocked.post(f"{BASE}/api/resource/Customer", json={"data": {"name": "C1"}})
    mocked.put(f"{BASE}/api/resource/Customer/C1", json={"data": {"name": "C1", "phone": "1"}})
    assert client.create_doc({"doctype": "Customer", "customer_name": "Acme"}) == {"name": "C1"}
    client.update_doc({"doctype": "Customer", "name": "C1", "phone": "1"})
    assert json.loads(form(mocked.calls[1])["data"])["phone"] == "1"


def test_post_api_sends_form_body(mocked, client):
    mocked.post(
        f"{BASE}/api/method/myapp.api.process",
        json={"message": "ok"},
        match=[matchers.urlencoded_params_matcher({"order_id": "O1", "items": '["a"]'})],
    )
    assert client.post_api("myapp.api.process", {"order_id": "O1", "items": ["a"]}) == "ok"


def test_delete_and_rename(mocked, client):
    mocked.post(BASE, json={"message": None})
    client.delete_doc("Customer", "C1")
    client.rename_doc("Customer", "C1", "C2")
    assert form(mocked.calls[0]) == {"cmd": "frappe.client.delete", "doctype": "Customer", "name": "C1"}
    assert form(mocked.calls[1])["new_name"] == "C2"


def test_submit_fetches_full_doc_and_submits(mocked, client):
    full = {"doctype": "Sales Invoice", "name": "S1", "customer": "C1", "docstatus": 0}
    mocked.get(f"{BASE}/api/resource/Sales%20Invoice/S1", json={"data": full})
    mocked.post(BASE, json={"message": {**full, "docstatus": 1}})
    result = client.submit_doc({"doctype": "Sales Invoice", "name": "S1"})
    assert result["docstatus"] == 1
    body = form(mocked.calls[1])
    assert body["cmd"] == "frappe.client.submit"
    assert json.loads(body["doc"]) == full


def test_submit_list(mocked, client):
    for name in ("S1", "S2"):
        mocked.get(f"{BASE}/api/resource/Sales%20Invoice/{name}", json={"data": {"name": name}})
    mocked.post(BASE, json={"message": {"docstatus": 1}})
    result = client.submit_doc(
        [{"doctype": "Sales Invoice", "name": "S1"}, {"doctype": "Sales Invoice", "name": "S2"}]
    )
    assert result == [{"docstatus": 1}, {"docstatus": 1}]
