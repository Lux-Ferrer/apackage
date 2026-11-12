/* Playwright 的全局准备：真实图片夹具（真实浏览器要真字节）。
 *
 * 用 Python + Pillow 生成，因为需要一个**带 EXIF Orientation=6** 的 JPEG ——
 * 手写 EXIF 段容易写出浏览器不认的畸形文件，那样测出来的"方向正确"是假的。
 */
import { spawnSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

export default function globalSetup() {
    const out = join(ROOT, '_work', 'e2e', 'fixtures');
    mkdirSync(out, { recursive: true });
    mkdirSync(join(ROOT, '_work', 'e2e', 'screenshots'), { recursive: true });
    mkdirSync(join(ROOT, '_work', 'e2e', 'artifacts'), { recursive: true });

    const result = spawnSync(process.env.PYTHON ?? 'python',
        [join(ROOT, 'web', 'e2e', 'make_fixtures.py'), '--out', out],
        { cwd: ROOT, encoding: 'utf8' });
    if (result.status !== 0) {
        throw new Error(`生成图片夹具失败：\n${result.stdout ?? ''}\n${result.stderr ?? ''}`);
    }
    process.stdout.write(result.stdout);
}
