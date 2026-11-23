# 本地 / 云端 APK 打包指南

> 目标：把**纯前端交付包 v1.0.1** 装进一个 Capacitor 壳，产出可分发的 `.apk`。
> 本文档对应 `D:\project\Capstone\apk-wrapper\`，编写时本机环境是 **Windows + 无 JDK / 无 Android SDK**。
>
> **两条路，任选**：
> - **云端（推荐，零安装）**：推到 GitHub → Actions → `Build Android APK` → Run workflow → 下载 Artifact。见 §9。
> - **本地**：装 JDK 21 + Android SDK 后 `gradlew assembleDebug`。见 §1–§5。

---

## 0. 现在的状态：壳与原生适配都已完成，只差构建环境

已经做完（都不需要 Java）：

| 项 | 状态 |
| --- | --- |
| `apk-wrapper/` 独立隔离区（不碰 `web/` 源码） | ✅ 已建，`npm init` + 依赖已装 |
| Capacitor 版本 | ✅ **8.6.2**（core / cli / android）；插件 `@capacitor/filesystem` 8.1.5、`@capacitor/share` 8.0.3 |
| `capacitor.config.json` | ✅ `appId=com.mccri.curtainwall`、`appName=幕墙检测`、`webDir=www` |
| Web 资源 | ✅ `www/` = 交付包解压（53 个文件，`VERSION.txt` 里是 v1.0.2），由 `scripts/prepare-www.py` 从 `dist/*.zip` 生成并校验版本 |
| Android 工程 | ✅ `npx cap add android` **成功**，已生成 `apk-wrapper/android/` |
| 图标 | ✅ 已替换成产品的 PWA 图标（含自适应图标，避开了 Capacitor 默认 logo） |
| 启动图 | ✅ 11 张 splash 已换成品牌蓝 + 居中图标（原先是 Capacitor 默认画面） |
| 本地原生插件 | ✅ `DownloadSaverPlugin.java`：用 MediaStore 写「下载/幕墙检测/」，无接收方时弹 Toast（见 §6.1） |
| 版本号 | ✅ `versionName "1.0.2"`、`versionCode 2` |
| **原生适配（导出/返回键/SW）** | ✅ **已实现**，见 §6；Web 端 250 项前端测试 + 21 项 E2E 全绿，行为未变 |
| 云端出包 | ✅ `.github/workflows/build-android.yml`（手动触发 → 下载 APK，见 §9） |
| `npx cap sync android` | ✅ 通过（资源已拷进 `android/app/src/main/assets/public`） |
| `npx cap doctor` | ✅ `Android looking great` |

**本地构建唯一的缺项**是 JDK（以及编 APK 要用的 Android SDK）。现在直接构建会停在：

```
ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
```

> 只想拿 APK、不想装环境 → 直接跳到 **§9 云端出包**。

（`gradlew.bat assembleDebug`，退出码 9009。按约定**没有**去下载 SDK。）

---

## 1. 需要装什么（版本是这份工程实测要求，不是猜的）

工程里的硬性参数（读自 `android/variables.gradle` / `android/gradle/wrapper/...`）：

| 参数 | 值 | 说明 |
| --- | --- | --- |
| compileSdk / targetSdk | **36**（Android 16） | Capacitor 8 默认 |
| minSdk | 24（Android 7.0） | 现场手机基本都满足 |
| Gradle | **8.14.3** | 由 wrapper 自动下载，不用手装 |
| Android Gradle Plugin | **8.13.0** | 由 Gradle 拉取 |
| 需要的 JDK | **JDK 21（LTS）** | Capacitor 8 要求 21；AGP 8.13 的官方下限是 17，装 21 一劳永逸 |

### 装这些

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| **JDK** | **21 LTS**（Eclipse Temurin 21 或 Microsoft Build of OpenJDK 21） | ⚠️ 不要用 JDK 25/26（Gradle 8.14 不支持），也不要 8/11 |
| **Android Studio** | **最新稳定版**（2025.1 Narwhal 系列或更新） | 判断标准只有一条：它的 SDK Manager 能装到 **Android 16 (API 36)** |
| Android SDK Platform | **Android 16 (API 36)** | `platforms;android-36` |
| Android SDK Build-Tools | **36.0.0** | `build-tools;36.0.0` |
| Android SDK Platform-Tools | 最新 | 提供 `adb` |
| Android SDK Command-line Tools | 最新 | 提供 `sdkmanager`（命令行路线必需） |

> **不想装 Android Studio？** 可以，只装 **JDK 21 + command-line tools**（省约 1.5 GB，但没有图形界面）：
> ```powershell
> # 解压到 C:\Android\cmdline-tools\latest
> sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0"
> ```
>
> **只能用旧版 Android Studio（装不到 API 36）？** 把 `android/variables.gradle` 里
> `compileSdkVersion` / `targetSdkVersion` 从 36 改成 **35**，装 `platforms;android-35` + `build-tools;35.0.0` 即可。
> 功能不受影响，只是没吃到 Android 16 的新行为适配。

磁盘与网络预估：Studio ≈ 1.5 GB，SDK 平台 + build-tools ≈ 1.2 GB，**首次构建**还要下 Gradle 8.14.3 与 AGP 依赖 ≈ 1 GB。

---

## 2. 装完后的环境变量（Windows）

用 Android Studio 装的话，JDK 已随 Studio 自带（`...\Android Studio\jbr`），但**命令行构建仍建议单独装一个 JDK 21**，避免 Studio 升级把构建搞挂。

```powershell
# 1) 查实际路径后改成你的
$jdk    = "C:\Program Files\Eclipse Adoptium\jdk-21.0.5.11-hotspot"
$sdk    = "$env:LOCALAPPDATA\Android\Sdk"

# 2) 写入用户环境变量（开新终端才生效）
setx JAVA_HOME   "$jdk"
setx ANDROID_HOME "$sdk"
setx ANDROID_SDK_ROOT "$sdk"
setx PATH "$env:PATH;$jdk\bin;$sdk\platform-tools;$sdk\cmdline-tools\latest\bin"
```

验证三行（**必须是新开的终端**）：

```powershell
java -version                     # 期望 21.x
adb version                       # 期望有输出
sdkmanager --list | Select-String "build-tools;36"
```

在 Android Studio 里装 SDK 包：**More Actions → SDK Manager → SDK Platforms** 勾 *Android 16 (API 36)*；
**SDK Tools** 勾 *Android SDK Build-Tools 36*、*Android SDK Platform-Tools*、*Android SDK Command-line Tools*。

---

## 3. 出包（三条命令）

```powershell
cd D:\project\Capstone\apk-wrapper

# ① 把交付包解成 www，并同步进 Android 工程（不需要 Java）
npm run sync

# ② 编 debug 包（首次会下载 Gradle 与依赖，5~15 分钟）
cd android
.\gradlew.bat assembleDebug
```

产物：

```
apk-wrapper\android\app\build\outputs\apk\debug\app-debug.apk
```

也可以直接用脚本（等价于上面两步）：

```powershell
npm run apk:debug
```

换了图标/启动图/版本号之后，记得各自重跑一次（都不需要 Java）：

```powershell
npm run icons     # 图标 → mipmap-*（含自适应图标前景）
npm run splash    # 启动图 → drawable*/splash.png（品牌蓝 + 居中图标）
```

**release（正式分发）**：

```powershell
cd apk-wrapper\android
.\gradlew.bat assembleRelease
# → app\build\outputs\apk\release\app-release-unsigned.apk（未签名，见 §5）
```

常见小坑：

- 报 `SDK location not found` → 在 `apk-wrapper\android\local.properties` 里写一行
  `sdk.dir=C\:\\Users\\<你>\\AppData\\Local\\Android\\Sdk`（Studio 打开工程时会自动生成）。
- 首次构建卡在 `Downloading https://services.gradle.org/...` → 网络问题，配代理或用镜像（见 §7）。
- 每次改了 `web/` 的代码，**先 `python tools/make_release_zip.py` 重新出包**，再 `npm run sync`——
  `www/` 的来源永远是 `dist/*.zip`，不是源码目录（这样 APK 里的东西和你交付给客户的一模一样）。

