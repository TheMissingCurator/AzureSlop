import tempfile
import unittest
from pathlib import Path

from azureslop.commands.test import _copy_local_place


class LocalPlaceTests(unittest.TestCase):
    def test_copies_relative_baseline_to_disposable_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "places" / "Game.rbxlx"
            source.parent.mkdir()
            source.write_text("<roblox />", encoding="utf-8")

            destination = _copy_local_place(str(root), "places/Game.rbxlx")

            self.assertEqual(destination.parent, root / ".azureslop-local")
            self.assertEqual(destination.read_text(encoding="utf-8"), "<roblox />")
            self.assertNotEqual(destination, source)

    def test_rejects_non_place_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Game.txt"
            source.write_text("not a place", encoding="utf-8")
            with self.assertRaises(ValueError):
                _copy_local_place(directory, str(source))


if __name__ == "__main__":
    unittest.main()
