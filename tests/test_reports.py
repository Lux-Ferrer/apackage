# -*- coding: utf-8 -*-
"""M4 报告管理：列表 / 筛选 / 顶部统计 / 详情 / 缩略图 / 删除。

需求依据：`docs/requirements/需求报告.txt` 3.4 a~e。
设计依据：`docs/management/M4-设计.md`。

两条容易被写错、因此专门上锁的语义：

1. ``created_at`` 精度只到秒 —— 同秒内必须靠 ``id DESC`` 兜底，否则列表顺序会抖动；
2. 顶部统计**恒为全量**，不随等级筛选变化（需求 3.4b 与 3.4c 是两件事）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from webapp import config, db
from webapp.services import defects as defect_service
from webapp.services import images

FORM = {
    "defect_type": "密封胶开裂",
    "project_part": "东立面三层 1# 立柱",
    "risk_level": "中",
    "rectification_plan": "第一行：更换密封胶。\n第二行：复检确认无渗漏。",
}


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------
def post_report(client, make_image, **overrides):
    """走真实填报链路建一份报告（含必填的隐患图片）。"""
    payload = dict(FORM)
    payload.update(overrides)
    payload.setdefault("image", make_image(filename="缺陷照片.png"))
    response = client.post("/defects/", data=payload, content_type="multipart/form-data")
    assert response.status_code == 302, response.get_data(as_text=True)
    return int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


def insert_report(level="中", created_at="2026-09-22 10:00:00", defect_type="密封胶开裂",
                  project_id=None, image_path=None) -> int:
    """直接入库，便于精确控制时间（接口链路只到秒，排序测试需要确定值）。"""
    with db.transaction() as conn:
        return conn.execute(
            """
            INSERT INTO defects (project_id, defect_type, project_part, risk_level,
                                 rectification_plan, reporter_name, reporter_department,
                                 image_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, defect_type, "东立面三层 1# 立柱", level, "更换密封胶",
             "Zeyu Jin", "结构工程部", image_path, created_at),
        ).lastrowid


def insert_project(project_no="JCZG-2026-001", house_name="金骐智谷") -> int:
    with db.transaction() as conn:
        return conn.execute(
            "INSERT INTO projects (project_no, house_name) VALUES (?, ?)",
            (project_no, house_name),
        ).lastrowid


def stat_values(html: str) -> list:
    """页面顶部统计条上的四个数字，顺序为 全部 / 高 / 中 / 低。"""
    return [int(value) for value in re.findall(r'stat-value">(\d+)<', html)]


def card_count(html: str) -> int:
    return html.count('class="report-card"')


# --------------------------------------------------------------------------
# 列表与统计
# --------------------------------------------------------------------------
def test_empty_state_and_zero_stats(client):
    html = client.get("/reports/").get_data(as_text=True)
    assert "还没有报告" in html
    assert stat_values(html) == [0, 0, 0, 0]
    # COALESCE 存在的意义：空表时 SUM(...) 是 NULL，页面会写成「None」
    assert "None" not in html


def test_stats_on_empty_table_returns_zeros(ctx):
    assert defect_service.stats() == {"total": 0, "high": 0, "medium": 0, "low": 0}


def test_stats_counts_by_level(ctx):
    for level in ("高", "高", "中", "低", "低", "低"):
        insert_report(level=level)

    assert defect_service.stats() == {"total": 6, "high": 2, "medium": 1, "low": 3}


def test_list_is_sorted_by_created_at_desc(ctx, client):
    insert_report(defect_type="最早", created_at="2026-09-20 09:00:00")
    insert_report(defect_type="居中", created_at="2026-09-22 10:00:00")
    insert_report(defect_type="最新", created_at="2026-09-25 18:30:00")

    html = client.get("/reports/").get_data(as_text=True)
    assert html.index("最新") < html.index("居中") < html.index("最早")


