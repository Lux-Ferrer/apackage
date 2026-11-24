#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把"给客户的东西"打成一个交付包（APK + 网页版部署包 + 文档）。

为什么单独一个脚本：以前交付物散在 dist/ 和 docs/ 里，客户拿到手要自己判断"装哪个、看哪个"。
这里固定一种摆放方式，并在 **00-交付清单.md** 里写清楚"装哪个 / 看哪个 / 各自校验值"。

会做的校验（任一不过就报错，不产出包）
--------------------------------------
1. 版本一致：`web/app/product.js` = `dist/mcc-inspection-tool-v<版本>.zip` 里的 `VERSION.txt`；
2. APK 真的是这个版本：读 APK 里的 `assets/public/VERSION.txt`（Capacitor 把 www 打进 APK）；
3. 手册、部署说明、sha256 文件都在。

用法::

    python tools/make_delivery_bundle.py                       # 自动找 APK 并封包
    python tools/make_delivery_bundle.py --apk 路径\\xxx.apk    # 指定 APK
    python tools/make_delivery_bundle.py --no-apk --out _work/delivery-preview   # 只看结构
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
RELEASE = ROOT / "docs" / "release"

APK_PATTERNS = ("mcc-inspection-tool-v{version}-debug.apk", "mcc-inspection-tool-v{version}.apk")
APK_SEARCH_DIRS = (ROOT, Path.home() / "Downloads", Path.home() / "Desktop")


