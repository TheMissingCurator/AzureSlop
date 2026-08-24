import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from azureslop.action_server import ActionServer


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
                "session": config["session"],
                "changes": [
                    {
                        "path": "ServerScriptService/Main",
                        "source": "print('ok')",
                        "type": "Script",
                    }
                ],
            }
        ).encode()
        request = urllib.request.Request(
            url + "/pull",
            data=body,
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
            "print('ok')",
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


if __name__ == "__main__":
    unittest.main()
