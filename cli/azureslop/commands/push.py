"""Implementation of the one-shot disk-to-Studio push command."""

import os
import sys

from azureslop.action_server import serve_action
from azureslop.config import CONFIG_FILE, load_config
from azureslop.project import record_disk_snapshot


def cmd_push(port_override: int | None = None):
    project_root = os.getcwd()
    if not os.path.exists(os.path.join(project_root, CONFIG_FILE)):
        print("No AzureSlop project found in this directory.")
        print("Run `azureslop init` first.")
        sys.exit(1)

    config = load_config(project_root)
    port = port_override if port_override is not None else config.get("port", 25123)
    print("AzureSlop Push")
    print(f"  Project : {config.get('name', 'Unknown')}")
    print(f"  Root    : {project_root}")
    print(f"  Port    : {port}")
    print()
    print("Waiting for the Studio plugin. Click 'Push into Studio' in AzureSlop.")
    print("Studio must still match the last sync. Changed files and tracked deletions will be sent.")
    print("Press Ctrl+C to cancel.\n")

    try:
        result = serve_action(project_root, config, "push", port_override=port_override)
    except OSError as error:
        print(f"Could not start the AzureSlop server: {error}")
        sys.exit(1)

    if not result:
        return
    if result.get("ok") is False:
        print("Push blocked: Studio changed since your last sync.")
        for conflict in result.get("conflicts", []):
            print(
                f"  {conflict.get('kind', 'source')}:{conflict.get('path', '?')}"
                f" - {conflict.get('reason', 'version conflict')}"
            )
        print("Nothing was applied. Run `azureslop sync`, review any conflicts, then push again.")
        sys.exit(1)
    if result.get("skipped", 0) == 0 and not result.get("errors"):
        record_disk_snapshot(project_root, config.get("services", []))
    print(
        "Push complete: "
        f"{result.get('updated', 0)} updated, "
        f"{result.get('created', 0)} created, "
        f"{result.get('deleted', 0)} deleted, "
        f"{result.get('unchanged', 0)} unchanged, "
        f"{result.get('skipped', 0)} skipped."
    )
    for error in result.get("errors", []):
        print(f"  warning: {error}")
