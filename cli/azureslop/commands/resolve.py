"""Interactive conflict resolution for a running AzureSlop action."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from azureslop.config import CONFIG_FILE, load_config


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.load(response)


def cmd_resolve(port_override: int | None = None) -> None:
    project_root = os.getcwd()
    if not os.path.exists(os.path.join(project_root, CONFIG_FILE)):
        print("No AzureSlop project found in this directory.")
        print("Run `azureslop init` first.")
        sys.exit(1)

    config = load_config(project_root)
    port = port_override if port_override is not None else config.get("port", 25123)
    base_url = f"http://localhost:{port}"
    try:
        active = _get_json(base_url + "/config")
        session = urllib.parse.quote(active["session"], safe="")
        pending = _get_json(base_url + f"/conflicts?session={session}")
    except (OSError, KeyError, ValueError, urllib.error.URLError) as error:
        print(f"Could not find a waiting AzureSlop conflict on port {port}: {error}")
        sys.exit(1)

    action = pending.get("action", "action")
    conflicts = pending.get("conflicts", [])
    if not conflicts:
        print("The active AzureSlop command has no unresolved conflicts.")
        return

    print(f"AzureSlop Resolve ({action})")
    print("Choose which version should win for each path:")
    print("  [d] disk    Keep the file currently in the IDE")
    print("  [s] Studio  Keep the instance currently in Roblox Studio")
    print("  [q] quit    Leave the conflict unresolved")
    print()

    decisions: dict[str, str] = {}
    try:
        for index, conflict in enumerate(conflicts, start=1):
            kind = conflict.get("kind", "source")
            path = conflict.get("path", "?")
            reason = conflict.get("reason", "version conflict")
            key = f"{kind}:{path}"
            while True:
                choice = input(
                    f"[{index}/{len(conflicts)}] {path}\n"
                    f"  {reason}\n"
                    "  Keep [d]isk, [s]tudio, or [q]uit? "
                ).strip().lower()
                if choice in {"d", "disk"}:
                    decisions[key] = "disk"
                    break
                if choice in {"s", "studio"}:
                    decisions[key] = "studio"
                    break
                if choice in {"q", "quit"}:
                    print("Resolution cancelled; the original command is still waiting.")
                    return
                print("Enter d, s, or q.")
    except (EOFError, KeyboardInterrupt):
        print("\nResolution cancelled; the original command is still waiting.")
        return

    request = urllib.request.Request(
        base_url + "/resolve",
        data=json.dumps(
            {"session": active["session"], "decisions": decisions}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        print(f"Resolution was rejected: {detail}")
        sys.exit(1)
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(f"Could not send the resolution: {error}")
        sys.exit(1)

    if not result.get("ok"):
        print(f"Resolution was rejected: {result.get('error', 'unknown error')}")
        sys.exit(1)
    print("Resolution prepared. Return to Studio and click 'Apply resolution'.")
