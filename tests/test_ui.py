# -*- coding: utf-8 -*-
"""UI 层契约测试：底部 Tab、表单页操作条、横向表格布局、卡片列表、我的页。

这些断言锁的是**标记与结构契约**（docs/management/UI-设计.md 第 5.2 节）：
UI 改造允许换容器，但 id / name / class 与"哪个元素必须包住哪个元素"不能悄悄变，
否则 `record_form.js`、`defects_form.js` 和 CSS 会一起失效而测试却还是绿的。
"""

from __future__ import annotations

import io

from webapp import db
from webapp.services import defects as defect_service
from webapp.services import images

FORM = {
    "defect_type": "密封胶开裂",
    "project_part": "东立面三层 1# 立柱",
    "risk_level": "中",
    "rectification_plan": "更换密封胶",
}


def _project(client, project_no="JCZG-2026-001", house_name="金骐智谷"):
    client.post("/projects/", data={"project_no": project_no, "house_name": house_name})
    return 1


def _defect(client, make_image, **overrides):
    payload = dict(FORM)
    payload.update(overrides)
    payload.setdefault("image", make_image(filename="缺陷照片.png"))
    response = client.post("/defects/", data=payload, content_type="multipart/form-data")
    assert response.status_code == 302, response.get_data(as_text=True)
    return int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


