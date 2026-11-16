#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
局域网静态服务器（支持 HTTP Range，供手机在 Wi-Fi 下访问学习包）

为什么需要它：
  手机 Safari 无法直接打开本地 HTML 文件，但可以通过局域网访问。
  普通 python -m http.server 不支持 Range 请求，音频无法拖动/跳句；
  本服务器实现了完整的 Range 支持，进度条、单句跳转都能正常工作。

用法：
  python3 tools/serve_range.py [--port 8765] [--dir 学习包]

启动后会在终端打印手机访问地址，例如：
  http://192.168.1.23:8765/
手机与电脑连同一个 Wi-Fi，用 Safari 打开该地址即可（可在 Safari 中「添加到主屏幕」）。
"""

import argparse
import os
import re
import socket
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """在 SimpleHTTPRequestHandler 基础上实现单段 Range 请求支持。"""

    def end_headers(self):
        # 告诉浏览器可以按 Range 请求音频
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()

        range_header = self.headers.get("Range")
        if not range_header or not os.path.isfile(path):
            return super().send_head()

        m = re.match(r"bytes=(\d*)-(\d*)\s*$", range_header.strip())
        if not m:
            return super().send_head()

        file_size = os.path.getsize(path)
        if m.group(1) == "" and m.group(2) == "":
            return super().send_head()
        if m.group(1) == "":  # 后缀范围：bytes=-N
            start = max(0, file_size - int(m.group(2)))
            end = file_size - 1
        else:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else file_size - 1
        end = min(end, file_size - 1)

        if start > end or start >= file_size:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None

        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        return _LimitedReader(f, end - start + 1)

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("  [访问] %s\n" % (fmt % args))


class _LimitedReader:
    """只允许读取指定字节数的文件包装器（配合 Range 响应）。"""

    def __init__(self, fileobj, remaining):
        self._f = fileobj
        self._remaining = remaining

    def read(self, n=-1):
        if self._remaining <= 0:
            return b""
        if n is None or n < 0:
            n = self._remaining
        n = min(n, self._remaining)
        data = self._f.read(n)
        self._remaining -= len(data)
        return data

    def close(self):
        self._f.close()


def get_lan_ip():
    """获取本机在局域网中的 IP 地址。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_dir = os.path.normpath(os.path.join(base_dir, "..", "学习包"))

    ap = argparse.ArgumentParser(description="局域网静态服务器（支持 Range，手机访问学习包）")
    ap.add_argument("--port", type=int, default=8765, help="端口，默认 8765")
    ap.add_argument("--dir", default=default_dir, help="要分享的目录，默认 ../学习包")
    ap.add_argument("--bind", default="0.0.0.0", help="监听地址，默认 0.0.0.0（局域网可访问）")
    args = ap.parse_args()

    directory = os.path.abspath(args.dir)
    if not os.path.isdir(directory):
        print(f"❌ 目录不存在：{directory}")
        sys.exit(1)

    handler = partial(RangeRequestHandler, directory=directory)
    with ThreadingHTTPServer((args.bind, args.port), handler) as httpd:
        ip = get_lan_ip()
        print("=" * 64)
        print("🎧 学习包局域网服务已启动（支持进度拖动 / 单句跳转）")
        print("=" * 64)
        print(f"📱 手机访问地址（需与电脑连同一 Wi-Fi）：")
        print(f"    http://{ip}:{args.port}/            ← 📚 书架首页")
        movies_dir = os.path.join(directory, "movies")
        if os.path.isdir(movies_dir):
            for name in sorted(os.listdir(movies_dir))[:5]:
                if os.path.isfile(os.path.join(movies_dir, name, "learning.html")):
                    print(f"    http://{ip}:{args.port}/movies/{name}/learning.html")
        print()
        print("💡 iPhone 提示：")
        print("   1) 用 Safari 打开上面的地址（音频会自动载入，无需选择文件）；")
        print("   2) 可点 Safari 底部分享按钮 →「添加到主屏幕」，像 App 一样使用。")
        print()
        print(f"📁 分享目录：{directory}")
        print("⏹ 停止服务：按 Ctrl+C")
        print("=" * 64)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止服务。")


if __name__ == "__main__":
    main()
