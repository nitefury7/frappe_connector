import requests
import json
from base64 import b64encode
from urllib.parse import quote

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
    def __init__(self, server_traceback: str, response=None):
        super().__init__(server_traceback, response)
        self.server_traceback = server_traceback


class FrappeConnector:
    def __init__(
        self,
        base_url: str = None,
        username: str = None,
        password: str = None,
        api_key: str = None,
        api_secret: str = None,
        ssl_verify: bool = True,
    ):
        self.base_url = base_url
        self.ssl_verify = ssl_verify

        self._session = requests.Session()
        self._headers = {"Accept": "application/json"}

        if username and password:
            self._session_login(username, password)

        if api_key and api_secret:
            self._token_login(api_key, api_secret)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _session_login(self, username: str, password: str):
        response = self._session.post(
            self.base_url,
            data={"cmd": "login", "usr": username, "pwd": password},
            verify=self.ssl_verify,
            headers=self._headers,
        )
        payload = response.json()
        if payload.get("message") != "Logged In":
            raise LoginFailedError(response=response)

    def _token_login(self, api_key: str, api_secret: str):
        raw = f"{api_key}:{api_secret}".encode()
        token = b64encode(raw).decode()
        self._session.headers.update({"Authorization": f"Basic {token}"})

    def close(self):
        self._session.get(self.base_url, params={"cmd": "logout"})

    def get_api(self, method: str, params: dict = None):
        res = self._session.get(
            f"{self.base_url}/api/method/{method}/",
            params=params or {},
        )
        return self._handle_response(res)

    def post_api(self, method: str, params: dict = None):
        res = self._session.post(
            f"{self.base_url}/api/method/{method}/",
            params=params or {},
        )
        return self._handle_response(res)

    def _get(self, params: dict):
        res = self._session.get(self.base_url, params=self._serialize(params))
        return self._handle_response(res)

    def _post(self, data: dict):
        res = self._session.post(self.base_url, data=self._serialize(data))
        return self._handle_response(res)

    def _serialize(self, params: dict) -> dict:
        return {
            k: json.dumps(v) if isinstance(v, (dict, list)) else v
            for k, v in params.items()
        }

    def _handle_response(self, response):
        try:
            body = response.json()
        except ValueError:
            print(response.text)
            raise

        if body and body.get("exc"):
            raise ServerError(body["exc"], response=response)

        return body.get("message") or body.get("data")
    
    def get_list(
        self,
        doctype: str,
        fields: list = None,
        filters: dict = None,
        offset: int = 0,
        page_size: int = 0,
        order_by: str = None,
    ) -> list:
        if fields is None:
            fields = ["*"]

        if not isinstance(fields, str):
            fields = json.dumps(fields)

        params = {"fields": fields}

        if filters:
            params["filters"] = json.dumps(filters)
        if page_size:
            params["limit_start"] = offset
            params["limit_page_length"] = page_size
        if order_by:
            params["order_by"] = order_by

        res = self._session.get(
            f"{self.base_url}/api/resource/{doctype}",
            params=params,
            verify=self.ssl_verify,
            headers=self._headers,
        )
        return self._handle_response(res)

    def get_doc(
        self,
        doctype: str,
        name: str = "",
        filters: dict = None,
        fields: list = None,
    ) -> dict:
        params = {}
        if filters:
            params["filters"] = json.dumps(filters)
        if fields:
            params["fields"] = json.dumps(fields)

        res = self._session.get(
            f"{self.base_url}/api/resource/{doctype}/{name}",
            params=params,
        )
        return self._handle_response(res)
    
    def create_doc(self, doc: dict) -> dict:
        endpoint = f"{self.base_url}/api/resource/{quote(doc['doctype'])}"
        res = self._session.post(endpoint, data={"data": json.dumps(doc)})
        return self._handle_response(res)

    def update_doc(self, doc: dict) -> dict:
        url = (
            f"{self.base_url}/api/resource/"
            f"{quote(doc['doctype'])}/{quote(doc['name'])}"
        )
        res = self._session.put(url, data={"data": json.dumps(doc)})
        return self._handle_response(res)

    def delete_doc(self, doctype: str, name: str) -> dict:
        return self._post({
            "cmd": "frappe.client.delete",
            "doctype": doctype,
            "name": name,
        })

    def submit_doc(self, doclist: list) -> dict:
        return self._post({
            "cmd": "frappe.client.submit",
            "doclist": json.dumps(doclist),
        })

    def rename_doc(self, doctype: str, old_name: str, new_name: str) -> dict:
        return self._post({
            "cmd": "frappe.client.rename_doc",
            "doctype": doctype,
            "old_name": old_name,
            "new_name": new_name,
        })


