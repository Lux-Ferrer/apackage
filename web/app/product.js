/* 产品身份与出厂默认值 —— **交付版只需要改这一个文件**。
 *
 * 为什么单独一个文件，而不是塞进 `config.js`
 * ------------------------------------------
 * `web/app/config.js` 是 `tools/export_web_assets.py` 从 `webapp/config.py` 生成的
 * （那是参考实现 Flask 版的业务配置，作为对拍基准被冻住了，不该再动）。
 * 产品名称、版本号、出品方属于"这一版怎么交付"，与业务规则无关，所以放在手写文件里，
 * 重新生成资产时也不会被覆盖。
 *
 * 客户（或部署人员）要改的东西
 * ----------------------------
 *   1. 默认报告人：改下面 `DEFAULT_PROFILE` 的两行 —— 或者不改，直接在 app 里
 *      「我的 → 个人信息配置」里填一次（保存在本机 IndexedDB，改一次就够）。
 *      **两者优先级：界面里保存过的 > 这里的出厂默认值。**
 *   2. 版本号：改 `PRODUCT.version`（它与交付包文件名 `mcc-inspection-tool-v<版本>.zip`
 *      一致；`tools/make_release_zip.py` 会读这个字段来命名压缩包）。
 *   3. 出品方 / 技术支持：改 `PRODUCT.vendor` / `PRODUCT.support`。
 *
 * ⚠️ 改完必须重新生成离线清单（版本号会变，Service Worker 才会更新）：
 *      python tools/export_web_assets.py
 *   然后把「我的 → 关于」里的「离线缓存版本」与上一版比一眼 —— 变了才算生效。
 *
 * 版本历史
 * --------
 *   1.0.0  首个交付包（真机验收当场暴露 3 个 P0：boot 崩溃 / 导出 nodebuffer / 备份导入失效）
 *   1.0.1  两轮真实浏览器 + 安卓模拟器验证后的交付版：
 *          · 修复「导入备份」必然失败（`zip.files` 被当数组用）
 *          · 修复软键盘弹起时「保存」被键盘挡住（visualViewport → `--keyboard-inset`）
 *          · 操作条「取消」触控区 28×22 → 44×44
 *          · 交付包不再打包测试资产（`web/e2e`）
 *   1.0.2  APK 体验补丁（Web 端同步受益）：
 *          · 导出/备份在壳里改走本地插件 DownloadSaver → 写「下载/幕墙检测/」，
 *            没有可打开 .docx 的应用时弹 Toast 告知路径（不再只剩空分享面板）
 *          · 返回键在根路由（项目/报告/我的）直接退出 App，不再在历史里绕
 */

export const PRODUCT = Object.freeze({
    /** 产品名（界面顶栏、关于页、安装到主屏后的名称都用它） */
    name: '建筑幕墙检测报告工具',
    /** 英文名（安装到主屏时部分系统会用它） */
    name_en: 'Curtain Wall Inspection Report Tool',
    /** 版本号：不带 "v" 前缀，界面统一显示成 v1.0.2 */
    version: '1.0.2',
    /** 出品方 */
    vendor: '中冶建筑研究总院（深圳）有限公司',
    /** 技术支持（可留空：留空时关于页不显示这一行） */
    support: '',
});

/**
 * 出厂默认的报告人 / 部门。
 *
 * 只影响**还没在界面里保存过**的情况；用户保存过之后以 IndexedDB 里的为准。
 * 已经保存过的历史报告里存的是当时的快照，**不会**被这里改动。
 */
export const DEFAULT_PROFILE = Object.freeze({
    reporter_name: '检测员',
    reporter_department: '检测部',
});

/** 个人信息字段的长度上限（与表单 maxlength、服务端校验同一处定义）。 */
export const PROFILE_LIMITS = Object.freeze({
    reporter_name: 20,
    reporter_department: 30,
});

/** 界面上的版本标签：`v1.0.2`。 */
export function versionLabel() {
    return `v${PRODUCT.version}`;
}

/** 「姓名（部门）」—— 报告人字段在界面与 Word 里的统一写法。 */
export function profileLabel(profile) {
    const name = profile?.reporter_name || DEFAULT_PROFILE.reporter_name;
    const department = profile?.reporter_department || DEFAULT_PROFILE.reporter_department;
    return `${name}（${department}）`;
}

export default PRODUCT;
