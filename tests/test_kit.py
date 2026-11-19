"""Regression coverage for updates and source integrity through the public CLI."""
import base64
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

CLI = Path(__file__).resolve().parents[1] / "skills/game-asset-kit/scripts/kit.py"


class WorkbenchTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name) / "game"
        self.out = Path(temp.name) / "workbench"
        self.project.mkdir()
        self.out.mkdir()
        self.asset = self.project / "gem.txt"
        self.asset.write_text("sprite one")
        self.item = {"id": "gem", "name": "宝石", "category": "道具", "evidence": "file",
                     "sources": [{"path": self.asset.name}]}
        self.catalog = {"version": 1, "project": "游戏", "coverage": "道具目录",
                        "mode": "library", "items": [self.item]}
        self.manifest_path = self.out / "manifest.json"

    def cli(self, command, success=True):
        (self.out / "catalog.json").write_text(json.dumps(self.catalog), encoding="utf-8")
        result = subprocess.run([sys.executable, str(CLI), command, "--project", str(self.project),
                                 "--out", str(self.out)], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)

    def item_after_build(self):
        self.cli("build")
        self.cli("check")
        return json.loads(self.manifest_path.read_text())["items"][0]

    def test_incremental_identity_and_edits(self):
        self.assertEqual(self.item_after_build()["status"], "added")
        manifest = json.loads(self.manifest_path.read_text())
        manual = {"name": "我的宝石", "note": "上架前核对"}
        manifest["items"][0]["manual"] = manual
        self.manifest_path.write_text(json.dumps(manifest))
        self.cli("check", success=False)
        self.asset.write_text("sprite two")
        self.assertEqual(self.item_after_build()["manual"], manual)
        self.assertEqual(json.loads(self.manifest_path.read_text())["items"][0]["status"], "changed")
        self.asset.rename(self.project / "blue.txt")
        self.item["sources"][0]["path"] = "blue.txt"
        self.item["name"] = "蓝宝石"
        self.assertEqual(self.item_after_build()["status"], "changed")
        (self.project / "blue.txt").unlink()
        self.cli("check", success=False)
        self.assertEqual(self.item_after_build()["status"], "missing")
        self.catalog["items"] = []
        self.assertEqual(self.item_after_build()["status"], "removed")
        (self.project / "blue.txt").write_text("restored")
        self.catalog["items"] = [self.item]
        item = self.item_after_build()
        self.assertEqual((item["manual"], item["status"]), (manual, "changed"))
        self.assertEqual(self.item_after_build()["status"], "unchanged")

    def test_invalid_update_preserves_workbench(self):
        self.cli("build")
        before = self.manifest_path.read_bytes()
        page = self.out / "index.html"
        html = page.read_bytes()
        for path in ("missing.bin", "../workbench/manifest.json"):
            self.item["sources"] = [{"path": path}]
            self.cli("build", success=False)
        self.item["sources"] = [{"path": self.asset.name}]
        self.catalog["items"].append(dict(self.item))
        self.cli("build", success=False)
        self.assertEqual(self.manifest_path.read_bytes(), before)
        self.assertEqual(page.read_bytes(), html)

    def test_shared_atlas_and_region_bounds(self):
        (self.project / "atlas.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aOt8AAAAASUVORK5CYII="))
        self.item["sources"] = [{"path": "atlas.png", "rect": [0, 0, 1, 1], "preview": "道具"}]
        self.catalog["items"].append({**self.item, "id": "gauge", "name": "HUD 宝石"})
        self.cli("build")
        manifest = json.loads(self.manifest_path.read_text())
        self.assertEqual((len(manifest["items"]), len(manifest["files"])), (2, 1))
        self.item["sources"][0]["rect"][0] = 1
        self.cli("check", success=False)
        self.cli("build", success=False)


if __name__ == "__main__":
    unittest.main()