def test_list_tie_breaks_same_second_by_id_desc(ctx, client):
    """同一秒内的多条报告：按 id 倒序，后录的在前（否则顺序不确定）。"""
    insert_report(defect_type="先录", created_at="2026-09-22 10:00:00")
    insert_report(defect_type="后录", created_at="2026-09-22 10:00:00")

    html = client.get("/reports/").get_data(as_text=True)
    assert html.index("后录") < html.index("先录")


def test_filter_by_risk_level(ctx, client):
    insert_report(level="高", defect_type="高风险项")
    insert_report(level="中", defect_type="中风险项")
    insert_report(level="低", defect_type="低风险项")

    html = client.get("/reports/?level=高").get_data(as_text=True)
    assert card_count(html) == 1
    assert "高风险项" in html and "中风险项" not in html


def test_stats_are_not_affected_by_filter(ctx, client):
    """需求 3.4b 的顶部统计与 3.4c 的筛选是两件事：统计恒为全量。"""
    insert_report(level="高")
    insert_report(level="高")
    insert_report(level="中")

    html = client.get("/reports/?level=高").get_data(as_text=True)
    assert card_count(html) == 2                       # 列表只剩高
    assert stat_values(html) == [3, 2, 1, 0]           # 统计仍是全量


def test_invalid_filter_shows_all_with_warning(ctx, client):
    """非法等级值不报 400，按"不筛选"处理但给出提示（不静默吞掉）。"""
    insert_report(level="高")
    insert_report(level="低")

    response = client.get("/reports/?level=紧急")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert card_count(html) == 2
    assert "未知的筛选值" in html


def test_filter_with_no_match_offers_reset(ctx, client):
    insert_report(level="低")
    html = client.get("/reports/?level=高").get_data(as_text=True)
    assert "没有「高」等级的报告" in html
    assert 'href="/reports/"' in html                  # 一键回到全部


def test_list_shows_thumbnail_project_and_time(ctx, client, make_image, app):
    project_id = insert_project()
    post_report(client, make_image, project_id=str(project_id))

    html = client.get("/reports/").get_data(as_text=True)
    assert "密封胶开裂" in html                          # 缺陷类型
    assert "东立面三层 1# 立柱" in html                   # 工程部位
    assert "金骐智谷（JCZG-2026-001）" in html           # 绑定项目
    assert config.RISK_BADGE_CLASSES["中"] in html       # 等级徽标
    assert "/thumbnail" in html                          # 缩略图
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", html)   # 时间


def test_list_shows_placeholder_when_image_file_missing(ctx, client, app, make_image):
    """入库有路径但文件已不在 → 渲染占位块，而不是让浏览器显示碎图。"""
    report_id = post_report(client, make_image)
    stored = defect_service.get(report_id)["image_path"]
    images.absolute_path(stored).unlink()

    html = client.get("/reports/").get_data(as_text=True)
    assert "无图" in html
    assert "/thumbnail" not in html


def test_list_handles_unbound_report(ctx, client):
    """未绑定项目（project_id 为空）不能因 LEFT JOIN 缺列而渲染失败。"""
    insert_report(project_id=None)
    response = client.get("/reports/")
    assert response.status_code == 200
    assert "密封胶开裂" in response.get_data(as_text=True)


# --------------------------------------------------------------------------
# 详情
# --------------------------------------------------------------------------
def test_detail_shows_all_fields_and_image(ctx, client, make_image):
    project_id = insert_project()
    report_id = post_report(client, make_image, project_id=str(project_id),
                            related_standards="《建筑幕墙》GB/T 21086-2007",
                            extra_advice="建议雨季前复检")

    html = client.get("/reports/%d" % report_id).get_data(as_text=True)
    assert "缺陷报告 #%d" % report_id in html
    assert "密封胶开裂" in html
    assert "东立面三层 1# 立柱" in html
    assert "《建筑幕墙》GB/T 21086-2007" in html
    assert "建议雨季前复检" in html
    assert "Zeyu Jin" in html
    assert "金骐智谷（JCZG-2026-001）" in html
    assert "/reports/%d/image" % report_id in html       # 大图
    assert "缺陷照片.png" in html                        # 原文件名可追溯


