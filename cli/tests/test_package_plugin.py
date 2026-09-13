import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("package_plugin", ROOT / "tools/package_plugin.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class PackageTests(unittest.TestCase):
    def test_preview_modules_are_siblings_with_exact_source(self):
        modules = {name: (ROOT / "plugin" / f"{name}.lua").read_text(encoding="utf-8")
                   for name in ("HarnessPreview", "HarnessVision", "HarnessMotion")}
        root = ET.fromstring(packager.package("-- main <&>", modules))
        main = root.find("Item")
        self.assertEqual(main.find("Properties/ProtectedString").text, "-- main <&>")
        children = main.findall("Item")
        self.assertEqual(len(children), 3)
        for child in children:
            self.assertEqual(child.attrib["class"], "ModuleScript")
            name = child.find("Properties/string").text
            self.assertEqual(child.find("Properties/ProtectedString").text, modules[name])


if __name__ == "__main__":
    unittest.main()
