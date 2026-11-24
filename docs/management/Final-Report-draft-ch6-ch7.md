# Final Report — Draft of §6 and §7

> Counts used here: **348** Python tests · **250** front-end tests · **16** gates ·
> **21** desktop E2E cases · **14** on-device assertions · **9** defects fixed (3 P0).
> Where a historical figure differs (e.g. the front-end suite had 205 tests when the
> Android crash was found), the text says so explicitly rather than back-dating today's number.

---

# §6 Implementation (~1,800 words)

## 6.1 Stack and repository layout

The product is served from a directory; there is no build step to run at deployment time and
no bundler at development time. `index.html` declares an import map mapping the two
third-party dependencies (`docx`, `jszip`) to vendored files, and every other module is a
native ES module fetched by the browser from the same paths a developer edits. This was a
deliberate trade: no bundler means no transpilation step, no source maps to trust, and a
stack trace in a phone's remote inspector that points at the file the developer wrote. The
cost is that the module graph must be explicit and that nothing minifies the payload — both
acceptable for a ~50-file, ~470 KB application.

Generated artefacts are the one exception to "the browser fetches what you edit". Some
values must not be maintained twice: the layout numbers, the defect vocabulary, the
requirement clauses, and the CSS that both the Python reference implementation and the web
client share. These are generated from the Python source of truth by
`tools/export_web_assets.py` into `web/app/config.js`, `web/app/report/spec.js`,
`web/assets/report_layout.json`, `web/styles/app.css` and `web/assets/shell.js`, and the
generator supports `--check`, which is the first gate in the verification suite. Drift
between a hand-edited copy and its source is therefore a build failure rather than a
runtime mystery — a decision that paid for itself the first time a CSS tweak was made in the
generated file and promptly rejected.

The repository separates the three things that must not be confused: `webapp/` is the frozen
Python reference implementation (a Flask app kept only as a comparison oracle and never
modified), `web/` is the production client, and `tools/` holds the gates. Freezing the
reference implementation was the single most useful structural decision of the project: it
turned "does the new code behave like the old code?" from an opinion into a diff.

## 6.2 Data layer and transaction discipline

All persistence goes through one module, which is the only place allowed to open a
transaction. Business modules call `withTransaction(stores, mode, fn)`, which resolves when
the transaction *commits*, not when the callback returns — a distinction that matters,
because a callback can resolve while the commit is still in flight.

Three rules are enforced by review and documented at the top of the module. **Never await a
non-IndexedDB promise inside a transaction.** Canvas encoding, `fetch`, `setTimeout` and
dynamic `import()` all yield to the microtask queue, and IndexedDB commits a transaction as
soon as control returns to the event loop with no pending requests; the next `put()` then
throws `TransactionInactiveError`. This rule shapes the image pipeline (§5.4): the JPEG is
encoded *before* the transaction opens. **Read-modify-write in one transaction**, so a
concurrent write cannot interleave. **Recompute derived values at write time**: the minimum
of five readings is computed by the data layer, not copied from the form, because the form's
value is a preview and previews can be stale.

Cascades are hand-written. Deleting a project walks the `project_id` index of `records`,
then the `record_id` index of `readings`, then deletes the images of each linked defect —
all inside one read-write transaction, because a partial cascade leaves orphaned blobs that
no later code path can find. The alternative, letting the UI delete row by row, is how
orphan images appear in systems like this one.

## 6.3 The report engine: from specification to document

Generation is a five-stage pipeline with no branch that depends on wall-clock time or
iteration order, which is what makes the output comparable byte for byte:

1. **Flatten.** Records are exploded into rows, one per detection face, carrying a back
   reference to their member. A second pass assigns vertical-merge spans: member columns
   span the faces of one member, and the requirement column spans consecutive rows that
   share the same clause text.
2. **Build.** A declarative builder emits the table: header rows (two, with a horizontally
   merged group header), body rows, and the merged cells the flattening pass described.
3. **Serialise.** `docx` converts the declarative tree into OOXML.
4. **Patch.** Eleven deterministic transformations rewrite the attribute families that
   differ from the approved template (Table 5.3).
