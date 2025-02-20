import requests
import json
from base64 import b64encode
from urllib.parse import quote


class FrappeConnector:
    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        api_secret: str = None,
        ssl_verify: bool = True,
    ):
        self.base_url = base_url
        self.ssl_verify = ssl_verify

        self._session = requests.Session()
        self._headers = {"Accept": "application/json"}

        if api_key and api_secret:
            self._token_login(api_key, api_secret)


    def _token_login(self, api_key: str, api_secret: str):
        raw = f"{api_key}:{api_secret}".encode()
        token = b64encode(raw).decode()
        self._session.headers.update({"Authorization": f"Basic {token}"})

   