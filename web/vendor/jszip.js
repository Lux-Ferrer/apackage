/* JSZip 的浏览器 ESM 包装。
 *
 * 为什么需要这一层：JSZip 只发布 UMD 构建（`dist/jszip.min.js`），没有 ESM 产物，
 * 而本应用**不引入打包器**（M5 设计第 5 节），浏览器里只能靠原生 ES modules。
 * UMD 文件被当模块加载时会把导出挂到 `self` 上（它内部的 `this` 在模块里是 undefined，
 * 于是走 `global = global || self` 那一支），所以这里 import 之后再 `export default`。
 *
 * 用法：靠 index.html 里的 <script type="importmap"> 把裸名 `jszip` 指到本文件，
 * 于是**同一份源码**在浏览器（vendor/）与 Node（node_modules）里都跑得起来。
 *
 * ⚠️ 本文件是手写的，不参与生成；`jszip.min.js` 由 `tools/export_web_assets.py` 从
 * node_modules 复制（带版本标记，`--check` 能发现升级后忘了重新 vendor）。
 */
import './jszip.min.js';

export default globalThis.JSZip;
