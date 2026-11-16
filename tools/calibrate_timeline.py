#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间轴校准工具（字幕 ↔ 音频自动对齐）

用途：
  当音视频与字幕来源不同（片头长度/版本差异）时，自动测量字幕整体需要偏移的秒数。

原理：
  1. 解码音视频中对白声道的低采样率单声道音频（默认 8kHz）；
  2. 计算音频的语音活动包络（短时 RMS 能量，0.25s 一帧）；
  3. 用字幕的"说话区间"作为参考信号，与音频包络做归一化互相关（NCC），
     在 ±N 秒范围内搜索最佳整体偏移；
  4. 抛物线插值细化到约 0.05s 精度，并给出置信度与次优峰供交叉验证。

用法：
  python3 calibrate_timeline.py <音视频文件> <字幕.srt|.ass> [选项]

选项：
  --stream N        指定相对音轨序号（0 = 第一条音轨，默认 0）
  --all             对所有音轨分别测量（用于交叉验证，强烈推荐 5.1+2.0 双音轨文件）
  --channel auto    声道模式：auto(≥6声道取中置 FC，否则混单) | FC | mono
  --max-shift 180   最大搜索偏移秒数，默认 ±180
  --limit 600       只分析前 N 秒（快速试跑用）
  --json            以 JSON 输出（便于脚本调用）

输出含义：
  偏移 = 播放时应使用的公式：音频时间 = 字幕时间 + 偏移
  例如输出 "+3.4s"，表示字幕整体比声音早了 3.4 秒，需要把字幕时间加 3.4 秒。
