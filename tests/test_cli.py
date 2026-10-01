import json
from urllib.parse import parse_qs, urlparse

import pytest

from frappe_connector.cli import main

from .conftest import BASE


@pytest.fixture(autouse=True)
def _env(frappe_env):
    pass


def run(capsys, *argv):
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_list(mocked, capsys):
    mocked.get(f"{BASE}/api/resource/Customer", json={"data": [{"name": "C1"}]})
    code, out, _ = run(capsys, "list", "Customer", "--fields", "name,customer_name", "--limit", "5")
    assert code == 0
    assert json.loads(out) == [{"name": "C1"}]
    q = parse_qs(urlparse(mocked.calls[0].request.url).query)
    assert q["fields"] == ['["name", "customer_name"]']
    assert q["limit_page_length"] == ["5"]


def test_get_by_filters(mocked, capsys):
    mocked.get(f"{BASE}/api/method/frappe.client.get", json={"message": {"name": "C1"}})
    code, out, _ = run(capsys, "get", "Customer", "--filters", '{"customer_name": "Acme"}')
    assert code == 0 and json.loads(out) == {"name": "C1"}


def test_create_from_file(mocked, capsys, tmp_path):
    path = tmp_path / "doc.json"
    path.write_text('{"customer_name": "Acme"}')
    mocked.post(f"{BASE}/api/resource/Customer", json={"data": {"name": "C1"}})
    code, out, _ = run(capsys, "--compact", "create", "Customer", f"@{path}")
    assert code == 0 and out.strip() == '{"name": "C1"}'
    sent = parse_qs(mocked.calls[0].request.body)["data"][0]
    assert json.loads(sent) == {"customer_name": "Acme", "doctype": "Customer"}


def test_update_rejects_non_object(capsys):
    code, _, err = run(capsys, "update", "Customer", "C1", "[1, 2]")
    assert code == 1 and "must be a JSON object" in err


def test_delete_needs_confirmation_when_not_interactive(mocked, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    code, _, err = run(capsys, "delete", "Customer", "C1")
    assert code == 1 and "--yes" in err
    assert len(mocked.calls) == 0


def test_delete_with_yes(mocked, capsys):
    mocked.post(BASE, json={"message": None})
    code, out, _ = run(capsys, "delete", "Customer", "C1", "--yes")
    assert code == 0 and json.loads(out)["deleted"] is True


def test_call_get(mocked, capsys):
    mocked.get(f"{BASE}/api/method/frappe.client.get_count", json={"message": 42})
    code, out, _ = run(capsys, "call", "frappe.client.get_count", "--get", "--params", '{"doctype": "Customer"}')
    assert code == 0 and out.strip() == "42"


def test_server_error_exit_code(mocked, capsys):
    mocked.get(
        f"{BASE}/api/resource/Customer/X",
        json={"exc": "Traceback\nDoesNotExistError", "exc_type": "DoesNotExistError"},
        status=404,
    )
    code, out, err = run(capsys, "get", "Customer", "X")
    assert code == 1 and out == ""
    assert "DoesNotExistError" in err


def test_missing_url(capsys, monkeypatch):
    monkeypatch.delenv("FRAPPE_URL")
    code, _, err = run(capsys, "list", "Customer")
    assert code == 1 and "FRAPPE_URL" in err


def test_no_verify_ssl_flag(mocked, capsys):
    mocked.get(f"{BASE}/api/resource/Customer", json={"data": []})
    run(capsys, "--no-verify-ssl", "list", "Customer")
    assert mocked.calls[0].request.req_kwargs["verify"] is False
