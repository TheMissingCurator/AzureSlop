"""One-shot HTTP server shared by pull, push, and test commands."""

import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from azureslop.project import (
    apply_studio_choices_to_disk,
    apply_studio_snapshot,
    build_disk_delta,
    compare_disk_to_studio,
    disk_deletions,
    entry_key,
    normalize_instance_path,
    operation_version_map,
    snapshot_version_map,
    studio_snapshot_conflicts,
)


MAX_PULL_CHUNK_BYTES = 600 * 1024
MAX_PULL_CHUNKS = 10_000


def _ambiguous_conflicts(entries: object, services: list[str]) -> list[dict]:
    if not isinstance(entries, list):
        raise ValueError("'ambiguous' must be an array")
    conflicts = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Ambiguous entries must be objects")
        kind = entry.get("kind", "source")
        if kind not in {"source", "gui"}:
            raise ValueError(f"Unsupported entry kind: {kind!r}")
        path = normalize_instance_path(entry.get("path", ""), services)
        conflicts.append(
            {
                "path": path,
                "kind": kind,
                "reason": "duplicate Studio instances have different versions",
            }
        )
    return conflicts


def _report_conflicts(action: str, conflicts: list[dict]) -> None:
    print(f"[{action}] Version conflict; nothing was applied:")
    for conflict in conflicts:
        print(
            f"  {conflict.get('kind', 'source')}:{conflict.get('path', '?')}"
            f" - {conflict.get('reason', 'version conflict')}"
        )
    print("Choose the operation-side override in Studio, or run `azureslop resolve`.")


def _conflict_key(conflict: dict) -> str:
    return entry_key(conflict["path"], conflict.get("kind", "source"))


