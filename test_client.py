"""Offline protocol tests. The HTTP fixture binds to loopback only."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import threading
import unittest

from client import Client, ClientError, limit_value, read_result, usd_value


@contextmanager
def server(sse=False, reject=False, tool_error=False):
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            observed.append({"body": body, "headers": dict(self.headers)})
            if reject:
                self.send_response(402)
                self.end_headers()
                return
            if body["method"] == "notifications/initialized":
                self.send_response(202)
                self.end_headers()
                return
            if body["method"] == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {},
                          "serverInfo": {"name": "offline-fixture", "version": "1"}}
            else:
                data = {"items": [{"id": "fixture:1", "title": "Example"}]}
                result = {"content": [{"type": "text", "text": json.dumps(data)}]}
                if tool_error:
                    result = {"isError": True, "content": [{"type": "text", "text": "failed"}]}
            reply = {"jsonrpc": "2.0", "id": body["id"], "result": result}
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream" if sse else "application/json")
            if body["method"] == "initialize":
                self.send_header("Mcp-Session-Id", "fixture-session")
            self.end_headers()
            if sse:
                # A keep-alive and notification must not be mistaken for the reply.
                self.wfile.write(b': ping\n\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n')
                self.wfile.write(("data: " + json.dumps(reply) + "\n\n").encode())
            else:
                self.wfile.write(json.dumps(reply).encode())

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/mcp", observed
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def response(raw, kind="application/json"):
    stream = BytesIO(raw)
    stream.headers = {"Content-Type": kind}
    return stream


class ProtocolTests(unittest.TestCase):
    def exercise(self, sse):
        with server(sse=sse) as (url, observed):
            client = Client(endpoint=url, timeout=2)
            client.initialize()
            self.assertEqual(client.call("list_bounties")["items"][0]["id"], "fixture:1")
            self.assertEqual([x["body"]["method"] for x in observed],
                             ["initialize", "notifications/initialized", "tools/call"])
            for request in observed:
                self.assertIn("application/json", request["headers"]["Accept"])
                self.assertIn("text/event-stream", request["headers"]["Accept"])
            # HTTP header capitalization is not semantically significant.
            for request in observed[1:]:
                headers = {k.lower(): v for k, v in request["headers"].items()}
                self.assertEqual(headers["mcp-session-id"], "fixture-session")
                self.assertEqual(headers["mcp-protocol-version"], "2025-06-18")

    def test_json_lifecycle_and_session(self):
        self.exercise(False)

    def test_sse_lifecycle_and_session(self):
        self.exercise(True)

    def test_http_402_stops_without_retry(self):
        with server(reject=True) as (url, observed):
            with self.assertRaisesRegex(ClientError, "no payment was attempted"):
                Client(endpoint=url).initialize()
            self.assertEqual(len(observed), 1)

    def test_tool_error_is_not_a_successful_empty_feed(self):
        with server(tool_error=True) as (url, _):
            client = Client(endpoint=url)
            client.initialize()
            with self.assertRaisesRegex(ClientError, "Feed tool failed"):
                client.call("list_bounties")

    def test_mismatched_response_id(self):
        raw = b'{"jsonrpc":"2.0","id":99,"result":{}}'
        with self.assertRaisesRegex(ClientError, "ID does not match"):
            read_result(response(raw), 1)

    def test_rpc_error(self):
        raw = b'{"jsonrpc":"2.0","id":1,"error":{"code":-32602,"message":"bad input"}}'
        with self.assertRaisesRegex(ClientError, "-32602"):
            read_result(response(raw), 1)

    def test_sse_multiline_and_unrelated_id(self):
        raw = (b'data: {"jsonrpc":"2.0","id":9,"result":{}}\r\n\r\n'
               b'data: {"jsonrpc":"2.0",\r\ndata: "id":1,"result":{"ok":true}}\r\n\r\n')
        self.assertEqual(read_result(response(raw, "text/event-stream"), 1), {"ok": True})

    def test_sse_returns_before_waiting_for_connection_close(self):
        class StillOpen:
            headers = {"Content-Type": "text/event-stream"}

            def __init__(self):
                self.lines = iter([b'data: {"jsonrpc":"2.0","id":1,"result":{}}\n', b'\n'])

            def readline(self, size):
                try:
                    return next(self.lines)
                except StopIteration:
                    raise AssertionError("Client waited after receiving its reply")

        self.assertEqual(read_result(StillOpen(), 1), {})

    def test_truncated_sse_fails(self):
        with self.assertRaisesRegex(ClientError, "ended before"):
            read_result(response(b": ping\n\n", "text/event-stream"), 1)

    def test_html_is_not_parsed_as_feed_data(self):
        with self.assertRaisesRegex(ClientError, "Expected JSON or SSE"):
            read_result(response(b"<html>error</html>", "text/html"), 1)

    def test_argument_bounds(self):
        import argparse
        for invalid in ("0", "101"):
            with self.assertRaises(argparse.ArgumentTypeError):
                limit_value(invalid)
        for invalid in ("-1", "nan", "inf"):
            with self.assertRaises(argparse.ArgumentTypeError):
                usd_value(invalid)

    def test_unknown_tool_is_never_sent(self):
        with self.assertRaisesRegex(ClientError, "four documented free"):
            Client().call("pay_for_bounties")


if __name__ == "__main__":
    unittest.main()
