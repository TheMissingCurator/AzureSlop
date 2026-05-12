"""
Watches the project directory for Roblox source file changes.
Maintains a dict of { abs_path -> mtime } for changed files,
and { abs_path -> mtime } for deleted files.
"""

import os
import time
from threading import Lock

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCHED_EXTS = (
    ".server.lua", ".client.lua", ".module.lua", ".lua",
    ".stringvalue", ".numbervalue", ".intvalue", ".boolvalue",
    ".remoteevent", ".remotefunction", ".bindableevent", ".bindablefunction",
)


def _is_watched(path: str) -> bool:
    return any(path.endswith(ext) for ext in WATCHED_EXTS)


class _Handler(FileSystemEventHandler):
    def __init__(self, changed_files: dict, deleted_files: dict, lock: Lock):
        self._changed = changed_files
        self._deleted = deleted_files
        self._lock = lock

    def _handle(self, path: str):
        if not _is_watched(path):
            return
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return  # file vanished before we could stat it
        with self._lock:
            self._changed[path] = mtime
            self._deleted.pop(path, None)  # un-delete if re-created

    def _handle_delete(self, path: str):
        if not _is_watched(path):
            return
        with self._lock:
            self._deleted[path] = time.time()
            self._changed.pop(path, None)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._handle_delete(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle_delete(event.src_path)
            self._handle(event.dest_path)


class FileWatcher:
    def __init__(self, root: str):
        self._root = root
        self.lock = Lock()  # public — shared with sync.py for _our_writes/_our_deletes
        self.changed_files: dict[str, float] = {}
        self.deleted_files: dict[str, float] = {}

        # Seed with all existing watched files
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if _is_watched(fname):
                    abs_path = os.path.join(dirpath, fname)
                    self.changed_files[abs_path] = os.path.getmtime(abs_path)

        self._observer = Observer()
        self._observer.schedule(
            _Handler(self.changed_files, self.deleted_files, self.lock),
            path=root,
            recursive=True,
        )

    def start(self):
        self._observer.start()

    def stop(self):
        self._observer.stop()
        self._observer.join()
