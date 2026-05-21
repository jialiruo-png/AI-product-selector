#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import mimetypes
import re
import shutil
from pathlib import Path


IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def data_uri(path: Path) -> str | None:
    mime = mimetypes.guess_type(str(path))[0]
    if not mime or not mime.startswith("image/"):
        return None
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def normalize_link(raw: str) -> str:
    link = raw.strip()
    if link.startswith("<") and link.endswith(">"):
        link = link[1:-1].strip()
    return link


def should_skip(link: str) -> bool:
    lowered = link.lower()
    return lowered.startswith(("http://", "https://", "data:", "mailto:", "#"))


def inline_file(md_path: Path, root: Path) -> tuple[int, set[Path]]:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    cleanup_dirs: set[Path] = set()
    converted = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal converted
        alt = match.group(1)
        original_link = match.group(2)
        link = normalize_link(original_link)
        if should_skip(link):
            return match.group(0)

        image_path = (md_path.parent / link).resolve()
        try:
            image_path.relative_to(root.resolve())
        except ValueError:
            return match.group(0)

        if not image_path.is_file():
            return match.group(0)

        uri = data_uri(image_path)
        if not uri:
            return match.group(0)

        rel_parts = Path(link).parts
        if rel_parts:
            first_dir = (md_path.parent / rel_parts[0]).resolve()
            if first_dir.is_dir():
                cleanup_dirs.add(first_dir)

        converted += 1
        return f"![{alt}]({uri})"

    new_text = IMAGE_RE.sub(replace, text)
    if new_text != text:
        md_path.write_text(new_text, encoding="utf-8")

    return converted, cleanup_dirs


def cleanup_empty_or_asset_dirs(root: Path, dirs: set[Path]) -> int:
    removed = 0
    candidates = set(dirs)
    for child in root.iterdir():
        if child.is_dir() and (child.name in {"assets", "images", "media"} or child.name.endswith("-media")):
            candidates.add(child.resolve())

    for directory in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
        if not directory.exists() or not directory.is_dir():
            continue
        try:
            directory.relative_to(root.resolve())
        except ValueError:
            continue
        shutil.rmtree(directory, ignore_errors=True)
        removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="把 Markdown 本地图片内嵌为 data URI，并清理图片目录。")
    parser.add_argument("directory", help="Markdown 输出目录")
    args = parser.parse_args()

    root = Path(args.directory).resolve()
    if not root.exists():
        print("内嵌图片：目录不存在")
        return 1

    total = 0
    cleanup_dirs: set[Path] = set()
    for md_path in sorted(root.rglob("*.md")):
        converted, dirs = inline_file(md_path, root)
        total += converted
        cleanup_dirs.update(dirs)

    removed = cleanup_empty_or_asset_dirs(root, cleanup_dirs)
    print(f"内嵌图片：{total} 张，清理目录：{removed} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