# --------------------------------------------------------------------------
# 落地页与 Tab 导航
# --------------------------------------------------------------------------
def test_landing_is_the_projects_tab(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/projects/")


def test_tabs_show_on_browse_pages_and_highlight(client):
    for path, label in (("/projects/", "项目"), ("/reports/", "报告"), ("/me/", "我的")):
        html = client.get(path).get_data(as_text=True)
        assert 'class="tabbar"' in html, path
        assert "nav-item active" in html, path
        assert label in html, path


def test_tabs_hidden_on_form_pages_but_action_bar_present(client, ctx):
    """表单页隐藏 Tab，改用固定的底部操作条（保存必须落在拇指可达处）。"""
    _project(client)
    for path in ("/defects/new", "/projects/new", "/projects/1/edit",
                 "/projects/1/records/new?template=column"):
        html = client.get(path).get_data(as_text=True)
        assert 'class="tabbar"' not in html, path
        assert 'class="action-bar"' in html, path


def test_desktop_topnav_is_rendered_too(client):
    """同一个 partial 渲染两处：顶栏导航（桌面）+ 底部 Tab（移动端）。"""
    html = client.get("/projects/").get_data(as_text=True)
    assert 'class="topnav"' in html
    assert 'class="tabbar"' in html


def test_active_tab_mapping_follows_requirement_modules(client):
    """检测记录归「项目」、缺陷填报归「报告」（UI 设计 1.2）。"""
    from webapp import config

    assert config.TAB_BY_ENDPOINT_PREFIX["records"] == "projects"
    assert config.TAB_BY_ENDPOINT_PREFIX["defects"] == "reports"

    _project(client)
    html = client.get("/projects/1/records/new?template=column").get_data(as_text=True)
    assert 'href="/projects/"' in html


# --------------------------------------------------------------------------
# 横向表格布局
# --------------------------------------------------------------------------
def test_record_form_uses_horizontal_table_layout(client, ctx):
    """构件信息：label 左 / 控件右的两列网格，桌面复用同一 DOM。"""
    _project(client)
    html = client.get("/projects/1/records/new?template=column").get_data(as_text=True)

    assert 'class="form-table"' in html
    assert 'class="form-row"' in html
    # label 必须在 .form-control 之前（网格的第一列）
    assert html.index('for="floor"') < html.index('id="floor"')
    assert 'class="form-control"' in html
    # 旧的三列 flex 布局不该再出现
    assert 'class="field-row"' not in html


def test_defect_form_uses_horizontal_layout_and_segmented_level(client):
    """需求 3.3.2：隐患等级为"三选一按钮"。"""
    html = client.get("/defects/new").get_data(as_text=True)

    assert 'class="form-table"' in html
    assert 'class="segmented"' in html
    for level in ("高", "中", "低"):
        assert 'name="risk_level" value="%s"' % level in html
    # 默认选中「中」
    assert html.count('name="risk_level"') == 3
    assert 'value="中"\n                                   checked' in html or 'value="中" ' in html


def test_custom_defect_type_input_is_collapsed_by_default(client):
    """自定义类型输入框默认收起，由 JS 在选中「其他」时展开。"""
    html = client.get("/defects/new").get_data(as_text=True)
    assert 'id="custom_defect_type"' in html
    assert "hidden-row" in html


# --------------------------------------------------------------------------
# 卡片列表（统一布局，桌面也只是变宽）
# --------------------------------------------------------------------------
def test_project_list_is_cards_not_a_table(client, ctx):
    _project(client)
    html = client.get("/projects/").get_data(as_text=True)

    assert 'class="report-list project-list"' in html
    assert "金骐智谷" in html and "JCZG-2026-001" in html
    assert "立柱 0 · 横梁 0" in html
    assert "<table" not in html
    assert 'data-confirm=' in html                       # 删除仍有二次确认


def test_report_list_is_cards(client, make_image):
    _defect(client, make_image)
    html = client.get("/reports/").get_data(as_text=True)
    assert 'class="report-card"' in html
    assert "密封胶开裂" in html


def test_project_detail_keeps_edit_actions_inside_the_expanded_body(client, ctx):
    """编辑/删除移到展开区：summary 里的链接命中区太小，且与展开点击冲突。"""
    _project(client)
    client.post("/projects/1/records/?template=column", data={
        "floor": "六层", "member_position": "1", "face_0": "B", "value_0_1": "2.99",
    })
    html = client.get("/projects/1").get_data(as_text=True)

    summary = html[html.index("<summary>"):html.index("</summary>")]
    assert "/records/1/edit" not in summary               # summary 里不再有操作链接
    assert 'class="record-actions-bar"' in html           # 移到了展开区
    assert 'class="table-scroll"' in html                 # 明细表可横向滚动


# --------------------------------------------------------------------------
# 「我的」（需求 3.7）
# --------------------------------------------------------------------------
def test_me_page_shows_reporter_and_overview(client, ctx):
    _project(client)
    html = client.get("/me/").get_data(as_text=True)

    assert "Zeyu Jin" in html
    assert "结构工程部" in html
    assert "数据概览" in html
    assert "清除全部报告" not in html                      # 没有报告时不给破坏性入口
    assert "没有可清除的报告" in html
    assert "模块进度与范围说明" in html                     # 通向 /about


def test_me_page_hides_employee_no_when_empty(client):
    """需求 3.7a：工号"有则显示"，配置为空时不应出现空行。"""
    from webapp import config

    assert config.DEFAULT_REPORTER["employee_no"] == ""
    html = client.get("/me/").get_data(as_text=True)
    assert "工号" not in html


def test_overview_counts(client, ctx, make_image):
    from webapp.routes.me import overview

    _project(client)
    client.post("/projects/1/records/?template=column", data={
        "floor": "六层", "member_position": "1", "face_0": "B", "value_0_1": "2.99",
    })
    _defect(client, make_image)

    assert overview() == {"projects": 1, "records": 1, "reports": 1}

    html = client.get("/me/").get_data(as_text=True)
    assert "1</span>" in html                              # 概览数字渲染出来


def test_clear_all_reports_removes_rows_and_images(client, ctx, make_image):
    """需求 3.7c：清除全部报告；隐患图片一并删除，条数如实回显。"""
    first = _defect(client, make_image)
    second = _defect(client, make_image)
    paths = [images.absolute_path(defect_service.get(i)["image_path"])
             for i in (first, second)]
    assert all(p.exists() for p in paths)

    response = client.post("/me/reports/clear")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/me/")

    assert defect_service.stats()["total"] == 0
    assert all(not p.exists() for p in paths)              # 图片不再留孤儿

    html = client.get("/me/").get_data(as_text=True)
    assert "已清除全部报告：2 份" in html                    # flash 如实回显
    assert "报告与项目的关联同时消失" in html or "没有可清除的报告" in html


def test_clear_all_reports_keeps_projects(client, ctx, make_image):
    """清除报告不能连项目一起删掉（两张表互不级联删除）。"""
    _project(client)
    _defect(client, make_image, project_id="1")

    client.post("/me/reports/clear")

    assert db.query_one("SELECT COUNT(*) AS c FROM projects")["c"] == 1
    assert db.query_one("SELECT COUNT(*) AS c FROM measurement_records")["c"] == 0


def test_clear_all_reports_on_empty_database_is_safe(client, ctx):
    response = client.post("/me/reports/clear")
    assert response.status_code == 302
    assert "没有可清除的报告" in client.get("/me/").get_data(as_text=True)


def test_clear_reports_requires_post(client):
    """破坏性操作不接受 GET（避免被预取/爬虫误触发）。"""
    assert client.get("/me/reports/clear").status_code == 405


# --------------------------------------------------------------------------
# 关于页
# --------------------------------------------------------------------------
def test_about_page_has_no_stale_todo_text(client):
    """/about 是演示时会被看到的地方：已完成的里程碑不能还挂着「待开发」。"""
    html = client.get("/about").get_data(as_text=True)
    assert "模块进度" in html
    assert "待开发" not in html
    assert "报告管理" in html and "M4" in html
    assert "移动端界面" in html
