# 本地 APK 打包指南

> 目标：把**纯前端交付包 v1.0.1** 装进一个 Capacitor 壳，产出可分发的 `.apk`。
> 本文档对应 `D:\project\Capstone\apk-wrapper\`，环境是 **Windows + 无 JDK / 无 Android SDK**。

---

## 0. 现在的状态：壳已经搭好了，只差 JDK

已经做完（都不需要 Java）：

| 项 | 状态 |
| --- | --- |
| `apk-wrapper/` 独立隔离区（不碰 `web/` 源码） | ✅ 已建，`npm init` + 依赖已装 |
| Capacitor 版本 | ✅ **8.6.2**（core / cli / android 三件套） |
| `capacitor.config.json` | ✅ `appId=com.mccri.curtainwall`、`appName=幕墙检测`、`webDir=www` |
| Web 资源 | ✅ `www/` = 交付包解压（53 个文件，`VERSION.txt` 里是 v1.0.1），由 `scripts/prepare-www.py` 从 `dist/*.zip` 生成并校验版本 |
| Android 工程 | ✅ `npx cap add android` **成功**，已生成 `apk-wrapper/android/` |
| 图标 | ✅ 已替换成产品的 PWA 图标（含自适应图标，避开了 Capacitor 默认 logo） |
| 启动图 | ✅ 11 张 splash 已换成品牌蓝 + 居中图标（原先是 Capacitor 默认画面） |
| 版本号 | ✅ `versionName "1.0.1"`、`versionCode 1` |
| `npx cap sync android` | ✅ 通过（资源已拷进 `android/app/src/main/assets/public`） |
| `npx cap doctor` | ✅ `Android looking great` |

**唯一缺的**是 JDK（以及编 APK 要用的 Android SDK）。现在直接构建会停在：

```
ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
```

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
| 3 | 项目详情 → **导出 Word** | ⚠️ **会失败**（见 §6.1，出包前必须补） |
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

- `versionCode` 每次发版 **必须 +1**（当前 1）；
- `versionName` 与 `web/app/product.js` 保持一致（当前都是 **1.0.1**）；
- 升级覆盖安装要求**同一个签名**，否则报 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`（只能先卸载，**数据会没**）；
- `versionCode` 变小 → `INSTALL_FAILED_VERSION_DOWNGRADE`。

---

## 6. ⚠️ 出包前必须补的 3 处（WebView 与浏览器的差异，不是环境问题）

这三条和 JDK 无关，但**不补就发不出去**。第 1 条是 P0。

### 6.1 P0：导出的 Word / 备份存不下来

**原因**：导出走的是 `web/app/export.js::downloadBlob()` —— `URL.createObjectURL(blob)` +
`<a download>` 点击。这个套路在 Android WebView 里**没有任何效果**：WebView 不支持
`download` 属性，也不处理 `blob:` 链接，`DownloadListener` 只认 http/https。表现为"点了没反应、控制台也不报错"。

**好消息**：全项目只有**一个**下载入口（`downloadBlob`，`web/app/export.js:119`）。
Word 报告、备份 zip 都走它，改一处即可。

**做法**（推荐）：装两个插件，在 `downloadBlob` 里按平台分支。

```powershell
cd apk-wrapper
npm install @capacitor/filesystem @capacitor/share
npx cap sync android
```

```js
// web/app/export.js —— 在 downloadBlob 开头加分支（浏览器行为完全不变）
export async function downloadBlob(blobOrBytes, filename, options = {}) {
    const blob = blobOrBytes instanceof Blob ? blobOrBytes : new Blob([blobOrBytes], { type: DOCX_MIME });

    // 原生壳里：写进 App 的缓存目录，再拉起系统"分享/打开"面板
    if (globalThis.Capacitor?.isNativePlatform?.()) {
        const { Filesystem, Directory } = await import('@capacitor/filesystem');
        const { Share } = await import('@capacitor/share');
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(',')[1]);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
        const { uri } = await Filesystem.writeFile({
            path: filename, data: base64, directory: Directory.Cache, recursive: true,
        });
        await Share.share({ title: filename, url: uri, dialogTitle: '保存 / 打开' });
        return { uri, size: blob.size, filename };
    }

    // …浏览器分支保持原样（Blob URL + <a download>）…
}
```

> 用 `Directory.Cache` + 分享面板：用户可以直接"用 WPS 打开"或"保存到文件"，
> 不需要申请存储权限（Android 10+ 的存储权限对 App 目录之外才需要）。
> 也可以换成 `Directory.Documents`（App 专属外部目录），但分享面板仍是手机端最顺的交互。

### 6.2 P1：硬件返回键会直接退出 App

WebView 里按返回键默认关闭 Activity。表单填到一半按返回 → 整个 App 没了。

```powershell
npm install @capacitor/app && npx cap sync android
```

```js
// web/app/main.js（start() 里，仅原生壳生效）
if (globalThis.Capacitor?.isNativePlatform?.()) {
    const { App } = await import('@capacitor/app');
    App.addListener('backButton', ({ canGoBack }) => {
        if (globalThis.history.length > 1) globalThis.history.back();
        else App.exitApp();
    });
}
```

（我们的路由是 hash 路由，`history.back()` 会走 `hashchange` → 正常返回上一页。）

### 6.3 P1：Service Worker 会让"更新后还是旧界面"

APK 里的资源是打包进去的，本来不需要 SW；但 `web/app/main.js:278` 的 `registerServiceWorker()`
在 `https://localhost`（安全上下文）下**会真的注册并缓存**。缓存跨 APK 升级保留 →
装了 1.0.2 却还显示 1.0.1 的界面，很难排查。

```js
// web/app/main.js —— 原生壳里跳过注册
async function registerServiceWorker() {
    if (globalThis.Capacitor?.isNativePlatform?.()) return null;   // ← 加这一行
    if (!('serviceWorker' in navigator)) return null;
    …
}
```

### 6.4 P2：相机

缺陷表单用的是 `<input type="file" accept="image/*" capture="environment">`（`web/app/views/reports.js:208`）。
Capacitor 的 `BridgeWebChromeClient` 实现了 `onShowFileChooser`，会弹"相机 / 文件"选择器，**多数机型直接可用**。
如果某些机型调不起相机，再上 `@capacitor/camera`（那时才需要在
`AndroidManifest.xml` 加 `<uses-permission android:name="android.permission.CAMERA"/>` 并处理运行时授权）。

### 6.5 P2：数据和浏览器版**不互通**

APK 里的页面源是 `https://localhost`，IndexedDB 按 origin 隔离 —— 与浏览器里那份（`http://内网IP`
或 `http://localhost:9000`）**不是同一个库**。从 PWA 迁到 APK 要走"**导出备份 → 在 APK 里导入备份**"。
同理，卸载 App 或"清除数据"会连库一起删掉 —— 备份纪律照旧。

### 6.6 P2：APK 没有热更新

装了 APK 的设备只能靠**发新包**升级（PWA 那套"关页面重开就更新"在壳里不成立）。
建议两个渠道都保留：现场用 APK（完全离线、无浏览器差异），需要快速修文案时先用 PWA 顶上。

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

# 上线前还要做：§6.1 导出保存（P0）、§6.2 返回键、§6.3 关掉 SW、§5 正式签名
```

**判断"能不能发"的三条硬指标**：① 导出 Word 能用（§6.1 补完）；② 返回键不退出（§6.2）；
③ 同签名 + `versionCode` 递增能覆盖安装（§5）。
