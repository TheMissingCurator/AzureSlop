"""
AzureSlop sync server.

Endpoints (called by the Studio plugin every ~5 seconds):

  GET  /changes?since=<unix_timestamp>
       Returns files changed or deleted on disk since that timestamp.
       Response: {
         "changes":   [ { "path": "...", "source": "...", "type": "Script|LocalScript|ModuleScript", "timestamp": 0 }, ... ],
         "deletions": [ "ServerScriptService/Light1/ControlScript", ... ]
       }

  POST /update
       Receives script changes from Studio and writes them to disk.
       Body: { "changes": [ { "path": "...", "source": "...", "timestamp": 0 }, ... ] }
       Response: { "ok": true }

  POST /delete
       Receives paths of scripts deleted in Studio and removes them from disk.
       Body: { "paths": [ "ServerScriptService/Light1/ControlScript", ... ] }
       Response: { "ok": true }

  GET  /config
       Returns the current project config so the plugin knows which services to watch.
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from azureslop.config import load_config, CONFIG_FILE
from azureslop.watcher import FileWatcher

# Tracks writes/deletes we made ourselves to break echo-loops.
# Both dicts are protected by _watcher.lock (set in cmd_sync).
_our_writes: dict[str, float] = {}
_our_deletes: dict[str, float] = {}

_watcher: "FileWatcher | None" = None
_project_root: str = ""


_TYPE_TO_EXT = {
    "Script": ".server.lua",
    "LocalScript": ".client.lua",
    "ModuleScript": ".module.lua",
}
# Order matters: check longer/specific extensions before the legacy catch-all.
_KNOWN_EXTS = (".server.lua", ".client.lua", ".module.lua", ".lua")


def _script_path_to_file(rel_path: str, script_type: str = "") -> str:
    """
    Convert a script path like 'ServerScriptService/Light1/ControlScript'
    to an absolute file path. Searches for an existing file first; for new
    files uses script_type to pick the right extension.
    """
    for ext in _KNOWN_EXTS:
        candidate = os.path.join(_project_root, rel_path + ext)
        if os.path.exists(candidate):
            return candidate
    ext = _TYPE_TO_EXT.get(script_type, ".module.lua")
    return os.path.join(_project_root, rel_path + ext)


def _file_to_script_path(abs_path: str) -> str | None:
    """
    Convert an absolute file path back to a rel script path, stripping extensions.
    Returns None if the file isn't under the project root or isn't a .lua file.
    """
    rel = os.path.relpath(abs_path, _project_root)
    if rel.startswith(".."):
        return None
    for ext in _KNOWN_EXTS:
        if rel.endswith(ext):
            return rel[: -len(ext)]
    return None


def _infer_type(abs_path: str) -> str:
    if abs_path.endswith(".server.lua"):
        return "Script"
    if abs_path.endswith(".client.lua"):
        return "LocalScript"
    return "ModuleScript"


class SyncHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/config":
            self._send_json(load_config(_project_root))

        elif parsed.path == "/changes":
            params = parse_qs(parsed.query)
            since = float(params.get("since", ["0"])[0])
            changes, deletions = self._get_changes_since(since)
            if changes:
                print(f"[sync] Disk → Studio: {len(changes)} script(s) updated")
            if deletions:
                print(f"[sync] Disk → Studio: {len(deletions)} script(s) deleted")
            self._send_json({"changes": changes, "deletions": deletions})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/update":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                self._apply_updates(data.get("changes", []))
                self._send_json({"ok": True})
            except Exception as e:
                print(f"[ERROR] /update failed: {e}")
                self.send_response(500)
                self.end_headers()

        elif parsed.path == "/delete":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                self._handle_deletes(data.get("paths", []))
                self._send_json({"ok": True})
            except Exception as e:
                print(f"[ERROR] /delete failed: {e}")
                self.send_response(500)
                self.end_headers()

        else:
            self.send_response(404)
            self.end_headers()

    def _get_changes_since(self, since: float) -> tuple[list[dict], list[str]]:
        if _watcher is None:
            return [], []

        changes = []
        deletions = []

        with _watcher.lock:
            for abs_path, mtime in list(_watcher.changed_files.items()):
                if mtime <= since:
                    continue
                # Skip files we wrote ourselves (avoid echo loop)
                if abs(mtime - _our_writes.get(abs_path, 0)) < 0.5:
                    continue
                rel = _file_to_script_path(abs_path)
                if rel is None:
                    continue
                try:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    changes.append({
                        "path": rel,
                        "source": source,
                        "type": _infer_type(abs_path),
                        "timestamp": mtime,
                    })
                except Exception:
                    pass

            for abs_path, mtime in list(_watcher.deleted_files.items()):
                if mtime <= since:
                    continue
                # Skip files we deleted ourselves (avoid echo loop)
                if abs(mtime - _our_deletes.get(abs_path, 0)) < 0.5:
                    continue
                rel = _file_to_script_path(abs_path)
                if rel is not None:
                    deletions.append(rel)

        return changes, deletions

    def _apply_updates(self, changes: list[dict]):
        for change in changes:
            rel_path = change.get("path", "")
            source = change.get("source", "")
            studio_ts = float(change.get("timestamp", 0))
            script_type = change.get("type", "ModuleScript")

            abs_path = _script_path_to_file(rel_path, script_type)
            disk_ts = os.path.getmtime(abs_path) if os.path.exists(abs_path) else 0

            # Last write wins
            if studio_ts >= disk_ts:
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(source)
                # Store the file's actual mtime so the echo filter can do an
                # exact-match comparison rather than a fragile timing window.
                with _watcher.lock:
                    _our_writes[abs_path] = os.path.getmtime(abs_path)
                print(f"[sync] Studio → disk: {rel_path}")
            else:
                print(f"[skip] Disk is newer, skipping: {rel_path}")

    def _handle_deletes(self, rel_paths: list[str]):
        for rel_path in rel_paths:
            abs_path = _script_path_to_file(rel_path)
            if not os.path.exists(abs_path):
                continue
            os.remove(abs_path)
            with _watcher.lock:
                _our_deletes[abs_path] = time.time()
                _watcher.changed_files.pop(abs_path, None)
            # Remove empty parent dirs up to project root
            parent = os.path.dirname(abs_path)
            try:
                while parent != _project_root and not os.listdir(parent):
                    os.rmdir(parent)
                    parent = os.path.dirname(parent)
            except OSError:
                pass
            print(f"[sync] Studio → disk: deleted {rel_path}")

    def _send_json(self, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress default noisy HTTP logs; we do our own
        pass


def cmd_sync(port_override: int | None = None):
    global _watcher, _project_root

    cwd = os.getcwd()
    config_path = os.path.join(cwd, CONFIG_FILE)

    if not os.path.exists(config_path):
        print(f"No AzureSlop project found in this directory.")
        print(f"Run `azureslop init` first.")
        sys.exit(1)

    config = load_config(cwd)
    _project_root = cwd
    port = port_override if port_override is not None else config.get("port", 25123)

    print(f"AzureSlop Sync")
    print(f"  Project : {config.get('name', 'Unknown')}")
    print(f"  Root    : {cwd}")
    print(f"  Port    : {port}")
    print(f"  Services: {', '.join(config.get('services', []))}")
    print()
    print(f"Waiting for Studio plugin to connect on http://localhost:{port} ...")
    print(f"Press Ctrl+C to stop.\n")

    # Start file watcher
    _watcher = FileWatcher(cwd)
    _watcher.start()

    # Start HTTP server
    server = HTTPServer(("localhost", port), SyncHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Stopped]")
        _watcher.stop()
        sys.exit(0)
