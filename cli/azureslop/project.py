"""Filesystem mapping, snapshots, GUI sidecars, and version comparisons."""

import hashlib
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
GUI_EXTENSION = ".gui.json"
GUI_CLASSES = {
    "ScreenGui",
    "SurfaceGui",
    "BillboardGui",
    "Frame",
    "ScrollingFrame",
    "CanvasGroup",
    "TextLabel",
    "TextButton",
    "TextBox",
    "ImageLabel",
    "ImageButton",
    "ViewportFrame",
    "VideoFrame",
    "UICorner",
    "UIStroke",
    "UIPadding",
    "UIListLayout",
    "UIGridLayout",
    "UIPageLayout",
    "UITableLayout",
    "UIAspectRatioConstraint",
    "UISizeConstraint",
    "UITextSizeConstraint",
    "UIScale",
    "UIGradient",
    "UIFlexItem",
}
KNOWN_EXTENSIONS = tuple(sorted((*EXT_TO_TYPE, GUI_EXTENSION), key=len, reverse=True)) + (
    ".lua",
)
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


def entry_key(instance_path: str, kind: str = "source") -> str:
    return f"{kind}:{instance_path}"


def _split_entry_key(key: str) -> tuple[str, str]:
    if ":" not in key:
        return "source", key
    kind, instance_path = key.split(":", 1)
    return kind, instance_path


def instance_path_to_file(
    project_root: str,
    instance_path: str,
    class_name: str = "",
    kind: str = "source",
) -> Path:
    """Resolve an instance path to an existing file or its canonical new file."""
    posix_path = PurePosixPath(instance_path)
    if posix_path.is_absolute() or any(part in ("", ".", "..") for part in posix_path.parts):
        raise ValueError(f"Invalid instance path: {instance_path!r}")
    relative = Path(*posix_path.parts)
    root = Path(project_root).resolve()

    if kind == "gui" or class_name in GUI_CLASSES:
        extensions = (GUI_EXTENSION,)
        new_extension = GUI_EXTENSION
    else:
        extensions = tuple(extension for extension in KNOWN_EXTENSIONS if extension != GUI_EXTENSION)
        new_extension = TYPE_TO_EXT.get(class_name, ".module.lua")

    for extension in extensions:
        candidate = root / f"{relative}{extension}"
        if candidate.is_symlink():
            raise ValueError(f"Refusing to follow a symlinked source file: {candidate}")
        if candidate.is_file():
            return candidate
    candidate = root / f"{relative}{new_extension}"
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
    if path.endswith(GUI_EXTENSION):
        document = _read_gui_document(file_path)
        return document["className"]
    for extension, class_name in EXT_TO_TYPE.items():
        if path.endswith(extension):
            return class_name
    return "ModuleScript"


def infer_kind(file_path: Path) -> str:
    return "gui" if str(file_path).endswith(GUI_EXTENSION) else "source"


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


def _validate_gui_document(document: object, source_name: str) -> dict:
    if not isinstance(document, dict):
        raise ValueError(f"GUI file must contain a JSON object: {source_name}")
    class_name = document.get("className")
    properties = document.get("properties")
    if class_name not in GUI_CLASSES:
        raise ValueError(f"Unsupported GUI class in {source_name}: {class_name!r}")
    if not isinstance(properties, dict):
        raise ValueError(f"GUI file needs a 'properties' object: {source_name}")
    return {
        "$schema": "azureslop-gui/v1",
        "className": class_name,
        "properties": properties,
    }


def _read_gui_document(file_path: Path) -> dict:
    try:
        document = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid GUI JSON in {file_path}: {error}") from error
    return _validate_gui_document(document, str(file_path))


def _normalize_gui_source(source: str, source_name: str) -> tuple[str, dict]:
    try:
        document = json.loads(source)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid GUI JSON for {source_name}: {error}") from error
    document = _validate_gui_document(document, source_name)
    pretty = json.dumps(document, indent=2, sort_keys=True) + "\n"
    return pretty, document


def build_disk_snapshot(project_root: str, services: list[str]) -> list[dict]:
    changes = []
    seen_entries: dict[str, Path] = {}
    for file_path in iter_project_files(project_root, services):
        instance_path = file_to_instance_path(project_root, file_path)
        if instance_path is None:
            continue
        kind = infer_kind(file_path)
        key = entry_key(instance_path, kind)
        if key in seen_entries:
            raise ValueError(
                f"Multiple disk files map to {key}: {seen_entries[key]} and {file_path}"
            )
        seen_entries[key] = file_path
        if kind == "gui":
            document = _read_gui_document(file_path)
            source = json.dumps(document, indent=2, sort_keys=True) + "\n"
            class_name = document["className"]
        else:
            source = file_path.read_text(encoding="utf-8")
            class_name = infer_type(file_path)
        changes.append(
            {
                "path": instance_path,
                "source": source,
                "type": class_name,
                "kind": kind,
            }
        )
    return sorted(changes, key=lambda change: (change["path"], change["kind"]))


