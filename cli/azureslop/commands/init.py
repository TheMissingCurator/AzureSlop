import json
import os
import sys

CONFIG_FILE = ".azureslop"

DEFAULT_CONFIG = {
    "name": "MyGame",
    "port": 25123,
    "services": [
        "ServerScriptService",
        "ReplicatedStorage",
        "StarterGui",
        "StarterPlayer",
        "StarterPack",
        "ServerStorage",
    ],
}


def cmd_init():
    cwd = os.getcwd()
    config_path = os.path.join(cwd, CONFIG_FILE)

    if os.path.exists(config_path):
        print(f"AzureSlop project already exists in this directory.")
        print(f"Edit {CONFIG_FILE} to change settings.")
        sys.exit(0)

    # Prompt for project name
    folder_name = os.path.basename(cwd)
    name = input(f"Project name [{folder_name}]: ").strip()
    if not name:
        name = folder_name

    config = {**DEFAULT_CONFIG, "name": name}

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Initialized AzureSlop project: {name}")
    print(f"  Config: {config_path}")
    print(f"  Watching services: {', '.join(config['services'])}")
    print()
    print("Run `azureslop sync` to start syncing.")
