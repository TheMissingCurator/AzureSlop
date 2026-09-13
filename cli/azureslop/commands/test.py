"""Apply local sources as Studio drafts or to a disposable local place."""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from azureslop.action_server import serve_action
from azureslop.config import CONFIG_FILE, load_config


def _copy_local_place(project_root: str, configured_place: str) -> Path:
    source = Path(configured_place).expanduser()
    if not source.is_absolute():
        source = Path(project_root) / source
    source = source.resolve()
    if not source.is_file() or source.suffix.lower() not in {".rbxl", ".rbxlx"}:
        raise ValueError(f"Local testing place does not exist or is not .rbxl/.rbxlx: {source}")

    destination_root = Path(project_root) / ".azureslop-local"
    destination_root.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = destination_root / f"{source.stem}-{timestamp}{source.suffix}"
    shutil.copy2(source, destination)
    return destination


def _open_place(place_path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(place_path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(place_path)])
    else:
        subprocess.Popen(["xdg-open", str(place_path)])


def cmd_test(
    local: bool = False,
    place_override: str | None = None,
    port_override: int | None = None,
):
    project_root = os.getcwd()
    if not os.path.exists(os.path.join(project_root, CONFIG_FILE)):
        print("No AzureSlop project found in this directory.")
        print("Run `azureslop init` first.")
        sys.exit(1)

    config = load_config(project_root)
    port = port_override if port_override is not None else config.get("port", 25123)

    if local:
        configured_place = place_override or config.get("place")
        if not configured_place:
            print("`azureslop test --local` needs a baseline Roblox place file.")
            print("Set one with `azureslop config set place path/to/game.rbxl`.")
            sys.exit(1)
        try:
            local_place = _copy_local_place(project_root, configured_place)
            _open_place(local_place)
        except (OSError, ValueError) as error:
            print(f"Could not prepare the local test place: {error}")
            sys.exit(1)
        print(f"Opened disposable place: {local_place}")

    print("AzureSlop Test")
    print(f"  Project : {config.get('name', 'Unknown')}")
    print(f"  Mode    : {'local copy' if local else 'Studio drafts'}")
    print(f"  Port    : {port}")
    print()
    button = "Apply to local copy" if local else "Apply drafts"
    print(f"Waiting for the Studio plugin. Click '{button}' in AzureSlop.")
    print("Press Ctrl+C to cancel.\n")

    try:
        result = serve_action(
            project_root,
            config,
            "test",
            local=local,
            port_override=port_override,
        )
    except OSError as error:
        print(f"Could not start the AzureSlop server: {error}")
        sys.exit(1)

    if not result:
        return
    if result.get("ok") is False:
        print("Test blocked: Studio has changes that are not in the disk baseline.")
        for conflict in result.get("conflicts", []):
            print(
                f"  {conflict.get('kind', 'source')}:{conflict.get('path', '?')}"
                f" - {conflict.get('reason', 'version conflict')}"
            )
        print("Nothing was applied. Reconcile the two versions, then try again.")
        sys.exit(1)
    print(
        "Test apply complete: "
        f"{result.get('updated', 0)} updated, "
        f"{result.get('created', 0)} created, "
        f"{result.get('deleted', 0)} deleted, "
        f"{result.get('unchanged', 0)} unchanged, "
        f"{result.get('skipped', 0)} skipped."
    )
    for error in result.get("errors", []):
        print(f"  warning: {error}")
