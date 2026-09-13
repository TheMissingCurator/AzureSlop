"""Package AzureSlop and its bundled harness modules as a local plugin model."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def package(source, modules=None):
    root = ET.Element("roblox", version="4")
    item = ET.SubElement(root, "Item", {"class": "Script", "referent": "AzureSlop"})
    props = ET.SubElement(item, "Properties")
    ET.SubElement(props, "string", name="Name").text = "AzureSlop"
    ET.SubElement(props, "bool", name="Disabled").text = "false"
    ET.SubElement(props, "ProtectedString", name="Source").text = source
    for name, module_source in sorted((modules or {}).items()):
        child = ET.SubElement(item, "Item", {"class": "ModuleScript", "referent": name})
        child_props = ET.SubElement(child, "Properties")
        ET.SubElement(child_props, "string", name="Name").text = name
        ET.SubElement(child_props, "ProtectedString", name="Source").text = module_source
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "dist/AzureSlop.rbxmx")
    parser.add_argument("--install", type=Path, help="Exact destination AzureSlop.rbxmx path; backs up any existing file")
    args = parser.parse_args()
    source = (root / "plugin/AzureSlop.lua").read_text(encoding="utf-8")
    modules = {name: (root / "plugin" / f"{name}.lua").read_text(encoding="utf-8")
               for name in ("HarnessPreview", "HarnessVision", "HarnessMotion")}
    encoded = package(source, modules)
    assert ET.fromstring(encoded).find(".//ProtectedString").text == source
    assert len(ET.fromstring(encoded).findall(".//Item")) == 1 + len(modules)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(f"Built {args.output}")
    if args.install:
        target = args.install
        if target.name != "AzureSlop.rbxmx" or target.is_symlink():
            parser.error("--install must target a regular AzureSlop.rbxmx file")
        if not target.parent.is_dir():
            parser.error("Plugin directory does not exist")
        if target.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = target.with_name(target.name + ".backup-" + stamp)
            shutil.copy2(target, backup)
            print(f"Backup: {backup}")
        shutil.copyfile(args.output, target)
        assert target.read_bytes() == encoded
        print(f"Installed and verified {target}; reload Studio to load it")


if __name__ == "__main__":
    main()