def test_detail_placeholder_when_no_image(ctx, client):
    """没有图片的报告（服务层直接入库）也要能打开详情。"""
    report_id = insert_report(image_path=None)
    response = client.get("/reports/%d" % report_id)
    assert response.status_code == 200
    assert "这份报告没有隐患图片" in response.get_data(as_text=True)


def test_detail_placeholder_when_file_missing(ctx, client, make_image):
    report_id = post_report(client, make_image)
    images.absolute_path(defect_service.get(report_id)["image_path"]).unlink()

    html = client.get("/reports/%d" % report_id).get_data(as_text=True)
    assert "图片文件缺失" in html


def test_detail_404_for_unknown_id(client):
    assert client.get("/reports/999").status_code == 404


# --------------------------------------------------------------------------
# 缩略图与原图
# --------------------------------------------------------------------------
def test_thumbnail_returns_immutable_jpeg(client, make_image):
    report_id = post_report(client, make_image)

    response = client.get("/reports/%d/thumbnail" % report_id)
    assert response.status_code == 200
    assert response.content_type == "image/jpeg"
    # 落盘名含 uuid 且系统没有"改图"路径 → 同一 URL 的字节永不变化，可以放心 immutable
    assert "immutable" in response.headers["Cache-Control"]
    assert response.data[:2] == b"\xff\xd8"             # JPEG SOI


def test_image_returns_original(client, make_image):
    report_id = post_report(client, make_image)
    response = client.get("/reports/%d/image" % report_id)
    assert response.status_code == 200
    assert response.data[:8] == b"\x89PNG\r\n\x1a\n"    # 原图是 PNG，未经改动


def test_thumbnail_404_without_image(ctx, client):
    report_id = insert_report(image_path=None)
    assert client.get("/reports/%d/thumbnail" % report_id).status_code == 404
    assert client.get("/reports/%d/image" % report_id).status_code == 404


def test_thumbnail_404_when_file_missing(ctx, client, make_image):
    report_id = post_report(client, make_image)
    images.absolute_path(defect_service.get(report_id)["image_path"]).unlink()
    assert client.get("/reports/%d/thumbnail" % report_id).status_code == 404


def test_thumbnail_404_for_unknown_id(client):
    assert client.get("/reports/999/thumbnail").status_code == 404


# --------------------------------------------------------------------------
# 删除
# --------------------------------------------------------------------------
def test_delete_removes_report_and_image_file(ctx, client, make_image):
    report_id = post_report(client, make_image)
    path = images.absolute_path(defect_service.get(report_id)["image_path"])
    assert path.exists()

    response = client.post("/reports/%d/delete" % report_id)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/reports/")

    assert defect_service.get(report_id) is None
    assert not path.exists()                            # 图片一并删除，不留孤儿

    html = client.get("/reports/").get_data(as_text=True)
    assert defect_service.stats()["total"] == 0
    assert "报告已删除" in html                          # flash 反馈


def test_delete_tolerates_missing_file(ctx, client, make_image):
    """图片文件已被手工删掉时，删除报告仍然成功（remove() 吞掉缺失错误）。"""
    report_id = post_report(client, make_image)
    images.absolute_path(defect_service.get(report_id)["image_path"]).unlink()

    assert client.post("/reports/%d/delete" % report_id).status_code == 302
    assert defect_service.get(report_id) is None


def test_delete_report_without_image(ctx, client):
    report_id = insert_report(image_path=None)
    assert client.post("/reports/%d/delete" % report_id).status_code == 302
    assert defect_service.get(report_id) is None


def test_delete_404_for_unknown_id(client):
    assert client.post("/reports/999/delete").status_code == 404


