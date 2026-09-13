import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from azureslop.commands.test import _copy_local_place, _open_place


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

    def test_platform_launchers_keep_paths_as_single_arguments(self):
        # Branch tests are portable; actual Studio launches still need each OS.
        place = Path("Projects") / "Café Game" / "My Place.rbxlx"
        with patch("azureslop.commands.test.sys.platform", "win32"), patch(
            "azureslop.commands.test.os.startfile", create=True
        ) as launch:
            _open_place(place)
            launch.assert_called_once_with(place)
        for platform, command in (("darwin", "open"), ("linux", "xdg-open")):
            with self.subTest(platform=platform), patch(
                "azureslop.commands.test.sys.platform", platform
            ), patch("azureslop.commands.test.subprocess.Popen") as launch:
                _open_place(place)
                launch.assert_called_once_with([command, str(place)])

    def test_unicode_paths_spaces_and_uppercase_place_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Café Project"
            root.mkdir()
            source = root / "My Place.RBXLX"
            source.write_text("<roblox>é</roblox>", encoding="utf-8")
            destination = _copy_local_place(str(root), source.name)
            self.assertEqual(destination.read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
