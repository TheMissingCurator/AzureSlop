import json
import os
import sys

from azureslop.config import load_config, CONFIG_FILE


def cmd_config(args):
    cwd = os.getcwd()
    config_path = os.path.join(cwd, CONFIG_FILE)

    if not os.path.exists(config_path):
        print("No AzureSlop project found in this directory.")
        print("Run `azureslop init` to create one.")
        sys.exit(1)

    subcommand = getattr(args, "config_command", None)

    if subcommand is None or subcommand == "show":
        config = load_config(cwd)
        print(json.dumps(config, indent=2))

    elif subcommand == "set":
        _set_value(config_path, args.key, args.value)

    else:
        print(f"Unknown config subcommand: {subcommand}")
        sys.exit(1)


_INT_KEYS = {"port"}
_LIST_KEYS = {"services"}


def _set_value(config_path: str, key: str, raw_value: str):
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if key not in config and key not in _INT_KEYS | _LIST_KEYS | {"name", "place"}:
        print(f"Unknown key: {key!r}")
        print("Valid keys: name, port, services, place")
        sys.exit(1)

    if key in _INT_KEYS:
        try:
            value = int(raw_value)
        except ValueError:
            print(f"'{key}' must be an integer, got: {raw_value!r}")
            sys.exit(1)
    elif key in _LIST_KEYS:
        value = [s.strip() for s in raw_value.split(",") if s.strip()]
    else:
        value = raw_value

    old = config.get(key)
    config[key] = value

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"Updated {key}: {old!r} → {value!r}")
