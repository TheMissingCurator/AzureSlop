import json
import os

CONFIG_FILE = ".azureslop"


def load_config(project_root: str) -> dict:
    path = os.path.join(project_root, CONFIG_FILE)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
