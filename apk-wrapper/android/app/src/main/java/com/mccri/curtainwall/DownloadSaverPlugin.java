package com.mccri.curtainwall;

import android.app.Activity;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.widget.Toast;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.Locale;

/**
 * 把导出的 Word / 备份 zip 存到**公共下载目录**，然后（有接收方的话）拉起分享面板。
 *
 * 为什么需要它：WebView 不认 `<a download>`，也不处理 `blob:` 链接。1.0.1 里先用
 * Capacitor 的 Filesystem 写进 App 缓存再 Share —— 文件写出来了，但这台机器**没装能打开
 * .docx 的应用**时，分享面板是空的（"没有应用可执行此操作"），用户拿不到文件。
 *
 * 所以这一版改成：
 *   1. `Download/幕墙检测/<文件名>`（Android 10+ 走 MediaStore，不需要任何存储权限；
 *      9 及以下退到 App 专属外部目录，同样不需要权限）；
 *   2. 再尝试 `ACTION_SEND`：有接收方就弹选择器，没有就 Toast 告诉用户文件在哪。
 *
 * JS 侧见 `web/app/export.js::saveInNativeShell()`：优先调这个插件，
 * 只有旧版壳（没有本插件）才回退到 Filesystem + Share。
 */
@CapacitorPlugin(name = "DownloadSaver")
public class DownloadSaverPlugin extends Plugin {

    /** 下载目录下的子目录，避免客户的文件和别的 App 下的一坨混在一起。 */
    private static final String SUB_DIR = "幕墙检测";

    @PluginMethod
    public void saveAndShare(PluginCall call) {
        String fileName = call.getString("fileName");
        String base64 = call.getString("data");
        String mime = call.getString("mime", "application/octet-stream");
        String title = call.getString("title", fileName);
        if (fileName == null || fileName.isEmpty()) {
            call.reject("缺少 fileName");
            return;
        }
        if (base64 == null || base64.isEmpty()) {
            call.reject("缺少 data（base64）");
            return;
        }

        byte[] bytes;
        try {
            bytes = Base64.decode(base64, Base64.DEFAULT);
        } catch (IllegalArgumentException error) {
            call.reject("base64 解码失败：" + error.getMessage(), error);
            return;
        }

        String safeName = sanitize(fileName);
        Context context = getContext();
        Uri uri = null;
        String displayPath = null;

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                ContentValues values = new ContentValues();
                values.put(MediaStore.Downloads.DISPLAY_NAME, safeName);
                values.put(MediaStore.Downloads.MIME_TYPE, mime);
                values.put(MediaStore.Downloads.RELATIVE_PATH,
                        Environment.DIRECTORY_DOWNLOADS + "/" + SUB_DIR);
                values.put(MediaStore.Downloads.IS_PENDING, 1);
                uri = context.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if (uri == null) {
                    call.reject("系统拒绝了下载目录写入（MediaStore 未返回 uri）");
                    return;
                }
                try (OutputStream out = context.getContentResolver().openOutputStream(uri)) {
                    if (out == null) {
                        call.reject("无法打开下载目录的输出流");
                        return;
                    }
                    out.write(bytes);
                    out.flush();
                }
                values.clear();
                values.put(MediaStore.Downloads.IS_PENDING, 0);
                context.getContentResolver().update(uri, values, null, null);
                displayPath = "下载/" + SUB_DIR + "/" + safeName;
            } else {
                // Android 9 及以下：公共 Downloads 要 WRITE_EXTERNAL_STORAGE，这里退到 App 专属外部目录
                File dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                if (dir == null) {
                    call.reject("这台设备没有可用的外部存储");
                    return;
                }
                File subDir = new File(dir, SUB_DIR);
                if (!subDir.exists() && !subDir.mkdirs()) {
                    call.reject("无法创建目录 " + subDir.getAbsolutePath());
                    return;
                }
                File target = new File(subDir, safeName);
                try (FileOutputStream out = new FileOutputStream(target)) {
                    out.write(bytes);
                }
                uri = Uri.fromFile(target);
                displayPath = target.getAbsolutePath();
            }
        } catch (Exception error) {
            call.reject("保存到下载目录失败：" + error.getMessage(), error);
            return;
        }

        boolean shared = share(uri, mime, title);
        if (!shared) {
            toast("文件已保存至 " + displayPath);
        }

        JSObject result = new JSObject();
        result.put("saved", true);
        result.put("shared", shared);
        result.put("uri", uri.toString());
        result.put("displayPath", displayPath);
        call.resolve(result);
    }

    /** 有接收方才拉起选择器；没有就返回 false，交给调用方提示用户。 */
    private boolean share(Uri uri, String mime, String title) {
        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType(mime);
        send.putExtra(Intent.EXTRA_STREAM, uri);
        if (title != null) {
            send.putExtra(Intent.EXTRA_TITLE, title);
        }
        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);

        if (send.resolveActivity(getContext().getPackageManager()) == null) {
            return false;
        }
        final Intent chooser = Intent.createChooser(send, "打开 / 分享");
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        toastLater(() -> getContext().startActivity(chooser));
        return true;
    }

    private void toast(String message) {
        toastLater(() -> Toast.makeText(getContext(), message, Toast.LENGTH_LONG).show());
    }

    /** 插件方法可能跑在后台线程上：Toast / startActivity 都丢回主线程（Activity 已销毁时直接跳过）。 */
    private void toastLater(Runnable action) {
        Activity activity = getActivity();
        if (activity == null) {
            return;
        }
        activity.runOnUiThread(action);
    }

    /** 文件名清洗：去掉路径分隔符与非法字符，保留中文。 */
    private String sanitize(String name) {
        String cleaned = name.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        if (cleaned.isEmpty()) {
            cleaned = "export.bin";
        }
        return String.format(Locale.ROOT, "%s", cleaned);
    }
}