"""

import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

try:
    from build_offline_pack import parse_subtitle  # 复用同一套字幕解析逻辑
except Exception as exc:  # pragma: no cover
    print(f"❌ 无法导入同目录下的 build_offline_pack.py：{exc}")
    sys.exit(1)

SAMPLE_RATE = 8000
FRAME_SECONDS = 0.25  # 包络帧长


def probe_audio_streams(media_path):
    """返回音频流列表：[{audio_index, channels, codec}, ...]（audio_index 为相对序号）。"""
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", media_path]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    streams = []
    audio_index = 0
    for st in info.get("streams", []):
        if st.get("codec_type") == "audio":
            streams.append({
                "audio_index": audio_index,
                "channels": int(st.get("channels") or 0),
                "codec": st.get("codec_name", "?"),
            })
            audio_index += 1
    return streams


def decode_mono(media_path, audio_index=0, channel="mono", sr=SAMPLE_RATE, duration=None):
    """把指定音轨解码为单声道 16bit PCM（返回 np.int16 数组）。"""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", media_path]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-map", f"0:a:{audio_index}"]
    if channel == "FC":
        cmd += ["-af", "pan=mono|c0=FC"]  # 5.1 原始混音：对白集中在中置
    else:
        cmd += ["-ac", "1"]
    cmd += ["-ar", str(sr), "-f", "s16le", "-"]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(proc.stdout, dtype=np.int16)


def rms_envelope(x, sr=SAMPLE_RATE, frame=FRAME_SECONDS):
    """分帧 RMS 能量（dB），分块计算以控制内存。"""
    frame_samples = int(round(sr * frame))
    n_frames = len(x) // frame_samples
    usable = x[: n_frames * frame_samples]  # 截断到整数帧，避免最后一块不整除
    env = np.empty(n_frames, dtype=np.float32)
    chunk_frames = 4000
    for i in range(0, n_frames, chunk_frames):
        seg = usable[i * frame_samples:(i + chunk_frames) * frame_samples].astype(np.float32)
        seg = seg.reshape(-1, frame_samples)
        env[i:i + len(seg)] = np.sqrt(np.mean(seg * seg, axis=1) + 1e-9)
    env_db = 20.0 * np.log10(env / 32768.0 + 1e-9)
    return np.clip(env_db, -70.0, 0.0)


def subtitle_activity(items, n_frames, frame=FRAME_SECONDS):
    """把字幕说话区间转成 0/1 活动信号。"""
    act = np.zeros(n_frames, dtype=np.float32)
    for it in items:
        a = max(0, int(math.floor(it["start"] / frame)))
        b = min(n_frames, int(math.ceil(it["end"] / frame)) + 1)
        if b > a:
            act[a:b] = 1.0
    return act


def ncc_scan(env, act, frame=FRAME_SECONDS, max_shift_s=180.0):
    """在 ±max_shift 范围内计算归一化互相关，返回 (lags, scores)。"""
    n = min(len(env), len(act))
    env = env[:n].astype(np.float64)
    act = act[:n].astype(np.float64)
    env -= env.mean()
    act -= act.mean()
    max_lag = int(round(max_shift_s / frame))
    lags = np.arange(-max_lag, max_lag + 1)
    scores = np.full(lags.shape, np.nan)
    for i, k in enumerate(lags):
        if k >= 0:
            a, s = env[k:], act[:n - k]
        else:
            a, s = env[:n + k], act[-k:]
        na, ns = np.linalg.norm(a), np.linalg.norm(s)
        if na > 0 and ns > 0:
            scores[i] = float(np.dot(a, s) / (na * ns))
    return lags, scores


def refine_peak(lags, scores):
    """抛物线插值细化峰值位置，返回 (峰值索引, 亚帧偏移, 峰值)。"""
    i = int(np.nanargmax(scores))
    delta = 0.0
    if 0 < i < len(scores) - 1:
        y0, y1, y2 = scores[i - 1], scores[i], scores[i + 1]
        denom = y0 - 2.0 * y1 + y2
        if abs(denom) > 1e-12:
            delta = max(-0.5, min(0.5, 0.5 * (y0 - y2) / denom))
    return i, delta, float(scores[i])


def measure(media_path, subtitle_path, audio_index=0, channel="auto", max_shift_s=180.0, limit=None):
    """对单条音轨测量偏移，返回结果 dict。"""
    streams = probe_audio_streams(media_path)
    if audio_index >= len(streams):
        raise SystemExit(f"❌ 音轨 a:{audio_index} 不存在（共 {len(streams)} 条音轨）")
    n_channels = streams[audio_index]["channels"]

    ch_mode = channel
    if channel == "auto":
        ch_mode = "FC" if n_channels >= 6 else "mono"
    if ch_mode == "FC" and n_channels < 6:
        ch_mode = "mono"

    items = parse_subtitle(subtitle_path)
    if not items:
        raise SystemExit("❌ 字幕解析为空，无法校准")

    x = decode_mono(media_path, audio_index=audio_index, channel=ch_mode, duration=limit)
    if len(x) < SAMPLE_RATE * 10:
        raise SystemExit("❌ 音频太短（<10 秒），无法校准")
    env = rms_envelope(x)
    media_seconds = len(x) / SAMPLE_RATE

    used_items = [it for it in items if limit is None or it["start"] < media_seconds]
    act = subtitle_activity(used_items, len(env))

    lags, scores = ncc_scan(env, act, FRAME_SECONDS, max_shift_s)
    i, delta, peak = refine_peak(lags, scores)
    offset = (float(lags[i]) + delta) * FRAME_SECONDS

    med = float(np.nanmedian(scores))
    std = float(np.nanstd(scores)) + 1e-12
    confidence = (peak - med) / std

    # 次优峰（与主峰至少相隔 5 秒）
    exclude = int(round(5.0 / FRAME_SECONDS))
    mask = np.abs(np.arange(len(scores)) - i) > exclude
    second_peak = float(np.nanmax(scores[mask])) if mask.any() else float("nan")

    # 前 3 个互相间隔 ≥5s 的候选峰（人工复核用）
    order = np.argsort(np.nan_to_num(scores, nan=-1.0))[::-1]
    top_peaks = []
    for idx in order:
        if scores[idx] <= -0.99:
            break
        if all(abs(int(idx) - int(j)) > exclude for j, _ in top_peaks):
            top_peaks.append((int(idx), float(scores[idx])))
        if len(top_peaks) >= 3:
            break

    # 分片验证：把全片等分 4 段独立测量，结果一致才可信
    n = min(len(env), len(act))
    segment_offsets = []
    n_seg = 4
    for s in range(n_seg):
        a0 = s * n // n_seg
        a1 = (s + 1) * n // n_seg
        seg_env, seg_act = env[a0:a1], act[a0:a1]
        if len(seg_env) < int(300 / FRAME_SECONDS):  # 片段太短（<5 分钟）则跳过
            continue
        seg_lags, seg_scores = ncc_scan(seg_env, seg_act, FRAME_SECONDS, min(max_shift_s, 60.0))
        si, sd, _ = refine_peak(seg_lags, seg_scores)
        segment_offsets.append(round(float(seg_lags[si] + sd) * FRAME_SECONDS, 2))
    segment_spread = round(max(segment_offsets) - min(segment_offsets), 2) if segment_offsets else None

    return {
        "top_peaks": [{"offset": round(float(lags[j]) * FRAME_SECONDS, 2), "score": round(v, 4)}
                      for j, v in top_peaks],
        "segment_offsets": segment_offsets,
        "segment_spread": segment_spread,
        "media": media_path,
        "subtitle": subtitle_path,
        "audio_index": audio_index,
        "channels": n_channels,
        "channel_mode": ch_mode,
        "media_seconds": round(media_seconds, 2),
        "subtitle_items": len(items),
        "offset": round(offset, 2),
        "confidence": round(confidence, 2),
        "second_peak": round(second_peak, 4),
    }


def print_result(r, quiet=False):
    ch_desc = {"FC": "中置声道", "mono": "混单"}.get(r["channel_mode"], r["channel_mode"])
    arrow = "+" if r["offset"] >= 0 else ""
    if r["offset"] == 0:
        arrow = "±"
    print(f"▶ 音轨 a:{r['audio_index']}（{r['channels']}声道/{r['channel_mode']}/{ch_desc}）")
    print(f"  建议偏移：{arrow}{r['offset']:.2f}s  ·  置信度 {r['confidence']:.1f}"
          f"  ·  次优峰 {r['second_peak']:.3f}")
    if r.get("top_peaks"):
        peaks = "，".join(f"{p['offset']:+.2f}s({p['score']:.3f})" for p in r["top_peaks"])
        print(f"  候选峰：{peaks}")
    if r.get("segment_offsets"):
        segs = "，".join(f"{v:+.2f}s" for v in r["segment_offsets"])
        spread = r.get("segment_spread")
        verdict = "✅ 分片一致" if (spread is not None and spread <= 0.75) else "⚠️ 分片不一致，需人工复核"
        print(f"  分片验证：{segs}  →  {verdict}（最大差 {spread}s）")
    gap = r["confidence"]
    if abs(r["offset"]) >= 0.99 * 180:
        print("  ⚠️ 峰值落在搜索边界，建议扩大 --max-shift 重测")
    elif gap < 3.0:
        print("  ⚠️ 置信度偏低，请检查音轨是否包含完整对白")
    if not quiet and r["offset"] != 0:
        direction = "后移" if r["offset"] > 0 else "前移"
        print(f"  含义：音频时间 = 字幕时间 {arrow}{r['offset']:.2f}s（播放时字幕需整体{direction} {abs(r['offset']):.2f}s）")


def main():
    ap = argparse.ArgumentParser(description="字幕与音频时间轴自动校准")
    ap.add_argument("media", help="音视频或音频文件")
    ap.add_argument("subtitle", help="字幕文件（SRT/ASS）")
    ap.add_argument("--stream", type=int, default=0, help="音轨序号，默认 0")
    ap.add_argument("--all", action="store_true", help="测量所有音轨并交叉验证")
    ap.add_argument("--channel", default="auto", choices=["auto", "FC", "mono"], help="声道模式")
    ap.add_argument("--max-shift", type=float, default=180.0, help="最大搜索偏移（秒）")
    ap.add_argument("--limit", type=float, default=None, help="只分析前 N 秒（快速试跑）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    for p in (args.media, args.subtitle):
        if not os.path.exists(p):
            raise SystemExit(f"❌ 找不到文件：{p}")

    if args.all:
        streams = probe_audio_streams(args.media)
        indices = [s["audio_index"] for s in streams]
    else:
        indices = [args.stream]

    results = []
    for idx in indices:
        results.append(measure(args.media, args.subtitle, audio_index=idx,
                               channel=args.channel, max_shift_s=args.max_shift, limit=args.limit))

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"📖 字幕：{args.subtitle}")
        print(f"🎬 音视频：{args.media}")
        for r in results:
            print_result(r)
        if len(results) >= 2:
            o1, o2 = results[0]["offset"], results[1]["offset"]
            if abs(o1 - o2) <= 0.5:
                print(f"✅ 交叉验证通过：两组音轨测量结果一致（差值 {abs(o1 - o2):.2f}s）")
            else:
                print(f"⚠️ 交叉验证不一致（差值 {abs(o1 - o2):.2f}s），请人工复核")


if __name__ == "__main__":
    main()
