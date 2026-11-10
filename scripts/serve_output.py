#!/usr/bin/env python3
"""本地静态服务:把 output/ 目录以「无缓存」方式暴露,供右侧预览面板直连原文件。

用途(见专家层「产物实时预览」规则):
  档案/报告是「同路径反复重建」的,快照式预览永远看不到更新。
  起这个服务后把 http://127.0.0.1:8899/<文件名> 交给 preview,
  每次重建只要 ⌘R 刷新就能看到最新内容。

用法:
    python3 scripts/serve_output.py            # 前台启动,默认 8899
    python3 scripts/serve_output.py --port 8899 --dir ./output

已在跑时不要重复启动(会 Address already in use),直接复用同端口即可。
"""
import argparse
import functools
import http.server
import os
import socketserver
import sys

DEFAULT_PORT = 8899


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """禁用缓存的静态文件处理器,保证刷新即见最新。"""

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):  # 静音访问日志
        pass


def make_handler(directory: str):
    return functools.partial(NoCacheHandler, directory=directory)


def main() -> int:
    ap = argparse.ArgumentParser(description="无缓存静态服务,供分析产物实时预览")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--dir", default="./output", help="产物目录,默认 ./output")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    directory = os.path.abspath(args.dir)
    if not os.path.isdir(directory):
        print(f"[x] 目录不存在: {directory}", file=sys.stderr)
        return 1

    handler = make_handler(directory)
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.ThreadingTCPServer((args.host, args.port), handler) as httpd:
            print(f"[ok] 服务已启动: http://{args.host}:{args.port}/  ->  {directory}")
            print(f"[ok] 产物链接形如: http://{args.host}:{args.port}/<文件名>.html")
            sys.stdout.flush()
            httpd.serve_forever()
    except OSError as exc:
        print(f"[x] 端口 {args.port} 启动失败: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
