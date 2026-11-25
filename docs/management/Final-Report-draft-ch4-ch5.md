# Final Report — Draft of §4 and §5 (with literature candidates)

> Status: draft for review. All figures are taken from the project's own verification runs
> (348 Python tests · 250 front-end tests · 16 gates · 21 desktop E2E cases · 14 on-device
> assertions · 9 defects fixed). Nothing in this draft is estimated or rounded up.
> Section numbering follows `docs/management/Final-Report-骨架.md`.

---

# Part A — Literature candidates (12 + 3 supplementary)

I could not reach the internet from this environment, so **none of these has been
DOI-verified**. Before they enter the References section, run each through Crossref or
Google Scholar and paste the DOI. The "confidence" column says how sure I am that the
entry exists as written; treat *medium* as "the paper certainly exists, but check volume
and page numbers".

## A.1 Peer-reviewed (core citations)

| # | Theme | Citation | Why it earns a place | Confidence |
| --- | --- | --- | --- | --- |
| 1 | Inspection data capture | Park, C.-S., Lee, D.-Y., Kwon, O.-S., & Wang, X. (2013). A framework for proactive construction defect management using BIM, augmented reality and ontology-based data collection template. *Automation in Construction, 33*, 61–71. | Defect management as a *data-collection template* problem — the same framing we use when we treat the client's Word table as the data model. | high |
| 2 | Inspection data capture | Ma, Z., Cai, S., Mao, N., Yang, Q., Feng, J., & Wang, P. (2018). Construction quality management based on a collaborative system using BIM and indoor positioning. *Automation in Construction, 92*, 35–45. | Shows the dominant research path (BIM + positioning + server) that this project deliberately does *not* take; useful for arguing why a server-less tool is still defensible for a single-inspector workflow. | high |
| 3 | Inspection data capture | Davies, R., & Harty, C. (2013). Implementing "Site BIM": A case study of ICT innovation on a large hospital project. *Automation in Construction, 30*, 15–24. | The canonical field study of *how* site staff actually adopt (and resist) digital tools; grounds the "process change, not just software" argument in §4.1. | high |
| 4 | Inspection data capture | Sacks, R., Eastman, C., Lee, G., & Teicholz, P. (2018). *BIM Handbook: A guide to building information modeling* (3rd ed.). Wiley. | Reference for information-deliverable quality and exchange requirements; supports the claim that the *deliverable format* is part of the requirement, not an afterthought. | high |
| 5 | PWA / offline | Majchrzak, T. A., Biørn-Hansen, A., & Grønli, T.-M. (2018). Progressive Web Apps: The definite approach to cross-platform development? *Proceedings of the 51st Hawaii International Conference on System Sciences (HICSS)*. | The main peer-reviewed evaluation of PWA trade-offs; use it for both the case *for* PWAs and their acknowledged limits (iOS, storage eviction). | medium-high |
| 6 | PWA / offline | Biørn-Hansen, A., Majchrzak, T. A., & Grønli, T.-M. (2017). Progressive Web Apps: The possible web-native unifier for mobile development. *Proceedings of WEBIST 2017*, 344–351. | Earlier, more architectural treatment (service worker, app shell, offline); pairs with #5. | medium-high |
| 7 | PWA / offline | W3C. (2018). *Indexed Database API 2.0* (W3C Recommendation). World Wide Web Consortium. | The normative source for the storage layer we build on (transactions, key ranges, indexes). Cite it whenever we claim "transaction-scoped" behaviour. | high |
| 8 | Testing | McKeeman, W. M. (1998). Differential testing for software. *Digital Technical Journal, 10*(1), 100–107. | The origin of the idea our gates instantiate: run two implementations on the same input and compare. Gate B (our engine vs the client's real report) *is* differential testing with a human-authored oracle. | high |
| 9 | Testing | Chen, T. Y., Cheung, S. C., & Yiu, S. M. (1998). *Metamorphic testing: A new approach for generating next test cases* (Technical Report HKUST-CS98-01). Hong Kong University of Science and Technology. | Gives the vocabulary for our sensitivity test: we do not know the "correct" output for a poisoned document, but we know the *relation* (gate must turn red), so we assert the relation. | high |
| 10 | Testing | Feathers, M. (2004). *Working effectively with legacy code*. Prentice Hall. | Source of "characterization test" / golden-master thinking: freeze today's output, then defend it. Explains why Gate A compares against a *frozen* baseline rather than a written spec. | high |
| 11 | Document fidelity | Ecma International. (2021). *ECMA-376: Office Open XML file formats* (5th ed.). Also published as ISO/IEC 29500. | The normative definition of every XML attribute our 11 patches touch (`w:docGrid`, `w:tblLook`, `w:vMerge`, …). Without it the patches look arbitrary. | high |
| 12 | Document fidelity | Miu, D. (2024). *docx: Generate .docx files with JavaScript/TypeScript* [Computer software]. npm. | The library we generate with, and the reason patches exist at all: it produces *valid* OOXML, not *identical* OOXML. | high |

## A.2 Supplementary (standards / practitioner sources — label them as such)

| # | Type | Citation | Use |
| --- | --- | --- | --- |
| S1 | Standard | Ministry of Construction, P.R. China. (2003). *Technical code for glass curtain wall engineering* (JGJ 102-2003). | Domain basis for the thickness-requirement clauses and the 3.0/2.5 mm thresholds. |
| S2 | Practitioner | Archibald, J. (2019). *The offline cookbook*. web.dev (Google). | Not peer-reviewed, but the canonical catalogue of offline caching strategies; cite only for implementation patterns, and say so. |
| S3 | Software | Canny, S. (2013). *python-docx* [Computer software]. | The reference implementation's generator; relevant because the gold standard was produced by a *different* library than the one under test. |

**How I would use them.** §3 gets three paragraphs: (3.1) field capture in construction —
#1–#4 establish that the hard part is the *data template and its governance*, not the
hardware; (3.2) offline-first delivery — #5–#7 plus S2; (3.3) *proving* document fidelity —
#8–#12 plus S3, where the gap is clearest: the literature treats document generation as an
API problem ("does it open?") and rarely as an *equality* problem ("is every attribute the
same?"). Our three gates are the answer to that gap, and §3.5 should say so in one sentence.

---

# Part B — §4 Requirements and Analysis (~1,200 words)

## 4.1 Stakeholders and the as-is process

The client is the Shenzhen branch of MCC Central Research Institute of Building and
Construction, a materials-testing institute whose curtain-wall group inspects façade
systems for building owners and main contractors. Four groups touch the deliverable, and
they want different things from it:

**Field inspectors** (primary users) measure the aluminium profiles of curtain-wall
columns and beams with a coating-thickness gauge, five readings per detection face, and
photograph defects. They work on scaffolds, in lift shafts and in unfinished floors where
there is no usable network; their device is a personal Android phone, not a rugged
handheld. What they need is speed and the certainty that nothing they typed is lost.

**The inspection-department lead** assembles the deliverable. Today this means collecting
paper forms and photographs, re-typing measurements into the corporate Word template,
computing the five-reading minimum by hand, and rebuilding the table layout for every
project. What this role needs is a report that is already correct when it arrives.

**The report reviewer and the project sponsor** sign the report before it leaves the
institute. Reports are contractual evidence: a report whose table widths, merged cells or
header wording differ from the standard is returned, regardless of whether the numbers are
right. What this group needs is *sameness* — the new tool must not become a second house
style.

**The client's IT function** has no budget for a new server, no administrative rights on
inspectors' phones, and no appetite for a native app that must be distributed through a
store. What it needs is a folder of static files it can host, plus an installable Android
package it can hand out directly.

The as-is process therefore has five hand-offs, and every one of them is a transcription
step: gauge → paper form → spreadsheet → Word template → PDF/print. The minimum of five
readings is recomputed by hand at step three and again at step four; photographs live in a
chat application and are re-selected by filename at step four; the table layout is rebuilt
per project because the template is edited rather than instantiated.

Table 4.1 contrasts this with the to-be process.

**Table 4.1 — As-is vs. to-be**

| Dimension | As-is | To-be |
| --- | --- | --- |
| Capture medium | Paper form, then keyboard | Phone form, typed once, in place |
| Network | Not required at capture, required for hand-off | Not required at any point |
| Five-reading minimum | Computed by hand, twice | Computed by the data layer on save and again at export |
| Report layout | Rebuilt per project in Word | One layout specification, applied deterministically |
| Photographs | Chat application, re-selected by filename | Stored with the defect record, exported into attachment pages |
| Hand-off | Word file e-mailed, or printed and signed | Word file generated on the phone, plus a one-file backup |
| Failure mode | Silent transcription error | Loud validation error, or a failed gate |

## 4.2 Functional requirements

Requirements were elicited from the client's existing report and from two working sessions
with the inspection group, then frozen in a traceability matrix. Table 4.2 lists the
functional core; "evidence" names the artefact that demonstrates the requirement rather
than asserting it.

**Table 4.2 — Functional requirements (core)**

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| R1 | Create, edit and delete projects; project number unique; house name required | 348-test Python suite + 250-test front-end suite; unique index on `project_no` |
| R2 | Project detail groups inspection records by template (column/beam) and lists linked defect reports | Desktop E2E case set (21 cases) |
| R3 | Column template: floor, member position, size result, one requirement clause, 1–6 detection faces × 5 thickness readings, minimum computed automatically | Front-end tests + exported-document comparison |
| R4 | Beam template: same fields, three requirement clauses | Same |
| R5 | Size results normalised (`63x164` and `63*164` → `63×164`; `12+75` preserved) | Unit tests on the parser |
| R6 | Records editable, template type immutable after creation, records deletable | Front-end tests + E2E |
| R7 | Defect report: photograph mandatory (≤ 20 MB), 10 preset defect types plus free text, risk level (high/medium/low, default medium), rectification plan mandatory, optional project binding | Front-end tests + on-device walkthrough |
| R8 | Report list with counts and risk badges, filter by risk level, detail view with full-size image | E2E |
| R9 | Deleting a report unlinks it from its project in the same transaction | Front-end tests |
| R10 | Project-level Word export: project block, column/beam sections, note paragraph, deliverable filename; optional attachment pages, one per report, each starting on a new page | Gates A/B/C (zero differences) |
| R11 | Whole-database backup to a single `.zip` (including originals) and restore by import | Front-end tests + on-device round trip |
| R12 | Inspector profile (name, department) captured once and snapshotted into each report | Front-end tests; profile page E2E |
| R13 | About page exposing product name, version, offline-cache fingerprint and issuing organisation | E2E |
| R14 | "Clear all reports" guarded by an explicit confirmation that states the blast radius | E2E |

## 4.3 Non-functional requirements and constraints

**NFR1 — No network, ever.** A full session (create project → record measurements → defect
report → export Word → export backup) must complete with the application's own traffic
blocked. Verified on an Android device by dropping outbound packets for the application's
UID: the session completed and the exported file remained valid.

**NFR2 — No back-end.** The deliverable is a directory of static files. This is a
constraint inherited from the client's IT posture, and it propagates into every other
decision: durability becomes the browser's storage, "sharing" becomes a file on the phone,
and "upgrade" becomes a cache invalidation problem.

**NFR3 — Phone-first.** The primary viewport is 360–480 CSS pixels wide. Interactive
targets are at least 44 × 44 px, the soft keyboard must not cover the save action, and the
hardware back key must navigate rather than exit from anywhere except a root screen.

**NFR4 — Report fidelity is binary.** The generated document must equal the approved
template attribute by attribute — table width, border weights, cell margins, row
alignment, vertical-merge encoding, style and theme parts — not merely "open and look
right".

**NFR5 — No silent data loss.** Every write is transactional; derived values (thumbnails,
minimums) are recomputed rather than trusted; and the only destructive action in the
product (clear reports, restore backup) must state what it will destroy before it does it.

**NFR6 — Sub-second export.** Generating a report with 20 attachment pages must stay under
one second on a mid-range phone, because inspectors export several reports per site visit
(measured in §7.5).

**NFR7 — Deployable by a non-specialist.** Nginx, IIS or the bundled static server; the only
non-obvious requirement is a correct MIME type for `.mjs`.

## 4.4 Scope decisions

Scope was set with the client in writing (the confirmed requirement set supersedes the
original document). Six items were discussed and deliberately excluded:

| Excluded | Why |
| --- | --- |
| User accounts and login | A single-inspector, single-device tool; accounts would add a server and a password-recovery path for no field benefit. The report person is taken from a local profile instead. |
| Quick notes (free-text capture) | The client confirmed the workflow does not include an intermediate notebook; notes would have created a second, unsynchronised store. |
| Statistics dashboards | Already produced in the client's spreadsheet workflow; duplicating them in the app would create two sources of truth. |
| Department code / employee number | Only meaningful with accounts. |
| Single-report JSON export | Marked optional in the original requirement; no consumer was identified. |
| Coating-thickness and glass-panel modules | Different instruments and different report templates; out of this project's vertical slice. |

## 4.5 Acceptance criteria

Acceptance was defined before implementation as eight testable statements: (1) both
templates record and export with the minimum computed automatically; (2) an empty
requirement clause prints as "none" rather than a blank cell; (3) the exported document
matches the client's report with zero differences across three independent comparison
gates; (4) attachment pages are one per page with a nine-row information table and an
"(n/total)" title; (5) data lives only on the device and survives a backup/restore round
trip including originals; (6) the tool works offline; (7) it is usable on a real phone,
keyboard and back key included; (8) the delivery package deploys on a plain static host.
§7 reports these against measured evidence; §8 maps them back to requirements.

## 4.6 Alternate solutions and selection rationale

Five architectures were considered before the design in §5 was fixed. They are compared against
the criteria that actually decide this project — not against generic criteria such as "modern"
or "scalable", but against the six properties a delivery to this client depends on (Table 4.3).

**A1 — Native Android application (Kotlin, Room, system camera).** The strongest option on
device integration: the camera, the file system and background behaviour are all first-class,
and a native app can write to the Downloads folder without a plugin. It fails on two criteria.
Distribution is the first: the client's IT function has no store channel, so an APK would have
to be handed out and updated by hand anyway — exactly what the eventual solution also does, but
without the compensating advantage. Report fidelity is the second and decisive one: the
document-generation problem would have had to be solved from scratch in a Kotlin OOXML library
of unproven maturity, discarding both the verified Python implementation and the frozen
baseline that made fidelity measurable. The fidelity risk was the project's central risk; a
platform choice that multiplies it was rejected on that ground alone.

**A2 — Server-based application (extend the existing Flask implementation).** This was the
cheapest possible route: the reference implementation already existed and already produced the
accepted report. It fails on the field criterion. Inspectors work on scaffolds and in unfinished
floors with no usable mobile data; a server-mediated application solves the office step and
leaves the site step — the error-prone one — on paper. It also fails the client's IT posture: a
server, a database and a backup job are exactly the operational burden the institute wanted to
avoid. A hybrid (local-first with optional sync) was noted as the natural future extension
rather than the first delivery.

**A3 — Desktop application (Electron or Tauri with a local database).** Good file-system access
and a familiar desktop feel, and it would have reused the Python engine through a bundled
runtime. It fails the device criterion outright: inspectors carry phones, not laptops, and the
tool's whole point is to capture at the member being measured.

**A4 — A low-code form platform or a commercial inspection SaaS.** Fastest to a working form, and
it would have provided multi-user access and dashboards for free. It fails the fidelity
criterion: the deliverable is a Word document with a fixed layout, and no form platform emits
that document attribute by attribute. Buying the capability was also inconsistent with the
client's constraint that data must not leave the device.

**A5 — Offline-first PWA with IndexedDB (selected).** One codebase; installable without a store;
no server; and — critically — the document engine runs in the same JavaScript runtime as the rest
of the application, so the layout specification and the gate harness could be carried over intact
from the Python reference. The costs are real and were accepted: storage belongs to the browser
(hence the backup feature), there is no server-side rendering escape hatch (hence §5.3), and iOS
behaviour is unproven (stated as a limitation).

**A6 — PWA with SQLite compiled to WebAssembly, instead of IndexedDB.** Considered inside A5, and
rejected in ADR-2: it adds roughly a megabyte of payload, requires a second persistence model
(origin-private file system for durability), and buys SQL semantics that this data model — four
tables and a blob store — does not need.

**Table 4.3 — Alternatives against the deciding criteria**

| Criterion | A1 Native | A2 Server web | A3 Desktop | A4 Low-code | A5 PWA + IndexedDB |
| --- | --- | --- | --- | --- | --- |
| Works on site with no network | yes | **no** | yes | depends on vendor | yes |
| Reachable report fidelity | low (new engine) | high (already verified) | high | **very low** | high (verified engine carried over) |
| No infrastructure for the client | APK by hand | **needs server + DB** | installer | vendor subscription | folder + APK |
| Reuses the verified layout work | no | yes | yes | no | yes |
| Single codebase to maintain | no (Android only) | yes | no | n/a | yes |
| Platform risk accepted | Android fragmentation | server drift | OS/runtime drift | vendor lock-in | browser storage, iOS |

**Selection rationale.** The deciding criterion was not convenience but *reachable fidelity*.
The acceptance condition is attribute-level equality with the client's report, and the only asset
the project had that could deliver it was the verified Python engine plus its frozen baseline.
A5 was the single option that preserved that asset while satisfying the field constraint (no
network) and the client's infrastructure constraint (no server). Every candidate that scored
better on some axis — A1 on device integration, A2 on cost, A4 on time-to-form — scored worse on
fidelity or on the field constraint, and those two were non-negotiable. The decision is recorded
as ADR-1 in §5.6, together with its consequences: device-local data, an explicit backup path, and
a cache-fingerprint update mechanism.

---

## 4.7 Risks and mitigations

Six risks were logged at project planning; two were not logged and materialised anyway. The
table below lists all eight, with the mitigation as planned and, in the last column, what
actually happened — because the gap between those two columns is the project's most honest
result.

**R1 — the client's report might not be reproducible mechanically.** Logged as the project's
top risk, and correctly so. The mitigation was to attempt reproduction in Python *before*
committing to a delivery architecture, to compare attribute by attribute rather than visually,
and to freeze the first output that matched as a baseline. It was the right mitigation and it
was still underestimated by a factor of three: closing the diff took four rounds and eleven
distinct patch families.

**R2 — data loss on the device.** Browser storage can be evicted, and uninstalling an Android
package deletes its data. The mitigation was a whole-database backup, an explicit request for
persistent storage, and no destructive action without a confirmation that states its blast
radius. The mitigation was correct and, for a period, decorative: the restore path itself was
broken and untested (§6.8, class 3). A mitigation that is never executed is a plan, not a
control.

**R3 — the runtime gap between the development environment and the phone.** Logged late and
vaguely ("test on a phone before delivery"). It materialised twice — an export that required a
Node global, and an entry point that only the real application used — which is what turned the
vague mitigation into the environment ladder of §7.5.

**R4 — scope creep.** The client's wider product line includes coating-thickness and glass-panel
inspection, either of which would have doubled the report engine. The mitigation was a written
scope confirmation, a traceability matrix with row-level status, and a standing rule that a new
requirement displaces an existing one rather than joining it. Three modules were removed by
agreement; no module was added.

**R5 — sponsor availability.** Sign-off gates a deliverable that depends on a third party's
calendar. The mitigation was to prepare the acceptance documents early, to keep the acceptance
criteria testable rather than narrative, and to present evidence measured before the meeting
rather than after it.

**R6 — single-person team.** The bus factor is one. The mitigation was not documentation
volume but reproducibility: one command reproduces every gate, the version is single-sourced,
and the package rebuilds from a script. The risk remains for maintenance after handover.

**R7 — Android distribution and signing (not logged).** Two days were lost to a CI pipeline
that generated a fresh debug keystore on every run, making each build un-upgradable over the
last one. The lesson is recorded as Lesson 5 in §8.7.

**R8 — file-system and permission behaviour on Android 10+ (not logged).** Writing an export
to a shared folder is a permission-sensitive operation whose rules changed with scoped storage.
The mitigation was adopted during implementation rather than planned: use the media store,
with a share-sheet fallback and a toast that names the path.

**Table 4.4 — Risk register with outcomes**

| # | Risk | Mitigation as planned | What happened |
| --- | --- | --- | --- |
| R1 | Report not reproducible | Python spike first; attribute diff; frozen baseline | Materialised at 3× the estimate; closed to zero differences |
| R2 | Device data loss | Backup, persistent storage, guarded destructive actions | Backup existed but restore was broken and untested |
| R3 | Runtime gap (Node vs phone) | "Test on a phone before delivery" | Materialised twice; became the environment ladder |
| R4 | Scope creep | Written scope, traceability matrix, displacement rule | Held; three modules removed, none added |
| R5 | Sponsor availability | Early acceptance documents, testable criteria | Held; signed within the planned window |
| R6 | Single-person team | Reproducible gates, single-sourced version, scripted package | Held during the project; open after handover |
| R7 | Android signing (not logged) | — | Two days of rework; keystore pinned in CI |
| R8 | Scoped storage (not logged) | — | Media-store write with fallback and toast |

---

## 中文对照（§4 审阅要点）

**4.1 利益相关者与现状流程**：写了四类人（现场检测员 / 检测部负责人 / 报告审核与甲方签字人 /
客户 IT）各自真正在意的东西 —— 检测员要"输一次不丢"，负责人要"到手就是对的"，签字人要"和标准
长得一模一样"，IT 要"不用服务器、不用商店"。现状流程的关键论点是：**五个交接、每个都是转录**
（量具→纸→Excel→Word→PDF），最小值被手算两遍、照片靠文件名重选、版式每个项目重建。

**4.2 功能需求**：14 条（R1–R14），每条都配"验收证据"，而不是只写"系统应支持"。

**4.3 非功能**：7 条。NFR1 用"封锁 App 的 UID 流量"来定义，NFR4 把"保真"定义成**逐属性相等**
（不是"能打开、看起来对"），NFR5 把"不丢数据"落到事务与派生值重算。

**4.4 范围**：明确列了 6 项不做 + 每项理由（避免答辩时被问"为什么没有统计"）。

**4.5 验收**：8 条可跑判据，指向 §7/§8。

**需要你确认的两处**：① R3 里"截面尺寸要求"是单条（立柱）/三条（横梁）——与需求 v2 一致；
② 我把"膜厚/玻璃检测"也列在"不做"里（原始需求里它们是别的产品线外观），如果答辩时想强调
"本工具只做幕墙截面+缺陷"，这条留着有用。

# Part C — §5 System Design (~1,500 words)

## 5.1 Architecture overview

The system is a single static artefact with four internal layers and no server process
(Fig. 5.1). The **shell** is plain HTML, CSS and native ES modules loaded through an import
map, with no bundler: `index.html` declares the module graph, and the browser fetches the
same files a developer edits. The **data layer** wraps IndexedDB and is the only module
allowed to open a transaction. The **report engine** builds the document in memory: a
declarative builder assembles tables and runs from the layout specification, the `docx`
library serialises them to OOXML, and a deterministic post-processor rewrites eleven
attribute families so the output matches the approved template exactly. The **cache layer**
is a service worker keyed by a content fingerprint.

**Table 5.1 — Layers, responsibilities and failure modes**

| Layer | Responsibility | Depends on | Characteristic failure |
| --- | --- | --- | --- |
| Shell / views | Routing (hash), rendering, form validation | Data layer, engine | Renders but does not persist (validation passed, write rejected) |
| Data layer | Transactions, indexes, hand-written cascades, migrations | IndexedDB | `TransactionInactiveError` if an awaited promise outlives the transaction |
| Report engine | Spec → table XML, patches, attachment pages | `docx`, layout spec | Valid document that differs from the template by an attribute |
| Cache layer | Offline app shell, version pinning | `SHELL_VERSION` | Serving mixed generations of assets after an update |

Three properties follow from having no server, and they shape everything else. First,
**durability is delegated**: the browser may evict storage, so the product ships an explicit
backup and asks for persistent storage in the UI rather than assuming it. Second, **there is
no natural "share" endpoint**: the export must produce a file on the device and hand it to
the OS. Third, **there is no server-side rendering escape hatch**: everything the report
needs — fonts, styles, theme — must be shipped inside the document. This is precisely why
the fidelity work in §5.3 is architectural rather than cosmetic.

## 5.2 Data model

The database has six object stores: four business tables (`projects`, `records`,
`readings`, `defects`), the binary table `images`, and `meta` for schema version and the
inspector profile (Table 5.2). Business keys are auto-increment integers; `images` is keyed
by content-derived id; `meta` is keyed by name. `DB_VERSION` is 1, and the profile was
placed in `meta` specifically so that adding it did not require a schema migration.

**Table 5.2 — Object stores**

| Store | Key | Indexes | Referential behaviour |
| --- | --- | --- | --- |
| `projects` | `id` (auto) | `project_no` (unique) | Deleting a project deletes its records, readings, and unlinks (not deletes) defect reports |
| `records` | `id` (auto) | `project_id`; compound (`project_id`, `template_type`, `sort_order`) | Deleting a record deletes its readings |
| `readings` | `id` (auto) | `record_id`; unique (`record_id`, `face`) | Leaf table |
| `defects` | `id` (auto) | `project_id`; `risk_level`; `created_at` | `project_id` is nullable; deleting a report unlinks its image |
| `images` | `id` | — | Deleted with its defect report |
| `meta` | `key` | — | Holds `schemaVersion` and the profile |

IndexedDB has no foreign keys, so every cascade is code, and every cascade is written
inside one read-write transaction: deleting a project walks the `project_id` index of
`records`, then the `record_id` index of `readings`, then deletes images for each linked
defect. The alternative — letting the UI delete rows one request at a time — is how orphan
images appear. The same discipline produced three rules that are documented at the top of
the data module and enforced by review: **never await a promise that is not an IndexedDB
request inside a transaction** (canvas encoding, `fetch`, `setTimeout`), because the
transaction closes on the next microtask and the following write throws
`TransactionInactiveError`; **read-modify-write in one transaction**; and **recompute derived
values at write time** instead of trusting what the form displayed.

## 5.3 Report-fidelity design

The client's report is treated as an executable specification, not as a style guide. It
decomposes into three artefacts:

1. **A layout specification in JSON** (`report_layout.json`), language-neutral so that the
   Python reference implementation and the JavaScript production engine read the same
   numbers: page 11 907 × 16 839 twips with margins 1 440/1 843/907 and a document grid
   line pitch of 312; a fixed-layout table 10 833 twips wide, centred, with outer borders
   12 and inner borders 6 eighths of a point and a cell margin of 57 twips per side; eleven
   column widths measured from the client's column table, with an override set for the beam
   table; and the per-cell line spacing used in the header's continuation cells.
2. **A declarative builder** that maps domain records onto the table: one row group per
   detection face, vertical merge for the member columns, and a second merge pass that
   groups consecutive rows sharing the same requirement clause — so one clause is written
   once and centred across its block, while a change of clause starts a new cell.
3. **Eleven deterministic patches** applied to the serialised OOXML (Table 5.3). They exist
   because a general-purpose DOCX library emits *valid* markup, not *identical* markup.

**Table 5.3 — The eleven post-processing patches**

| # | Attribute family | Library output vs. approved template | Patch |
| --- | --- | --- | --- |
| ① | `w:docGrid` | line pitch differs | rewrite to the specified pitch |
| ② | `w:tblLook` | no `w:val`, booleans spelled `true`/`false` | insert `w:val`, normalise to `1`/`0` |
| ③ | `w:trHeight` | carries `w:hRule` | drop the attribute |
| ④ | `w:tblCellMar` | declares edges the template does not | keep only declared edges |
| ⑤ | Continuation cells of merged rows | bare `<w:p/>`, no vertical alignment | add `vAlign=center`, centred paragraph, header line spacing |
| ⑥ | `word/styles.xml`, `word/theme/theme1.xml` | library defaults | replace with the base template's parts |
| ⑦ | `w:sectPr` | no `<w:cols>` | insert `<w:cols w:space="720"/>` in schema order |
| ⑧ | `w:pgSz` | writes `w:orient="portrait"` | drop the attribute |
| ⑨ | `w:trPr` | no row-level justification | add `<w:jc w:val="center"/>` per row |
| ⑩ | `w:tblBorders` | no `w:space` on edges | add `w:space="0"` to each edge |
| ⑪ | `w:vMerge` | writes `val="continue"` explicitly | reduce to `<w:vMerge/>` |

Patch ⑪ is the one that taught us the most, and it is worth stating plainly. `val="continue"`
and an absent `val` are **semantically identical** in OOXML. Our first comparator normalised
the two forms and reported no difference; our second comparator — the one that reconstructs
the merge grid — treats "no value" as the only signal for a continuation cell, and therefore
reported the whole table as structurally wrong. Both comparisons were correct; only their
domains differed. The lesson generalises beyond this project: when fidelity is the goal,
"equivalent" is not good enough, because *some* consumer of the document will compare the
literal encoding. Patches are therefore written to produce byte-identical markup, and the
gate that catches literal differences is kept precisely because it disagrees with the
semantic one.

## 5.4 Image pipeline

Photographs arrive from a phone camera, which means they arrive with EXIF orientation flags
and are larger than anything the report needs. The pipeline is: validate size (≤ 20 MB) and
type; decode; apply the EXIF orientation transform; downscale only if a cap applies; and
store the original bytes as a `Blob` in `images`, untouched.

Two decisions matter. **The original is preserved** so that a future report template with a
larger image box does not require re-photographing the site; the thumbnail is treated as a
derived value and can be rebuilt for the whole database from the originals, which the
"rebuild thumbnails" maintenance action does. **Orientation is baked in during re-encoding**:
we read the orientation tag (values 1–8, of which 5–8 swap width and height), compute a
canvas transform rather than rotating pixels in place, and write a fresh JPEG. Re-encoding
discards the EXIF block, which is exactly what we want — a document viewer that ignores EXIF
will still display the photograph upright. Thumbnails are capped at 240 px on the long edge
at quality 75, small enough that a list of reports scrolls smoothly on a low-end device.

## 5.5 Offline and update strategy

The app shell is cached by a service worker whose cache name is derived from a
**content fingerprint** — a 12-hex-digit hash of every shell asset, generated at build time
so it cannot drift from the assets it describes. A new deployment therefore produces a new
cache name and a new install; an unchanged deployment produces no churn.

Three rules govern updates. **No automatic `skipWaiting`.** A newly installed worker waits
until every tab is closed, because activating mid-session would mix generations of ES
modules (a cached `main.js` importing a fresh engine) and produce failures that are
impossible to reproduce. **The shell is served cache-first**, and the cache is the unit of
consistency: either the whole generation is present or the browser keeps the old one.
**The native (Android) build does not register a service worker at all**: its assets come
from the package, so a worker would add a second, competing cache. In a session recorded with
the device's traffic blocked, all 30 requests were served from the installed generation and
none left the device.

## 5.6 Design decisions (ADRs)

**ADR-1 — No back-end; the product is a static directory.** *Context:* the client has no
server budget and no store-distribution channel. *Alternatives:* a small Flask/SQLite
service; a hosted BaaS. *Decision:* static files only, with storage in the browser.
*Consequences:* zero operational cost and true offline operation, at the price of
device-local data (hence backup/restore) and of losing server-side rendering — which pushed
document generation entirely into the client and made §5.3 the project's hardest problem.

**ADR-2 — IndexedDB rather than `localStorage` or SQLite-WASM.** *Context:* the data model
is relational (projects → records → readings), includes binary photographs, and must survive
partial writes. *Alternatives:* `localStorage` (synchronous, ~5 MB, strings only); a WASM
SQLite build (a ~1 MB payload and a second persistence model to reason about). *Decision:*
IndexedDB, wrapped in a single transactional module. *Consequences:* native indexes and
blobs, asynchronous APIs that force explicit transaction discipline — the source of three
documented traps — and a database that is inspectable in devtools, which turned out to be
the single most useful debugging affordance of the project.

**ADR-3 — Use a DOCX library and patch its output, rather than hand-writing OOXML.**
*Context:* fidelity is required at the attribute level. *Alternatives:* emit the XML by
hand (total control, unbounded surface area); accept the library's output (fast, wrong in
eleven attribute families). *Decision:* library for structure, then a deterministic
post-processor for the eleven families. *Consequences:* the diff surface is small, named,
and testable — `verify_docx_patches.py` re-checks all eleven after any library upgrade —
while the fragile part is pinned to a version and guarded by a test that fails loudly.

**ADR-4 — Three independent fidelity gates instead of one.** *Context:* a single comparator
can be self-consistent and still blind. *Alternatives:* one golden-file comparison.
*Decision:* three comparisons with different domains and different blind spots — a frozen
baseline (Gate A), the client's real report (Gate B, differential testing against a
human-authored oracle), and a Python-free fingerprint self-check (Gate C). *Consequences:*
three times the maintenance, and each gate has caught a defect the others missed —
including the `vMerge` case in §5.3, where agreement between two of them would have hidden a
structural error.

