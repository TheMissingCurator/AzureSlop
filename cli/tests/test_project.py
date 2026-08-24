import json
import tempfile
import unittest
from pathlib import Path

from azureslop.project import (
    STATE_FILE,
    apply_studio_snapshot,
    build_disk_snapshot,
    disk_deletions,
    normalize_instance_path,
)


SERVICES = ["ServerScriptService", "ReplicatedStorage"]


class ProjectSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_first_pull_writes_snapshot_and_preserves_untracked_file(self):
        untracked = self.root / "ServerScriptService" / "LocalOnly.server.lua"
        untracked.parent.mkdir(parents=True)
        untracked.write_text("print('mine')", encoding="utf-8")

        result = apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [
                {
                    "path": "ServerScriptService/GameManager",
                    "source": "print('studio')",
                    "type": "Script",
                }
            ],
        )

        self.assertEqual(result, {"updated": 1, "deleted": 0})
        self.assertTrue(untracked.exists())
        pulled = self.root / "ServerScriptService" / "GameManager.server.lua"
        self.assertEqual(pulled.read_text(encoding="utf-8"), "print('studio')")
        state = json.loads((self.root / STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(state["paths"], ["ServerScriptService/GameManager"])

    def test_later_pull_deletes_only_previously_tracked_paths(self):
        changes = [
            {
                "path": "ReplicatedStorage/Shared/Utils",
                "source": "return {}",
                "type": "ModuleScript",
            }
        ]
        apply_studio_snapshot(str(self.root), SERVICES, changes)
        untracked = self.root / "ReplicatedStorage" / "Keep.module.lua"
        untracked.write_text("return true", encoding="utf-8")

        result = apply_studio_snapshot(str(self.root), SERVICES, [])

        self.assertEqual(result, {"updated": 0, "deleted": 1})
        self.assertFalse((self.root / "ReplicatedStorage/Shared/Utils.module.lua").exists())
        self.assertTrue(untracked.exists())

    def test_disk_snapshot_and_deletions_use_pulled_state(self):
        apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [
                {
                    "path": "ServerScriptService/Main",
                    "source": "print('one')",
                    "type": "Script",
                },
                {
                    "path": "ReplicatedStorage/Flag",
                    "source": "true",
                    "type": "BoolValue",
                },
            ],
        )
        (self.root / "ReplicatedStorage/Flag.boolvalue").unlink()

        snapshot = build_disk_snapshot(str(self.root), SERVICES)

        self.assertEqual([change["path"] for change in snapshot], ["ServerScriptService/Main"])
        self.assertEqual(snapshot[0]["type"], "Script")
        self.assertEqual(disk_deletions(str(self.root), SERVICES), ["ReplicatedStorage/Flag"])

    def test_rejects_traversal_and_unwatched_services(self):
        with self.assertRaises(ValueError):
            normalize_instance_path("ServerScriptService/../../escape", SERVICES)
        with self.assertRaises(ValueError):
            normalize_instance_path("Workspace/Bad", SERVICES)

    def test_ignores_unsafe_paths_in_state_file(self):
        outside = self.root.parent / "outside.server.lua"
        outside.write_text("keep", encoding="utf-8")
        (self.root / STATE_FILE).write_text(
            json.dumps({"paths": ["ServerScriptService/../../../outside"]}),
            encoding="utf-8",
        )

        result = apply_studio_snapshot(str(self.root), SERVICES, [])

        self.assertEqual(result["deleted"], 0)
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")
        outside.unlink()


if __name__ == "__main__":
    unittest.main()
