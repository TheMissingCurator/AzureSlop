import json
import tempfile
import unittest
from pathlib import Path

from azureslop.project import (
    STATE_FILE,
    apply_studio_choices_to_disk,
    apply_studio_snapshot,
    build_disk_delta,
    build_disk_snapshot,
    compare_disk_to_studio,
    disk_deletions,
    normalize_instance_path,
    record_disk_snapshot,
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

        self.assertTrue(result["ok"])
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["deleted"], 0)
        self.assertTrue(untracked.exists())
        pulled = self.root / "ServerScriptService" / "GameManager.server.lua"
        self.assertEqual(pulled.read_text(encoding="utf-8"), "print('studio')")
        state = json.loads((self.root / STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(state["version"], 3)
        self.assertEqual(
            list(state["entries"]),
            ["source:ServerScriptService/GameManager"],
        )
        self.assertEqual(
            [change["path"] for change in build_disk_delta(str(self.root), SERVICES)],
            ["ServerScriptService/LocalOnly"],
        )

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

        self.assertTrue(result["ok"])
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["deleted"], 1)
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
        self.assertEqual(
            disk_deletions(str(self.root), SERVICES),
            [{"path": "ReplicatedStorage/Flag", "kind": "source"}],
        )

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

    def test_record_disk_snapshot_tracks_newly_pushed_files(self):
        script = self.root / "ServerScriptService/New.server.lua"
        script.parent.mkdir()
        script.write_text("print('new')", encoding="utf-8")

        record_disk_snapshot(str(self.root), SERVICES)
        script.unlink()

        self.assertEqual(
            disk_deletions(str(self.root), SERVICES),
            [{"path": "ServerScriptService/New", "kind": "source"}],
        )

    def test_disk_delta_contains_only_added_and_modified_files(self):
        apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [
                {
                    "path": "ServerScriptService/Changed",
                    "source": "print('old')",
                    "type": "Script",
                },
                {
                    "path": "ServerScriptService/Unchanged",
                    "source": "print('same')",
                    "type": "Script",
                },
            ],
        )
        (self.root / "ServerScriptService/Changed.server.lua").write_text(
            "print('new')",
            encoding="utf-8",
        )
        (self.root / "ServerScriptService/Added.module.lua").write_text(
            "return true",
            encoding="utf-8",
        )

        delta = build_disk_delta(str(self.root), SERVICES)

        self.assertEqual(
            [change["path"] for change in delta],
            ["ServerScriptService/Added", "ServerScriptService/Changed"],
        )

    def test_legacy_state_causes_one_compatibility_delta(self):
        script = self.root / "ServerScriptService/Legacy.server.lua"
        script.parent.mkdir()
        script.write_text("print('legacy')", encoding="utf-8")
        (self.root / STATE_FILE).write_text(
            json.dumps({"paths": ["ServerScriptService/Legacy"]}),
            encoding="utf-8",
        )

        delta = build_disk_delta(str(self.root), SERVICES)

        self.assertEqual([change["path"] for change in delta], ["ServerScriptService/Legacy"])

    def test_pull_preserves_a_disk_only_change(self):
        studio = [
            {
                "path": "ServerScriptService/Main",
                "source": "print('base')",
                "type": "Script",
            }
        ]
        apply_studio_snapshot(str(self.root), SERVICES, studio)
        script = self.root / "ServerScriptService/Main.server.lua"
        script.write_text("print('disk')", encoding="utf-8")

        result = apply_studio_snapshot(str(self.root), SERVICES, studio)

        self.assertTrue(result["ok"])
        self.assertEqual(result["preserved"], 1)
        self.assertEqual(script.read_text(encoding="utf-8"), "print('disk')")
        self.assertEqual(len(build_disk_delta(str(self.root), SERVICES)), 1)

    def test_pull_blocks_when_disk_and_studio_both_changed(self):
        apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [{"path": "ServerScriptService/Main", "source": "base", "type": "Script"}],
        )
        script = self.root / "ServerScriptService/Main.server.lua"
        script.write_text("disk", encoding="utf-8")

        result = apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [{"path": "ServerScriptService/Main", "source": "studio", "type": "Script"}],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["conflicts"][0]["reason"], "changed on disk and in Studio")
        self.assertEqual(script.read_text(encoding="utf-8"), "disk")

    def test_pull_accepts_a_studio_only_change(self):
        apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [{"path": "ServerScriptService/Main", "source": "base", "type": "Script"}],
        )

        result = apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [{"path": "ServerScriptService/Main", "source": "studio", "type": "Script"}],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            (self.root / "ServerScriptService/Main.server.lua").read_text(encoding="utf-8"),
            "studio",
        )

    def test_push_compare_blocks_a_changed_studio_version(self):
        base = {"path": "ServerScriptService/Main", "source": "base", "type": "Script"}
        apply_studio_snapshot(str(self.root), SERVICES, [base])
        (self.root / "ServerScriptService/Main.server.lua").write_text(
            "disk", encoding="utf-8"
        )

        conflicts = compare_disk_to_studio(
            str(self.root),
            SERVICES,
            [{"path": "ServerScriptService/Main", "source": "studio", "type": "Script"}],
        )
        safe = compare_disk_to_studio(str(self.root), SERVICES, [base])

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["path"], "ServerScriptService/Main")
        self.assertEqual(safe, [])

    def test_gui_sidecar_round_trip_and_delta(self):
        source = json.dumps(
            {
                "$schema": "azureslop-gui/v1",
                "className": "TextButton",
                "properties": {
                    "Text": "Play",
                    "Size": {
                        "$type": "UDim2",
                        "x": {"scale": 0, "offset": 160},
                        "y": {"scale": 0, "offset": 48},
                    },
                },
            }
        )
        result = apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [
                {
                    "path": "ReplicatedStorage/Interface/Play",
                    "source": source,
                    "type": "TextButton",
                    "kind": "gui",
                }
            ],
        )
        sidecar = self.root / "ReplicatedStorage/Interface/Play.gui.json"

        self.assertTrue(result["ok"])
        self.assertTrue(sidecar.exists())
        self.assertEqual(build_disk_delta(str(self.root), SERVICES), [])
        document = json.loads(sidecar.read_text(encoding="utf-8"))
        document["properties"]["Text"] = "Start"
        sidecar.write_text(json.dumps(document), encoding="utf-8")
        delta = build_disk_delta(str(self.root), SERVICES)
        self.assertEqual(delta[0]["kind"], "gui")
        self.assertEqual(delta[0]["type"], "TextButton")

    def test_studio_class_change_renames_the_source_extension(self):
        apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [{"path": "ServerScriptService/Main", "source": "base", "type": "Script"}],
        )

        result = apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [
                {
                    "path": "ServerScriptService/Main",
                    "source": "return true",
                    "type": "ModuleScript",
                }
            ],
        )

        self.assertTrue(result["ok"])
        self.assertFalse((self.root / "ServerScriptService/Main.server.lua").exists())
        self.assertEqual(
            (self.root / "ServerScriptService/Main.module.lua").read_text(encoding="utf-8"),
            "return true",
        )

    def test_rejects_two_disk_files_for_the_same_entry(self):
        service = self.root / "ServerScriptService"
        service.mkdir()
        (service / "Main.server.lua").write_text("one", encoding="utf-8")
        (service / "Main.module.lua").write_text("two", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Multiple disk files map"):
            build_disk_snapshot(str(self.root), SERVICES)

    def test_push_resolution_can_take_studio_for_one_file(self):
        apply_studio_snapshot(
            str(self.root),
            SERVICES,
            [{"path": "ServerScriptService/Main", "source": "base", "type": "Script"}],
        )
        script = self.root / "ServerScriptService/Main.server.lua"
        script.write_text("disk", encoding="utf-8")

        result = apply_studio_choices_to_disk(
            str(self.root),
            SERVICES,
            [{"path": "ServerScriptService/Main", "source": "studio", "type": "Script"}],
            {"source:ServerScriptService/Main": "studio"},
        )

        self.assertEqual(result, {"updated": 1, "deleted": 0})
        self.assertEqual(script.read_text(encoding="utf-8"), "studio")


if __name__ == "__main__":
    unittest.main()