def _change_digest(class_name: str, source: str, kind: str = "source") -> str:
    if kind == "gui":
        _, document = _normalize_gui_source(source, class_name)
        source = json.dumps(document, sort_keys=True, separators=(",", ":"))
    payload = class_name.encode("utf-8") + b"\0" + source.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _digest_entry(change: dict) -> str:
    return _change_digest(change["type"], change["source"], change.get("kind", "source"))


def _normalize_change(change: dict, services: list[str]) -> dict:
    if not isinstance(change, dict):
        raise ValueError("Snapshot entries must be objects")
    instance_path = normalize_instance_path(change.get("path", ""), services)
    kind = str(change.get("kind", "source"))
    if kind not in {"source", "gui"}:
        raise ValueError(f"Unsupported entry kind for {instance_path}: {kind!r}")
    class_name = str(change.get("type", "ModuleScript"))
    source = str(change.get("source", ""))
    if kind == "gui":
        source, document = _normalize_gui_source(source, instance_path)
        if document["className"] != class_name:
            raise ValueError(f"GUI class mismatch for {instance_path}")
    return {"path": instance_path, "source": source, "type": class_name, "kind": kind}


def _snapshot_map(changes: list[dict], services: list[str]) -> dict[str, dict]:
    normalized = {}
    for raw_change in changes:
        change = _normalize_change(raw_change, services)
        normalized[entry_key(change["path"], change["kind"])] = change
    return normalized


def _load_state(project_root: str, services: list[str]) -> dict[str, str | None]:
    state_path = Path(project_root) / STATE_FILE
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}

    state: dict[str, str | None] = {}
    entries = data.get("entries", {})
    if isinstance(entries, dict):
        for raw_key, digest in entries.items():
            if not isinstance(raw_key, str) or not isinstance(digest, str):
                continue
            kind, path = _split_entry_key(raw_key)
            if kind not in {"source", "gui"}:
                continue
            try:
                path = normalize_instance_path(path, services)
            except ValueError:
                continue
            state[entry_key(path, kind)] = digest

    # Version 2 stored hashes by source path only.
    files = data.get("files", {})
    if isinstance(files, dict):
        for path, digest in files.items():
            if not isinstance(path, str) or not isinstance(digest, str):
                continue
            try:
                state.setdefault(entry_key(normalize_instance_path(path, services)), digest)
            except ValueError:
                continue

    # Version 1 stored only paths. Preserve deletion tracking; the unknown hash
    # forces a comparison instead of assuming either side is safe.
    paths = data.get("paths", [])
    if isinstance(paths, list):
        for path in paths:
            if not isinstance(path, str):
                continue
            try:
                state.setdefault(entry_key(normalize_instance_path(path, services)), None)
            except ValueError:
                continue
    return state


def _save_state(project_root: str, entries: dict[str, str]) -> None:
    state_path = Path(project_root) / STATE_FILE
    state_path.write_text(
        json.dumps({"version": 3, "entries": dict(sorted(entries.items()))}, indent=2) + "\n",
        encoding="utf-8",
    )


def build_disk_delta(project_root: str, services: list[str]) -> list[dict]:
    """Return entries added or modified since the last successful pull/push."""
    state = _load_state(project_root, services)
    changes = []
    for change in build_disk_snapshot(project_root, services):
        key = entry_key(change["path"], change["kind"])
        if state.get(key) != _digest_entry(change):
            changes.append(change)
    return changes


def disk_deletions(project_root: str, services: list[str]) -> list[dict]:
    """Return previously tracked entries which have since been deleted on disk."""
    existing = {
        entry_key(change["path"], change["kind"])
        for change in build_disk_snapshot(project_root, services)
    }
    deletions = []
    for key in sorted(set(_load_state(project_root, services)) - existing):
        kind, path = _split_entry_key(key)
        deletions.append({"path": path, "kind": kind})
    return deletions


def record_disk_snapshot(project_root: str, services: list[str]) -> None:
    """Record current disk entries after Studio accepts a complete push."""
    entries = {
        entry_key(change["path"], change["kind"]): _digest_entry(change)
        for change in build_disk_snapshot(project_root, services)
    }
    _save_state(project_root, entries)