---

## 4. 装到手机 / 模拟器上验证

```powershell
adb devices
adb install -r android\app\build\outputs\apk\debug\app-debug.apk
```

用 MuMu 模拟器（本机已验证过的路径）：

```powershell
D:\MuMuPlayer-12.0\MuMuPlayer\nx_main\adb.exe -s 127.0.0.1:16416 install -r `
  D:\project\Capstone\apk-wrapper\android\app\build\outputs\apk\debug\app-debug.apk
```

**装完先跑这 6 条**（这是 APK 与浏览器版最容易不一样的地方）：

| # | 检查 | 期望 |
| --- | --- | --- |
| 1 | 建项目 → 录一条记录（5 个读数） | 最小值自动算出 |
| 2 | 缺陷填报 → 拍照 | 能调起相机并回填缩略图 |
| 3 | 项目详情 → **导出 Word** | 壳里会写文件并弹分享面板（见 §6.1）；浏览器里仍是直接下载 |
| 4 | 我的 → 导出备份 | ⚠️ 同上（同一个 `downloadBlob` 入口） |
| 5 | 按手机返回键 | ⚠️ 默认会**直接退出 App**（见 §6.2） |
| 6 | 装新版本后再打开 | ⚠️ 可能还是旧界面（见 §6.3） |

调试：`chrome://inspect` 能看到 WebView（`webContentsDebuggingEnabled` 已开）；
控制台里的报错和桌面浏览器一致，看到什么就能查什么。

