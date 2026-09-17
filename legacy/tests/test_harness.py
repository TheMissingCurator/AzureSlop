import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from azureslop.commands.harness import apply_harness_pull, call, request
from azureslop.harness import HarnessServer, HarnessState, JOB_SECONDS
from azureslop.project import apply_studio_snapshot


class HarnessStateTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.state = HarnessState(lambda: self.now)
        self.peer = {"epoch": self.state.epoch, "session": "studio-a"}
        self.poll()

    def poll(self, **extra):
        return self.state.dispatch("/harness/poll", dict(self.peer, **extra))

    def submit(self, ident="job", **extra):
        return self.state.dispatch("/harness/submit", dict(id=ident, method="execute", params={}, **extra))

    def result(self, ident="job", result=None):
        encoded = json.dumps(result or {"ok": True, "value": "hello"}).encode()
        data = dict(self.peer, id=ident, index=1, total=1)
        self.state.receive_chunk(data, encoded)
        return self.state.dispatch("/harness/result/complete", data)

    def test_dispatch_once_and_retry_submit_and_result(self):
        self.submit()
        self.assertEqual(self.poll()["job"]["id"], "job")
        self.submit()
        self.assertIsNone(self.poll()["job"])
        self.result()
        self.result(result={"ok": True, "value": "duplicate must not replace result"})
        self.assertEqual(self.state.jobs["job"]["result"]["value"], "hello")
        self.assertIsNone(self.poll()["job"])

    def test_multiple_windows_require_target_and_keep_results_separate(self):
        self.poll(session="studio-b")
        with self.assertRaisesRegex(ValueError, "specify --session"):
            self.submit()
        self.submit(session="studio-a")
        self.assertIsNone(self.poll(session="studio-b")["job"])
        self.assertIsNotNone(self.poll()["job"])
        with self.assertRaisesRegex(ValueError, "dispatched"):
            self.state.receive_chunk(dict(self.peer, session="studio-b", id="job", index=1, total=1), b"{}")

    def test_unknown_execution_blocks_new_commands_until_late_result(self):
        self.submit()
        self.poll()
        self.now = JOB_SECONDS + 1
        self.assertIsNone(self.poll()["job"])
        self.assertEqual(self.state.jobs["job"]["status"], "unknown")
        self.submit("second")
        self.assertIsNone(self.poll()["job"])
        self.result()
        self.assertEqual(self.poll()["job"]["id"], "second")

    def test_queued_expiry_disconnect_and_restart(self):
        self.submit()
        self.now = JOB_SECONDS + 1
        self.assertIsNone(self.poll()["job"])
        self.assertEqual(self.state.jobs["job"]["status"], "expired")
        self.submit("second")
        self.state.dispatch("/harness/disconnect", self.peer)
        self.assertEqual(self.state.jobs["second"]["status"], "expired")
        with self.assertRaisesRegex(ValueError, "offline"):
            self.submit("third", session="studio-a")
        with self.assertRaisesRegex(ValueError, "restarted"):
            self.poll(epoch="old-server")

    def test_chunk_validation_and_unicode_reassembly(self):
        self.submit()
        self.poll()
        body = json.dumps({"ok": True, "value": "é"}, ensure_ascii=False).encode()
        split = body.index(b"\xc3") + 1
        self.state.receive_chunk(dict(self.peer, id="job", index=2, total=2), body[split:])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.state.dispatch("/harness/result/complete", dict(self.peer, id="job"))
        with self.assertRaisesRegex(ValueError, "content changed"):
            self.state.receive_chunk(dict(self.peer, id="job", index=2, total=2), b"different")
        self.state.receive_chunk(dict(self.peer, id="job", index=1, total=2), body[:split])
        self.state.dispatch("/harness/result/complete", dict(self.peer, id="job"))
        self.assertEqual(self.state.jobs["job"]["result"]["value"], "é")


class HarnessHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = HarnessServer(0, self.temp.name, {"services": ["ServerScriptService"], "place": "private"})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.peer = {"session": "studio", "epoch": self.server.state.epoch}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_token_free_config_and_browser_rejection(self):
        cfg = request(self.port, "/config")
        self.assertEqual(cfg["action"], "harness")
        self.assertNotIn("place", cfg)
        self.assertNotIn("token", cfg)
        request(self.port, "/harness/poll", self.peer)
        self.assertTrue(request(self.port, "/harness/status", {})["sessions"][0]["online"])
        for headers in ({"Origin": "https://example.com"}, {"Host": "rebinding.example"}):
            req = Request(f"http://127.0.0.1:{self.port}/config", headers=headers)
            with self.assertRaises(HTTPError) as error:
                urlopen(req)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

    def test_agent_call_with_simulated_studio_and_batched_result(self):
        request(self.port, "/harness/poll", self.peer)
        output = []
        caller = threading.Thread(target=lambda: output.append(call(self.port, "ping", {}, timeout=5, ident="call-id")))
        caller.start()
        # Wait on the transport, not shared implementation state.
        import time
        deadline = time.monotonic() + 3
        job = None
        while job is None and time.monotonic() < deadline:
            job = request(self.port, "/harness/poll", self.peer)["job"]
            if job is None:
                time.sleep(0.01)
        self.assertIsNotNone(job)
        body = json.dumps({"ok": True, "value": "x" * 850_000}).encode()
        chunks = [body[i:i+400*1024] for i in range(0, len(body), 400*1024)]
        for index, chunk in enumerate(chunks, start=1):
            req = Request(f"http://127.0.0.1:{self.port}/harness/result/chunk?"
                          f"epoch={self.peer['epoch']}&session=studio&id={job['id']}&index={index}&total={len(chunks)}",
                          data=chunk, headers={"Content-Type": "text/plain"})
            with urlopen(req) as response:
                self.assertTrue(json.load(response)["ok"])
        request(self.port, "/harness/result/complete", dict(self.peer, id=job["id"]))
        caller.join(timeout=6)
        self.assertFalse(caller.is_alive())
        self.assertEqual(output[0]["status"], "done")
        self.assertEqual(len(output[0]["result"]["value"]), 850_000)
        self.assertEqual(request(self.port, "/config")["action"], "harness")

    def test_malformed_requests_do_not_kill_server(self):
        for body in (b"[]", b"{", b'{"method":[],"id":"bad"}'):
            req = Request(f"http://127.0.0.1:{self.port}/harness/submit", data=body,
                          headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as error:
                urlopen(req)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        self.assertIn("sessions", request(self.port, "/harness/status", {}))


class HarnessPullTests(unittest.TestCase):
    def test_shared_merge_blocks_all_conflicts_without_writing(self):
        with tempfile.TemporaryDirectory() as root:
            services = ["ServerScriptService"]
            base = {"path": "ServerScriptService/Main", "source": "base", "type": "Script"}
            apply_studio_snapshot(root, services, [base])
            script = Path(root) / "ServerScriptService/Main.server.lua"
            script.write_text("disk")
            state = (Path(root) / ".azureslop-state.json").read_bytes()
            snapshot = {"changes": [dict(base, source="studio")],
                        "ambiguous": [{"path": "ServerScriptService/Duplicate"}]}
            result = apply_harness_pull(root, services, snapshot)
            self.assertFalse(result["ok"])
            self.assertEqual(len(result["conflicts"]), 2)
            self.assertEqual(script.read_text(), "disk")
            self.assertEqual((Path(root) / ".azureslop-state.json").read_bytes(), state)
            script.write_text("base")
            snapshot["ambiguous"] = []
            self.assertTrue(apply_harness_pull(root, services, snapshot)["ok"])
            self.assertEqual(script.read_text(), "studio")


if __name__ == "__main__":
    unittest.main()