def test_delete_unlinks_from_project(ctx, client, make_image):
    """需求 3.4e：删除已绑定项目的报告后，关联自动解除（项目侧不再出现它）。"""
    project_id = insert_project()
    report_id = post_report(client, make_image, project_id=str(project_id))
    assert "密封胶开裂" in client.get("/projects/%d" % project_id).get_data(as_text=True)

    client.post("/reports/%d/delete" % report_id)

    html = client.get("/projects/%d" % project_id).get_data(as_text=True)
    assert "暂无关联报告" in html
    assert defect_service.list_for_project(project_id) == []


def test_delete_only_removes_the_target_report(ctx, client, make_image):
    keep_id = post_report(client, make_image)
    drop_id = post_report(client, make_image)
    keep_path = images.absolute_path(defect_service.get(keep_id)["image_path"])

    client.post("/reports/%d/delete" % drop_id)

    assert defect_service.get(keep_id) is not None
    assert keep_path.exists()                           # 别人的图片不能被误删


# --------------------------------------------------------------------------
# 路由边界：需求 3.3（填报）与 3.4（报告管理）的切分
# --------------------------------------------------------------------------
def test_legacy_defects_detail_redirects_permanently(ctx, client):
    report_id = insert_report()
    response = client.get("/defects/%d" % report_id)
    assert response.status_code == 308
    assert response.headers["Location"].endswith("/reports/%d" % report_id)


def test_legacy_redirect_still_404_after_following(client):
    """旧链接指向不存在的报告：跟随后是 404，不会静默跳到别处。"""
    response = client.get("/defects/999", follow_redirects=True)
    assert response.status_code == 404


def test_defect_form_still_lives_under_defects(client):
    """填报（需求 3.3）留在 /defects，没有被搬走。"""
    html = client.get("/defects/new").get_data(as_text=True)
    assert "缺陷" in html
    assert client.get("/reports/new").status_code == 404


def test_create_lands_on_report_detail(client, make_image):
    report_id = post_report(client, make_image)
    html = client.get("/reports/%d" % report_id).get_data(as_text=True)
    assert "报告已保存" in html                          # 创建后的 flash 反馈
    assert "缺陷报告 #%d" % report_id in html


def test_nav_exposes_report_management(client):
    html = client.get("/").get_data(as_text=True)
    assert "报告管理" in html
    assert 'href="/reports/"' in html


# --------------------------------------------------------------------------
# 视图装配（M4 的 UI 交接面，见设计文档第 6.1 节）
# --------------------------------------------------------------------------
def test_card_view_is_pure_and_complete(ctx, client, make_image, app):
    """_card() 是模板与将来 JS 渲染器共用的数据形状，字段不能少。"""
    from webapp.routes.reports import _card

    project_id = insert_project()
    report_id = post_report(client, make_image, project_id=str(project_id))
    # _card 里会拼 URL，需要请求上下文（路由里天然有，单测要自己开一个）
    with app.test_request_context():
        card = _card(defect_service.get_with_project(report_id))

    assert set(card) == {"id", "defect_type", "project_part", "risk_level", "badge_class",
                         "created_at_text", "project_label", "has_image",
                         "thumbnail_url", "detail_url"}
    assert card["badge_class"] == config.RISK_BADGE_CLASSES["中"]
    assert card["project_label"] == "金骐智谷（JCZG-2026-001）"
    assert card["has_image"] is True
    assert card["created_at_text"].count(":") == 1       # yyyy-MM-dd HH:mm，不带秒


def test_card_view_for_unbound_report_without_image(ctx, app):
    from webapp.routes.reports import _card

    report_id = insert_report(image_path=None)
    with app.test_request_context():
        card = _card(defect_service.get_with_project(report_id))

    assert card["project_label"] == ""
    assert card["has_image"] is False


def test_cards_are_reused_by_list_and_detail(client, make_image):
    """列表与详情用的是同一个 _card()，两处徽标类名必须一致。"""
    report_id = post_report(client, make_image, risk_level="高")
    marker = 'badge %s' % config.RISK_BADGE_CLASSES["高"]

    assert marker in client.get("/reports/").get_data(as_text=True)
    assert marker in client.get("/reports/%d" % report_id).get_data(as_text=True)
