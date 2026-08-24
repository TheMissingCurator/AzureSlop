"""Filesystem mapping and snapshot helpers for AzureSlop projects."""

import json
import os
from pathlib import Path, PurePosixPath


TYPE_TO_EXT = {
    "Script": ".server.lua",
    "LocalScript": ".client.lua",
    "ModuleScript": ".module.lua",
    "StringValue": ".stringvalue",
    "NumberValue": ".numbervalue",
    "IntValue": ".intvalue",
    "BoolValue": ".boolvalue",
    "RemoteEvent": ".remoteevent",
    "RemoteFunction": ".remotefunction",
    "BindableEvent": ".bindableevent",
    "BindableFunction": ".bindablefunction",
}
EXT_TO_TYPE = {extension: class_name for class_name, extension in TYPE_TO_EXT.items()}
KNOWN_EXTENSIONS = tuple(sorted(EXT_TO_TYPE, key=len, reverse=True)) + (".lua",)
STATE_FILE = ".azureslop-state.json"


def normalize_instance_path(raw_path: str, services: list[str]) -> str:
    """Validate an instance path received over HTTP and return POSIX form."""
    path = PurePosixPath(str(raw_path).replace("\\", "/"))
    parts = path.parts
    if (
        not parts
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in parts)
        or parts[0] not in services
    ):
        raise ValueError(f"Invalid or unwatched instance path: {raw_path!r}")
    return "/".join(parts)


def instance_path_to_file(
    project_root: str,
    instance_path: str,
    class_name: str = "",
) -> Path:
    """Resolve an instance path to an existing file or its canonical new file."""
    posix_path = PurePosixPath(instance_path)
    if posix_path.is_absolute() or any(part in ("", ".", "..") for part in posix_path.parts):
        raise ValueError(f"Invalid instance path: {instance_path!r}")
    relative = Path(*posix_path.parts)
    root = Path(project_root).resolve()
    for extension in KNOWN_EXTENSIONS:
        candidate = root / f"{relative}{extension}"
        if candidate.is_symlink():
            raise ValueError(f"Refusing to follow a symlinked source file: {candidate}")
        if candidate.is_file():
            return candidate
    candidate = root / f"{relative}{TYPE_TO_EXT.get(class_name, '.module.lua')}"
    if candidate.is_symlink():
        raise ValueError(f"Refusing to follow a symlinked source file: {candidate}")
    return candidate


def file_to_instance_path(project_root: str, file_path: Path) -> str | None:
    root = Path(project_root).resolve()
    try:
        relative = file_path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None
    for extension in KNOWN_EXTENSIONS:
        if relative.endswith(extension):
            return relative[: -len(extension)]
    return None


def infer_type(file_path: Path) -> str:
    path = str(file_path)
    for extension, class_name in EXT_TO_TYPE.items():
        if path.endswith(extension):
            return class_name
    return "ModuleScript"


def iter_project_files(project_root: str, services: list[str]):
    root = Path(project_root).resolve()
    for service in services:
        service_root = root / service
        if not service_root.is_dir():
            continue
        for directory, _, filenames in os.walk(service_root):
            for filename in filenames:
                file_path = Path(directory) / filename
                if any(filename.endswith(extension) for extension in KNOWN_EXTENSIONS):
                    yield file_path


def build_disk_snapshot(project_root: str, services: list[str]) -> list[dict]:
    changes = []
    for file_path in iter_project_files(project_root, services):
        instance_path = file_to_instance_path(project_root, file_path)
        if instance_path is None:
            continue
        changes.append(
            {
                "path": instance_path,
                "source": file_path.read_text(encoding="utf-8"),
                "type": infer_type(file_path),
            }
        )
    return sorted(changes, key=lambda change: change["path"])


def _load_state(project_root: str, services: list[str]) -> set[str]:
    state_path = Path(project_root) / STATE_FILE
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()
    if not isinstance(data, dict) or not isinstance(data.get("paths", []), list):
        return set()
    paths = set()
    for path in data.get("paths", []):
        if not isinstance(path, str):
            continue
        try:
            paths.add(normalize_instance_path(path, services))
        except ValueError:
            continue
    return paths


def _save_state(project_root: str, paths: set[str]) -> None:
    state_path = Path(project_root) / STATE_FILE
    state_path.write_text(
        json.dumps({"paths": sorted(paths)}, indent=2) + "\n",
        encoding="utf-8",
    )


def disk_deletions(project_root: str, services: list[str]) -> list[str]:
    """Return previously pulled paths which the user has since deleted on disk."""
    existing = {
        path
        for file_path in iter_project_files(project_root, services)
        if (path := file_to_instance_path(project_root, file_path)) is not None
    }
    return sorted(_load_state(project_root, services) - existing)


def apply_studio_snapshot(
    project_root: str,
    services: list[str],
    changes: list[dict],
) -> dict:
    """Apply a Studio snapshot and delete only paths tracked by an earlier pull."""
    normalized: dict[str, dict] = {}
    for change in changes:
        instance_path = normalize_instance_path(change.get("path", ""), services)
        normalized[instance_path] = {
            "source": str(change.get("source", "")),
            "type": str(change.get("type", "ModuleScript")),
        }

    previous_paths = _load_state(project_root, services)
    current_paths = set(normalized)
    deleted = 0
    for instance_path in previous_paths - current_paths:
        file_path = instance_path_to_file(project_root, instance_path)
        if file_path.exists():
            file_path.unlink()
            deleted += 1
            parent = file_path.parent
            root = Path(project_root).resolve()
            while parent != root:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent

    for instance_path, change in normalized.items():
        file_path = instance_path_to_file(
            project_root,
            instance_path,
            change["type"],
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(change["source"], encoding="utf-8")

    _save_state(project_root, current_paths)
    return {"updated": len(normalized), "deleted": deleted}
