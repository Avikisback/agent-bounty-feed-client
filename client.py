"""Small, dependency-free client for Agent Bounty Feed's free MCP endpoint."""
import argparse
import json
import math
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://agent-bounty-feed.dailydollar.workers.dev/mcp"
PROTOCOL = "2025-06-18"
MAX_BYTES = 4 * 1024 * 1024


class ClientError(Exception):
    """A transport, protocol, or feed error suitable for the command line."""


def rpc_result(message, request_id):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise ClientError("Invalid JSON-RPC response")
    if type(message.get("id")) is not type(request_id) or message.get("id") != request_id:
        return None
    if "error" in message:
        raise ClientError("JSON-RPC error: " + json.dumps(message["error"]))
    if "result" not in message:
        raise ClientError("JSON-RPC response has no result")
    return message["result"]


def read_result(response, request_id):
    """Read JSON or SSE, returning as soon as this request's reply arrives."""
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type == "application/json":
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ClientError("Response exceeds 4 MiB")
        result = rpc_result(json.loads(raw), request_id)
        if result is None:
            raise ClientError("JSON-RPC response ID does not match")
        return result
    if content_type != "text/event-stream":
        raise ClientError("Expected JSON or SSE, received " + repr(content_type))
    total, data = 0, []
    while True:
        raw = response.readline(MAX_BYTES - total + 1)
        total += len(raw)
        if total > MAX_BYTES:
            raise ClientError("Response exceeds 4 MiB")
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                result = rpc_result(json.loads("\n".join(data)), request_id)
                data = []
                if result is not None:
                    return result
            if not raw:
                raise ClientError("SSE ended before the matching response")
        elif line.startswith("data:"):
            value = line[5:]
            data.append(value[1:] if value.startswith(" ") else value)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward an MCP session to an unexpected endpoint.
        return None


class Client:
    def __init__(self, endpoint=ENDPOINT, timeout=20):
        self.endpoint, self.timeout = endpoint, timeout
        self.session, self.protocol, self.sequence = None, None, 0
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, params=None, notification=False):
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notification:
            self.sequence += 1
            body["id"] = self.sequence
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "User-Agent": "agent-bounty-feed-client/0.1.0"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if self.protocol:
            headers["MCP-Protocol-Version"] = self.protocol
        req = urllib.request.Request(self.endpoint, data=json.dumps(body).encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                if notification:
                    if response.status != 202:
                        raise ClientError("Notification was not acknowledged with HTTP 202")
                    return None
                result = read_result(response, body["id"])
                if method == "initialize":
                    self.session = response.headers.get("Mcp-Session-Id")
                return result
        except urllib.error.HTTPError as exc:
            suffix = "; no payment was attempted" if exc.code == 402 else ""
            raise ClientError(f"HTTP {exc.code}{suffix}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ClientError(f"Connection failed: {exc}") from exc

    def initialize(self):
        result = self.request("initialize", {
            "protocolVersion": PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "agent-bounty-feed-client", "version": "0.1.0"}})
        self.protocol = result.get("protocolVersion")
        if self.protocol != PROTOCOL:
            raise ClientError("Server selected an unsupported protocol: " + repr(self.protocol))
        self.request("notifications/initialized", notification=True)
        return result

    def call(self, name, arguments=None):
        if name not in {"list_bounties", "get_new_bounties", "get_bounty", "get_feed_stats"}:
            raise ClientError("Only the four documented free feed tools are supported")
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise ClientError("Feed tool failed: " + json.dumps(result.get("content", [])))
        if isinstance(result.get("structuredContent"), dict):
            return result["structuredContent"]
        for part in result.get("content", []):
            if part.get("type") == "text":
                try:
                    value = json.loads(part["text"])
                except (KeyError, ValueError) as exc:
                    raise ClientError("Feed returned non-JSON text") from exc
                if isinstance(value, dict):
                    return value
        raise ClientError("Feed returned no JSON object")


def limit_value(value):
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("limit must be between 1 and 100")
    return number


def usd_value(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("min-usd must be finite and nonnegative")
    return number


def clean(value):
    """Keep external text on one line and suppress terminal control characters."""
    return " ".join("".join(c if c.isprintable() else " " for c in str(value)).split())


def display(data):
    if "items" not in data:
        print(json.dumps(data, indent=2, ensure_ascii=True))
        return
    print(f"Returned: {len(data['items'])}; feed: {clean(data.get('generated_at', 'unknown'))}")
    for item in data["items"]:
        print(f"\n{clean(item.get('reward', '?'))} {clean(item.get('currency', ''))} | "
              f"{clean(item.get('title', 'Untitled'))}")
        print("  " + clean(item.get("url", "")))
        print("  Requires: " + clean(", ".join(item.get("requires", [])) or "none listed"))
        if item.get("deadline"):
            print("  Deadline: " + clean(item["deadline"]))
        if item.get("eligibility"):
            print("  Eligibility: " + clean(item["eligibility"]))
    print("\nDiscovery only: confirm current eligibility and payment terms on the source board.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "stats", "get", "new"):
        command = commands.add_parser(name)
        command.add_argument("--json", action="store_true", help="print the complete free response")
        if name in ("list", "new"):
            command.add_argument("--limit", type=limit_value, default=5)
            command.add_argument("--min-usd", type=usd_value, default=0)
            command.add_argument("--source")
            command.add_argument("--exclude-requires", default="",
                                 help="comma-separated gates, e.g. kyc,stake,bond,purchase")
            command.add_argument("--query", help="search titles and eligibility")
        if name == "get":
            command.add_argument("id")
        if name == "new":
            command.add_argument("--since", required=True)
            command.add_argument("--after-id")
    args = parser.parse_args(argv)
    arguments = {}
    if args.command in ("list", "new"):
        arguments = {"limit": args.limit, "min_usd": args.min_usd}
        for field, name in (("source", "source"), ("exclude_requires", "exclude_requires"),
                            ("query", "q")):
            if getattr(args, field):
                arguments[name] = getattr(args, field)
    if args.command == "get":
        arguments["id"] = args.id
    if args.command == "new":
        arguments["since"] = args.since
        if args.after_id:
            arguments["after_id"] = args.after_id
    tool = {"list": "list_bounties", "stats": "get_feed_stats",
            "get": "get_bounty", "new": "get_new_bounties"}[args.command]
    try:
        client = Client()
        client.initialize()
        data = client.call(tool, arguments)
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=True))
        else:
            display(data)
        return 0
    except (ClientError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print("Error: " + clean(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
