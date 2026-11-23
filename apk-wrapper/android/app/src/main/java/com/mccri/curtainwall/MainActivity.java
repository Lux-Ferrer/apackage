package com.mccri.curtainwall;

import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;

/**
 * APK 壳的唯一一段原生代码：接管"返回键"。
 *
 * 为什么不用 JS 的 backButton 监听（@capacitor/app）：
 * 我们的 www/ 是**免打包**的静态站（没有 bundler 去解析 `@capacitor/app`），
 * 而 `Capacitor.registerPlugin` 并不在原生注入的 bridge 里 —— 也就是说 JS 侧
 * 拿不到那个插件代理。返回键是纯 Android 生命周期的事，放在这里最稳，也最短。
 *
 * 行为（与浏览器里按"后退"一致）：
 *   WebView 里还有历史 → 后退（hash 变化会触发页面的 hashchange，路由自然重绘）；
 *   已经在第一页    → 走系统默认（退出 App）。
 */
public class MainActivity extends BridgeActivity {

    @Override
    public void onBackPressed() {
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }
}
