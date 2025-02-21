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

   