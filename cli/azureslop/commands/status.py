import os
import sys
import urllib.request

from azureslop.config import load_config, CONFIG_FILE


def cmd_status():
    cwd = os.getcwd()
    config_path = os.path.join(cwd, CONFIG_FILE)

    if not os.path.exists(config_path):
        print("No AzureSlop project found in this directory.")
        print("Run `azureslop init` to create one.")
        sys.exit(1)

    config = load_config(cwd)
    port = config.get("port", 25123)

    print(f"Project : {config.get('name', 'Unknown')}")
    print(f"Root    : {cwd}")
    print(f"Port    : {port}")
    print(f"Services: {', '.join(config.get('services', []))}")
    print()

    try:
        with urllib.request.urlopen(f"http://localhost:{port}/config", timeout=1):
            print(f"Action  : \033[32mwaiting for Studio\033[0m  (http://localhost:{port})")
    except Exception:
        print("Action  : \033[33mnone\033[0m  (run `azureslop sync`, `push`, or `test`)")
