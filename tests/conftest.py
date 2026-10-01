import pytest
import responses

BASE = "https://erp.example.com"


@pytest.fixture
def mocked():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def client():
    from frappe_connector import FrappeConnector

    return FrappeConnector(BASE + "/", api_key="key", api_secret="secret")


@pytest.fixture
def frappe_env(monkeypatch):
    for name in ("FRAPPE_USERNAME", "FRAPPE_PASSWORD", "FRAPPE_SSL_VERIFY", "FRAPPE_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FRAPPE_URL", BASE)
    monkeypatch.setenv("FRAPPE_API_KEY", "key")
    monkeypatch.setenv("FRAPPE_API_SECRET", "secret")
