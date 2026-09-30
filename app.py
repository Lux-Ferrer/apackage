# -*- coding: utf-8 -*-
"""应用入口。

用法::

    python app.py                     # 只在本机访问：http://127.0.0.1:5000
    python app.py --lan               # 绑定 0.0.0.0，手机可经局域网访问（真机验证用）
    python app.py --lan --port 8080   # 换端口
    python app.py --debug             # 开调试器（**不允许**与 --lan 同时用，见下）

为什么 `--lan` 与 `--debug` 互斥
--------------------------------
Werkzeug 的调试器带交互式回溯页面，能在浏览器里执行任意 Python 代码。把它绑到
``0.0.0.0`` 等于把代码执行权限开放给同一网段的每一台设备（咖啡厅 Wi-Fi 上尤其危险）。
所以这里直接拒绝启动这个组合，而不是打印一句"请注意安全"。

另外：本应用**没有登录**（已确认范围外），局域网内任何能打开网址的人都能增删数据、
清除全部报告。`--lan` 只适用于可信网络（自己的热点 / 家里 / 办公室内网）下的演示与
真机验证。详见 README「手机真机验证」一节。
"""

from __future__ import annotations

import argparse
import socket
import sys

from webapp import create_app


def lan_ipv4_addresses() -> list:
    """本机在局域网里的 IPv4 地址（可能有多个网卡）。

    第一条用 UDP ``connect`` 技巧：不会真的发包，只是让内核按路由表选出出口网卡，
    因此拿到的通常是手机最可能连上的那个地址。其余来自主机名解析作为补充。
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
            candidates.append(info[4][0])
    except OSError:
        pass

    unique = []
    for address in candidates:
        if address.startswith("127.") or address.startswith("169.254."):
            continue                                  # 回环与"没拿到 DHCP"的自分配地址
        if address not in unique:
            unique.append(address)
    return unique


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="建筑幕墙检测报告工具 —— 本地服务")
    parser.add_argument("--lan", action="store_true",
                        help="绑定 0.0.0.0，允许手机通过局域网访问（真机验证用）")
    parser.add_argument("--host", default=None, help="自定义绑定地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=5000, help="端口（默认 5000）")
    parser.add_argument("--debug", action="store_true",
                        help="开启调试器与自动重载（不要与 --lan 同时用）")
    return parser


def print_banner(host: str, port: int) -> None:
    local = "http://127.0.0.1:%d" % port
    print()
    print("  建筑幕墙检测报告工具")
    print("  " + "-" * 46)
    print("  本机访问：%s" % local)

    if host == "0.0.0.0":
        addresses = lan_ipv4_addresses()
        if addresses:
            for index, address in enumerate(addresses):
                prefix = "  手机访问：" if index == 0 else "            "
                print("%shttp://%s:%d" % (prefix, address, port))
        else:
            print("  手机访问：没找到局域网地址，请在终端执行 ipconfig 查看 IPv4 地址")

        print()
        print("  前提：手机与电脑连同一个 Wi-Fi · 手机关掉 VPN ·")
        print("        Windows 防火墙放行 TCP %d（首次运行弹窗选「专用网络」）" % port)
        print("  安全：本应用没有登录，同网段的任何设备都能打开并修改数据，")
        print("        只在可信网络下使用；调试器已禁止与 --lan 同时开启。")
    else:
        print("  想让手机访问？用：python app.py --lan")
    print()


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")

    if args.debug and host == "0.0.0.0":
        print("拒绝启动：--debug 不能与绑定 0.0.0.0 同时使用。", file=sys.stderr)
        print("Werkzeug 调试器能在浏览器里执行任意代码，绑定到局域网等于把它开放出去。",
              file=sys.stderr)
        return 2

    print_banner(host, args.port)
    # 应用对象在 main() 里才创建：模块级 create_app() 会在 import 时就去建库，
    # 测试 import app 就会污染仓库里的 defects.db。
    # （要用 WSGI 服务器跑：flask --app "app:create_app()" run）
    app = create_app()
    app.run(host=host, port=args.port, debug=args.debug,
            use_reloader=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
