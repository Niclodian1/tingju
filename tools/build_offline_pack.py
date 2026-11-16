#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中英双语字幕处理与学习包生成工具

功能：
1. 解析标准中英双语字幕：SRT / VTT / ASS / SSA（自动识别 UTF-8 / UTF-16 / GBK 编码）。
2. 自动拆分并对齐每一句的英文原句与中文译文（支持中英混排在同一行）。
3. 自动跳过字幕组署名、片头标题卡（主演/片名/导演等）等噪声行。
4. 将解析后的台词数据注入 index.html 模板，生成开箱即用的单个 HTML 文件。
5. 请仅对自己合法持有的音频与字幕使用本工具。

用法：
    python3 build_offline_pack.py <字幕文件> [输出.html] [--offset 秒]

示例：
    python3 build_offline_pack.py "samples/daily_english/lesson.srt" --id demo --title 每日口语（演示）
    python3 build_offline_pack.py "素材/字幕/my_lesson.srt" --id my_lesson --title 我的课文
"""

import sys
import os
import re
import json
import argparse
from datetime import datetime

# index.html 中的注入标记（勿随意修改，两端需保持一致）
MARK_START = "/* __SUBTITLE_DATA_START__ */"
MARK_END = "/* __SUBTITLE_DATA_END__ */"

# 片头字幕卡 / 字幕组署名等噪声（默认过滤）
CREDIT_RE = re.compile(r'^\s*(主演|片名|导演|编剧|译制|翻译|校对|时间轴)\s*[:：]')
NOISE_RE = re.compile(r'(YYeTs|人人影视|字幕组|www\.|https?://)', re.IGNORECASE)

TIME_RE = re.compile(r'(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}|\d{1,2}:\d{2}[,.]\d{1,3})')
ARROW_RE = re.compile(r'(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})')


def read_text(path):
    """读取字幕文件，自动识别常见编码：UTF-8(BOM) / UTF-16 LE/BE / GBK。"""
    with open(path, "rb") as f:
        raw = f.read()

    # BOM 优先
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8", errors="replace")
    if raw[:2] == b"\xff\xfe":
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw[:2] == b"\xfe\xff":
        return raw[2:].decode("utf-16-be", errors="replace")

    # 无 BOM 的 UTF-16 启发式判断（大量空字节）
    sample = raw[:400]
    if sample.count(b"\x00") > len(sample) // 5:
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError:
            pass

    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_timestamp(ts_str):
    """将 00:01:23,456 / 0:01:23.45 / 83.5 转换为秒数 (float)。"""
    ts_str = ts_str.strip().replace(",", ".")
    parts = ts_str.split(":")
    try:
        if len(parts) == 3:
            return round(float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2]), 2)
        if len(parts) == 2:
            return round(float(parts[0]) * 60 + float(parts[1]), 2)
        return round(float(ts_str), 2)
    except ValueError:
        return 0.0


def clean_line(line):
    """清理单行：ASS 标签 {\\...}、HTML 标签、转义换行、零宽字符。"""
    line = re.sub(r'\{[^}]*\}', '', line)          # ASS/SSA 样式与定位标签
    line = re.sub(r'<[^>]+>', '', line)            # HTML 标签
    line = line.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
    line = line.replace('\u200b', '')
    # 常见 HTML 实体
    for entity, ch in (('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'),
                       ('&#39;', "'"), ('&apos;', "'"), ('&nbsp;', ' ')):
        line = line.replace(entity, ch)
    return line.strip()


def split_en_zh(lines):
    """将若干文本行归类为英文/中文，支持中英混排在同一行。"""
    en_parts, zh_parts = [], []
    for raw in lines:
        cleaned = clean_line(raw)
        cleaned = re.sub(r'^[-–—]\s*', '', cleaned)  # 去掉对白破折号
        for text in cleaned.split('\n'):
            text = text.strip()
            if not text:
                continue
            has_zh = bool(re.search(r'[\u4e00-\u9fff]', text))
            has_en = bool(re.search(r'[a-zA-Z]', text))
            if has_zh and not has_en:
                zh_parts.append(text)
            elif has_en and not has_zh:
                en_parts.append(text)
            elif has_zh and has_en:
                idx = re.search(r'[\u4e00-\u9fff]', text).start()
                en_sub = text[:idx].strip().rstrip(' -–—:：')
                zh_sub = text[idx:].strip()
                if en_sub:
                    en_parts.append(en_sub)
                if zh_sub:
                    zh_parts.append(zh_sub)
    return " ".join(en_parts).strip(), " ".join(zh_parts).strip()


def build_items(blocks, time_getter, text_getter):
    """
    通用组装：blocks 为字幕块列表，
    time_getter(block) -> (start_sec, end_sec) 或 None
    text_getter(block) -> 文本行列表
    """
    items = []
    auto_id = 1
    for block in blocks:
        times = time_getter(block)
        if not times:
            continue
        start_sec, end_sec = times
        en_text, zh_text = split_en_zh(text_getter(block))
        if not en_text and not zh_text:
            continue
        # 过滤片头标题卡（仅中文且形如 "主演: xxx"）与字幕组噪声
        if not en_text and CREDIT_RE.match(zh_text):
            continue
        if NOISE_RE.search(en_text + zh_text):
            continue
        if end_sec <= start_sec:
            end_sec = round(start_sec + 2.0, 2)
        items.append({
            "id": auto_id,
            "start": round(start_sec, 2),
            "end": round(end_sec, 2),
            "en": en_text,
            "zh": zh_text,
        })
        auto_id += 1
    return items


def parse_srt(content):
    """解析 SRT / VTT 文本。"""
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r'\n\s*\n', content.strip())

    def time_getter(block):
        m = ARROW_RE.search(block)
        if not m:
            return None
        return parse_timestamp(m.group(1)), parse_timestamp(m.group(2))

    def text_getter(block):
        lines = [l.strip() for l in block.split("\n")]
        time_idx = -1
        for i, line in enumerate(lines):
            if "-->" in line:
                time_idx = i
                break
        if time_idx == -1:
            return []
        return lines[time_idx + 1:]

    return build_items(blocks, time_getter, text_getter)


def parse_ass(content):
    """解析 ASS / SSA 文本（Dialogue 行）。"""
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    dialogue_lines = [l for l in content.split("\n") if re.match(r'^\s*Dialogue\s*:', l, re.IGNORECASE)]

    def time_getter(line):
        # Dialogue: Layer, Start, End, Style, Actor, ML, MR, MV, Effect, Text
        fields = line.split(":", 1)[1].split(",", 9)
        if len(fields) < 10:
            return None
        try:
            return parse_timestamp(fields[1]), parse_timestamp(fields[2])
        except (ValueError, IndexError):
            return None

    def text_getter(line):
        fields = line.split(":", 1)[1].split(",", 9)
        return [fields[9]] if len(fields) >= 10 else []

    return build_items(dialogue_lines, time_getter, text_getter)


def parse_subtitle(path):
    """按扩展名分派解析器。"""
    ext = os.path.splitext(path)[1].lower()
    content = read_text(path)
    if ext in (".ass", ".ssa"):
        return parse_ass(content)
    return parse_srt(content)


def inject_subtitles(template_html_path, subtitles_data, output_html_path, offset=0.0, movie_meta=None):
    """将台词 JSON 与课文元信息注入 HTML 模板的标记区间（兼容无标记的旧模板）。"""
    with open(template_html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 保证字幕文本中出现 "</script>" 也不会破坏页面
    json_str = json.dumps(subtitles_data, ensure_ascii=False, separators=(',', ':')).replace("</", "<\\/")
    meta = movie_meta or {"id": "default", "title": "逐句精听", "audioFile": "audio.m4a"}
    meta = dict(meta)
    meta["lines"] = len(subtitles_data)
    meta["offset"] = round(offset, 2)
    meta["htmlFile"] = os.path.basename(output_html_path)
    meta["builtAt"] = datetime.now().isoformat(timespec="seconds")
    meta_json = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    replacement = (
        f"let subtitleData = {json_str};\n"
        f"    let DEFAULT_OFFSET = {offset:.2f};\n"
        f"    let MOVIE_META = {meta_json};"
    )

    if MARK_START in html and MARK_END in html:
        pattern = re.escape(MARK_START) + r'[\s\S]*?' + re.escape(MARK_END)
        new_html = re.sub(pattern, f"{MARK_START}\n    {replacement}\n    {MARK_END}", html, count=1)
    else:
        # 旧版模板的回退匹配
        pattern = r'let subtitleData = \[\s*\{[\s\S]*?\}\s*\];'
        if re.search(pattern, html):
            new_html = re.sub(pattern, replacement, html, count=1)
        else:
            print("❌ 模板中找不到字幕注入标记，请确认 index.html 未被修改坏。")
            sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(output_html_path)), exist_ok=True)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(new_html)

    # 写出课文元信息（书架页据此生成）
    meta_path = os.path.join(os.path.dirname(os.path.abspath(output_html_path)), "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(output_html_path) / 1024
    print(f"✅ 生成成功！输出文件：{output_html_path}（{size_kb:.0f} KB）")
    print(f"📊 共注入 {len(subtitles_data)} 句台词。")
    print(f"🎯 时间轴偏移：{offset:+.2f}s（音频时间 = 字幕时间 {offset:+.2f}s）")
    if subtitles_data:
        first, last = subtitles_data[0], subtitles_data[-1]
        print(f"⏱ 时间轴范围：{first['start']}s ~ {last['end']}s")
        en_count = sum(1 for it in subtitles_data if it["en"])
        zh_count = sum(1 for it in subtitles_data if it["zh"])
        print(f"🔤 英文覆盖 {en_count} 句 · 中文覆盖 {zh_count} 句")
    print(f"🗂 课文元信息：{meta_path}")


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "index.html")
    pack_dir = os.path.normpath(os.path.join(base_dir, "..", "学习包"))

    if len(sys.argv) < 2:
        print("=" * 64)
        print("双语字幕一键打包工具（支持多课文书架）")
        print("=" * 64)
        print("用法：")
        print("  python3 build_offline_pack.py <字幕文件> [输出.html] [选项]")
        print("\n选项：")
        print("  --offset 秒      时间轴全局偏移（由 calibrate_timeline.py 测得）")
        print("  --id 标识        课文英文标识（文件夹名，如 my_lesson）")
        print("  --title 标题     显示用标题（如 我的课文）")
        print("  --audio 文件名   音频文件名（相对学习页目录，默认 audio.m4a）")
        print("\n示例：")
        print('  python3 build_offline_pack.py "samples/daily_english/lesson.srt" \\')
        print('      --id demo --title 每日口语（演示）')
        print("\n输出默认：../学习包/movies/<id>/learning.html，并自动刷新书架页")
        print("=" * 64)
        return

    parser = argparse.ArgumentParser(description="双语字幕学习包打包工具")
    parser.add_argument("subtitle", help="字幕文件（SRT / VTT / ASS / SSA）")
    parser.add_argument("output", nargs="?", default=None, help="输出 HTML 路径（默认 学习包/movies/<id>/learning.html）")
    parser.add_argument("--offset", type=float, default=0.0,
                        help="时间轴全局偏移秒数（音频时间 = 字幕时间 + offset，默认 0）")
    parser.add_argument("--id", default="default", help="课文标识（用作文件夹名与数据隔离，默认 default）")
    parser.add_argument("--title", default=None, help="显示标题（默认取字幕文件名）")
    parser.add_argument("--audio", default="audio.m4a", help="音频文件名（相对学习页目录，默认 audio.m4a）")
    args = parser.parse_args()

    srt_path = args.subtitle
    if not os.path.exists(srt_path):
        print(f"❌ 找不到字幕文件：{srt_path}")
        sys.exit(1)

    title = args.title or os.path.splitext(os.path.basename(srt_path))[0]
    output_path = args.output or os.path.join(pack_dir, "movies", args.id, "learning.html")

    print(f"📖 正在解析字幕文件：{srt_path} ...")
    subs = parse_subtitle(srt_path)
    print(f"🎯 解析完成，提取到 {len(subs)} 句台词。")
    if not subs:
        print("❌ 未解析到任何台词，请检查字幕格式。")
        sys.exit(1)
    if len(subs) < 50:
        print("⚠️  台词数量偏少，可能字幕不完整或格式不受支持，请留意检查。")

    print("📦 正在打包进单个离线 HTML 文件...")
    inject_subtitles(template_path, subs, output_path, offset=args.offset, movie_meta={
        "id": args.id,
        "title": title,
        "audioFile": args.audio,
    })

    # 自动刷新该输出所在学习包的书架页
    abs_out = os.path.abspath(output_path)
    parts = abs_out.split(os.sep)
    refresh_dir = pack_dir
    if "movies" in parts:
        idx = parts.index("movies")
        refresh_dir = os.sep.join(parts[:idx]) or os.sep
    try:
        import build_library
        build_library.build(refresh_dir)
    except Exception as exc:  # pragma: no cover
        print(f"⚠️ 书架页刷新失败（可手动运行 tools/build_library.py）：{exc}")


if __name__ == "__main__":
    main()
