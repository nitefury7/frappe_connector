"""Command-line interface for frappe-connector.

Examples:

    export FRAPPE_URL=https://erp.example.com
    export FRAPPE_API_KEY=... FRAPPE_API_SECRET=...

    fcn list Customer --fields name,customer_name --filters '{"disabled": 0}'
    fcn get Customer CUST-00001
    fcn create Customer '{"customer_name": "Globex"}'
    fcn update Customer CUST-00001 @changes.json
    fcn call frappe.client.get_count --params '{"doctype": "Customer"}'
"""

import argparse
import json
import sys

from . import config
from .connector import FrappeException, ServerError

__all__ = ["main"]


def _parse_json(value: str, what: str):
    """Parse JSON given inline, as @path to a file, or as - for stdin."""
    if value == "-":
        text = sys.stdin.read()
    elif value.startswith("@"):
        with open(value[1:], encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = value
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for {what}: {exc}") from None


def _parse_fields(value: str):
    if value is None:
        return None
    value = value.strip()
    if value.startswith("["):
        return _parse_json(value, "--fields")
    return [f.strip() for f in value.split(",") if f.strip()]


def _parse_object(value: str, what: str) -> dict:
    data = _parse_json(value, what)
    if not isinstance(data, dict):
        raise ValueError(f"{what} must be a JSON object")
    return data


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise ValueError("Refusing to run without confirmation; pass --yes.")
    return input(f"{prompt} [y/N] ").strip().lower() in {"y", "yes"}


def _cmd_list(client, args):
    filters = _parse_json(args.filters, "--filters") if args.filters else None
    return client.get_list(
        args.doctype,
        fields=_parse_fields(args.fields),
        filters=filters,
        offset=args.offset,
        page_size=args.limit,
        order_by=args.order_by,
    )


def _cmd_get(client, args):
    filters = _parse_json(args.filters, "--filters") if args.filters else None
    if not args.name and not filters:
        raise ValueError("Give a document name or --filters.")
    return client.get_doc(
        args.doctype, name=args.name or "", filters=filters, fields=_parse_fields(args.fields)
    )


def _cmd_create(client, args):
    data = _parse_object(args.data, "DATA")
    return client.create_doc({**data, "doctype": args.doctype})


def _cmd_update(client, args):
    data = _parse_object(args.data, "DATA")
    return client.update_doc({**data, "doctype": args.doctype, "name": args.name})


def _cmd_delete(client, args):
    if not _confirm(f"Delete {args.doctype} {args.name}?", args.yes):
        raise ValueError("Aborted.")
    client.delete_doc(args.doctype, args.name)
    return {"deleted": True, "doctype": args.doctype, "name": args.name}


def _cmd_rename(client, args):
    return client.rename_doc(args.doctype, args.old_name, args.new_name)


def _cmd_submit(client, args):
    if not _confirm(f"Submit {args.doctype} {args.name}?", args.yes):
        raise ValueError("Aborted.")
    return client.submit_doc({"doctype": args.doctype, "name": args.name})


def _cmd_call(client, args):
    params = _parse_object(args.params, "--params") if args.params else None
    if args.get:
        return client.get_api(args.method, params=params)
    return client.post_api(args.method, params=params)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fcn",
        description="Work with documents and API methods on a Frappe site. "
        "Connection options fall back to the FRAPPE_URL, FRAPPE_API_KEY, "
        "FRAPPE_API_SECRET, FRAPPE_USERNAME, FRAPPE_PASSWORD, FRAPPE_SSL_VERIFY "
        "and FRAPPE_TIMEOUT environment variables.",
        epilog="JSON arguments accept inline JSON, @path/to/file.json, or - for stdin.",
    )
    conn = parser.add_argument_group("connection")
    conn.add_argument("--url", help="Base URL of the Frappe site.")
    conn.add_argument("--api-key", help="API key (token auth).")
    conn.add_argument("--api-secret", help="API secret (token auth).")
    conn.add_argument("--username", help="Username (session auth).")
    conn.add_argument(
        "--password", help="Password (session auth). Prefer FRAPPE_PASSWORD to keep it out of shell history."
    )
    conn.add_argument(
        "--no-verify-ssl", dest="ssl_verify", action="store_false", default=None,
        help="Skip TLS certificate verification.",
    )
    conn.add_argument("--timeout", type=float, help="Request timeout in seconds (default 30).")
    parser.add_argument("--compact", action="store_true", help="Print compact single-line JSON.")

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("list", help="List documents of a doctype.")
    p.add_argument("doctype")
    p.add_argument("--fields", help='Comma-separated fields or a JSON list (default: all, "*").')
    p.add_argument("--filters", help='Frappe filters as JSON, e.g. \'{"status": "Active"}\'.')
    p.add_argument("--order-by", help='Sort clause, e.g. "creation desc".')
    p.add_argument("--offset", type=int, default=0, help="Records to skip.")
    p.add_argument("--limit", type=int, help="Max records (server default 20; 0 for all).")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("get", help="Fetch one document by name or filters.")
    p.add_argument("doctype")
    p.add_argument("name", nargs="?")
    p.add_argument("--filters", help="Frappe filters as JSON (used when no name is given).")
    p.add_argument("--fields", help="Only print these fields (comma-separated or JSON list).")
    p.set_defaults(func=_cmd_get)

    p = sub.add_parser("create", help="Create a document.")
    p.add_argument("doctype")
    p.add_argument("data", help="Field values as a JSON object.")
    p.set_defaults(func=_cmd_create)

    p = sub.add_parser("update", help="Update fields on a document.")
    p.add_argument("doctype")
    p.add_argument("name")
    p.add_argument("data", help="Field values to change, as a JSON object.")
    p.set_defaults(func=_cmd_update)

    p = sub.add_parser("delete", help="Delete a document.")
    p.add_argument("doctype")
    p.add_argument("name")
    p.add_argument("-y", "--yes", action="store_true", help="Do not ask for confirmation.")
    p.set_defaults(func=_cmd_delete)

    p = sub.add_parser("rename", help="Rename a document.")
    p.add_argument("doctype")
    p.add_argument("old_name")
    p.add_argument("new_name")
    p.set_defaults(func=_cmd_rename)

    p = sub.add_parser("submit", help="Submit a draft document.")
    p.add_argument("doctype")
    p.add_argument("name")
    p.add_argument("-y", "--yes", action="store_true", help="Do not ask for confirmation.")
    p.set_defaults(func=_cmd_submit)

    p = sub.add_parser("call", help="Call a whitelisted server method.")
    p.add_argument("method", help='Dotted method path, e.g. "frappe.client.get_count".')
    p.add_argument("--params", help="Method arguments as a JSON object.")
    p.add_argument("--get", action="store_true", help="Use GET instead of POST.")
    p.set_defaults(func=_cmd_call)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        client = config.connect(
            url=args.url,
            api_key=args.api_key,
            api_secret=args.api_secret,
            username=args.username,
            password=args.password,
            ssl_verify=args.ssl_verify,
            timeout=args.timeout,
        )
        with client:
            result = args.func(client, args)
    except ServerError as exc:
        print(f"error: server raised {exc.exc_type or 'an exception'}", file=sys.stderr)
        print(exc.server_traceback, file=sys.stderr)
        return 1
    except (FrappeException, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    indent = None if args.compact else 2
    print(json.dumps(result, indent=indent, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