5. **Assemble.** Attachment pages are appended, the package is zipped, and the result is
   handed to the download layer.

Two findings from this stage are worth recording because they contradict a natural instinct.
First, the engine was brought to zero differences by *using the diff list as a to-do list*,
converging 201 → 33 → 2 → 0 differences over three rounds; each round was committed
separately so a regression could be attributed to a round. Second, we considered building a
"declared deviation" mechanism — a manifest of intentional differences, so the gate could
ignore them — and rejected it after measuring: all eleven discrepancies turned out to be
attribute-level and closable (a `w:val` spelling, an attribute order, an optional attribute,
the presence of `hRule`), and *none* required a semantic departure from the baseline. A
mechanism to excuse differences would therefore have excused nothing and hidden everything.

## 6.4 Attachment pages

When a project has linked defect reports, the export can append them as attachment pages.
Each report occupies exactly one page: a title of the form "检测报告附页（n/total）", a
nine-row two-column information table (defect type, location, risk level, rectification,
code references, suggestions, report person, date, image file), and the photograph scaled to
the available box. A page break is emitted *before* each attachment rather than after, which
is what keeps the last attachment from producing a trailing blank page — a defect that is
invisible in a scrolling preview and obvious in print.

Degradation is explicit. A field the inspector left empty prints as "无" (none) rather than
as a blank cell, because a blank cell reads as a data-entry error and invites the reviewer to
re-open the record. An image too large for the box is scaled down and the cell is annotated
"已压缩" (compressed), so the reviewer knows the print is not at native resolution. The
report person is a **snapshot**: the attachment records the name and department as they were
when the report was saved, so editing the profile later does not rewrite history.

## 6.5 The UI shell

The interface is mobile-first in a literal sense: the primary viewport is 360–480 CSS pixels
wide, and the layout was designed at that width before being checked at 1280. Two structural
choices follow. **List screens show a bottom tab bar; form screens do not.** A long form with
the numeric keyboard open needs the thumb area, and a tab bar there is both an obstruction
and a mis-tap generator; form screens instead show a fixed action bar with *Cancel* and
*Save*.

Three implementation traps are worth naming, because each produced a defect that passed
every unit test. The `.card` and `.action-bar` blocks are siblings, not nested, so a
component that searches for its own controls inside its own root finds nothing — the fix was
to pass a wrapper as the root, and the lesson is that **the frozen contract is the
`id`/`class` vocabulary, not the DOM hierarchy**. Author CSS overrode the `[hidden]`
attribute on the tab bar (attribute selectors lose to class selectors), so form screens still
showed tabs; the fix was a `[hidden] { display: none !important }` base rule, with a
regression test that asserts computed style rather than the attribute. And SVG icons
rendered as empty boxes because `document.createElement('svg')` produces an element in the
HTML namespace: it exists in the DOM, has a size, and is found by `querySelector`, but the
browser never paints it. The fix is `createElementNS`, and the test asserts `namespaceURI`
instead of presence.

The soft keyboard required a measurement rather than an assumption. On the test device,
`innerHeight` does not change when the keyboard opens (774 px in both states); only
`visualViewport.height` shrinks, to 478 px. A `position: fixed; bottom: 0` action bar is
therefore laid out *behind* the keyboard: before the fix, the bar occupied 713–774 px while
the visible area ended at 478. The fix writes the keyboard height into a CSS variable
(`--keyboard-inset`) and offsets the bar by it; using `transform` instead was tried and
rejected, because a transform creates a new stacking context and made tap hit-testing land in
the wrong place in the Android WebView. After the fix, with a 296 px keyboard, the bar moves
from 713–774 to 417–478 — exactly on the keyboard's upper edge — and the Save button
(426–470) stays visible and tappable.

## 6.6 Release engineering

The delivery package is not a zip of the working tree: it is built by a script with an
explicit whitelist and an explicit blacklist, and it refuses to produce output if a test
asset appears inside it. That assertion exists because the browser test scripts were once
included — the packaging log went from 52 to 62 files and the extra ten were `.spec.mjs`
files and helper scripts. The package carries `VERSION.txt` (product version, build time,
offline-cache fingerprint), a `.sha256` sidecar, and a `.manifest.json` listing every file.

