# -*- coding: utf-8 -*-
"""入口脚本（app.py）：局域网启动的安全护栏与地址探测。

这两条都是"错了会很危险/很难查"的地方：
- `--debug` 与绑定 `0.0.0.0` 的组合必须被拒绝（Werkzeug 调试器 = 远程代码执行）；
- 探测出来的地址不能把回环 / 169.254 自分配地址当成"手机可以访问的地址"发给用户。
"""

from __future__ import annotations

import app as entry


def test_debug_with_lan_is_refused(capsys):
    assert entry.main(["--debug", "--lan"]) == 2
    captured = capsys.readouterr()
    assert "拒绝启动" in captured.err
    assert "任意代码" in captured.err


def test_debug_with_explicit_wildcard_host_is_also_refused(capsys):
    """不只挡 --lan，直接把 --host 写成 0.0.0.0 也要挡。"""
    assert entry.main(["--debug", "--host", "0.0.0.0"]) == 2
    assert "拒绝启动" in capsys.readouterr().err


def test_parser_defaults_are_loopback_only():
    args = entry.build_parser().parse_args([])
    assert args.lan is False
    assert args.debug is False
    assert args.port == 5000
    assert args.host is None


def test_lan_addresses_exclude_loopback_and_link_local():
    for address in entry.lan_ipv4_addresses():
        assert not address.startswith("127."), address
        assert not address.startswith("169.254."), address
        assert address.count(".") == 3, address


def test_banner_mentions_lan_url_and_prerequisites(capsys, monkeypatch):
    monkeypatch.setattr(entry, "lan_ipv4_addresses", lambda: ["192.168.1.9"])
    entry.print_banner("0.0.0.0", 5000)

    output = capsys.readouterr().out
    assert "http://127.0.0.1:5000" in output
    assert "http://192.168.1.9:5000" in output
    assert "防火墙" in output                    # 前置条件要提示到位
    assert "没有登录" in output                  # 安全边界要提示到位


def test_banner_without_lan_hints_how_to_enable_it(capsys):
    entry.print_banner("127.0.0.1", 5000)
    output = capsys.readouterr().out
    assert "--lan" in output
    # 只给出本机地址，不列局域网地址（避免用户误以为已经能手机访问）
    assert output.count("http://") == 1


def test_banner_still_works_when_no_lan_address_found(capsys, monkeypatch):
    monkeypatch.setattr(entry, "lan_ipv4_addresses", lambda: [])
    entry.print_banner("0.0.0.0", 5000)
    assert "ipconfig" in capsys.readouterr().out