---

## 5. 正式签名（release）

Debug 包用系统自动生成的 debug keystore，**只能内部测试**。要发给客户必须自己签。

```powershell
# 1) 生成 keystore（有效期 25 年，别丢，丢了就不能升级覆盖安装）
keytool -genkeypair -v -keystore mccri-curtainwall.jks `
  -alias curtainwall -keyalg RSA -keysize 2048 -validity 9125 `
  -dname "CN=MCC Research Institute Shenzhen, OU=Inspection, O=MCC, L=Shenzhen, C=CN"
```

2) 在 `apk-wrapper\android\` 下建 `key.properties`（**不要提交到仓库**，`.gitignore` 已排除）：

```properties
storeFile=../../mccri-curtainwall.jks
storePassword=你的密码
keyAlias=curtainwall
keyPassword=你的密码
```

3) 在 `android/app/build.gradle` 的 `android { }` 内加：

```gradle
def keystoreProperties = new Properties()
def keystoreFile = rootProject.file("key.properties")
if (keystoreFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystoreFile))
}

android {
    // …保持原样…
    signingConfigs {
        release {
            if (keystoreFile.exists()) {
                storeFile file(keystoreProperties['storeFile'])
                storePassword keystoreProperties['storePassword']
                keyAlias keystoreProperties['keyAlias']
                keyPassword keystoreProperties['keyPassword']
            }
        }
    }
    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled false
        }
    }
}
```

4) `.\gradlew.bat assembleRelease` → `app-release.apk`（已签名）。
   或者用 Android Studio：**Build → Generate Signed App Bundle / APK → APK**。

**版本规则**（踩了就装不上）：

- `versionCode` 每次发版 **必须 +1**（当前 2）；
- `versionName` 与 `web/app/product.js` 保持一致（当前都是 **1.0.2**）；
- 升级覆盖安装要求**同一个签名**，否则报 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`（只能先卸载，**数据会没**）；
- `versionCode` 变小 → `INSTALL_FAILED_VERSION_DOWNGRADE`。

---

## 6. 原生适配：已实现（Web 端行为不变）

下面三条是 WebView 与浏览器的差异，跟 JDK 无关。**都已经落地**，并且只在
`window.Capacitor.isNativePlatform()` 为真时生效 —— 浏览器里连分支都进不去，
250 项前端测试与 21 项桌面 E2E 全绿（`web/tests/native_shell.test.mjs` 专门锁这条边界）。

### 6.1 P0：导出的 Word / 备份存不下来 —— 已修（写公共下载目录）

**问题**：导出走 `URL.createObjectURL(blob)` + `<a download>`。Android WebView **不认**
`download` 属性、也不处理 `blob:` 链接，表现为"点了没反应、控制台也不报错"。

**第一版修法（1.0.1）**：写 App 缓存 + `Share` 拉起分享面板。文件是写出来了，但真机验证时发现
**如果设备上没有能打开 .docx 的应用，分享面板是空的**（"没有应用可执行此操作"）—— 用户还是拿不到文件。

**现在的修法（1.0.2）**：新增本地原生插件 `DownloadSaverPlugin.java`：

| 步骤 | 做法 |
| --- | --- |
| 1 | `MediaStore.Downloads` 写入 **`下载/幕墙检测/<文件名>`**（Android 10+ 无需任何存储权限；9 及以下退到 App 专属外部目录） |
| 2 | `ACTION_SEND` + `resolveActivity()`：有接收方 → 弹选择器；**没有 → Toast「文件已保存至 下载/幕墙检测/…」** |
| 3 | 返回 `{ saved, shared, uri, displayPath }`，JS 侧据此给出结果 |

**JS 侧的两级降级**（`web/app/export.js::saveInNativeShell()`）：

1. 有 `DownloadSaver` 插件 → 直接调它（保存 + 分享 + 提示都在原生侧，因为只有
   `intent.resolveActivity()` 能判断"系统里有没有应用能收这个 MIME"）；
