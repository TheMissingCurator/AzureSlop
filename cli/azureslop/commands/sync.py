"""Implementation of the one-shot Studio-to-disk pull command."""

import os
import sys

from azureslop.action_server import serve_action
from azureslop.config import CONFIG_FILE, load_config


def cmd_sync(port_override: int | None = None):
    project_root = os.getcwd()
    if not os.path.exists(os.path.join(project_root, CONFIG_FILE)):
        print("No AzureSlop project found in this directory.")
        print("Run `azureslop init` first.")
        sys.exit(1)

    config = load_config(project_root)
    port = port_override if port_override is not None else config.get("port", 25123)
    print("AzureSlop Pull")
    print(f"  Project : {config.get('name', 'Unknown')}")
    print(f"  Root    : {project_root}")
    print(f"  Port    : {port}")
    print()
    print("Waiting for the Studio plugin. Click 'Pull into disk' in AzureSlop.")
    print("Press Ctrl+C to cancel.\n")

    try:
        result = serve_action(project_root, config, "pull", port_override=port_override)
    except OSError as error:
        print(f"Could not start the AzureSlop server: {error}")
        sys.exit(1)

    if result:
        print(
            "Pull complete: "
            f"{result.get('updated', 0)} updated, "
            f"{result.get('deleted', 0)} deleted."
        )