Three release facts are single-sourced. The **version** lives in one file
(`web/app/product.js`) and is asserted equal to the package's `VERSION.txt` at build time;
it appeared in three places before that rule existed. The **offline-cache fingerprint** is
computed from the shell assets, so it cannot disagree with them. The **signature** is pinned
by caching the debug keystore in CI, because a fresh keystore per run makes each build
un-upgradable over the previous one (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`, recoverable only
by uninstalling, which deletes the inspector's data).

The Android channel is a thin shell rather than a second product: the same web bundle is
packaged by Capacitor, and exactly three behaviours diverge — exports are written to the
public Downloads folder through a small native plugin (with a share-sheet fallback and a
toast when no viewer is installed), the hardware back key navigates within the app and exits
only at a root screen, and the service worker is not registered because the assets already
come from the package.

## 6.7 Code-level lessons

Three practices earned their place. **Generated artefacts are checked in and diffed in CI**,
so a stale copy cannot ship. **Assertions that inspect source code must strip comments
first** — our "the service worker must not call `skipWaiting()`" check failed on its own
documentation comment that said "this is where we do not call `skipWaiting()`". And **a test
that waits for a selector must wait for a monotonically increasing signal**, not for a class
name that also exists on the previous page; the app now writes a render counter onto
`<body>` and tests wait for it to grow, which removed a whole class of false positives in
which a test read the previous page's DOM and concluded that a deletion had failed.

---

# §7 Evaluation and Quality Assurance (~2,100 words)

## 7.1 Strategy: five layers, ordered by cost

Verification is layered deliberately, cheapest first, so that a mistake is caught by the
cheapest layer that can see it (Table 7.1). The numbers below are the state at delivery.

**Table 7.1 — The verification layers**

| Layer | What it can see | Count | Cost per run |
| --- | --- | --- | --- |
| Unit and component tests (Python) | Data rules, layout extraction, export assembly, defect semantics | 348 tests | ~10 s |
| Unit and component tests (JavaScript) | Data layer, engine, attachments, image pipeline, real `index.html` UI | 250 tests | ~6 s |
| Fidelity gates | Attribute-level equality with the approved report | 16 gates total (5 of them fidelity) | ~30 s |
| Desktop end-to-end (real browser) | Canvas, dialogs, service worker, downloads, viewports, real `File`/`Blob` | 21 cases | ~35 s |
| On-device (Android) | Camera, file manager, soft keyboard, install, offline with traffic blocked | 14 assertions | manual, ~20 min |

The layering is not a formality. Each layer was added because the layer below it was
demonstrably unable to see something, and §7.5 tells that story in order.

## 7.2 The three fidelity gates

A single comparison can be self-consistent and still blind, so fidelity is asserted by three
gates whose domains differ (Table 7.2). All three run in the 16-gate suite.

**Gate A — frozen baseline, in two halves.** The expected document is a `.docx` generated
once by the Python reference implementation and then frozen in the repository. The gate
compares the JavaScript engine's output against it attribute by attribute — body paragraphs,
tables, rows, cells, cell properties, run properties, embedded images — and is run twice:
once for a report without attachments, once for a report with attachment pages, because the
attachment path exercises a different builder and a different page-break rule. Gate A's
oracle is the *old implementation*, which makes it excellent at detecting regressions and
useless at detecting a mistake the reference implementation shares.

**Gate B — differential testing against the client's real report.** The expected document is
a cropped excerpt of the client's actual delivered report (`检测表_真实裁剪.docx`), reduced to
the tables so that no client-identifying content is compared. The actual document is
generated from the same fixture data the crop was taken from. This is differential testing in
McKeeman's sense with a human-authored oracle: it is the only gate that can say "the output
differs from what the client actually accepts", and it is what anchors Gate A — without B, A
would only prove the JavaScript port agrees with the Python port.

**Gate C — a Python-free self-check.** The third gate compares a canonical JSON fingerprint
of the document (paragraph styles, table geometry, row heights, cell merge grid, run
properties, image extents) computed **entirely in JavaScript**, so it shares no code with the
comparators used by Gates A and B, both of which are Python. Its purpose is to break
correlated failure: if the Python comparator has a bug, Gates A and B can agree with each
other and both be wrong, while Gate C is looking through a different lens.

**Table 7.2 — What each gate compares, and what it cannot see**

| Gate | Oracle | Compares | Blind spot |
| --- | --- | --- | --- |
| A | Frozen output of the Python reference implementation | Body, tables, rows, cells, cell/run properties, image extents — twice (plain, with attachments) | Inherits any error the reference implementation shares; says nothing about rendering |
| B | Real cropped client report | The same attribute families, against a document the client has accepted | Only the cropped region; the crop is a fixture, not a live document |
| C | Structural fingerprint computed in JavaScript | Styles, geometry, merge grid, run properties, image extents | Structure only — no fonts, no pagination, no visual appearance |

None of the three renders the document. That is intentional: rendering comparison would add
a font bottleneck and a platform dependency to a gate that must run in CI on every commit.
The consequence — a document can pass all three gates and still paginate differently — is
stated as a limitation in §8.4.

## 7.3 Sensitivity: proving the gates are not decorative

A gate that reports zero differences is only as meaningful as its sensitivity, so the suite
includes a poisoning harness: seven deliberate mutations are applied to a known-good
document, and each must be caught **at a specific point in the comparison** — the gate must
fail, and it must fail on the right attribute (Table 7.3).

**Table 7.3 — The seven poisons**

| Poison | Mutation | Expected failure point | Result |
| --- | --- | --- | --- |
| `image_extent` | Shrink an image's display size | `images[…]` | caught |
| `drop_drawing` | Delete one embedded drawing | `images[…]` | caught |
| `table_text` | Change one character in a table cell | `table[…]` | caught |
| `table_merge` | Write the continuation cell as `w:vMerge w:val="continue"` | `grid` | caught |
| `row_height` | Change a row height 400 → 500 | `rows[…]` | caught |
| `bold_label` | Remove bold from an attachment label run | `run_props` | caught |
| `image_media` | Replace the embedded image bytes | `images[…]` | caught |

Asserting the *path* of the failure, not merely that the run turned red, is what makes this
useful: it distinguishes "the gate noticed something" from "the gate noticed the right
thing". The `table_merge` poison is the most instructive of the seven, and it produced the
design rule discussed in §5.3 — the two comparators disagree about `val="continue"` versus an
absent `val`, so the patch chain emits the byte form that both accept.

## 7.4 Fidelity results

After three convergence rounds the diff count went 201 → 33 → 2 → 0, and all gates report
zero differences. The eleven residual discrepancies that were closed along the way were all
attribute-level; none required a semantic deviation, which is why no "declared deviation"
mechanism exists.

Zero differences in our own comparator is still a self-referential claim, so the artefacts
were re-verified with tools that share no code with the comparison: `python-docx` and Pillow
were used to open the exported file and read back its structure and media. For a
one-attachment export this confirmed two tables (3 and 9 rows), one attachment page, the
expected report person, and an embedded 1200 × 1600 JPEG — read by a parser that has never
seen our fingerprint code.

## 7.5 The environment ladder: where the real defects came from

This is the part of the project that changed how we work, and it is worth telling in order.
The strategy was to move the test environment one step closer to the user's environment at a
time, and the striking result is that **every one of the nine defects that reached a user-
facing environment was found by the layer above the one that was green.**

### 7.5.1 The jsdom layer, and what "green" does not mean

The front-end suite runs under `node --test` with a DOM implementation that is deliberately
not a browser. It is fast, it is deterministic, and it cannot see (Table 7.4) exactly the
things this product depends on.

**Table 7.4 — What jsdom cannot see (measured, not assumed)**

| Capability | jsdom / Node | Real browser | What it first exposed |
| --- | --- | --- | --- |
| canvas, `createImageBitmap` | absent (stubs only) | present | EXIF orientation, transparent PNG flattening, proportional downscale — first executed for real in the browser |
| `<dialog>.showModal()` | unimplemented (code silently used `confirm()`) | present | the modal confirmation path behind destructive actions, first executed for real |
| Service Worker, Cache | absent | present | offline reload, cache completeness, exporting while offline |
| `URL.createObjectURL` + `<a download>` | stubbed (intercepted) | real download | the actual file name and the actual bytes (re-verified with python-docx / Pillow) |
| Viewport, layout | constants | resizable | keyboard-compressed 375 × 400, landscape, 1280 × 900 |
| `Blob` / `File` / structured clone | mixed (needs Node's `File`) | consistent | "type errors that only exist on the real path" — the backup-import defect below |

The suite was green when the application did not start. That sentence is not rhetoric: the
`boot()` defect (§7.5.2) is one where every test constructed the application through an
entry point that the real application never used.

### 7.5.2 The three P0s

**P0-1 — the application died on open.** On a real device the app showed nothing and the
console reported `Cannot read properties of undefined (reading 'read')` (Chromium) and
`db is undefined` (Firefox). The cause was an initialisation order: `boot()` constructed the
application with an empty options object and *then* opened the database and assigned it to
the object. The constructor had already captured its arguments in a closure, so assigning
later changed nothing and every render saw `undefined`. The fix was two-part: open the
database first, construct second; and have the render context read dependencies from the app
object at use time rather than at construction time. **Why it survived a green suite:** every
test called `createApp({db: …})`, so the dependency was always present at construction; the
real entry point `boot()` had no test at all. The regression test now calls `boot()`, writes
a record through the UI, and reads it back; a positive control reverts `main.js` to the old
order and the test fails with the same two messages the phone produced.

**P0-2 — export crashed on the device, and only on the device.** Tapping *Export Word* on the
phone produced `导出失败：nodebuffer is not supported by this platform`. The generator had
been asked for a Node-specific output type, which requires a global `Buffer`; Node has it,
browsers do not. The full gate set and the front-end suite (205 tests at that point; 250
today) were green, because in Node the call succeeds. The fix was to request an output type
that exists in both environments and to prove the two outputs are byte-identical — Gate A
still reported zero differences afterwards, which is what makes the substitution safe rather
than merely convenient. The regression test deletes the global `Buffer` before importing the
module and then exports, so the Node-only path cannot come back unnoticed.

**P0-3 — the only recovery path had never been executed.** The desktop browser round's case
20 does what a worried inspector would do: export a backup, clear all reports, import the
backup. The confirmation dialog never appeared; instead a toast read
`导入失败：zip.files.filter is not a function`. `zip.files` is an object keyed by path, not an
array, and the import path calls `inspectBackup()` *before* showing the confirmation so the
user can see what will be overwritten — which means the failure was total: the one mechanism
for recovering from a lost phone could never have worked, for anyone, at any time. **Why it
survived:** there was no test for import. Export was covered end to end, and "export works"
had been read as "backup works". The fix replaced the call with `Object.entries(zip.files)`
filtered by the image prefix; the guard is a new eight-case test file (round trip, overwrite
semantics, images travelling with the package, thumbnail rebuild, missing/orphan image
reconciliation, bad-image degradation, four malformed-backup rejections, no partial state on
failure) plus the E2E case with a real `File` and a real `<dialog>`. A positive control
restores the old line, and the new tests fail with exactly the production error string.

### 7.5.3 The remaining six, and the ladder's arithmetic

The other six defects are less dramatic but follow the same pattern (Table 7.5): each was
found by the first environment that could execute the code path, and each is now guarded by a
test that runs in that environment or a cheaper one that can see the same signal.

**Table 7.5 — The nine defects**

| # | Sev. | Symptom | Root cause | Guard now |
| --- | --- | --- | --- | --- |
| 1 | P0 | Backup import always failed | `zip.files` treated as an array | 8 import/export tests + E2E case 20 + on-device round trip |
| 2 | P0 | Export always failed on device | Node-only output type requiring global `Buffer` | Platform test that deletes `Buffer` first; Gate A byte equality |
| 3 | P0 | App crashed on open | `boot()` constructed before opening the database | Regression test calling `boot()` + positive control |
| 4 | P1 | Editing a record crashed | Raw database row passed where a view object was expected | Record-edit tests |
| 5 | P1 | Bottom tab bar covered the Save button | Author CSS beat the `[hidden]` attribute | Computed-style assertion in a real browser |
| 6 | P1 | Tab icons rendered blank | SVG created in the HTML namespace | `namespaceURI` assertion + browser case |
| 7 | P1 | Test scripts shipped inside the delivery package | Packaging whitelist missed the new directory | Packaging asserts "no test assets" and refuses to build |
| 8 | P2 | *Cancel* was 28 × 22 px | No minimum target size | Tap-target assertion in E2E |
| 9 | P2 | Keyboard covered *Save* | `position: fixed` ignores the visual viewport | Keyboard-inset unit tests + real-keyboard device measurement |

Two of the nine (5 and 6) are rendering defects that a unit test cannot see at all: an
element can exist, have the right attributes and the right size, and still not be painted.
One (8) is a usability threshold, which only becomes visible when a human thumb is modelled
as 44 px. One (9) required a real keyboard: the emulator's bundled input method rendered no
keyboard window while still swallowing touches, so a third-party keyboard had to be installed
before the defect could even be reproduced.

### 7.5.4 The two questions

The conclusion we now apply to any green run is two questions, asked in this order:

> **Was this attribute actually compared? And is this environment the same as the user's?**

Every defect in Table 7.5 fails the first question or the second, never "the developer was
careless". The import path failed the first (never compared, because never executed); the
`nodebuffer` and `boot()` defects failed the second (the environment provided what the
browser would not); the tab bar, the SVG icons, the tap target and the keyboard all failed
the second in the rendering sense — the environment computed a layout the user never sees.

## 7.6 Performance and load

Load was measured in the browser, on the delivery package, with a realistic dataset (40
records, 20 reports with full-size photographs), not extrapolated from unit timings.

**Table 7.6 — Measured performance**

| Measurement | Result |
| --- | --- |
| Export with 20 attachment pages | 0.93 s, 59 KB `.docx`, all 20 images embedded and scaled to ≤ 1600 px |
| Three consecutive exports | 816 / 889 / 869 ms — no degradation, identical output size |
| Longest main-thread task | 50 ms, at most one per export (no "is it frozen?" pause) |
| JS heap after 20 exports | 5 → 47 MB, then stable |
| JS heap after 30 view switches | +3 MB (no leak trend) |

The heap figures matter more than the timings for a field tool: an inspector may keep the app
open for a week. The absence of a growth trend across 30 navigations — the pattern that
object URLs and detached DOM subtrees produce — was the evidence that the managed
`objectURL` registry (§5.4) is doing its job.

## 7.7 Threats to validity

**The gates do not render.** All three compare structure. A document can be attribute-
identical and still paginate differently on a machine with different fonts. This is a real
limitation, mitigated only by the fact that the deliverable is opened in the same corporate
Word environment that produced the template.

**The emulator is not a phone.** The Android round ran on an emulator (Android 15, WebView
110) with a third-party keyboard. Camera, file manager and keyboard were real components,
but device-specific rendering and vendor WebView builds were not exercised.

**No iOS device was available.** Safari is the platform most likely to differ — storage
eviction policy, PWA installation and service-worker lifetime all differ — and the product
compensates by asking for persistent storage and by shipping an explicit backup rather than
by claiming parity.

**One evaluator, one client, one workflow.** The requirements were gathered from a single
inspection group; the "as-is" process description is that group's process. Generalisation to
other institutes is an argument, not a measurement.

**The client's report is a fixture.** Gate B compares against a cropped excerpt, so its scope
is the two tables, not the whole document. It anchors the attribute families that matter for
the deliverable and says nothing about sections the project does not generate.

---

## 中文对照（§6 / §7 审阅要点）

**§6 实现**
- 6.1 无打包器 + import map；**生成物必须来自 Python 真相源**，`--check` 是第一条闸门（防"手改了生成文件"）
- 6.2 三条事务纪律，最硬的一条是**事务里不许 await 非 IDB 的 promise**（否则 `TransactionInactiveError`）；级联手写且必须同事务
- 6.3 五段流水线（展平 → 构建 → 序列化 → 补丁 → 组装）；**用差异清单当 TODO**，201→33→2→0；**主动否决了"声明偏离"机制**（实测 11 处全是属性级可抹平，机制收益为零）
- 6.4 附页：每份一页、9 行两列表、页码标题 `(n/total)`、**页break放在前面**（否则最后一页后多出空白页）、空字段打「无」、大图打「已压缩」、报告人是快照
- 6.5 三个"单测看不见"的坑：契约冻结的是 id/class **不是 DOM 层级**、`[hidden]` 被作者样式压过、`createElement('svg')` 在 HTML 命名空间里"存在但不画"；键盘那段的实测数字（774 不变 / visualViewport 478 / 操作条 713–774 → 417–478 / 保存 426–470）
- 6.6 发布工程：白名单+黑名单、**测试资产进包就拒绝产出**、版本单一真相源、指纹化缓存、CI 缓存 keystore（否则升级装不上）
- 6.7 三条代码级教训（生成物入库并 diff、源码断言先剥注释、等渲染计数器而不是等 class）

**§7 评估**
- 7.1 五层按"从便宜到贵"排列，并给了每层的用例数与耗时
- 7.2 三闸门展开成表：**A 冻结基线（跑两遍：纯报告 + 附页）/ B 客户真实报告（差分测试，人工 oracle）/ C 纯 JS 指纹自检（打破相关性）**，每道都写了"比什么、不比什么、盲区在哪"
- 7.3 七个下毒，**断言的是"失败落在哪个属性路径上"**（不只是"变红"）；`table_merge` 那项直接推出 §5.3 的设计规则
- 7.4 0 差异 + **用 python-docx/Pillow 做独立复核**（不共享比较器代码）
- 7.5 **本文最硬核的一段**：jsdom 六项盲区表 → 三个 P0 的完整故事（每个都写了"为什么绿灯还漏了"+"阳性对照"）→ 剩余六个 + 九缺陷表 → 落成两句提问：**"这个属性到底被比了吗？这个环境和用户的一样吗？"**
- 7.6 实测性能表（0.93s / 59KB / 816-889-869ms / 最长长任务 50ms / 堆 5→47MB→稳定 / 30 次切换 +3MB）
- 7.7 五条威胁（不渲染 / 模拟器≠真机 / 无 iOS / 单客户单评估者 / 客户报告是裁剪夹具）

**一处口径说明**：P0-2 的故事里我写的是"当时 205 个前端测试，今天 250"，**没有**把今天的数字回溯到当时的场景里 —— 这是有意的，避免评审对照历史文档时发现数字对不上。

---

## 数字出处

| 数字 | 出处 |
| --- | --- |
| 201 → 33 → 2 → 0 | `docs/management/M5-设计.md` §（差异收敛），`deliverables/m5-gate-a-diff.md` |
| 七个下毒的名称与期望路径 | `tools/verify_gate_sensitivity.py::DOCUMENT_POISONS` + `poison_image_media` |
| 205 个前端测试（当时） | `docs/management/M5-真机验证checklist.md` F 组说明 |
| 13,395 B / 14,998 B 导出 | `v1.0.1-浏览器E2E验证报告.md` §6.1.2 第 4、7 项 |
| 键盘 774 / 478 / 296 / 713–774 → 417–478 / 426–470 | 同上 §6.1.3(2) |
| 0.93 s / 59 KB / 816-889-869 ms / 50 ms / 5→47 MB / +3 MB | 同上 §5 负载实测 |
| 九缺陷（3 P0 + 4 P1 + 2 P2） | `交付验收报告-v1.0.2.md` §5 第 1–9 行 |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | 同上 §0 第 13 行 |
