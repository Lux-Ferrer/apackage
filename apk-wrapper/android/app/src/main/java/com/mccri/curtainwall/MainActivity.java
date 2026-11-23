package com.mccri.curtainwall;

import android.os.Bundle;
import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * APK 壳的原生代码，只有两件事：
 *
 * 1. **注册本地插件** `DownloadSaver`（把导出文件写进「下载/幕墙检测/」）。
 *    Capacitor 只自动注册 node_modules 里的插件，本地插件必须在 `super.onCreate()`
 *    之前 `registerPlugin(...)` —— 那时 bridgeBuilder 还没 build 出 bridge。
 *
 * 2. **接管返回键**：先判断当前是不是根路由（`#/projects`、`#/reports`、`#/me`）。
 *    根路由直接退出 App（不再回退历史）；其他页面回退一步。
 *    不然用户从「项目详情」一路点 tab 之后，在首页按返回会先回退到一堆历史页面里，
 *    看起来像"返回键没反应"。
 *
 * 为什么返回键不放在 JS 里监听 `backButton`：我们的 www/ 是免打包静态站，
 * 拿不到 `@capacitor/app` 的 JS 代理（原生注入的 bridge 没有 registerPlugin）。
 * 返回键本来就是 Android 生命周期的事，写在这里最短也最稳。
 */
public class MainActivity extends BridgeActivity {

    /** 底部三个 tab 的根路由（写在这里而不是从 JS 读，避免返回键处理依赖 WebView 求值）。 */
    private static final Set<String> ROOT_ROUTES =
            new HashSet<>(Arrays.asList("/projects", "/reports", "/me"));

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(DownloadSaverPlugin.class);
        super.onCreate(savedInstanceState);
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (webView != null && webView.canGoBack() && !isAtRootRoute(webView.getUrl())) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    /** `https://localhost/#/projects` → true；`https://localhost/#/projects/1` → false。 */
    private boolean isAtRootRoute(String url) {
        if (url == null) {
            return true;
        }
        int hash = url.indexOf('#');
        if (hash < 0) {
            return true;
        }
        String route = url.substring(hash + 1);
        int query = route.indexOf('?');
        if (query >= 0) {
            route = route.substring(0, query);
        }
        while (route.length() > 1 && route.endsWith("/")) {
            route = route.substring(0, route.length() - 1);
        }
        return ROOT_ROUTES.contains(route);
    }
}