def _plan_studio_snapshot(
    project_root: str,
    services: list[str],
    changes: list[dict],
    resolutions: dict[str, str] | None = None,
) -> dict:
    """Plan a three-way Studio merge without changing disk or baseline state."""
    resolutions = resolutions or {}
    studio = _snapshot_map(changes, services)
    disk = {
        entry_key(change["path"], change["kind"]): change
        for change in build_disk_snapshot(project_root, services)
    }
    state = _load_state(project_root, services)
    conflicts = []
    writes = []
    deletes = []
    preserved = 0

    def apply_resolution(
        key: str,
        disk_entry: dict | None,
        studio_entry: dict | None,
    ) -> bool:
        nonlocal preserved
        decision = resolutions.get(key)
        if decision == "disk":
            preserved += 1
            return True
        if decision == "studio":
            if studio_entry is not None:
                writes.append(studio_entry)
            elif disk_entry is not None:
                deletes.append((key, disk_entry))
            return True
        return False

    for key in sorted(set(state) | set(disk) | set(studio)):
        disk_entry = disk.get(key)
        studio_entry = studio.get(key)
        disk_digest = _digest_entry(disk_entry) if disk_entry else None
        studio_digest = _digest_entry(studio_entry) if studio_entry else None
        has_base = key in state
        base_digest = state.get(key)
        kind, path = _split_entry_key(key)

        if key in resolutions:
            if resolutions[key] not in {"disk", "studio"}:
                raise ValueError(f"Invalid pull resolution for {key}: {resolutions[key]!r}")
            apply_resolution(key, disk_entry, studio_entry)
            continue

        if not has_base:
            if disk_digest is None:
                if studio_entry:
                    writes.append(studio_entry)
            elif studio_digest is None:
                preserved += 1
            elif disk_digest == studio_digest:
                pass
            else:
                conflicts.append(
                    {"path": path, "kind": kind, "reason": "added on both sides"}
                )
            continue

        if base_digest is None:
            if disk_digest == studio_digest:
                continue
            conflicts.append(
                {"path": path, "kind": kind, "reason": "legacy baseline has no hash"}
            )
            continue

        if disk_digest == base_digest:
            if studio_entry is None:
                if disk_entry:
                    deletes.append((key, disk_entry))
            elif studio_digest != disk_digest:
                writes.append(studio_entry)
        elif studio_digest == base_digest:
            preserved += 1
        elif disk_digest == studio_digest:
            pass
        else:
            conflicts.append(
                {"path": path, "kind": kind, "reason": "changed on disk and in Studio"}
            )

    return {
        "studio": studio,
        "disk": disk,
        "writes": writes,
        "deletes": deletes,
        "preserved": preserved,
        "conflicts": conflicts,
    }


def studio_snapshot_conflicts(
    project_root: str,
    services: list[str],
    changes: list[dict],
    resolutions: dict[str, str] | None = None,
) -> list[dict]:
    """Return every unresolved three-way conflict without applying the snapshot."""
    return _plan_studio_snapshot(
        project_root,
        services,
        changes,
        resolutions,
    )["conflicts"]


