import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("package_plugin", ROOT / "tools/package_plugin.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class PackageTests(unittest.TestCase):
    def test_license_is_in_plugin_package_and_cli(self):
        license_text = (ROOT / "License.md").read_text(encoding="utf-8")
        self.assertEqual((ROOT / "cli/LICENSE").read_text(encoding="utf-8"), license_text)
        root = ET.fromstring(packager.package("-- main", license_text))
        notice = root.find("Item/Item[@class='StringValue']")
        self.assertEqual(notice.find("Properties/string[@name='Name']").text, "License")
        value = notice.find("Properties/string[@name='Value']").text
        self.assertIn("SPDX-License-Identifier: GPL-3.0-only", value)
        self.assertTrue(value.endswith(license_text))

    def test_release_package_contains_source_and_license_without_harness(self):
        license_text = (ROOT / "License.md").read_text(encoding="utf-8")
        root = ET.fromstring(packager.package("-- main <&>", license_text))
        main = root.find("Item")
        self.assertEqual(main.find("Properties/ProtectedString").text, "-- main <&>")
        children = main.findall("Item")
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].attrib["class"], "StringValue")

    def test_downloadable_package_matches_release_source(self):
        source = (ROOT / "plugin/AzureSlop.lua").read_text(encoding="utf-8")
        license_text = (ROOT / "License.md").read_text(encoding="utf-8")
        self.assertEqual(
            (ROOT / "releases/AzureSlop.rbxmx").read_bytes(),
            packager.package(source, license_text),
        )


if __name__ == "__main__":
    unittest.main()
