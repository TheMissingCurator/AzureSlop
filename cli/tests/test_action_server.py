import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from azureslop.action_server import ActionServer
from azureslop.project import apply_studio_snapshot, record_disk_snapshot


class ActionServerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config = {
            "name": "Test",
            "port": 0,
            "place": "/private/baseline.rbxl",
            "services": ["ServerScriptService"],
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def _start(self, action: str, local: bool = False):
        server = ActionServer(("localhost", 0), str(self.root), self.config, action, local)
        server.timeout = 0.05

        def run():
            while not server.completed:
                server.handle_request()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return server, thread, f"http://localhost:{server.server_port}"

    def test_pull_handshake_writes_files_and_completes(self):
        server, thread, url = self._start("pull")
        with urllib.request.urlopen(url + "/config") as response:
            config = json.load(response)
        self.assertEqual(config["action"], "pull")
        self.assertNotIn("place", config)

        body = json.dumps(
            {
                "changes": [
                    {
                        "path": "ServerScriptService/Main",
                        "source": "print('héllo')",
                        "type": "Script",
                    }
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        split_at = body.index("é".encode("utf-8")) + 1
        chunks = [body[:split_at], body[split_at:]]
        encoded_session = urllib.parse.quote(config["session"])
        for index, chunk in enumerate(chunks, start=1):
            request = urllib.request.Request(
                f"{url}/pull/chunk?session={encoded_session}&index={index}&total=2",
                data=chunk,
                headers={"Content-Type": "text/plain"},
            )
            with urllib.request.urlopen(request):
                pass
            if index == 1:
                incomplete = urllib.request.Request(
                    url + "/pull/complete",
                    data=json.dumps(
                        {"session": config["session"], "total": 2}
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as context:
                    urllib.request.urlopen(incomplete)
                self.assertEqual(context.exception.code, 400)
                context.exception.close()
                self.assertFalse(server.completed)
                self.assertFalse(
                    (self.root / "ServerScriptService/Main.server.lua").exists()
                )

        request = urllib.request.Request(
            url + "/pull/complete",
            data=json.dumps({"session": config["session"], "total": 2}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            result = json.load(response)
        thread.join(timeout=1)
        server.server_close()

        self.assertTrue(result["ok"])
        self.assertTrue(server.completed)
        self.assertEqual(
            (self.root / "ServerScriptService/Main.server.lua").read_text(),
            "print('héllo')",
        )

    def test_pull_conflict_keeps_session_open_for_retry(self):
        apply_studio_snapshot(
            str(self.root),
            self.config["services"],
            [{"path": "ServerScriptService/Main", "source": "base", "type": "Script"}],
        )
        script = self.root / "ServerScriptService/Main.server.lua"
        script.write_text("disk", encoding="utf-8")
        server, thread, url = self._start("pull")

        with urllib.request.urlopen(url + "/config") as response:
            config = json.load(response)
        body = json.dumps(
            {
                "changes": [
                    {
                        "path": "ServerScriptService/Main",
                        "source": "studio",
                        "type": "Script",
                    }
                ]
            }
        ).encode()
        chunk_url = (
            f"{url}/pull/chunk?session={urllib.parse.quote(config['session'])}"
            "&index=1&total=1"
        )

        for attempt in range(2):
            chunk = urllib.request.Request(chunk_url, data=body)
            with urllib.request.urlopen(chunk):
                pass
            complete = urllib.request.Request(
                url + "/pull/complete",
                data=json.dumps({"session": config["session"], "total": 1}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(complete) as response:
                result = json.load(response)
            if attempt == 0:
                self.assertFalse(result["ok"])
                self.assertFalse(server.completed)
                resolve = urllib.request.Request(
                    url + "/resolve",
                    data=json.dumps(
                        {
                            "session": config["session"],
                            "decisions": {
                                "source:ServerScriptService/Main": "studio"
                            },
                        }
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(resolve) as response:
                    resolution = json.load(response)
                self.assertTrue(resolution["ok"])

        thread.join(timeout=1)
        server.server_close()
        self.assertTrue(result["ok"])
        self.assertTrue(server.completed)
        self.assertEqual(script.read_text(encoding="utf-8"), "studio")

    def test_forced_batched_pull_resolves_all_conflict_types_together(self):
        apply_studio_snapshot(
            str(self.root),
            self.config["services"],
            [{"path": "ServerScriptService/Main", "source": "base", "type": "Script"}],
        )
        main = self.root / "ServerScriptService/Main.server.lua"
        main.write_text("disk", encoding="utf-8")
        server, thread, url = self._start("pull")

        with urllib.request.urlopen(url + "/config") as response:
            config = json.load(response)
        body = json.dumps(
            {
                "changes": [
                    {
                        "path": "ServerScriptService/Main",
                        "source": "studio",
                        "type": "Script",
                    },
                    {
                        "path": "ServerScriptService/Duplicate",
                        "source": "chosen duplicate",
                        "type": "ModuleScript",
                    },
                ],
                "ambiguous": [
                    {
                        "path": "ServerScriptService/Duplicate",
                        "kind": "source",
                    }
                ],
            }
        ).encode()
        split_points = (len(body) // 3, (len(body) * 2) // 3)
        chunks = [
            body[: split_points[0]],
            body[split_points[0] : split_points[1]],
            body[split_points[1] :],
        ]
        encoded_session = urllib.parse.quote(config["session"])

        def upload():
            for index, chunk_body in enumerate(chunks, start=1):
                request = urllib.request.Request(
                    f"{url}/pull/chunk?session={encoded_session}&index={index}&total=3",
                    data=chunk_body,
                )
                with urllib.request.urlopen(request):
                    pass
            request = urllib.request.Request(
                url + "/pull/complete",
                data=json.dumps({"session": config["session"], "total": 3}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request) as response:
                return json.load(response)

        blocked = upload()
        self.assertFalse(blocked["ok"])
        self.assertEqual(
            {
                (conflict["kind"], conflict["path"])
                for conflict in blocked["conflicts"]
            },
            {
                ("source", "ServerScriptService/Main"),
                ("source", "ServerScriptService/Duplicate"),
            },
        )
        self.assertEqual(main.read_text(encoding="utf-8"), "disk")
        self.assertFalse(
            (self.root / "ServerScriptService/Duplicate.module.lua").exists()
        )

        force = urllib.request.Request(
            url + "/force",
            data=json.dumps({"session": config["session"]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(force) as response:
            resolution = json.load(response)
        self.assertEqual(len(resolution["decisions"]), 2)

        completed = upload()
        thread.join(timeout=1)
        server.server_close()
        self.assertTrue(completed["ok"])
        self.assertTrue(server.completed)
        self.assertEqual(main.read_text(encoding="utf-8"), "studio")
        self.assertEqual(
            (
                self.root
                / "ServerScriptService/Duplicate.module.lua"
            ).read_text(encoding="utf-8"),
            "chosen duplicate",
        )

    def test_test_handshake_serves_snapshot_and_requires_session(self):
        script = self.root / "ServerScriptService/Main.server.lua"
        script.parent.mkdir()
        script.write_text("print('test')", encoding="utf-8")
        server, thread, url = self._start("test", local=True)

        with urllib.request.urlopen(url + "/config") as response:
            config = json.load(response)
        self.assertTrue(config["local"])
        with urllib.request.urlopen(url + "/changes") as response:
            snapshot = json.load(response)
        self.assertEqual(snapshot["changes"][0]["path"], "ServerScriptService/Main")

        bad_request = urllib.request.Request(
            url + "/complete",
            data=json.dumps({"session": "wrong"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(bad_request)
        self.assertEqual(context.exception.code, 403)
        context.exception.close()
        self.assertFalse(server.completed)

        request = urllib.request.Request(
            url + "/complete",
            data=json.dumps({"session": config["session"], "updated": 1}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request):
            pass
        thread.join(timeout=1)
        server.server_close()
        self.assertEqual(server.result, {"updated": 1})

    def test_push_handshake_serves_snapshot_and_completes(self):
        script = self.root / "ServerScriptService/Main.server.lua"
        script.parent.mkdir()
        script.write_text("print('before')", encoding="utf-8")
        unchanged = self.root / "ServerScriptService/Unchanged.server.lua"
        unchanged.write_text("print('same')", encoding="utf-8")
        record_disk_snapshot(str(self.root), self.config["services"])
        script.write_text("print('push')", encoding="utf-8")
        added = self.root / "ServerScriptService/Added.module.lua"
        added.write_text("return true", encoding="utf-8")
        server, thread, url = self._start("push")

        with urllib.request.urlopen(url + "/config") as response:
            config = json.load(response)
        self.assertEqual(config["action"], "push")
        with urllib.request.urlopen(url + "/changes") as response:
            snapshot = json.load(response)
        self.assertEqual(
            [change["path"] for change in snapshot["changes"]],
            ["ServerScriptService/Added", "ServerScriptService/Main"],
        )

        compare_request = urllib.request.Request(
            url + "/compare",
            data=json.dumps(
                {
                    "session": config["session"],
                    "current": [
                        {
                            "path": "ServerScriptService/Main",
                            "source": "print('before')",
                            "type": "Script",
                            "kind": "source",
                        }
                    ],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(compare_request) as response:
            comparison = json.load(response)
        self.assertTrue(comparison["ok"])
        self.assertFalse(server.completed)

        request = urllib.request.Request(
            url + "/complete",
            data=json.dumps(
                {"session": config["session"], "updated": 1, "created": 0}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request):
            pass
        thread.join(timeout=1)
        server.server_close()
        self.assertEqual(server.result, {"updated": 1, "created": 0})

    def test_push_compare_blocks_when_studio_changed(self):
        script = self.root / "ServerScriptService/Main.server.lua"
        script.parent.mkdir()
        script.write_text("base", encoding="utf-8")
        record_disk_snapshot(str(self.root), self.config["services"])
        script.write_text("disk", encoding="utf-8")
        server, thread, url = self._start("push")

        with urllib.request.urlopen(url + "/config") as response:
            config = json.load(response)
        request = urllib.request.Request(
            url + "/compare",
            data=json.dumps(
                {
                    "session": config["session"],
                    "current": [
                        {
                            "path": "ServerScriptService/Main",
                            "source": "studio",
                            "type": "Script",
                            "kind": "source",
                        }
                    ],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            result = json.load(response)

        self.assertFalse(result["ok"])
        self.assertFalse(server.completed)
        self.assertEqual(result["conflicts"][0]["path"], "ServerScriptService/Main")

        conflict_url = (
            url
            + "/conflicts?session="
            + urllib.parse.quote(config["session"], safe="")
        )
        with urllib.request.urlopen(conflict_url) as response:
            pending = json.load(response)
        self.assertEqual(pending["action"], "push")
        self.assertEqual(pending["conflicts"], result["conflicts"])

        force = urllib.request.Request(
            url + "/force",
            data=json.dumps({"session": config["session"]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(force) as response:
            resolution = json.load(response)
        self.assertEqual(
            resolution["decisions"],
            {"source:ServerScriptService/Main": "disk"},
        )

        retry = urllib.request.Request(
            url + "/compare",
            data=json.dumps(
                {
                    "session": config["session"],
                    "current": [
                        {
                            "path": "ServerScriptService/Main",
                            "source": "studio",
                            "type": "Script",
                            "kind": "source",
                        }
                    ],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(retry) as response:
            comparison = json.load(response)
        self.assertTrue(comparison["ok"])

        complete = urllib.request.Request(
            url + "/complete",
            data=json.dumps({"session": config["session"], "updated": 1}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(complete):
            pass
        thread.join(timeout=1)
        server.server_close()
        self.assertTrue(server.completed)

    def test_push_resolution_can_keep_studio_and_refresh_delta(self):
        script = self.root / "ServerScriptService/Main.server.lua"
        script.parent.mkdir()
        script.write_text("base", encoding="utf-8")
        record_disk_snapshot(str(self.root), self.config["services"])
        script.write_text("disk", encoding="utf-8")
        server, thread, url = self._start("push")
        with urllib.request.urlopen(url + "/config") as response:
            config = json.load(response)

        current = [
            {
                "path": "ServerScriptService/Main",
                "source": "studio",
                "type": "Script",
                "kind": "source",
            }
        ]

        def compare():
            request = urllib.request.Request(
                url + "/compare",
                data=json.dumps(
                    {"session": config["session"], "current": current}
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request) as response:
                return json.load(response)

        self.assertFalse(compare()["ok"])
        resolve = urllib.request.Request(
            url + "/resolve",
            data=json.dumps(
                {
                    "session": config["session"],
                    "decisions": {"source:ServerScriptService/Main": "studio"},
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(resolve):
            pass

        # The plugin fetches the old delta before comparing. The successful
        # comparison returns a refreshed delta after the Studio choice updates disk.
        with urllib.request.urlopen(url + "/changes"):
            pass
        result = compare()
        self.assertTrue(result["ok"])
        self.assertEqual(result["changes"][0]["source"], "studio")
        self.assertEqual(script.read_text(encoding="utf-8"), "studio")

        complete = urllib.request.Request(
            url + "/complete",
            data=json.dumps({"session": config["session"], "unchanged": 1}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(complete):
            pass
        thread.join(timeout=1)
        server.server_close()


if __name__ == "__main__":
    unittest.main()
