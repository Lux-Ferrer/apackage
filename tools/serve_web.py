# -*- coding: utf-8 -*-
"""给 M5 的纯静态前端起一个本地服务器（并打印手机能打开的局域网地址）。

为什么不直接用 ``python -m http.server``
----------------------------------------
那条命令**能用**（README 里也写了），但它只监听 127.0.0.1、也不告诉你局域网地址。
M5-3/M5-4 的验收必须**在真机上**跑（照片方向、IndexedDB 配额、离线），
所以这里补上两件小事：绑 `0.0.0.0` + 把可用的局域网地址列出来。

**这不是要替换任何东西**：Flask 版（``python app.py --lan``）仍然在跑它自己的服务；
这个脚本只服务 `web/` 这个静态目录，供 M5 的开发与真机验证使用。

用法::

    python tools/serve_web.py                 # http://<本机IP>:8080
    python tools/serve_web.py --port 9000
    python tools/serve_web.py --host 127.0.0.1   # 只给本机用（更安全）

安全提醒：绑 ``0.0.0.0`` 等于把 `web/` 目录暴露给同网段。验完记得 Ctrl+C；
不要在公司网络上长时间开着。
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socket
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"


def local_addresses() -> list:
    """本机的局域网 IPv4 地址（尽量不依赖外网：用 UDP 连一下再看本地端点）。"""
    addresses = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.2)
            # 不真的发包，只为让内核选出默认出口网卡
            probe.connect(("8.8.8.8", 80))
            addresses.append(probe.getsockname()[0])
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in addresses and not address.startswith("127."):
                addresses.append(address)
    except OSError:
        pass
    return addresses


class Handler(http.server.SimpleHTTPRequestHandler):
    """在默认处理器上加两件事：不缓存（开发时免得改了代码看不到）+ 安静一点的日志。"""

    # 显式声明关键类型。**为什么不能只靠系统 mimetypes**：
    # `.webmanifest` 在不少系统上认不出来，会被当成 application/octet-stream ——
    # 于是一个完全正确的 PWA 清单会被浏览器**静默拒绝**（不可安装，且几乎没有报错）。
    # 这类问题只在别人的机器上复现时最难查，所以把话直接写死在代码里。
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".webmanifest": "application/manifest+json",
        ".mjs": "text/javascript",
        ".js": "text/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".png": "image/png",
        ".svg": "image/svg+xml",
    }

    def end_headers(self):
        # 开发/验证阶段一律不缓存：否则手机上会一直看到旧版本
        # （离线缓存由 Service Worker 负责，走的是它自己的 Cache Storage，与这里无关）
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):                      # noqa: A003
        sys.stderr.write("  %s\n" % (fmt % args))


def main() -> int:
    parser = argparse.ArgumentParser(description="给 web/ 起一个静态服务器（供 M5 开发与真机验证）")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0", help="默认 0.0.0.0（手机可访问）")
    args = parser.parse_args()

    if not WEB_DIR.exists():
        print("找不到目录：%s" % WEB_DIR)
        return 2

    handler = functools.partial(Handler, directory=str(WEB_DIR))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((args.host, args.port), handler) as server:
        print("M5 纯静态前端已启动（Ctrl+C 停止）")
        print("  目录：%s" % WEB_DIR)
        print("  本机：http://127.0.0.1:%d" % args.port)
        if args.host == "0.0.0.0":
            for address in local_addresses():
                print("  手机：http://%s:%d   ← 手机与电脑需在同一 Wi-Fi" % (address, args.port))
        print()
        print("  提示：不要用 file:// 直接打开 index.html —— IndexedDB 与 ES modules 都会受限。")
        print("  真机验收清单：docs/management/M5-真机验证checklist.md（B 组是拍照方向）")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
