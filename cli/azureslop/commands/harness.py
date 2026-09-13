"""Terminal interface for coding agents controlling the AzureSlop plugin."""

import json
import math
from pathlib import Path
import sys
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

from azureslop.config import load_config
from azureslop.harness import HarnessServer, METHODS, MAX_BODY
from azureslop.action_server import _ambiguous_conflicts, _merge_conflicts
from azureslop.project import apply_studio_snapshot, studio_snapshot_conflicts
from azureslop.vision import decode_image, png_bytes, contact_sheet, write_new, export_result


def add_parser(subparsers):
    parser = subparsers.add_parser("harness", help="Persistent Studio tools for coding agents")
    subs = parser.add_subparsers(dest="harness_command", required=True)
    for command in ("serve", "status", "call", "result", "pull", "capture"):
        sub = subs.add_parser(command)
        sub.add_argument("--port", "-p", type=int, help="Override .azureslop port (default 25123)")
        if command in {"call", "pull", "capture"}:
            sub.add_argument("--session", help="Studio window ID from harness status")
            sub.add_argument("--timeout", type=float, default=30, help="Wait seconds; not a cancellation")
        if command == "call":
            sub.add_argument("method", choices=sorted(METHODS))
            sub.add_argument("--params", default="{}", help="JSON object or @file.json")
            sub.add_argument("--source", type=Path, help="UTF-8 Luau file for execute/write_source")
            sub.add_argument("--id", help="Reuse an existing request ID after a lost submit response")
        if command == "result":
            sub.add_argument("id")
        if command in {"call", "result", "capture"}:
            sub.add_argument("--output", type=Path, required=command == "capture",
                             help="New directory for viewport PNGs and metadata; never overwrites")
        if command == "capture":
            sub.add_argument("--preview", help="Preview ID; omit for one current-viewport screenshot")
            sub.add_argument("--times", help="Comma-separated seconds; defaults to the current preview time")
            sub.add_argument("--views", default="front,side,angled", help="Comma-separated preview camera views")
            sub.add_argument("--width", type=int, default=512)
            sub.add_argument("--height", type=int, default=512)


def request(port, path, data=None):
    body = None if data is None else json.dumps(data, ensure_ascii=True).encode()
    if body is not None and len(body) > MAX_BODY:
        raise ValueError("Command exceeds 600 KiB; split the command into smaller edits")
    req = Request(f"http://127.0.0.1:{port}{path}", data=body,
                  headers={"Content-Type": "application/json"})
    # Local Studio traffic must not go through a machine's HTTP proxy.
    try:
        with build_opener(ProxyHandler({})).open(req, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        with exc:
            raise ValueError(exc.read().decode("utf-8", errors="replace")) from None


def call(port, method, params, session=None, timeout=30, ident=None):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("--timeout must be a positive finite number")
    ident = ident or str(uuid.uuid4())
    # stderr keeps stdout machine-readable; ID is available even if submit fails.
    print(f"AzureSlop job {ident}; retrieve with: azureslop harness result {ident} --port {port}",
          file=sys.stderr, flush=True)
    request(port, "/harness/submit", {"id": ident, "method": method,
                                     "params": params, "session": session})
    deadline = time.monotonic() + timeout
    while True:
        result = request(port, "/harness/job", {"id": ident})
        if result["status"] in {"done", "expired", "unknown"}:
            return result
        if time.monotonic() >= deadline:
            return dict(result, waitTimedOut=True)
        time.sleep(min(0.25, max(0, deadline-time.monotonic())))


def apply_harness_pull(project_root, services, snapshot):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("changes"), list):
        raise ValueError("Studio returned an invalid snapshot")
    conflicts = _ambiguous_conflicts(snapshot.get("ambiguous", []), services)
    conflicts.extend(studio_snapshot_conflicts(project_root, services, snapshot["changes"]))
    if conflicts:
        return {"ok": False, "updated": 0, "deleted": 0,
                "conflicts": _merge_conflicts(conflicts)}
    return apply_studio_snapshot(project_root, services, snapshot["changes"])


