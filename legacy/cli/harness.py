"""Persistent, token-free loopback transport for AzureSlop Studio commands."""

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

METHODS = frozenset({
    "ping", "tree", "get", "selection", "create", "set", "delete",
    "read_source", "write_source", "execute", "logs", "snapshot",
    "preview_start", "preview_status", "preview_seek", "preview_step", "preview_camera",
    "preview_capture", "preview_keyframes", "preview_edit", "preview_undo", "preview_export",
    "preview_diagnose", "preview_stop", "vision_capabilities", "vision_permission", "viewport_capture",
})
MAX_BODY = 600 * 1024
MAX_RESULT_CHUNKS = 64
ONLINE_SECONDS = 10
JOB_SECONDS = 120
RETENTION_SECONDS = 3600


class HarnessState:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.epoch = str(uuid.uuid4())
        self.lock = threading.RLock()
        self.sessions = {}
        self.jobs = {}

    def _expire(self):
        now = self.clock()
        for ident, job in list(self.jobs.items()):
            if now >= job["expires"]:
                if job["status"] == "queued":
                    job["status"] = "expired"
                elif job["status"] == "running":
                    job["status"] = "unknown"
            # Unknown executions keep blocking their session until a late result
            # or explicit disconnect. Never overlap an uncertain mutation.
            if now >= job["expires"] + RETENTION_SECONDS and job["status"] != "unknown":
                del self.jobs[ident]
        for ident, session in list(self.sessions.items()):
            if now - session["seen"] > RETENTION_SECONDS and not any(
                j["session"] == ident for j in self.jobs.values()
            ):
                del self.sessions[ident]

    @staticmethod
    def _identifier(value):
        if not isinstance(value, str) or not value or len(value) > 100:
            raise ValueError("Expected a nonempty ID of at most 100 characters")
        return value

    def _peer(self, data):
        if data.get("epoch") != self.epoch:
            raise ValueError("Harness restarted; enable it again in Studio")
        return self._identifier(data.get("session"))

    def _job(self, ident):
        ident = self._identifier(ident)
        if ident not in self.jobs:
            raise ValueError("Unknown job ID (expired or harness restarted)")
        return self.jobs[ident]

    def dispatch(self, path, data):
        with self.lock:
            self._expire()
            now = self.clock()
            if path == "/harness/status":
                return {"epoch": self.epoch, "sessions": [
                    dict(v, id=k, online=v["enabled"] and now-v["seen"] < ONLINE_SECONDS)
                    for k, v in self.sessions.items()
                ]}
            if path == "/harness/poll":
                session = self._peer(data)
                self.sessions[session] = {
                    "seen": now, "enabled": True,
                    "place": str(data.get("place", ""))[:200],
                    "placeId": str(data.get("placeId", "0"))[:40],
                }
                if any(j["session"] == session and j["status"] in {"running", "unknown"}
                       for j in self.jobs.values()):
                    return {"job": None}
                for job in self.jobs.values():
                    if job["session"] == session and job["status"] == "queued":
                        job["status"] = "running"
                        return {"job": {k: job[k] for k in ("id", "method", "params")}}
                return {"job": None}
            if path == "/harness/disconnect":
                session = self._peer(data)
                if session in self.sessions:
                    self.sessions[session]["enabled"] = False
                for job in self.jobs.values():
                    if job["session"] == session and job["status"] == "queued":
                        job["status"] = "expired"
                return {"ok": True}
            if path == "/harness/submit":
                method, params = data.get("method"), data.get("params", {})
                if not isinstance(method, str) or method not in METHODS:
                    raise ValueError("Unknown harness method")
                if not isinstance(params, dict):
                    raise ValueError("params must be a JSON object")
                ident = self._identifier(data.get("id"))
                # Callers choose an ID before sending: retrying a lost submit
                # response with that same ID cannot enqueue a second mutation.
                if ident in self.jobs:
                    old = self.jobs[ident]
                    if old["method"] != method or old["params"] != params or (
                        data.get("session") and old["session"] != data["session"]
                    ):
                        raise ValueError("Job ID already used for different arguments")
                    return {"id": ident}
                online = [k for k, v in self.sessions.items()
                          if v["enabled"] and now-v["seen"] < ONLINE_SECONDS]
                session = data.get("session")
                if session is None:
                    if len(online) != 1:
                        raise ValueError("Enable one Studio window or specify --session")
                    session = online[0]
                if session not in online:
                    raise ValueError("Studio session is offline; enable harness in that window")
                if len(self.jobs) >= 1000 or sum(
                    j["status"] in {"queued", "running", "unknown"} for j in self.jobs.values()
                ) >= 100:
                    raise ValueError("Harness queue full")
                self.jobs[ident] = dict(id=ident, session=session, method=method,
                                       params=params, status="queued", expires=now+JOB_SECONDS,
                                       chunks={}, total=None)
                return {"id": ident}
            if path == "/harness/job":
                job = self._job(data.get("id"))
                return {k: v for k, v in job.items() if k not in {"params", "chunks", "total"}}
            if path == "/harness/result/complete":
                session = self._peer(data)
                job = self._job(data.get("id"))
                if job["session"] != session:
                    raise ValueError("Wrong Studio session for result")
                if job["status"] == "done":
                    return {"ok": True}
                total = job["total"]
                if total is None or len(job["chunks"]) != total:
                    raise ValueError("Result upload is incomplete")
                result = json.loads(b"".join(job["chunks"][i] for i in range(1, total+1)))
                if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                    raise ValueError("Expected a result object with boolean ok")
                job.update(status="done", result=result, chunks={})
                return {"ok": True}
            raise ValueError("Unknown harness endpoint")

    def receive_chunk(self, data, body):
        with self.lock:
            self._expire()
            session = self._peer(data)
            job = self._job(data.get("id"))
            if job["session"] != session or job["status"] not in {"running", "unknown", "done"}:
                raise ValueError("Job was not dispatched to this Studio session")
            index, total = int(data.get("index", 0)), int(data.get("total", 0))
            if not 1 <= index <= total <= MAX_RESULT_CHUNKS or len(body) > MAX_BODY:
                raise ValueError("Invalid result batch")
            if job["status"] == "done":
                return {"ok": True}
            if job["total"] not in (None, total):
                raise ValueError("Result batch count changed")
            if index in job["chunks"] and job["chunks"][index] != body:
                raise ValueError("Result batch content changed")
            job["total"] = total
            job["chunks"][index] = body
            return {"ok": True}


class HarnessServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, project_root, config):
        self.state = HarnessState()
        self.project_root = project_root
        self.config = config
        super().__init__(("127.0.0.1", port), HarnessHandler)


class HarnessHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _local_request(self):
        # No bearer token. Bind to loopback; reject browser origins and DNS
        # rebinding hosts without adding pairing friction to Studio.
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in allowed or self.headers.get("Origin") is not None:
            self._send(403, {"error": "Only local non-browser requests are accepted"})
            return False
        return True

    def do_GET(self):
        if not self._local_request():
            return
        if self.path == "/config":
            self._send(200, {"action": "harness", "session": self.server.state.epoch,
                             "name": self.server.config.get("name", "AzureSlop"),
                             "services": self.server.config.get("services", []),
                             "projectRoot": self.server.project_root})
        else:
            self._send(404, {"error": "Not found"})

    def do_POST(self):
        if not self._local_request():
            return
        self.connection.settimeout(10)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                raise ValueError("Request exceeds 600 KiB; use result batches or a smaller command")
            body = self.rfile.read(size)
            parsed = urlparse(self.path)
            if parsed.path == "/harness/result/chunk":
                data = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                result = self.server.state.receive_chunk(data, body)
            else:
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Expected application/json")
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object")
                result = self.server.state.dispatch(parsed.path, data)
            self._send(200, result)
        except (ValueError, TypeError, UnicodeError) as exc:
            self._send(400, {"error": str(exc)})
        except OSError:
            self.close_connection = True

    def _send(self, status, data):
        body = json.dumps(data, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