def product_version() -> str:
    text = (ROOT / "web" / "app" / "product.js").read_text(encoding="utf-8")
    match = re.search(r"version:\s*'([0-9.]+)'", text)
    if not match:
        raise SystemExit("在 web/app/product.js 里没找到 version")
    return match.group(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_apk(version: str, explicit: Path | None) -> Path | None:
    if explicit:
        path = explicit if explicit.is_absolute() else (ROOT / explicit)
        if not path.exists():
            raise SystemExit(f"× 指定的 APK 不存在：{path}")
        return path
    for folder in APK_SEARCH_DIRS:
        if not folder.is_dir():
            continue
        for pattern in APK_PATTERNS:
            candidate = folder / pattern.format(version=version)
            if candidate.exists():
                return candidate
        # 兜底：该目录下任何本版本的 apk
        for candidate in sorted(folder.glob(f"*v{version}*.apk")):
            return candidate
    return None


def apk_web_version(apk: Path) -> tuple[str | None, int]:
    """读 APK 里打包的 www/VERSION.txt（Capacitor 放在 assets/public/），顺便返回应用文件数。"""
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        version_file = next((name for name in names if name.endswith("assets/public/VERSION.txt")), None)
        if version_file is None:
            return None, 0
        text = archive.read(version_file).decode("utf-8")
        match = re.search(r"版本：v([0-9.]+)", text)
        # Capacitor 把 www 放在 assets/public/ 下（路径没有前导斜杠）
        app_files = sum(1 for name in names if name.startswith("assets/public/") and not name.endswith("/"))
        return (match.group(1) if match else None), app_files


def write_readme(target: Path, version: str, apk: Path | None, rows: list[tuple[str, str, str]]) -> None:
    apk_mb = apk.stat().st_size / 1024 / 1024 if apk else 0
    apk_block = (
        f"| `01-Android-APK/{apk.name}` | **手机安装用**（Android 7.0 及以上） | {sha256(apk)} |"
        if apk else
        "| `01-Android-APK/…apk` | **待放入**：把 CI 产出的 `mcc-inspection-tool-v{0}-debug.apk` 放进来 | — |".format(version)
    )
    lines = [
        f"# 交付清单 · 建筑幕墙检测报告工具 v{version}",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　出品：中冶建筑研究总院（深圳）有限公司",
        "",
        "## 一、先看这一页：你要哪个",
        "",
        "| 场景 | 用这个 | 看这个 |",
        "| --- | --- | --- |",
        f"| 现场检测员要用手机记录 | `01-Android-APK/` 里的 **.apk**（约 {apk_mb:.1f} MB） | 《用户操作手册》第 1 章（含微信改名成 `.apk.1` 的避坑） |",
        "| 内网部署、多人用浏览器打开 | `02-网页版部署包/` 里的 **.zip** | 《客户部署与使用说明》 |",
        "| 只想打印一份操作指引 | `03-文档/用户操作手册.pdf` | — |",
        "",
        "## 二、包里有什么（含校验值）",
        "",
        "| 文件 | 用途 | sha256 |",
        "| --- | --- | --- |",
        apk_block,
    ]
    for name, purpose, digest in rows:
        lines.append(f"| `{name}` | {purpose} | {digest} |")
    lines += [
        "",
        "> 校验方法：`certutil -hashfile 文件名 SHA256`（Windows）或 `shasum -a 256 文件名`（macOS）。",
        "",
        "## 三、三条纪律",
        "",
        "1. **先改报告人**：每台手机「我的 → 个人信息配置」填一次姓名/部门，之后新建的缺陷报告才会署你的名；",
        "2. **每天收工导出备份**：「我的 → 数据管理 → 导出备份」，数据只在这台手机里，丢了找不回来；",
        "3. **升级不要卸载**：新版本直接覆盖安装（`versionCode` 递增 + 同一签名），卸载会连数据一起删。",
        "",
        "## 四、版本对照",
        "",
        "| 东西 | 版本 |",
        "| --- | --- |",
        f"| 网页版 / APK 内嵌前端 | v{version} |",
        "| 手册 | 与 v" + version + " 界面一致（截图取自该版本） |",
        "",
    ]
    (target / "00-交付清单.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="打包客户交付物")
    parser.add_argument("--apk", type=Path, default=None, help="APK 路径（默认在项目根/下载里找）")
    parser.add_argument("--no-apk", action="store_true", help="不要求 APK（只看结构）")
    parser.add_argument("--out", type=Path, default=DIST / "delivery", help="输出目录")
    parser.add_argument("--no-zip", action="store_true", help="只生成目录，不压缩")
    args = parser.parse_args()

    # --out 允许相对路径，但后面要相对仓库根打印，先统一成绝对路径
    args.out = (args.out if args.out.is_absolute() else (ROOT / args.out)).resolve()

    version = product_version()
    web_zip = DIST / f"mcc-inspection-tool-v{version}.zip"
    if not web_zip.exists():
        raise SystemExit(f"× 缺少网页版部署包：{web_zip.relative_to(ROOT)}（先跑 python tools/make_release_zip.py）")

    with zipfile.ZipFile(web_zip) as archive:
        version_txt = archive.read("mcc-inspection-tool/VERSION.txt").decode("utf-8")
    zip_version = (re.search(r"版本：v([0-9.]+)", version_txt) or [None, None])[1]
    if zip_version != version:
        raise SystemExit(f"× 版本不一致：product.js={version}，但 zip 里是 {zip_version}")

    apk = None if args.no_apk else find_apk(version, args.apk)
    if not args.no_apk and apk is None:
        raise SystemExit(
            f"× 找不到 v{version} 的 APK。\n"
            f"  把下载到的 mcc-inspection-tool-v{version}-debug.apk 放到 {ROOT} 或 ~/Downloads，\n"
            f"  或者用 --apk 指定路径；只想看结构可加 --no-apk。")
    if apk is not None:
        found_version, app_files = apk_web_version(apk)
        if found_version != version:
            raise SystemExit(f"× APK 里的前端是 v{found_version}，不是 v{version}：{apk}")
        print(f"· APK 校验通过：v{found_version}，内含 {app_files} 个前端文件")

    bundle = args.out / f"mcc-inspection-tool-v{version}-交付包"
    if bundle.exists():
        shutil.rmtree(bundle)
    (bundle / "01-Android-APK").mkdir(parents=True)
    (bundle / "02-网页版部署包").mkdir(parents=True)
    (bundle / "03-文档").mkdir(parents=True)

    rows: list[tuple[str, str, str]] = []

    def copy(source: Path, target: Path, purpose: str) -> None:
        shutil.copy2(source, target)
        rows.append((target.relative_to(bundle).as_posix(), purpose, sha256(target)))

    if apk is not None:
        target_apk = bundle / "01-Android-APK" / apk.name
        shutil.copy2(apk, target_apk)
        rows.append((target_apk.relative_to(bundle).as_posix(),
                     "手机安装包（Android 7.0+，覆盖安装不丢数据）", sha256(target_apk)))
        (bundle / "01-Android-APK" / f"{apk.name}.sha256").write_text(
            f"{sha256(target_apk)}  {apk.name}\n", encoding="utf-8")

    copy(web_zip, bundle / "02-网页版部署包" / web_zip.name,
         "网页版部署包（解压即为站点根目录，内含部署说明、用户手册、deploy 样例）")
    for name in ("用户操作手册.pdf", "用户操作手册.md", "客户部署与使用说明.md"):
        source = RELEASE / name
        if not source.exists():
            raise SystemExit(f"× 缺少文档：{source.relative_to(ROOT)}")
        copy(source, bundle / "03-文档" / name,
             {"用户操作手册.pdf": "操作手册（打印/发微信给检测员）",
              "用户操作手册.md": "操作手册源文件（可再编辑）",
              "客户部署与使用说明.md": "部署与运维说明"}[name])

    write_readme(bundle, version, apk, rows)

    sums = bundle / "SHA256SUMS.txt"
    sums.write_text("\n".join(f"{digest}  {name}" for name, _purpose, digest in rows) + "\n", encoding="utf-8")

    print(f"✅ 交付目录：{bundle.relative_to(ROOT)}")
    for name, purpose, _digest in rows:
        print(f"   · {name:52} {purpose}")
    if apk is None:
        print("   ! 还没有放 APK（用 --no-apk 生成的结构，仅供预览）")

    if not args.no_zip and apk is not None:
        archive_path = args.out / f"mcc-inspection-tool-v{version}-交付包.zip"
        if archive_path.exists():
            archive_path.unlink()
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle.rglob("*")):
                if path.is_file():
                    archive.write(path, Path(bundle.name) / path.relative_to(bundle))
        print(f"✅ 压缩包：{archive_path.relative_to(ROOT)}（{archive_path.stat().st_size / 1024 / 1024:.2f} MB）")
        print(f"   sha256：{sha256(archive_path)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
