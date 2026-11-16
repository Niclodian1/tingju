#!/usr/bin/env bash
#
# 从「你自己合法持有的音视频拷贝」中提取并转换适合手机的音频
# ------------------------------------------------------------------
# 本脚本只做本地格式转换：视频文件 -> .m4a 音频，不下载任何内容。
# 请仅对你合法持有的文件使用（如已购买的数字版或光盘转录）。
#
# 用法:
#   ./tools/extract_audio.sh <视频文件> [输出.m4a] [音轨序号] [开始时间] [时长]
#
# 示例:
#   ./tools/extract_audio.sh "素材/my_video.mkv" "学习包/movies/my_lesson/audio.m4a"
#   ./tools/extract_audio.sh "素材/my_video.mkv" out.m4a 1            # 使用第 1 条音轨（0 为第一条）
#   ./tools/extract_audio.sh "素材/my_video.mkv" test.m4a 0 00:03:00 00:10:00
#                                                                 # 从 3:00 开始截取 10 分钟做测试
set -euo pipefail

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "❌ 未找到 ffmpeg。macOS 可通过 Homebrew 安装："
  echo "   brew install ffmpeg"
  exit 1
fi

if [ $# -lt 1 ]; then
  echo "用法: ./tools/extract_audio.sh <视频文件> [输出.m4a] [音轨序号] [开始时间] [时长]"
  echo "示例: ./tools/extract_audio.sh \"素材/my_video.mkv\" \"学习包/movies/my_lesson/audio.m4a\""
  exit 1
fi

INPUT="$1"
OUTPUT="${2:-audio.m4a}"
TRACK="${3:-0}"
START="${4:-}"
DURATION="${5:-}"

if [ ! -f "$INPUT" ]; then
  echo "❌ 找不到文件：$INPUT"
  exit 1
fi

echo "📋 文件中的音轨列表："
ffprobe -v error -select_streams a \
  -show_entries stream=index:stream_tags=language,title -show_entries stream=codec_name,channels \
  -of default=noprint_wrappers=1 "$INPUT" || true
echo "------------------------------------------------------------"

SEEK_ARGS=()
if [ -n "$START" ]; then
  SEEK_ARGS+=(-ss "$START")
fi
DUR_ARGS=()
if [ -n "$DURATION" ]; then
  DUR_ARGS+=(-t "$DURATION")
fi

echo "🎬 正在提取第 $TRACK 条音轨 -> $OUTPUT ..."
ffmpeg -hide_banner -loglevel warning -y \
  "${SEEK_ARGS[@]}" -i "$INPUT" \
  -vn -map "0:a:$TRACK" -c:a aac -b:a 128k -ac 2 \
  "${DUR_ARGS[@]}" "$OUTPUT"

echo "------------------------------------------------------------"
ls -lh "$OUTPUT"
echo "✅ 完成！把 $OUTPUT 传到手机，在网页里点击【载入音频】选择它即可。"
echo "💡 提示：128kbps 立体声对白清晰；若嫌文件大，可改为 -b:a 96k（或 -ac 1 单声道）。"