2. 插件不存在（1.0.1 的旧壳）**或写下载目录失败** → 回退到 `Filesystem` 缓存 + `Share`，
   并在返回值里带 `fallbackReason`；两条都失败才 `reject`（不假装成功）。

**为什么是本地插件而不是 npm 插件**：`Filesystem` 插件不提供 MediaStore 写入（它只会写
App 私有目录），公共下载目录只能自己用 `MediaStore` 写；插件注册在 `MainActivity.onCreate()`
里 `registerPlugin(DownloadSaverPlugin.class)`（必须在 `super.onCreate()` 之前）。

**调用方也跟着等结果了**：`exportProject()` 与 `me.js` 的备份按钮都会 `await saved.done`。

### 6.2 P1：硬件返回键会直接退出 App —— 已修（在 Java 里，不在 JS 里）

**实现**：`apk-wrapper/android/app/src/main/java/com/mccri/curtainwall/MainActivity.java`

```java
@Override
public void onBackPressed() {
    WebView webView = getBridge() != null ? getBridge().getWebView() : null;
    if (webView != null && webView.canGoBack()) {
        webView.goBack();          // hash 变化 → 页面 hashchange → 路由自然重绘
        return;
    }
    super.onBackPressed();         // 已在第一页 → 退出 App
}
```

**根路由直接退出（1.0.2 加的）**：只看 `canGoBack()` 的话，用户在首页按返回会
在历史里绕（点过几次 tab 就有几步历史），看起来像"返回键没反应"。现在先判断当前 hash：

```java
private static final Set<String> ROOT_ROUTES = Set.of("/projects", "/reports", "/me");
if (webView != null && webView.canGoBack() && !isAtRootRoute(webView.getUrl())) {
    webView.goBack();
    return;
}
super.onBackPressed();          // 根路由 → 退出 App
```

**为什么没按原计划写在 `main.js` 里监听 `backButton`**：那条路要 `@capacitor/app` 的
JS 代理，而我们免打包 → 拿不到代理（见 §6.1 的说明）。返回键本来就是 Android 生命周期
的事，写在这里最短也最稳；
`canGoBack() + goBack()` 复用 WebView 自己的历史，和浏览器里按"后退"一致。

### 6.3 P1：Service Worker 会让"更新后还是旧界面" —— 已修

APK 里的资源是打包进去的，本来不需要 SW；但 `https://localhost` 是安全上下文，
原代码会真的注册并缓存，而缓存**跨 APK 升级保留** → 装了 1.0.2 还显示 1.0.1 的界面。

```js
// web/app/main.js::registerServiceWorker() 第一行
if (globalThis.Capacitor?.isNativePlatform?.()) return null;
```

### 6.4 仍需注意（未改代码，属已知限制）

| # | 事项 | 说明 |
| --- | --- | --- |
| 1 | **相机** | `<input type="file" accept="image/*" capture="environment">`（`views/reports.js`）在 Core 的 `BridgeWebChromeClient` 下会弹"相机 / 文件"选择器，多数机型可用。个别机型调不起相机时再上 `@capacitor/camera`（那时才需要 `CAMERA` 权限与运行时授权） |
| 2 | **数据不互通** | APK 的页面源是 `https://localhost`，IndexedDB 按 origin 隔离 → 与浏览器里那份**不是同一个库**。从 PWA 迁到 APK 要走"导出备份 → 在 APK 里导入备份"；卸载 App / "清除数据"会连库删掉 |
| 3 | **没有热更新** | 新版本 = 新 APK（`versionCode` 递增 + 同签名）。需要快速修文案时先走 PWA |
| 4 | **导出后文件在哪** | 写在 App 缓存目录（`CACHE`），用户通过分享面板交出去。若希望"直接落到下载目录"可改 `Directory.Documents`，但安卓 10+ 的文件可见性反而更差 |

---

## 7. 报错对照表