def apply_studio_snapshot(
    project_root: str,
    services: list[str],
    changes: list[dict],
    resolutions: dict[str, str] | None = None,
) -> dict:
    """Three-way merge a Studio snapshot without overwriting local changes."""
    plan = _plan_studio_snapshot(project_root, services, changes, resolutions)
    conflicts = plan["conflicts"]
    preserved = plan["preserved"]
    if conflicts:
        return {
            "ok": False,
            "updated": 0,
            "deleted": 0,
            "preserved": preserved,
            "conflicts": conflicts,
        }

    studio = plan["studio"]
    disk = plan["disk"]
    writes = plan["writes"]
    deletes = plan["deletes"]
    deleted = 0
    for _, change in deletes:
        file_path = instance_path_to_file(
            project_root,
            change["path"],
            change["type"],
            change["kind"],
        )
        if file_path.exists():
            file_path.unlink()
            deleted += 1

    for change in writes:
        key = entry_key(change["path"], change["kind"])
        old_change = disk.get(key)
        if old_change and old_change["type"] != change["type"]:
            old_path = instance_path_to_file(
                project_root,
                old_change["path"],
                old_change["type"],
                old_change["kind"],
            )
            if old_path.exists():
                old_path.unlink()
        file_path = instance_path_to_file(
            project_root,
            change["path"],
            change["type"],
            change["kind"],
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(change["source"], encoding="utf-8")

    _save_state(
        project_root,
        {key: _digest_entry(change) for key, change in studio.items()},
    )
    return {
        "ok": True,
        "updated": len(writes),
        "deleted": deleted,
        "preserved": preserved,
        "conflicts": [],
    }


def compare_disk_to_studio(
    project_root: str,
    services: list[str],
    current_entries: list[dict],
) -> list[dict]:
    """Return push conflicts for changed/deleted disk entries."""
    state = _load_state(project_root, services)
    disk_changes = _snapshot_map(build_disk_delta(project_root, services), services)
    deletion_entries = disk_deletions(project_root, services)
    current = _snapshot_map(current_entries, services)
    conflicts = []

    operations: dict[str, dict | None] = dict(disk_changes)
    for deletion in deletion_entries:
        operations[entry_key(deletion["path"], deletion["kind"])] = None

    for key, disk_entry in operations.items():
        studio_entry = current.get(key)
        disk_digest = _digest_entry(disk_entry) if disk_entry else None
        studio_digest = _digest_entry(studio_entry) if studio_entry else None
        has_base = key in state
        base_digest = state.get(key)
        kind, path = _split_entry_key(key)

        if not has_base:
            safe = studio_digest is None or studio_digest == disk_digest
        elif base_digest is None:
            safe = studio_digest == disk_digest
        else:
            safe = studio_digest == base_digest or studio_digest == disk_digest
        if not safe:
            conflicts.append(
                {"path": path, "kind": kind, "reason": "Studio changed since the baseline"}
            )
    return sorted(conflicts, key=lambda conflict: (conflict["path"], conflict["kind"]))


def operation_version_map(
    project_root: str,
    services: list[str],
    current_entries: list[dict],
) -> dict[str, dict[str, str | None]]:
    """Return disk and Studio digests for every pending disk operation."""
    disk_operations: dict[str, dict | None] = {
        key: change
        for key, change in _snapshot_map(
            build_disk_delta(project_root, services), services
        ).items()
    }
    for deletion in disk_deletions(project_root, services):
        disk_operations[entry_key(deletion["path"], deletion["kind"])] = None
    current = _snapshot_map(current_entries, services)
    return {
        key: {
            "disk": _digest_entry(disk_entry) if disk_entry is not None else None,
            "studio": _digest_entry(current[key]) if key in current else None,
        }
        for key, disk_entry in disk_operations.items()
    }


def snapshot_version_map(
    project_root: str,
    services: list[str],
    studio_entries: list[dict],
) -> dict[str, dict[str, str | None]]:
    """Return disk and Studio digests for every path in a pull snapshot."""
    disk = {
        entry_key(change["path"], change["kind"]): change
        for change in build_disk_snapshot(project_root, services)
    }
    studio = _snapshot_map(studio_entries, services)
    return {
        key: {
            "disk": _digest_entry(disk[key]) if key in disk else None,
            "studio": _digest_entry(studio[key]) if key in studio else None,
        }
        for key in set(disk) | set(studio)
    }


def apply_studio_choices_to_disk(
    project_root: str,
    services: list[str],
    current_entries: list[dict],
    decisions: dict[str, str],
) -> dict:
    """Apply only conflict decisions which selected the current Studio version."""
    studio = _snapshot_map(current_entries, services)
    disk = {
        entry_key(change["path"], change["kind"]): change
        for change in build_disk_snapshot(project_root, services)
    }
    updated = 0
    deleted = 0

    for key, decision in decisions.items():
        if decision != "studio":
            continue
        kind, path = _split_entry_key(key)
        if kind not in {"source", "gui"}:
            raise ValueError(f"Unsupported resolution entry: {key!r}")
        normalize_instance_path(path, services)
        disk_entry = disk.get(key)
        studio_entry = studio.get(key)
        if studio_entry is None:
            if disk_entry is not None:
                file_path = instance_path_to_file(
                    project_root,
                    disk_entry["path"],
                    disk_entry["type"],
                    disk_entry["kind"],
                )
                if file_path.exists():
                    file_path.unlink()
                    deleted += 1
            continue

        if disk_entry and disk_entry["type"] != studio_entry["type"]:
            old_path = instance_path_to_file(
                project_root,
                disk_entry["path"],
                disk_entry["type"],
                disk_entry["kind"],
            )
            if old_path.exists():
                old_path.unlink()
        file_path = instance_path_to_file(
            project_root,
            studio_entry["path"],
            studio_entry["type"],
            studio_entry["kind"],
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(studio_entry["source"], encoding="utf-8")
        updated += 1

    return {"updated": updated, "deleted": deleted}