def capture_strip(args, port):
    """One bounded, recoverable job per view/time; never blindly retry a capture."""
    if not 64 <= args.width <= 1024 or not 64 <= args.height <= 1024:
        raise ValueError("Capture dimensions must be 64..1024")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("--timeout must be positive and finite")
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("Capture output directory already exists; choose a new directory")
    if not args.preview:
        if args.times:
            raise ValueError("--times requires --preview")
        result = call(port, "viewport_capture", {"width": args.width, "height": args.height},
                      args.session, args.timeout)
        return export_result(result, args.output)
    views = args.views.split(",")
    if not views or len(views) != len(set(views)) or any(v not in {"front", "side", "angled"} for v in views):
        raise ValueError("Use unique front,side,angled views")
    times = [float(t) for t in args.times.split(",")] if args.times else [None]
    if not times or len(times) * len(views) > 24 or any(t is not None and (not math.isfinite(t) or t < 0) for t in times):
        raise ValueError("Use nonnegative finite times and at most 24 total images")
    directory = args.output.absolute()
    directory.mkdir(parents=True, exist_ok=False)
    images, frames = [], []
    revision = None
    try:
        for view in views:
            for timestamp in times:
                params = {"preview": args.preview, "view": view, "width": args.width, "height": args.height}
                if revision is not None:
                    params["expectedRevision"] = revision
                if timestamp is not None:
                    params["time"] = timestamp
                result = call(port, "preview_capture", params, args.session, args.timeout)
                if result["status"] != "done" or not result.get("result", {}).get("ok"):
                    write_new(directory / "incomplete.json", json.dumps({"frames": frames, "job": result}, indent=2).encode())
                    return result
                value = result["result"]["value"]
                if revision is not None and value["revision"] != revision:
                    raise ValueError("Preview edited during capture; refusing a mixed-revision strip")
                revision = value["revision"]
                if timestamp is None:
                    times[0] = value["time"]
                image = decode_image(value["image"])
                filename = f"{len(images):03d}-{view}.png"
                write_new(directory / filename, png_bytes(*image))
                images.append(image)
                frames.append({"file": filename, "view": view, "time": value["time"],
                               "camera": value["camera"], "job": result["id"]})
        write_new(directory / "strip.png", contact_sheet(images, len(times)))
        manifest = {"ok": True, "preview": args.preview, "revision": revision, "rows": views,
                    "columns": times, "frames": frames, "strip": str(directory / "strip.png")}
        write_new(directory / "manifest.json", json.dumps(manifest, indent=2).encode())
        return manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Keep successful frames and their exact timestamps even when a later capture fails.
        write_new(directory / "incomplete.json", json.dumps({"frames": frames, "error": str(exc)}, indent=2).encode())
        if isinstance(exc, (KeyError, TypeError)):
            raise ValueError(f"Invalid Studio capture result: {exc}") from exc
        raise


def cmd_harness(args):
    try:
        root = str(Path.cwd().resolve())
        try:
            config = load_config(root)
        except FileNotFoundError:
            if args.harness_command in {"serve", "pull"}:
                raise ValueError("Run azureslop init in the project first") from None
            config = {}
        port = args.port if args.port is not None else config.get("port", 25123)
        if not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        if args.harness_command == "serve":
            with HarnessServer(port, root, config) as server:
                print(f"AzureSlop harness: http://127.0.0.1:{port}\nProject: {root}\n"
                      "Open AzureSlop in Studio and click Enable harness. No token required.", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
            return
        if args.harness_command == "status":
            result = request(port, "/harness/status", {})
        elif args.harness_command == "result":
            result = request(port, "/harness/job", {"id": args.id})
        elif args.harness_command == "capture":
            result = capture_strip(args, port)
        elif args.harness_command == "pull":
            remote_config = request(port, "/config")
            if remote_config.get("action") != "harness" or remote_config.get("projectRoot") != root:
                raise ValueError("Harness belongs to another project; run pull from its project directory")
            result = call(port, "snapshot", {}, args.session, args.timeout)
            if result["status"] == "done" and result["result"].get("ok"):
                result = apply_harness_pull(root, remote_config["services"], result["result"]["value"])
        else:
            if args.output and args.method not in {"viewport_capture", "preview_capture"}:
                raise ValueError("--output is only supported for viewport_capture and preview_capture")
            if args.output and (args.output.exists() or args.output.is_symlink()):
                raise ValueError("Capture output directory already exists; choose a new directory")
            params = json.loads(Path(args.params[1:]).read_text(encoding="utf-8")
                                if args.params.startswith("@") else args.params)
            if not isinstance(params, dict):
                raise ValueError("--params must be a JSON object")
            if args.source:
                if args.method not in {"execute", "write_source"}:
                    raise ValueError("--source is only supported for execute and write_source")
                params["source"] = args.source.read_text(encoding="utf-8")
            result = call(port, args.method, params, args.session, args.timeout, args.id)
        if args.harness_command in {"call", "result"} and args.output:
            result = export_result(result, args.output)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        if "status" in result:
            if result["status"] != "done":
                raise SystemExit(2)
            if not result["result"].get("ok"):
                raise SystemExit(1)
        elif result.get("ok") is False:
            raise SystemExit(1)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1) from None