| 报错 | 原因 | 处理 |
| --- | --- | --- |
| `JAVA_HOME is not set and no 'java' command could be found` | 没装 JDK / 没设 `JAVA_HOME` | §1 装 JDK 21，§2 设环境变量，**开新终端** |
| `SDK location not found` | 没有 `ANDROID_HOME` 或 `local.properties` | 设环境变量，或写 `android/local.properties` 的 `sdk.dir` |
| `Failed to install the following SDK components: platforms;android-36` | SDK 里没有 API 36 | `sdkmanager "platforms;android-36" "build-tools;36.0.0"` |
| `Unsupported class file major version 69` | JDK 太新（26） | 换 JDK 21 |
| `Could not determine java version from '21.0.x'` | Gradle 太旧 | 用工程自带的 wrapper（8.14.3），别用系统 gradle |
| `Could not resolve com.android.tools.build:gradle:8.13.0` | 网络/代理 | 配代理，或 `GRADLE_USER_HOME` 指到有缓存的机器目录 |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | 签名与已装版本不同 | 先卸载旧包（**会清数据**，先导出备份） |
| `INSTALL_FAILED_VERSION_DOWNGRADE` | `versionCode` 没递增 | 改大 `versionCode` |
| `App 白屏` | `www/` 没同步 / 路径错 | `npm run sync` 后确认 `android/app/src/main/assets/public/index.html` 存在 |
| `导出点了没反应` | 见 §6.1 | 补 Filesystem + Share 分支 |

---

## 8. 一页速查

```powershell
# 装：JDK 21 + Android Studio（或 cmdline-tools）+ SDK Platform 36 + Build-Tools 36.0.0
# 设：JAVA_HOME / ANDROID_HOME / PATH（开新终端）

cd D:\project\Capstone\apk-wrapper
npm run sync                                       # www ← dist 包，再同步进工程
cd android
.\gradlew.bat assembleDebug                        # 首次 5~15 分钟
adb install -r app\build\outputs\apk\debug\app-debug.apk

# 原生适配（导出/返回键/SW）已内置；正式分发前只需做 §5 签名
```

**判断"能不能发"的三条硬指标**：① 壳里导出 Word 能落到"分享/打开"面板（§6.1 已实现）；
② 返回键先回上一页、首页才退出（§6.2 已实现）；③ 同签名 + `versionCode` 递增能覆盖安装（§5）。

---

## 9. 云端出包（不装 JDK / SDK 也能拿 APK）

仓库里已经有一个 GitHub Actions 工作流：`.github/workflows/build-android.yml`

**它会做**：checkout → 装 JDK 21（temurin）→ 装 Node 22（Capacitor 8 的 CLI 要求 ≥22）→ 用 runner 预装的 Android SDK →
`sdkmanager "platforms;android-36" "build-tools;36.0.0" platform-tools` →
`npm ci` → `python3 scripts/prepare-www.py`（从 `dist/*.zip` 解出 www）→
`npx cap sync android` → `./gradlew assembleDebug` → 把 APK 传成 Artifact。

**用法**

1. 把仓库推到 GitHub（**私有库也行**，Actions 对私有库同样免费额度）；
2. 打开仓库 → **Actions** → 左侧选 **Build Android APK** → 右侧 **Run workflow**
   （默认 `debug`；选 `release` 会得到未签名包，签名见 §5）；
3. 等约 3–6 分钟（首次要下 Gradle 依赖，之后有缓存会快很多）；
4. 在本次运行页面底部 **Artifacts** 下载：
   `mcc-inspection-tool-v1.0.1-debug.apk`（保留 30 天）。

也可以命令行触发：

```bash
gh workflow run build-android.yml -f build_type=debug
gh run watch
gh run download -n mcc-inspection-tool-v1.0.1-debug.apk -D ./apk
```

**跑完在运行摘要（Summary）里能直接看到**：文件名、体积、sha256、JDK/SDK 版本、提交号 ——
发给客户时把 sha256 一起给，对方可以自己校验。

**注意**

- Artifact 是**未签名（debug 签名）**的包：能直接装、能测试，但**不能上架、不能作为正式分发包**。
  正式分发按 §5 生成 keystore 后，把签名配置提交到仓库（或用 GitHub Secrets 注入密码），
  再把 `build_type` 选 `release`。
- **签名与升级**：debug 包用的是 runner 上自动生成的 debug keystore，**每次运行都不同** ——
  所以工作流里加了"缓存 `~/.android/debug.keystore`"这一步，否则每次 APK 都装不上（要卸载、丢数据）。
  运行摘要里会打印签名指纹，**连续两次构建的指纹应当一致**；换仓库/缓存被清会变。
  给客户正式分发时按 §5 用 release keystore（走 GitHub Secrets），不要依赖 debug 签名。
- 工作流只构建 **debug** 时也要求 `dist/mcc-inspection-tool-v1.0.1.zip` 已提交 ——
  APK 里的内容永远来自交付包，不从 `web/` 源码直接打包。
- 想改版本号：改 `web/app/product.js` 的 version → `python tools/make_release_zip.py` →
  `apk-wrapper/package.json` 与 `android/app/build.gradle` 的 versionName/versionCode → 推代码。
