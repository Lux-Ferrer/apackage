#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一个零依赖的静态文件服务器 —— 只为了把本工具在内网里跑起来。

为什么包里要带它（而不是让大家 `python -m http.server`）
----------------------------------------------------------
Python 自带的 `http.server` **不认识 `.mjs`**，会以 `text/plain` 返回，
而浏览器对 ES module 的 MIME 检查很严格 —— 结果是**页面一片空白**，
控制台里只留一句 `Failed to load module script: Expected a JavaScript module script`。
这个坑在部署阶段最容易踩，而且看起来像"文件坏了"。

除此之外它只做三件必要的事：
  1. 补全 MIME（`.mjs` / `.webmanifest` / `.docx` …）；
  2. 一律 `Cache-Control: no-cache`（本工具的文件带内容指纹，
     但 `sw.js` 与 `index.html` 必须让浏览器每次都来问一次，否则更新推不下去）；
  3. 启动时打印**手机能用的地址**（局域网 IP，而不是 127.0.0.1）。

用法（在解压后的目录里）::

    python serve_static.py                 # 默认 8080 端口，服务当前目录
    python serve_static.py --port 9000     # 换端口
    python serve_static.py --dir . --port 8080

停止：Ctrl+C

安全边界（重要）
----------------
它是一个**开发/内网演示用**的静态服务器：没有认证、没有 TLS、支持目录列表。
只该在内网临时使用；正式部署请用 Nginx / IIS（见《客户部署与使用说明.md》）。
"""

from __future__ import annotations

import argparse
import functools
import socket
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 浏览器的"能不能加载"取决于这几个扩展名，缺一个就是白屏
EXTRA_MIME = {
    ".mjs": "text/javascript",
    ".js": "text/javascript",
    ".webmanifest": "application/manifest+json",
    ".json": "application/json",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
}


class Handler(SimpleHTTPRequestHandler):
    """补 MIME + 禁缓存 + 安静一点的日志。"""

    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, **EXTRA_MIME}

    def end_headers(self) -> None:                      # noqa: D102 - 见类说明
        # 交付物是"每次都要拿到最新那份"：sw.js 一变就要立刻生效，
        # 静态资源本身带内容指纹（文件名不变但 Service Worker 里带版本号）。
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:     # noqa: D102
        sys.stdout.write("  %s - %s\n" % (self.address_string(), fmt % args or ""))
        sys.stdout.flush()


def lan_addresses(port: int) -> list:
    """猜本机的局域网地址。

    不依赖 `gethostbyname`（在多网卡/虚拟机环境下经常给出没用的结果）：
    先连一个外部地址拿到"出口网卡"的 IP —— UDP connect 不会真的发包。
    """
    candidates = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.2)
            probe.connect(("8.8.8.8", 80))
            candidates.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in candidates:
                candidates.append(address)
    except OSError:
        pass
    usable = [address for address in candidates
              if not address.startswith("127.") and not address.startswith("169.254.")]
    return [f"http://{address}:{port}/" for address in usable]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="静态服务器（给本工具的内网部署/演示用）")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--dir", default=".", help="要服务的目录（解压后的根目录）")
    parser.add_argument("--bind", default="0.0.0.0",
                        help="监听地址；0.0.0.0 = 局域网可访问，127.0.0.1 = 只有本机")
    args = parser.parse_args(argv)

    root = Path(args.dir).resolve()
    if not (root / "index.html").exists():
        print(f"× {root} 里没有 index.html —— 请把 --dir 指到解压后的目录（里面有 app/、assets/）")
        return 1

    handler = functools.partial(Handler, directory=str(root))
    try:
        server = ThreadingHTTPServer((args.bind, args.port), handler)
    except OSError as error:
        print(f"× 端口 {args.port} 启动失败：{error}（换一个端口试试：--port 9000）")
        return 1

    print("=" * 62)
    print("  建筑幕墙检测报告工具 —— 静态服务器已启动")
    print("=" * 62)
    print(f"  目录：{root}")
    print(f"  本机打开：http://127.0.0.1:{args.port}/")
    for url in lan_addresses(args.port):
        print(f"  手机打开：{url}   ← 同一局域网、浏览器地址栏输入")
    print("")
    print("  · 手机与这台电脑必须在同一个局域网（同一 Wi-Fi）")
    print("  · 打不开先看防火墙是否放行该端口；公司网可能有客户端隔离（AP Isolation）")
    print("  · iOS：Safari → 分享 → 添加到主屏幕；Android：Chrome → ⋮ → 添加到主屏幕")
    print("  · 停止：Ctrl+C")
    print("=" * 62)
    sys.stdout.flush()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
