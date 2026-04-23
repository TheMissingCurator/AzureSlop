"""
Watches the project directory for .lua file changes.
Maintains a dict of { abs_path -> mtime } for changed files.
"""

import os
import time
from threading import Lock

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent


class _Handler(FileSystemEventHandler):
    def __init__(self, changed_files: dict, lock: Lock):
        self._changed = changed_files
        self._lock = lock

    def _handle(self, path: str):
        if not path.endswith(".lua"):
            return
        with self._lock:
            self._changed[path] = time.time()

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)


class FileWatcher:
    def __init__(self, root: str):
        self._root = root
        self._lock = Lock()
        self.changed_files: dict[str, float] = {}

        # Seed with all existing .lua files
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if fname.endswith(".lua"):
                    abs_path = os.path.join(dirpath, fname)
                    self.changed_files[abs_path] = os.path.getmtime(abs_path)

        self._observer = Observer()
        self._observer.schedule(
            _Handler(self.changed_files, self._lock),
            path=root,
            recursive=True,
        )

    def start(self):
        self._observer.start()

    def stop(self):
        self._observer.stop()
        self._observer.join()