def _merge_conflicts(conflicts: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for conflict in conflicts:
        key = _conflict_key(conflict)
        if key not in merged:
            merged[key] = dict(conflict)
            continue
        existing_reasons = merged[key]["reason"].split("; ")
        reason = conflict["reason"]
        if reason not in existing_reasons:
            merged[key]["reason"] += "; " + reason
    return sorted(merged.values(), key=lambda item: (item["path"], item["kind"]))


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
        self.pull_chunks: dict[int, bytes] = {}
        self.pull_total: int | None = None
        self.comparison_passed = False
        self.pending_conflict: dict | None = None
        self.resolutions: dict[str, str] = {}


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

        if parsed.path == "/conflicts":
            session = parse_qs(parsed.query).get("session", [""])[0]
            if session != server.session:
                self._send_json({"error": "Invalid session"}, status=403)
                return
            if server.pending_conflict is None:
                self._send_json({"error": "No unresolved conflict"}, status=404)
                return
            self._send_json(
                {
                    "action": server.action,
                    "conflicts": server.pending_conflict["conflicts"],
                }
            )
            return

        if parsed.path == "/changes" and server.action in {"push", "test"}:
            server.comparison_passed = False
            services = server.project_config.get("services", [])
            try:
                response = {
                    "changes": build_disk_delta(server.project_root, services),
                    "deletions": disk_deletions(server.project_root, services),
                }
            except (OSError, ValueError) as error:
                self._send_json({"error": str(error)}, status=400)
                return
            self._send_json(response)
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        server = self.action_server
        try:
            if parsed.path == "/pull/chunk" and server.action == "pull":
                self._receive_pull_chunk(parsed.query)
                return

            data = self._read_json()
            if data.get("session") != server.session:
                self._send_json({"error": "Invalid session"}, status=403)
                return

            if parsed.path == "/pull/complete" and server.action == "pull":
                self._complete_chunked_pull(data)
                return

            if parsed.path == "/resolve":
                self._receive_resolution(data, force=False)
                return

            if parsed.path == "/force":
                self._receive_resolution(data, force=True)
                return

            if parsed.path == "/compare" and server.action in {"push", "test"}:
                current = data.get("current", [])
                if not isinstance(current, list):
                    raise ValueError("'current' must be an array")
                services = server.project_config.get("services", [])
                current_versions = operation_version_map(
                    server.project_root, services, current
                )
                resolutions_valid = self._resolutions_match(current_versions)
                if server.resolutions and resolutions_valid:
                    apply_studio_choices_to_disk(
                        server.project_root,
                        services,
                        current,
                        server.resolutions,
                    )
                elif server.resolutions:
                    server.resolutions = {}
                conflicts = compare_disk_to_studio(
                    server.project_root,
                    services,
                    current,
                )
                conflicts.extend(_ambiguous_conflicts(data.get("ambiguous", []), services))
                conflicts = _merge_conflicts(conflicts)
                if resolutions_valid:
                    conflicts = [
                        conflict
                        for conflict in conflicts
                        if server.resolutions.get(_conflict_key(conflict)) != "disk"
                    ]
                if conflicts:
                    server.result = {"ok": False, "conflicts": conflicts}
                    server.comparison_passed = False
                    server.pending_conflict = {
                        "conflicts": conflicts,
                        "versions": operation_version_map(
                            server.project_root, services, current
                        ),
                    }
                    server.resolutions = {}
                    _report_conflicts(server.action, conflicts)
                    self._send_json(server.result)
                else:
                    server.comparison_passed = True
                    server.pending_conflict = None
                    server.resolutions = {}
                    self._send_json(
                        {
                            "ok": True,
                            "conflicts": [],
                            "changes": build_disk_delta(server.project_root, services),
                            "deletions": disk_deletions(server.project_root, services),
                        }
                    )
                return

            # Compatibility with plugin v0.5 and earlier.
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

            if parsed.path == "/complete" and server.action in {"push", "test"}:
                comparison_required = not (server.action == "test" and server.local)
                if comparison_required and not server.comparison_passed:
                    raise ValueError("Studio version comparison has not passed")
                server.result = {key: value for key, value in data.items() if key != "session"}
                server.completed = True
                self._send_json({"ok": True})
                return
        except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            self._send_json({"error": str(error)}, status=400)
            return
        except OSError as error:
            self._send_json({"error": str(error)}, status=500)
            return

        self._send_json({"error": "Not found"}, status=404)

    def _receive_resolution(self, data: dict, force: bool) -> None:
        server = self.action_server
        pending = server.pending_conflict
        if pending is None:
            raise ValueError("There is no unresolved conflict")
        conflict_keys = {_conflict_key(conflict) for conflict in pending["conflicts"]}
        if force:
            operation_side = "studio" if server.action == "pull" else "disk"
            decisions = {key: operation_side for key in conflict_keys}
        else:
            decisions = data.get("decisions")
            if not isinstance(decisions, dict):
                raise ValueError("'decisions' must be an object")
            decisions = {str(key): str(value) for key, value in decisions.items()}
            if set(decisions) != conflict_keys:
                raise ValueError("A disk or Studio decision is required for every conflict")
            if any(value not in {"disk", "studio"} for value in decisions.values()):
                raise ValueError("Conflict decisions must be 'disk' or 'studio'")
        server.resolutions = decisions
        self._send_json(
            {
                "ok": True,
                "action": server.action,
                "decisions": decisions,
                "message": "Return to Studio and apply the prepared resolution.",
            }
        )

    def _resolutions_match(
        self,
        current_versions: dict[str, dict[str, str | None]],
    ) -> bool:
        server = self.action_server
        if not server.resolutions or server.pending_conflict is None:
            return False
        expected = server.pending_conflict["versions"]
        return all(current_versions.get(key) == expected.get(key) for key in server.resolutions)

    def _receive_pull_chunk(self, query: str) -> None:
        server = self.action_server
        params = parse_qs(query)
        session = params.get("session", [""])[0]
        if session != server.session:
            self._send_json({"error": "Invalid session"}, status=403)
            return

        try:
            index = int(params.get("index", [""])[0])
            total = int(params.get("total", [""])[0])
        except ValueError as error:
            raise ValueError("Pull batch index and total must be integers") from error
        if total < 1 or total > MAX_PULL_CHUNKS or index < 1 or index > total:
            raise ValueError("Invalid pull batch index or total")
        if server.pull_total is not None and server.pull_total != total:
            raise ValueError("Pull batch total changed during upload")

        body = self._read_body(MAX_PULL_CHUNK_BYTES)
        existing = server.pull_chunks.get(index)
        if existing is not None and existing != body:
            raise ValueError(f"Pull batch {index} was uploaded with different content")
        server.pull_total = total
        server.pull_chunks[index] = body
        print(f"[pull] Received batch {index}/{total}")
        self._send_json({"ok": True, "received": index, "total": total})

    def _complete_chunked_pull(self, data: dict) -> None:
        server = self.action_server
        total = data.get("total")
        if not isinstance(total, int) or total < 1 or total > MAX_PULL_CHUNKS:
            raise ValueError("Invalid pull batch total")
        if server.pull_total != total:
            raise ValueError("Pull batch total does not match the upload")
        missing = [index for index in range(1, total + 1) if index not in server.pull_chunks]
        if missing:
            raise ValueError(f"Missing pull batches: {missing[:20]}")

        payload = b"".join(server.pull_chunks[index] for index in range(1, total + 1))
        snapshot = json.loads(payload.decode("utf-8"))
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("changes"), list):
            raise ValueError("Pull batches did not contain a valid snapshot")
        services = server.project_config.get("services", [])
        versions = snapshot_version_map(
            server.project_root, services, snapshot["changes"]
        )
        resolutions_valid = self._resolutions_match(versions)
        if server.resolutions and not resolutions_valid:
            server.resolutions = {}
        resolutions = server.resolutions if resolutions_valid else {}
        conflicts = studio_snapshot_conflicts(
            server.project_root,
            services,
            snapshot["changes"],
            resolutions=resolutions,
        )
        conflicts.extend(
            conflict
            for conflict in _ambiguous_conflicts(
                snapshot.get("ambiguous", []),
                services,
            )
            if _conflict_key(conflict) not in resolutions
        )
        conflicts = _merge_conflicts(conflicts)
        if conflicts:
            server.result = {"ok": False, "conflicts": conflicts}
            server.pending_conflict = {
                "conflicts": conflicts,
                "versions": versions,
            }
            server.resolutions = {}
            _report_conflicts(server.action, conflicts)
            server.pull_chunks.clear()
            server.pull_total = None
            self._send_json(server.result)
            return
        server.result = apply_studio_snapshot(
            server.project_root,
            services,
            snapshot["changes"],
            resolutions=resolutions,
        )
        server.completed = server.result.get("ok") is not False
        if not server.completed:
            server.pending_conflict = {
                "conflicts": server.result.get("conflicts", []),
                "versions": versions,
            }
            server.resolutions = {}
            _report_conflicts(server.action, server.result.get("conflicts", []))
            server.pull_chunks.clear()
            server.pull_total = None
        else:
            server.pending_conflict = None
            server.resolutions = {}
        self._send_json({"ok": True, **server.result})

    def _read_json(self) -> dict:
        data = json.loads(self._read_body() or b"{}")
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _read_body(self, maximum: int | None = None) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or (maximum is not None and length > maximum):
            raise ValueError("Request body is too large")
        return self.rfile.read(length)

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
