import requests
import json
from base64 import b64encode
from urllib.parse import quote

DEFAULT_TIMEOUT = 30


class FrappeException(Exception):
    def __init__(self, message: str, response=None):
        super().__init__(message)
        self.message = message
        self.response = response

    def __str__(self):
        return self.message


class LoginFailedError(FrappeException):
    def __init__(self, response=None):
        super().__init__("Invalid credentials or login rejected by server.", response)


class ServerError(FrappeException):
    def __init__(self, server_traceback: str, response=None, exc_type: str = None):
        super().__init__(server_traceback, response)
        self.server_traceback = server_traceback
        self.exc_type = exc_type


class FrappeConnector:
    def __init__(
        self,
        base_url: str = None,
        username: str = None,
        password: str = None,
        api_key: str = None,
        api_secret: str = None,
        ssl_verify: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        if not base_url:
            raise ValueError("base_url is required")

        self.base_url = base_url.rstrip("/")
        self.ssl_verify = ssl_verify
        self.timeout = timeout
        self._logged_in = False

        self._session = requests.Session()
        self._session.verify = ssl_verify
        self._session.headers.update({"Accept": "application/json"})

        if username and password:
            self._session_login(username, password)

        if api_key and api_secret:
            self._token_login(api_key, api_secret)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        # Passed per request because requests lets REQUESTS_CA_BUNDLE /
        # CURL_CA_BUNDLE override a session-level verify=False.
        kwargs.setdefault("verify", self.ssl_verify)
        return self._session.request(method, url, **kwargs)

    def _session_login(self, username: str, password: str):
        response = self._request(
            "POST",
            self.base_url,
            data={"cmd": "login", "usr": username, "pwd": password},
        )
        try:
            payload = response.json()
        except ValueError:
            raise LoginFailedError(response=response)
        if payload.get("message") != "Logged In":
            raise LoginFailedError(response=response)
        self._logged_in = True

    def _token_login(self, api_key: str, api_secret: str):
        raw = f"{api_key}:{api_secret}".encode()
        token = b64encode(raw).decode()
        self._session.headers.update({"Authorization": f"Basic {token}"})

    def close(self):
        try:
            if self._logged_in:
                self._request("GET", self.base_url, params={"cmd": "logout"})
                self._logged_in = False
        finally:
            self._session.close()

    def get_api(self, method: str, params: dict = None):
        res = self._request(
            "GET",
            f"{self.base_url}/api/method/{method}",
            params=self._serialize(params or {}),
        )
        return self._handle_response(res)

    def post_api(self, method: str, params: dict = None):
        res = self._request(
            "POST",
            f"{self.base_url}/api/method/{method}",
            data=self._serialize(params or {}),
        )
        return self._handle_response(res)

    def _post(self, data: dict):
        res = self._request("POST", self.base_url, data=self._serialize(data))
        return self._handle_response(res)

    def _serialize(self, params: dict) -> dict:
        return {
            k: json.dumps(v) if isinstance(v, (dict, list)) else v
            for k, v in params.items()
        }

    def _resource_url(self, doctype: str, name: str = None) -> str:
        url = f"{self.base_url}/api/resource/{quote(doctype, safe='')}"
        if name:
            url += f"/{quote(str(name), safe='')}"
        return url

    def _handle_response(self, response):
        try:
            body = response.json()
        except ValueError:
            snippet = response.text[:500]
            raise FrappeException(
                f"Expected JSON from server but got HTTP {response.status_code}: {snippet}",
                response=response,
            ) from None

        if not isinstance(body, dict):
            if not response.ok:
                raise FrappeException(f"HTTP {response.status_code}: {body}", response=response)
            return body

        if body.get("exc"):
            raise ServerError(body["exc"], response=response, exc_type=body.get("exc_type"))

        if not response.ok:
            raise FrappeException(
                self._error_message(body) or f"HTTP {response.status_code}",
                response=response,
            )

        if "message" in body:
            return body["message"]
        if "data" in body:
            return body["data"]
        return body

    @staticmethod
    def _error_message(body: dict) -> str:
        """Extract a human-readable message from a Frappe error payload."""
        messages = []
        raw = body.get("_server_messages")
        if raw:
            try:
                for item in json.loads(raw):
                    try:
                        item = json.loads(item)
                    except (TypeError, ValueError):
                        pass
                    messages.append(item.get("message", "") if isinstance(item, dict) else str(item))
            except (TypeError, ValueError):
                messages.append(str(raw))
        if not messages and body.get("message"):
            messages.append(str(body["message"]))
        prefix = body.get("exc_type")
        text = "; ".join(m for m in messages if m)
        if prefix:
            return f"{prefix}: {text}" if text else prefix
        return text

    def get_list(
        self,
        doctype: str,
        fields: list = None,
        filters: dict = None,
        offset: int = 0,
        page_size: int = None,
        order_by: str = None,
    ) -> list:
        """List documents. ``page_size=None`` uses the server default (20);
        ``page_size=0`` returns every matching record."""
        if fields is None:
            fields = ["*"]

        if not isinstance(fields, str):
            fields = json.dumps(fields)

        params = {"fields": fields}

        if filters:
            params["filters"] = json.dumps(filters)
        if offset:
            params["limit_start"] = offset
        if page_size is not None:
            params["limit_page_length"] = page_size
        if order_by:
            params["order_by"] = order_by

        res = self._request("GET", self._resource_url(doctype), params=params)
        return self._handle_response(res)

    def get_doc(
        self,
        doctype: str,
        name: str = "",
        filters: dict = None,
        fields: list = None,
    ) -> dict:
        if name:
            res = self._request("GET", self._resource_url(doctype, name))
            doc = self._handle_response(res)
        elif filters:
            doc = self.get_api(
                "frappe.client.get",
                params={"doctype": doctype, "filters": filters},
            )
        else:
            raise ValueError("get_doc requires either a name or filters")

        if fields and "*" not in fields and isinstance(doc, dict):
            doc = {k: v for k, v in doc.items() if k in fields}
        return doc

    def create_doc(self, doc: dict) -> dict:
        res = self._request(
            "POST",
            self._resource_url(doc["doctype"]),
            data={"data": json.dumps(doc)},
        )
        return self._handle_response(res)

    def update_doc(self, doc: dict) -> dict:
        res = self._request(
            "PUT",
            self._resource_url(doc["doctype"], doc["name"]),
            data={"data": json.dumps(doc)},
        )
        return self._handle_response(res)

    def delete_doc(self, doctype: str, name: str) -> dict:
        return self._post({
            "cmd": "frappe.client.delete",
            "doctype": doctype,
            "name": name,
        })

    def submit_doc(self, doc):
        """Submit a document. Accepts a single doc dict (needs ``doctype``
        and ``name``) or a list of them, in which case each one is submitted
        and a list of results is returned.

        The latest version is fetched from the server first, since
        ``frappe.client.submit`` expects the complete document.
        """
        if isinstance(doc, list):
            return [self.submit_doc(d) for d in doc]
        full_doc = self.get_doc(doc["doctype"], doc["name"])
        return self._post({"cmd": "frappe.client.submit", "doc": full_doc})

    def rename_doc(self, doctype: str, old_name: str, new_name: str) -> dict:
        return self._post({
            "cmd": "frappe.client.rename_doc",
            "doctype": doctype,
            "old_name": old_name,
            "new_name": new_name,
        })
