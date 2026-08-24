"""One-shot HTTP server shared by the pull and test commands."""

import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from azureslop.project import apply_studio_snapshot, build_disk_snapshot, disk_deletions


class ActionServer(HTTPServer):
    def __init__(self, address, project_root: str, config: dict, action: str, local: bool):
        super().__init__(address, ActionHandler)
        self.project_root = project_root
        self.project_config = config
        self.action = action
        self.local = local
        self.session = secrets.token_urlsafe(18)
        self.completed = False
        self.result: dict = {}


class ActionHandler(BaseHTTPRequestHandler):
    @property
    def action_server(self) -> ActionServer:
        return self.server  # type: ignore[return-value]

    def do_GET(self):
        parsed = urlparse(self.path)
        server = self.action_server

        if parsed.path == "/config":
            response = dict(server.project_config)
            response.pop("place", None)
            response.update(
                {
                    "action": server.action,
                    "local": server.local,
                    "session": server.session,
                }
            )
            self._send_json(response)
            return

        if parsed.path == "/changes" and server.action == "test":
            services = server.project_config.get("services", [])
            self._send_json(
                {
                    "changes": build_disk_snapshot(server.project_root, services),
                    "deletions": disk_deletions(server.project_root, services),
                }
            )
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        server = self.action_server
        try:
            data = self._read_json()
            if data.get("session") != server.session:
                self._send_json({"error": "Invalid session"}, status=403)
                return

            if parsed.path == "/pull" and server.action == "pull":
                changes = data.get("changes", [])
                if not isinstance(changes, list):
                    raise ValueError("'changes' must be an array")
                server.result = apply_studio_snapshot(
                    server.project_root,
                    server.project_config.get("services", []),
                    changes,
                )
                server.completed = True
                self._send_json({"ok": True, **server.result})
                return

            if parsed.path == "/complete" and server.action == "test":
                server.result = {key: value for key, value in data.items() if key != "session"}
                server.completed = True
                self._send_json({"ok": True})
                return
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._send_json({"error": str(error)}, status=400)
            return
        except OSError as error:
            self._send_json({"error": str(error)}, status=500)
            return

        self._send_json({"error": "Not found"}, status=404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def serve_action(
    project_root: str,
    config: dict,
    action: str,
    local: bool = False,
    port_override: int | None = None,
) -> dict:
    port = port_override if port_override is not None else config.get("port", 25123)
    server = ActionServer(("localhost", port), project_root, config, action, local)
    server.timeout = 0.5
    try:
        while not server.completed:
            server.handle_request()
    except KeyboardInterrupt:
        print("\n[Cancelled]")
        return {}
    finally:
        server.server_close()
    return server.result
