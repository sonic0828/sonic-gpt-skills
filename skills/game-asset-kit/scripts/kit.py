#!/usr/bin/env python3
"""Build or verify a local game asset workbench using only the standard library."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import struct
import sys
import tempfile
from urllib.parse import quote

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "workbench.html"
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif", ".bmp"}
MEDIA = IMAGES | {".mp3", ".wav", ".ogg", ".m4a", ".mp4", ".webm", ".mov"}
STATUSES = {"added", "changed", "unchanged", "removed", "missing"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def string(value):
    return isinstance(value, str) and bool(value.strip())


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def source_path(project, value):
    require(string(value), "引用缺少路径")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in value
            and value == path.as_posix() and path.parts, f"需要项目相对路径：{value}")
    target = project / path
    require(target.resolve().is_relative_to(project), f"引用超出项目：{value}")
    return target


def validate(catalog, project):
    require(isinstance(catalog, dict) and type(catalog.get("version")) is int
            and catalog["version"] == 1, "需要版本 1 的清单")
    require(catalog.get("mode") in ("ui", "library") and string(catalog.get("project"))
            and string(catalog.get("coverage")), "请填写 project、mode、coverage")
    require(isinstance(catalog.get("items"), list), "items 必须是列表")
    ids = set()
    for item in catalog["items"]:
        require(isinstance(item, dict) and all(string(item.get(k)) for k in
                ("id", "name", "category")), "条目缺少 id、name 或 category")
        key = item["id"]
        require(key not in ids, f"ID 重复：{key}")
        ids.add(key)
        evidence = item.get("evidence")
        sources, uses = item.get("sources"), item.get("uses", [])
        require(isinstance(sources, list) and sources, f"{key} 缺少来源")
        require(isinstance(uses, list) and evidence in ("used", "file", "visual")
                and (evidence == "used") == bool(uses), f"{key} 的使用证据与 uses 不符")
        states = item.get("states", [])
        require(isinstance(states, list) and all(string(s) for s in states), f"{key} 的 states 无效")
        for ref in sources + uses:
            require(isinstance(ref, dict), f"{key} 的引用格式错误")
            source_path(project, ref.get("path"))
            require("locator" not in ref or string(ref["locator"]), f"{key} 的定位无效")
        for ref in uses:
            require(string(ref.get("scene")), f"{key} 缺少使用场景")
        for ref in sources:
            suffix = PurePosixPath(ref["path"]).suffix.lower()
            require("preview" not in ref or (string(ref["preview"]) and suffix in MEDIA),
                    f"{key} 的预览需要图注与浏览器媒体文件")
            if "rect" in ref:
                r = ref["rect"]
                require(suffix in IMAGES and isinstance(r, list) and len(r) == 4
                        and all(type(x) is int and x >= 0 for x in r) and min(r[2:]) > 0,
                        f"{key} 的裁切区域无效")


def paths(item):
    return {ref["path"] for ref in item["sources"] + item.get("uses", [])}


def fingerprint(path):
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_png_regions(item, project, files, sizes):
    for ref in item["sources"]:
        name = ref["path"]
        if "rect" not in ref or not name.lower().endswith(".png") or not files[name]:
            continue
        if name not in sizes:
            with (project / name).open("rb") as stream:
                header = stream.read(24)
            require(len(header) == 24 and header[:8] == b"\x89PNG\r\n\x1a\n"
                    and header[12:16] == b"IHDR", f"无法读取 PNG 尺寸：{name}")
            sizes[name] = struct.unpack(">II", header[16:24])
        x, y, w, h = ref["rect"]
        width, height = sizes[name]
        require(x + w <= width and y + h <= height, f"{item['id']} 裁切超出原图：{name}")


def load_manifest(path, project):
    manifest = read_json(path)
    validate(manifest, project)
    require(isinstance(manifest.get("files"), dict), "已有清单缺少文件指纹")
    for item in manifest["items"]:
        manual = item.get("manual")
        require(isinstance(manual, dict) and all(isinstance(manual.get(k), str)
                for k in ("name", "note")) and item.get("status") in STATUSES,
                f"已有条目的人工字段或状态无效：{item['id']}")
    return manifest


def merge(catalog, previous, project, out):
    old_items = {i["id"]: i for i in previous.get("items", [])}
    old_files = previous.get("files", {})
    files = {}
    sizes = {}
    result = []
    current_ids = {i["id"] for i in catalog["items"]}
    historical = [i for k, i in old_items.items() if k not in current_ids]
    reserved = {"manual", "status"}
    for item in catalog["items"] + historical:
        key = item["id"]
        active = key in current_ids
        require(not active or reserved.isdisjoint(item), f"{key} 的人工字段与状态应保存在 manifest.json")
        old = old_items.get(key, {})
        missing = False
        modified = False
        for name in sorted(paths(item)):
            if name not in files:
                target = source_path(project, name)
                require(target.resolve() not in {out / n for n in ("index.html", "manifest.json", "catalog.json")},
                        f"输出文件不能引用自身：{name}")
                files[name] = fingerprint(target)
            if files[name] is None:
                require(old and name in paths(old), f"{key} 的新引用不存在：{name}")
                missing = True
            modified |= files[name] != old_files.get(name)
        if active:
            check_png_regions(item, project, files, sizes)
        if not active:
            status = "removed"
        elif missing:
            status = "missing"
        elif not old:
            status = "added"
        elif modified or old["status"] in {"removed", "missing"} or any(
                item.get(k) != old.get(k) for k in item.keys() | old.keys() if k not in reserved):
            status = "changed"
        else:
            status = "unchanged"
        result.append({**item, "manual": old.get("manual", {"name": "", "note": ""}), "status": status})
    return {**catalog, "items": result, "files": files}


def read_presentation(out):
    path = out / "presentation.json"
    if not path.exists():
        return {}
    view = read_json(path)
    require(isinstance(view, dict) and view.get("layout") in ("atlas", "compare", "catalog"),
            "presentation.json 的 layout 需为 atlas、compare 或 catalog")
    require(string(view.get("basis")), "请填写展示依据 basis")
    colors = view.get("colors", {})
    roles = {"paper", "panel", "ink", "accent", "stage"}
    require(isinstance(colors, dict) and colors.keys() <= roles and all(
        isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v) for v in colors.values()),
        "colors 需要已知颜色角色和六位十六进制色值")
    for key in ("label", "focus"):
        require(key not in view or string(view[key]), f"展示字段 {key} 需为非空文本")
    order = view.get("previewOrder", {})
    require(isinstance(order, dict) and all(isinstance(labels, list) and all(string(v) for v in labels)
            for labels in order.values()), "previewOrder 按条目 ID 列出优先图注")
    primary = view.get("categories", [])
    require(isinstance(primary, list) and all(string(v) for v in primary), "categories 需要分类名称列表")
    return view


def render(manifest, project, out):
    prefix = quote(Path(os.path.relpath(project, out)).as_posix(), safe="/")
    data = json.dumps({"root": prefix + "/", "manifest": manifest,
                       "view": read_presentation(out)}, ensure_ascii=False)
    return TEMPLATE.read_text(encoding="utf-8").replace("/*__KIT_DATA__*/", data.replace("<", "\\u003c"))


def write_atomic(path, body):
    tmp = tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False)
    try:
        with tmp:
            tmp.write(body)
        os.replace(tmp.name, path)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def run(command, project, out):
    require(project.is_dir() and out.is_dir(), "请指定已有游戏目录和含 catalog.json 的输出目录")
    catalog = read_json(out / "catalog.json")
    validate(catalog, project)
    manifest_path, page = out / "manifest.json", out / "index.html"
    previous = load_manifest(manifest_path, project) if manifest_path.exists() else {}
    if previous:
        require(all(catalog[k] == previous[k] for k in ("mode", "project")),
                "项目或模式与已有清单不同，请使用独立输出目录")
    elif page.exists():
        raise ValueError("目录已含其他 index.html，请选择独立输出目录")
    merged = merge(catalog, previous, project, out)
    if command == "check":
        require(bool(previous), "请先构建工作台")
        expected = {i["id"]: i for i in merged["items"]}
        for old in previous["items"]:
            new = expected[old["id"]]
            if old["status"] in {"added", "changed"} and new["status"] == "unchanged":
                new["status"] = old["status"]
        require(merged == previous, "盘点、引用或文件内容已变化，请重新构建")
        require(page.read_text(encoding="utf-8") == render(previous, project, out),
                "工作台与清单不同步，请重新构建")
    else:
        html = render(merged, project, out)
        write_atomic(manifest_path, json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
        write_atomic(page, html)
    print(f"{command} OK · {len(merged['items'])} 个条目 · {len(merged['files'])} 个引用文件 · {page}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    project, out = args.project.resolve(), args.out.resolve()
    lock = out / ".kit-build.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        parser.exit(1, f"已有任务占用 {lock}，如进程已退出可移除空锁目录后重试。\n")
    except OSError as exc:
        parser.exit(1, f"{exc}\n")
    try:
        run(args.command, project, out)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    finally:
        lock.rmdir()


if __name__ == "__main__":
    main()
