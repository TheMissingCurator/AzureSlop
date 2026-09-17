import json
import os
import sys

from azureslop.config import CONFIG_FILE

DEFAULT_SERVICES = [
    "ServerScriptService",
    "ReplicatedStorage",
    "StarterGui",
    "StarterPlayer",
    "StarterPack",
    "ServerStorage",
]


def cmd_init(name: str | None = None):
    cwd = os.getcwd()
    config_path = os.path.join(cwd, CONFIG_FILE)

    if os.path.exists(config_path):
        print(f"AzureSlop project already exists in this directory.")
        print(f"Edit {CONFIG_FILE} to change settings, or use `azureslop config set`.")
        sys.exit(0)

    if name is None:
        folder_name = os.path.basename(cwd)
        name = input(f"Project name [{folder_name}]: ").strip() or folder_name

    config = {
        "name": name,
        "port": 25123,
        "services": DEFAULT_SERVICES,
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"Initialized AzureSlop project: {name}")
    print(f"  Config  : {config_path}")
    print(f"  Services: {', '.join(config['services'])}")
    print()
    print("Run `azureslop sync` to bring your open Studio place into this project.")