**ADR-5 — Content-fingerprint cache versions with manual activation.** *Context:* inspectors
keep the app open in the background for days. *Alternatives:* timestamp-based cache busting;
automatic activation of new workers. *Decision:* hash-named caches plus deliberate
activation. *Consequences:* no mixed-generation failures and a reproducible "which version is
this phone running?" answer on the About page, at the cost of an explicit "close all tabs"
step that must be documented for users.

---

## 中文对照（§5 审阅要点）

**5.1 架构**：一张图四层（壳 / 数据层 / 报告引擎 / 缓存），并强调"没有服务端"派生出的三条
性质：耐久性外包给浏览器（所以要备份+持久化授权）、没有天然分享端点（要写文件交给系统）、
没有服务端渲染兜底（字体样式主题必须打进文档 —— 这也是 §5.3 是架构问题而不是美工问题的原因）。

**5.2 数据模型**：6 个 store（4 张业务表 + images + meta），3 条事务纪律（**绝不在事务里
await 非 IDB 的 promise**、读改写同事务、派生值写入时重算）。级联全靠手写且必须同事务 ——
否则就出现孤儿图片。

**5.3 保真设计**：把客户报告拆成三件东西：**语言中立的版式 JSON**（页码尺寸 11907×16839、
页边距、docGrid 312、表宽 10833、边框 12/6、单元格边距 57、11 列宽 + 横梁覆盖）、**声明式
构建器**（按面分行、构件列纵向合并、相同条文合并、条文变了就断开）、**11 个确定性补丁**。
第 ⑪ 个补丁（vMerge）是全文最有价值的一段：`val="continue"` 与不写 val 语义相同，但两个
比较器一个归一化、一个不归一化 → **"等价"不够，必须写成一样的字节**。

