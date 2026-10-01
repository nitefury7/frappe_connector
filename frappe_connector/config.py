"""Build a FrappeConnector from explicit values or environment variables.

Shared by the CLI and the MCP server. Supported environment variables:

    FRAPPE_URL          Base URL of the Frappe site (required)
    FRAPPE_API_KEY      API key for token auth
    FRAPPE_API_SECRET   API secret for token auth
    FRAPPE_USERNAME     Username for session auth
    FRAPPE_PASSWORD     Password for session auth
    FRAPPE_SSL_VERIFY   Set to 0/false/no to disable TLS certificate checks
    FRAPPE_TIMEOUT      Request timeout in seconds (default 30)
"""

import os

from .connector import DEFAULT_TIMEOUT, FrappeConnector

_FALSE_VALUES = {"0", "false", "no", "off"}


def env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in _FALSE_VALUES


def connect(
    url: str = None,
    api_key: str = None,
    api_secret: str = None,
    username: str = None,
    password: str = None,
    ssl_verify: bool = None,
    timeout: float = None,
) -> FrappeConnector:
    """Create a connector, falling back to FRAPPE_* environment variables
    for any value that is not given explicitly."""
    env = os.environ
    url = url or env.get("FRAPPE_URL")
    if not url:
        raise ValueError("No Frappe URL configured. Pass --url or set FRAPPE_URL.")

    api_key = api_key or env.get("FRAPPE_API_KEY")
    api_secret = api_secret or env.get("FRAPPE_API_SECRET")
    username = username or env.get("FRAPPE_USERNAME")
    password = password or env.get("FRAPPE_PASSWORD")

    if not ((api_key and api_secret) or (username and password)):
        raise ValueError(
            "No credentials configured. Set FRAPPE_API_KEY and FRAPPE_API_SECRET "
            "(or FRAPPE_USERNAME and FRAPPE_PASSWORD)."
        )

    if ssl_verify is None:
        ssl_verify = env_flag("FRAPPE_SSL_VERIFY", True)
    if timeout is None:
        timeout = float(env.get("FRAPPE_TIMEOUT") or DEFAULT_TIMEOUT)

    return FrappeConnector(
        url,
        username=username,
        password=password,
        api_key=api_key,
        api_secret=api_secret,
        ssl_verify=ssl_verify,
        timeout=timeout,
    )
