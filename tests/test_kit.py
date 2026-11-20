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

    def test_presentation_rebuild_preserves_legacy_notes(self):
        self.cli("build")
        manifest = json.loads(self.manifest_path.read_text())
        manual = {"name": "已命名", "note": "核对来源"}
        manifest["items"][0]["manual"] = manual
        self.manifest_path.write_text(json.dumps(manifest))
        config = self.out / "presentation.json"
        view = {"layout": "compare", "basis": "对照两种状态", "colors": {"stage": "#261c15"}}
        config.write_text(json.dumps(view))
        self.assertEqual(self.item_after_build()["manual"], manual)
        original_page = (self.out / "index.html").read_text()
        view["layout"] = "atlas"
        config.write_text(json.dumps(view))
        self.cli("check", success=False)
        self.assertEqual(self.item_after_build()["manual"], manual)
        updated_page = (self.out / "index.html").read_text()
        self.assertNotEqual(updated_page, original_page)
        self.assertEqual(json.loads(config.read_text()), view)
        view["colors"]["stage"] = "invalid"
        config.write_text(json.dumps(view))
        self.cli("build", success=False)
        self.assertEqual((self.out / "index.html").read_text(), updated_page)

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

    def test_switching_structures_keeps_attributes_and_manual_fields(self):
        self.item["attributes"] = {"价格": 0, "材质": "水晶"}
        config = self.out / "presentation.json"
        view = {"basis": "核对道具价格", "structure": "05", "columns": ["价格"]}
        config.write_text(json.dumps(view))
        self.item_after_build()
        manifest = json.loads(self.manifest_path.read_text())
        manual = {"name": "免费宝石", "note": "新手奖励"}
        manifest["items"][0]["manual"] = manual
        self.manifest_path.write_text(json.dumps(manifest))
        view.update(structure="03", groups={"商店": ["道具"]})
        config.write_text(json.dumps(view))
        item = self.item_after_build()
        self.assertEqual((item["id"], item["manual"], item["attributes"]),
                         ("gem", manual, self.item["attributes"]))
        view["structure"] = "07"
        config.write_text(json.dumps(view))
        before = (self.out / "index.html").read_bytes()
        self.cli("build", success=False)
        self.assertEqual((self.out / "index.html").read_bytes(), before)

    def test_each_scene_requires_an_object_region_on_that_image(self):
        config = self.out / "presentation.json"
        scenes = [{"name": "营地", "path": "camp.svg"}, {"name": "矿区", "path": "mine.svg"}]
        config.write_text(json.dumps({"structure": "06", "scenes": scenes, "basis": "点选地标"}))
        for scene in scenes:
            (self.project / scene["path"]).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>')
            self.item["sources"].append({"path": scene["path"]})
        self.item["sources"][1]["rect"] = [0, 0, 4, 4]
        self.cli("build", success=False)
        self.assertFalse(self.manifest_path.exists())
        self.item["sources"][2]["rect"] = [2, 2, 4, 4]
        self.assertEqual(self.item_after_build()["sources"], self.item["sources"])


if __name__ == "__main__":
    unittest.main()