**5.4 图片管线**：20MB 上限 → 解码 → 按 EXIF 1–8 做 canvas 变换（5–8 交换宽高）→ 重编码
（丢 EXIF 是好事）→ 原图原样存 Blob、缩略图 240px/质量 75 且可整库重建。

**5.5 离线与更新**：SHELL_VERSION 是**内容指纹**（12 位十六进制），缓存名跟着它走；
**不自动 skipWaiting**（否则 ES 模块混代，故障不可复现）；原生壳内不注册 SW（否则会有第二个
竞争的缓存）。

**5.6 五条 ADR**：无后端 / IndexedDB / 库+补丁 / 三道闸门 / 指纹化缓存 + 手动激活。每条都
写了"选项—取舍—代价"。

**需要你确认**：ADR 我选了 5 条（骨架里列了 6 条，我把"版本号单一真相源"并进了 ADR-5 的
consequences）。如果你希望第 6 条独立成条（`product.js` 作为版本单一真相源），我单独补一段。

---

## Numbers used in this draft (for the fact-check pass)

| Figure | Where it appears | Source |
| --- | --- | --- |
| 348 Python tests | §4.2 R1 evidence | `tools/verify_all.py` step description |
| 250 front-end tests | §4.2 R1 evidence | `npm test` (node --test) |
| 16 gates | §4.5, §5.6 | `tools/verify_all.py` (16 entries) |
| 21 desktop E2E cases | §4.2 | Playwright run against the delivery package |
| 14 on-device assertions | §4.3 NFR3 | Android verification checklist |
| 9 defects fixed | §7 (not in this draft) | Acceptance report repair table, rows 1–9 |
| Page 11 907 × 16 839 twips; table 10 833; borders 12/6; cell margin 57; docGrid 312 | §5.3 | `web/assets/report_layout.json` |
| 20 MB image cap; thumbnail 240 px @ q75 | §5.4 | `web/app/config.js` |
| 30 requests, 0 external | §5.5 | blocked-UID offline session |
