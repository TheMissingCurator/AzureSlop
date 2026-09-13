import argparse
import base64
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from azureslop.commands.harness import add_parser, capture_strip
from azureslop.vision import decode_image, png_bytes, contact_sheet, export_result


def image(w=2, h=1, pixels=None):
    return {"format": "rgba8", "encoding": "base64", "width": w, "height": h,
            "data": base64.b64encode(pixels or b"\xff\x00\x00\xff" * w * h).decode()}


def job(revision=1):
    return {"id": "image-job", "status": "done", "result": {"ok": True, "value": {
        "image": image(), "revision": revision, "time": .2, "camera": {"view": "front"}}}}


def read_png(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, compressed = 8, b""
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset+4])[0]
        kind = data[offset+4:offset+8]
        payload = data[offset+8:offset+8+length]
        crc = struct.unpack(">I", data[offset+8+length:offset+12+length])[0]
        assert crc == zlib.crc32(kind+payload) & 0xffffffff
        if kind == b"IHDR":
            width, height = struct.unpack(">II", payload[:8])
        if kind == b"IDAT":
            compressed += payload
        offset += length + 12
    raw = zlib.decompress(compressed)
    stride = width*4+1
    assert len(raw) == stride*height
    assert all(raw[i] == 0 for i in range(0, len(raw), stride))
    return width, height, b"".join(raw[i+1:i+stride] for i in range(0, len(raw), stride))


class VisionTests(unittest.TestCase):
    def test_rgba_png_round_trip_and_contact_sheet_order(self):
        red = (1, 1, b"\xff\0\0\xff")
        blue = (1, 1, b"\0\0\xff\xff")
        self.assertEqual(read_png(png_bytes(*red)), red)
        w, h, pixels = read_png(contact_sheet([red, blue, blue, red], 2))
        self.assertEqual((w, h), (2, 2))
        self.assertEqual(pixels, red[2]+blue[2]+blue[2]+red[2])

    def test_untrusted_image_validation(self):
        self.assertEqual(decode_image(image())[:2], (2, 1))
        for change in ({"width": True}, {"width": 2000}, {"height": 0}, {"data": "x"},
                       {"data": "!!!!!!!!!!!!"}, {"format": "png"}, {"encoding": "url"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                decode_image(dict(image(), **change))
        with self.assertRaises(ValueError):
            contact_sheet([(1, 1, b"x")], 1)

    def test_export_refuses_overwrites_and_removes_base64(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "shot"
            output = export_result(job(), directory)
            self.assertNotIn("data", output["result"]["value"]["image"])
            self.assertEqual(read_png((directory / "viewport.png").read_bytes())[:2], (2, 1))
            with self.assertRaises(FileExistsError):
                export_result(job(), directory)

    def test_failed_job_does_not_write_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shot"
            pending = {"status": "running", "id": "job"}
            self.assertEqual(export_result(pending, path), pending)
            self.assertFalse(path.exists())

    def args(self, directory):
        return argparse.Namespace(preview="preview", width=512, height=512, timeout=30,
                                  views="front,side", times="0,0.2", output=directory, session="studio")

    def test_strip_manifest_and_fixed_session(self):
        with tempfile.TemporaryDirectory() as tmp, patch("azureslop.commands.harness.call", side_effect=[job() for _ in range(4)]) as call:
            args = self.args(Path(tmp) / "strip")
            out = capture_strip(args, 25123)
            self.assertTrue(out["ok"])
            self.assertEqual([f["view"] for f in out["frames"]], ["front", "front", "side", "side"])
            self.assertEqual(read_png((args.output / "strip.png").read_bytes())[:2], (4, 2))
            for invocation in call.call_args_list:
                self.assertEqual(invocation.args[3], "studio")

    def test_partial_strip_retains_completed_frames_and_uncertain_job(self):
        unknown = {"id": "pending-job", "status": "unknown"}
        with tempfile.TemporaryDirectory() as tmp, patch("azureslop.commands.harness.call", side_effect=[job(), unknown]):
            args = self.args(Path(tmp) / "strip")
            self.assertEqual(capture_strip(args, 25123), unknown)
            manifest = json.loads((args.output / "incomplete.json").read_text())
            self.assertEqual(len(manifest["frames"]), 1)
            self.assertEqual(manifest["job"]["id"], "pending-job")
            self.assertFalse((args.output / "strip.png").exists())

    def test_changed_revision_rejects_mixed_strip(self):
        with tempfile.TemporaryDirectory() as tmp, patch("azureslop.commands.harness.call", side_effect=[job(), job(2)]):
            args = self.args(Path(tmp) / "strip")
            with self.assertRaisesRegex(ValueError, "mixed-revision"):
                capture_strip(args, 25123)
            self.assertTrue((args.output / "incomplete.json").exists())

    def test_capture_parser_and_invalid_times(self):
        parser = argparse.ArgumentParser()
        add_parser(parser.add_subparsers())
        args = parser.parse_args(["harness", "capture", "--preview", "x", "--output", "new"])
        self.assertEqual(args.width, 512)
        with tempfile.TemporaryDirectory() as tmp, patch("azureslop.commands.harness.call") as call:
            args = self.args(Path(tmp) / "invalid")
            for times in ("nan", "inf", "-1", ",", ",".join(str(i) for i in range(25))):
                args.times = times
                with self.assertRaises(ValueError):
                    capture_strip(args, 25123)
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
