#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把可公开上线的静态站点生成到 docs/，供 GitHub Pages 使用。"""

import os
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
DOCS = os.path.join(ROOT, "docs")
SAMPLE_DIR = os.path.join(ROOT, "samples", "daily_english")
SAMPLE_AUDIO = os.path.join(SAMPLE_DIR, "audio.m4a")
SAMPLE_SRT = os.path.join(SAMPLE_DIR, "lesson.srt")


def main():
    if not os.path.isfile(SAMPLE_AUDIO) or not os.path.isfile(SAMPLE_SRT):
        print("❌ 找不到演示课文，请先准备 samples/daily_english/{audio.m4a,lesson.srt}")
        sys.exit(1)

    demo_dir = os.path.join(DOCS, "movies", "demo")
    os.makedirs(demo_dir, exist_ok=True)
    shutil.copy2(SAMPLE_AUDIO, os.path.join(demo_dir, "audio.m4a"))

    sys.path.insert(0, BASE)
    import build_offline_pack
    import build_library

    out_html = os.path.join(demo_dir, "learning.html")
    subs = build_offline_pack.parse_subtitle(SAMPLE_SRT)
    build_offline_pack.inject_subtitles(
        os.path.join(BASE, "index.html"),
        subs,
        out_html,
        offset=0.0,
        movie_meta={"id": "demo", "title": "每日口语（演示）", "audioFile": "audio.m4a"},
    )
    build_library.build(DOCS)

    nojekyll = os.path.join(DOCS, ".nojekyll")
    open(nojekyll, "w").close()

    print(f"✅ GitHub Pages 站点已生成：{DOCS}")
    print("   打开 docs/index.html，或推送到 GitHub 后启用 Pages（Source = /docs）")


if __name__ == "__main__":
    main()
