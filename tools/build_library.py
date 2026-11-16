#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
书架页生成器：扫描 <学习包>/movies/*/meta.json，生成 index.html

用法：
  python3 tools/build_library.py [学习包目录]
"""

import json
import os
import re
import sys

MARK_START = "/* __LIBRARY_DATA_START__ */"
MARK_END = "/* __LIBRARY_DATA_END__ */"


def build(pack_dir):
    """扫描课文元信息并重新生成书架页，返回课文数量。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "library_template.html")
    movies_dir = os.path.join(pack_dir, "movies")

    entries = []
    if os.path.isdir(movies_dir):
        for name in sorted(os.listdir(movies_dir)):
            meta_path = os.path.join(movies_dir, name, "meta.json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        entries.append(json.load(f))
                except (OSError, json.JSONDecodeError) as exc:
                    print(f"⚠️ 跳过损坏的元信息 {meta_path}：{exc}")

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    data = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    replacement = f"let library = {data};"
    pattern = re.escape(MARK_START) + r"[\s\S]*?" + re.escape(MARK_END)
    if not re.search(pattern, html):
        print("❌ 书架模板缺少数据标记，请检查 library_template.html")
        sys.exit(1)

    out_html = re.sub(pattern, f"{MARK_START}\n    {replacement}\n    {MARK_END}", html, count=1)
    os.makedirs(pack_dir, exist_ok=True)
    out_path = os.path.join(pack_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_html)

    print(f"📚 书架页已更新：{out_path}（{len(entries)} 篇课文）")
    return len(entries)


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pack_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(os.path.join(base_dir, "..", "学习包"))
    build(pack_dir)


if __name__ == "__main__":
    main()
