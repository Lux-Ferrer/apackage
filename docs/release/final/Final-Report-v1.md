# Abstract

Field inspectors at a building-research institute record curtain-wall cross-section
measurements and defect findings on paper, then re-type them into a fixed corporate Word
template at the office. The re-typing introduces transcription errors, the five-reading
minimum is computed by hand twice, and the report layout is rebuilt for every project. This
applied project delivered a server-less, offline-first mobile web application that removes
that step: inspectors capture five thickness readings per detection face with the minimum
computed automatically, photograph defects, and generate the client's existing Word
inspection report — including defect-report attachment pages — directly on the phone.

The main technical risk was fidelity. "Looks the same" is not the same as "is the same", and
a general-purpose document library emits valid markup, not identical markup. The project
therefore treated the sponsor's report as an executable specification and built three
independent comparison gates over a language-neutral layout specification plus eleven
deterministic post-processing patches: a frozen baseline, a comparison against the client's
real report, and a Python-free structural self-check. All three report zero differences, and
a seven-case poisoning harness confirms that each gate fails on the right attribute, not
merely that it fails.

Verification then moved one environment closer to the user at a time, and this is where the
project's most transferable finding lies: nine defects that reached a user-facing
environment were all found by the layer above the one that was green, including three
priority-0 faults — an application that could not start, an export that crashed only in a
browser, and a backup import that had never been executed by any test. The result is a
reproducible delivery package (static web bundle plus Android package) with a recorded
SHA-256, a deployment guide and an end-user manual, in use on real devices without any
back-end service.

**Keywords:** curtain-wall inspection; offline-first PWA; document fidelity; differential
testing; field data collection; mobile web


# List of figures

| Number | Title | Page |
| --- | --- | --- |
| Figure 5.1 | System architecture: the frozen reference implementation and the offline client | 26 |
| Figure 7.1 | Gate sensitivity: seven poisoned documents, each caught at a specific comparison path | 45 |
| Figure 7.2 | Fidelity gate A convergence: 201 → 33 → 2 → 0 differences over four rounds | 46 |

# List of tables

| Number | Title | Page |
| --- | --- | --- |
| Table 4.1 | As-is versus to-be process | 15 |
| Table 4.2 | Functional requirements (core) | 16 |
| Table 4.3 | Alternatives against the deciding criteria | 21 |
| Table 4.4 | Risk register with outcomes | 24 |
| Table 5.1 | Layers, responsibilities and failure modes | 25 |
| Table 5.2 | Object stores | 26 |
| Table 5.3 | The eleven post-processing patches | 28 |
| Table 7.1 | The verification layers | 42 |
| Table 7.2 | What each gate compares, and what it cannot see | 44 |
| Table 7.3 | The seven poisons | 45 |
| Table 7.4 | What jsdom cannot see | 47 |
| Table 7.5 | The nine defects | 50 |
| Table 7.6 | Measured performance | 51 |
| Table 8.1 | Requirement coverage at acceptance | 54 |

# Abbreviations

| Abbreviation | Expansion |
| --- | --- |
| ADR | Architecture decision record |
| API | Application programming interface |
| CDP | Chrome DevTools Protocol |
| CI | Continuous integration |
| DOCX / OOXML | Office Open XML (WordprocessingML) document format |
| E2E | End-to-end (test) |
| EXIF | Exchangeable image file format (camera metadata) |
| IndexedDB | Browser-native transactional object database (W3C) |
| jsdom | A JavaScript DOM implementation used for unit tests, not a browser |
| PWA | Progressive web app |
| SW | Service worker |
| WBS | Work breakdown structure |
| WASM | WebAssembly |

# Acknowledgements

I sincerely thank my project sponsor at MCC Central Research Institute of Building and
Construction (Shenzhen) Co., Ltd. for the opportunity to conduct this applied project, and for
supplying the element that made it possible: the institute's actual delivered inspection report,
rather than a description of it.

I thank my course professor for the Applied Technical Project course and for the mentoring that
shaped this work, and the instructors of the NYU SPS Master's program in Management and
Systems, from whom I learned how to ask whether a system is *right*, not merely whether it runs.

I also thank the inspection engineers who walked me through their field process and answered
questions about details that no requirements document would have contained.

# Declaration

I grant powers of discretion to the Department, SPS, and NYU to allow this paper to be copied in
part or in whole without further reference to me. This permission covers only copies made for
study purposes or for inclusion in Department, SPS, and NYU research publications, subject to
normal conditions of acknowledgement.

Zeyu Jin
New York, November 2026

---

# §2 Introduction

## 2.1 Context

Curtain-wall inspection is a measurement discipline with a documentary output. An inspector
stands in front of a façade — on a scaffold, at the edge of a floor slab, inside a lift shaft
— and measures the aluminium profiles of vertical mullions and horizontal transoms with a
coating-thickness gauge, taking five readings on each detection face. Separately, the
inspector photographs defects: cracked or missing glass panels, sealant failure, corroded
fixings. Both bodies of evidence end up in one deliverable, a Word inspection report that the
institute signs and hands to the building owner, and that is subsequently used as contractual
evidence when a defect is disputed.

The client for this project is the Shenzhen branch of MCC Central Research Institute of
Building and Construction, a core research and testing institute of MCC (Metallurgical
Corporation of China), part of the China Minmetals group — a Fortune Global 500 enterprise. The
institute holds national and provincial qualifications for building-safety and curtain-wall
testing and carries a substantial share of such commissions in its region; its curtain-wall group
inspects façades for owners and main contractors. The report it issues is standardised: a fixed
table layout, prescribed requirement clauses quoted verbatim from the technical code, and — when
defects were found — attachment pages, one per defect report, each carrying a nine-row
information block and a photograph. That the deliverable is issued under a qualification, and not
merely under a letterhead, is why its form is not negotiable.

The project was also delivered across twelve to thirteen hours of time difference: the author
worked from New York, the client is in Shenzhen, and the two formal working sessions were held
online and supplemented by continuous day-to-day communication in a chat group. A former colleague
at the institute supplied the de-identified baseline used throughout this paper — the report
template and one delivered report with its attachment pages — which is the only way a remote
student could work against the real artifact rather than against a description of it. Charter,
work-breakdown structure, planning, design, implementation, verification and acceptance were
carried out by one person acting as both project manager and implementer.

## 2.2 Problem

The measurement is digital only at its two ends. In between sits a chain of transcription:
gauge display → paper form → spreadsheet → Word template → print or PDF. Each hand-off is a
place where a digit can change. The five-reading minimum is recomputed by hand at two of
them. Photographs are transferred through a chat application and later re-selected by
filename. The table layout is rebuilt for each project, because the corporate template is
*edited* rather than *instantiated*, and an edited template drifts.

Three constraints make the obvious fix unavailable. The inspectors work where there is no
usable mobile data, so a cloud form does not solve the problem on site. The institute's IT
function has no budget for a new server and no administrative rights over inspectors' personal
phones, so a hosted application is out. And the deliverable is not merely "a report": its
layout is contractually fixed, so any tool that produces a *nearly* identical report has made
the problem worse, not better, by adding a second house style to reconcile.

## 2.3 Importance of the project to the organization

The importance is easiest to state in the terms the institute uses internally: the report is what
gets invoiced and what gets audited.

*Commercially*, an inspection engagement closes when the report is accepted, and a returned report
costs the institute twice — once to re-open the record, once to re-sign the document. The
transcription chain described above is where those returns originate: a digit re-typed, a minimum
recomputed by hand, a photograph attached to the wrong record. The tool removes three of the five
hand-offs and both manual minimum computations, and it removes the *reason* for the remaining two,
because the report is generated from the same data that was captured. No controlled time study was
conducted (stated as a limitation in §8.4), so no percentage is claimed here — but the mechanism by
which rework arises is removed rather than reduced.

*Reputationally*, the institute issues reports under national and provincial qualifications, and a
report is a document that other parties rely on. A tool that produced a *second* house style would
be a liability that no efficiency gain could offset; the acceptance criterion of this project is
therefore attribute-level equality, not resemblance.

*Institutionally*, the layout specification turns a piece of institutional knowledge — the form of
the report — into a versioned artifact that can be reviewed, changed deliberately, and reused by
other groups. That is a different kind of value from a faster form: it makes the deliverable's form
governable.

Finally, the delivery context itself is evidence for the organization. A remote, single-person
engagement across a twelve-hour time difference that meets the same acceptance bar as a co-located
team engagement says something about how the institute might commission digital work in future: the
constraints that made this project hard — no server, no app store, no colleagues in the same room —
are the constraints under which distributed delivery happens at all.

## 2.4 Objectives

Three objectives follow directly, and they are the ones against which the project was
accepted:

1. **Capture once, on the phone, with no network.** A complete session — create a project,
   record both component types, file defect reports with photographs, export the report,
   export a backup — must succeed with the application's traffic blocked.
2. **Reproduce the report attribute by attribute.** The generated document must equal the
   approved template in table width, border weights, cell margins, row alignment, merge
   encoding and style parts, not merely "open and look right".
3. **Prove it, rather than assert it, in environments that keep getting closer to the user's.**
   Fidelity and usability claims must be backed by comparisons that could fail, in a browser
   rather than a DOM emulator, and on a phone rather than a desktop.

## 2.5 Contributions

The project offers three contributions, ordered by how transferable they are.

**A way to make "the deliverable's format" an executable requirement.** The client's report is
treated as the specification; a language-neutral layout description plus a fixed set of
deterministic post-processing patches reproduces it exactly; and three comparison gates with
disjoint domains assert equality continuously. The sensitivity harness is part of the
contribution: it asserts not only that a gate fails on a poisoned document, but *where* it
fails, which is what distinguishes a real comparison from a decorative one.

**An environment ladder, and the arithmetic of what it finds.** Verification moved from a DOM
emulator to a real desktop browser to a real Android device, and nine defects — three of them
priority 0 — were found by the layer above the one that was green. The defects are not
anecdotes: each is documented with its root cause, the reason the cheaper layer could not see
it, and the guard that now exists. The distilled rule is two questions asked of any green
run: *was this attribute actually compared, and is this environment the same as the user's?*

**A delivery pattern for server-less field tools.** With no back-end, durability, sharing and
upgrading all become the client's problem, and the project answers each concretely: a
whole-database backup that includes originals, an Android channel that writes to the public
Downloads folder, and a content-fingerprinted cache that never mixes generations.

**A documented, single-person delivery of a full project lifecycle.** The same person acted as
project manager and implementer, remotely, against a client twelve hours away: charter and
work-breakdown structure (Appendix E), baseline against actual schedule, requirements
traceability, monthly status reporting, architecture, implementation, verification, the
end-user manual and the acceptance documents. The artifacts are included as appendices, not
asserted, and §8.6 critiques the order in which they were produced.

The novelty claim of this paper is deliberately narrow, because the components are not new:
service workers, IndexedDB and JavaScript document generation are each mature. What we did not
find in the literature, and what this project contributes, is their combination under an
*equality* requirement — **we are not aware of a published inspection tool that reproduces a
corporate Word report attribute by attribute, offline, in the browser.**

## 2.6 Structure of the paper

§3 reviews the literature on field data capture, offline-first delivery and document fidelity
testing, and identifies the gap this project addresses. §4 derives stakeholders, requirements
and scope from the client's process. §5 presents the architecture, the data model, the
fidelity design and five architectural decisions. §6 describes the implementation and the
traps that only appear once the code runs. §7 is the evaluation: the three gates, their
sensitivity, and the environment ladder with the nine defects. §8 maps results back to
requirements, discusses what worked, and states the limitations. §9 concludes.

---

# §3 Related work

## 3.1 Field data capture in construction

Construction-informatics research has spent two decades moving site data from paper into
information systems, and the dominant architecture is BIM-centered and server-mediated. Park
et al. (2013) frame defect management as a problem of *data-collection templates* linked to a
BIM model, arguing that the ontology of a defect record determines what can later be
reasoned about; Ma et al. (2018) combine BIM with indoor positioning so that a captured record
knows where it was captured. Both are convincing on the value of structured capture, and both
assume an infrastructure this client does not have.

The adoption literature is more sobering and more useful here. Davies and Harty (2013),
studying "Site BIM" on a large hospital project, document how site staff reshape a digital tool
to fit existing practice, and how a tool that does not fit is quietly abandoned rather than
rejected. Sacks et al. (2018) make the complementary point at the level of deliverables:
exchange requirements — what a document must contain and in what form — are part of the
information specification, not an afterthought to it.

This project sits inside that literature but inverts its priorities. There is no BIM model to
link to and no server to link through; the deliverable's *format* is the specification that
matters, because a report in the wrong format is rejected regardless of the quality of the data
inside it. That inversion is what makes the fidelity problem (§3.3) the center of the work
rather than an output-formatting detail.

## 3.2 Offline-first delivery and progressive web apps

The case for progressive web apps as a cross-platform delivery mechanism is well documented.
Biørn-Hansen et al. (2017) describe the architectural ingredients — app shell, service worker,
cache — and Majchrzak et al. (2018) evaluate the approach against native development, noting
both the reduced distribution cost and the platform-specific limits, storage eviction and iOS
behavior among them. The normative foundations are equally clear: the Indexed Database API
(W3C, 2018) defines the transactional storage model used here, and practitioner catalogues
such as Archibald's (2019) offline cookbook enumerate the caching strategies that a service
worker can implement.

What this literature says less about is the *consequence* of having no server at all. Once the
back-end disappears, three ordinary functions lose their home: durability (there is no backup
job, so the user must be given one), sharing (there is no upload endpoint, so the artifact must
be written to the device and handed to the operating system), and upgrading (there is no
deployment pipeline in the usual sense, so cache invalidation becomes the release mechanism).
The design in §5.5 and the release engineering in §6.6 are responses to those three
consequences, and the "no automatic activation" rule in particular is a direct consequence of
ES modules being cached individually.

## 3.3 Proving document fidelity

The testing literature supplies the vocabulary for what this project had to do. McKeeman
(1998) introduced differential testing: run two implementations on the same input and compare
their outputs, using one as an oracle for the other. Gate B (§7.2) is differential testing with
a human-authored oracle — the client's actual delivered report. Feathers (2004) names the
complementary technique: when no specification exists, freeze the current behavior as a
characterization test and defend it. Gate A is exactly that, applied to a document. Chen et
al. (1998) contribute the third idea, metamorphic testing: when the correct output for a
mutated input is unknown, assert a *relation* instead. The poisoning harness (§7.3) is
metamorphic in this sense — we do not know what a correct rendering of a corrupted document
looks like, but we know the gate must fail, and we know which attribute it must fail on.

On the document side, the specification is explicit and public: ECMA-376 (Ecma International,
2021), also published as ISO/IEC 29500, defines every attribute that the eleven patches touch,
from the document grid to the vertical-merge encoding. The practical problem is that
general-purpose generators — `python-docx` (Canny, 2013) and the JavaScript `docx` library
(Miu, 2024), the two used here — implement the schema faithfully but make independent choices
wherever the schema permits alternatives. A document can therefore be perfectly valid and
still differ from an approved template in dozens of attributes.

The gap, then, is a framing gap. The literature treats document generation as an API
correctness problem ("does the file open, does it contain the values?") and rarely as an
*equality* problem ("is every attribute the same as the accepted document?"). Where equality
is discussed, it is usually visual regression on rendered pages, which introduces fonts and
pagination and is therefore expensive to run in continuous integration. This project's
contribution is to make equality an executable, cheap, structural assertion — and then to
prove that the assertion is sensitive.

## 3.4 Situational analysis

The literature says what is possible; the situation says what is worth doing. This section is a
qualitative analysis of the position the product occupies, conducted from the project's own
fieldwork (two formal online working sessions plus continuous day-to-day communication with the
client's inspection group) rather than from market
data. No market-sizing study was commissioned, and no figure in this section is a market
estimate; the analysis is structural, and it is reported as such.

**Buyers and the shape of demand.** The demand for curtain-wall inspection reports comes from
building owners, main contractors and property managers, and it is *regulatory in origin*: a
façade must be evidenced as compliant before hand-over and again before major works. The
institute is paid per engagement, and the report is the artifact that closes it. That has a
sharp consequence for a tool: the report is not a record of work, it is the deliverable that
gets invoiced and, later, litigated over. Anything that changes its appearance is a commercial
risk, which is why "fidelity" appears in this paper so often and "features" so rarely.

**Porter's five forces, applied to the tool's niche.** *Threat of substitutes* is high and
closer than it looks: the incumbent is a Word template plus manual typing, which costs nothing
to keep and is already trusted. A tool competes with a habit, not with a product. *Bargaining
power of buyers* is high: a single institute decides, its inspectors adopt or quietly do not,
and the switching cost of a rejected tool is a lost project rather than a lost license.
*Bargaining power of suppliers* is low in components — the stack is open source and replaceable
— but high in platforms: the rendering of the Word document is ultimately controlled by
Microsoft's implementation, and offline behavior by the WebView version shipped on the
inspector's phone. Those two suppliers cannot be negotiated with, only measured against.
*Threat of new entrants* is high at the feature level: a form with photographs is a
weeks-long build for any competent team. The defensible part is not the form, it is the
machinery that makes the output identical to the accepted document, which is expensive to
discover and cheap to copy once discovered. *Rivalry* is intense among BIM and inspection SaaS
vendors, but it is rivalry on a different axis — integrations, dashboards and cloud
collaboration — and it leaves the specific problem of this project (one inspector, no network,
one fixed Word layout) largely unaddressed.

**SWOT.** *Strengths:* the deliverable's format is reproduced attribute by attribute and the
claim is backed by three gates; the tool needs no infrastructure, so procurement is a folder and
an APK; the layout specification is data, so a second client's template is a configuration
exercise rather than a rewrite. *Weaknesses:* the data is device-local, so there is no
collaboration and no central audit trail; the product is Android-first with untested iOS
behavior; the team is one person, which bounds both the feature set and the bus factor.
*Opportunities:* other institutes in the same group issue structurally similar reports, so the
same engine with a different layout specification is a plausible product; the inspection
workflow is regulated and therefore stable, which rewards durable tooling over novelty; and the
fidelity method transfers to any regulated document (test reports, certificates, acceptance
records). *Threats:* platform drift — a Word update, a WebView change, a browser storage policy
change — can invalidate assumptions that took weeks to establish; the incumbent habit can win by
inertia if the first field week is not smooth; and a client-side-only tool has no answer to a
procurement requirement for central audit, which is a plausible future requirement in a
state-owned institute.

**What the analysis changed in the project.** Two decisions were made because of this analysis
rather than because of the requirements. The fidelity work was put *first* — before any user-
interface polish — on the grounds that it is the only defensible part of the offer and the only
thing the incumbent cannot trivially match. And the backup mechanism was treated as a
first-class feature rather than a maintenance utility, because the SWOT weakness "data is
device-local" is not an inconvenience in this market, it is an existential objection that a
reviewer will raise in the first meeting.

## 3.5 The gap this project addresses

Two gaps motivate the work. First, fidelity is under-specified in practice: teams assert
"the report looks right" and discover otherwise at the client's desk. Second, and less
commonly reported, test environments are systematically more permissive than production
environments, and the resulting defects are invisible to the suites that are supposed to catch
them. The literature on testing discusses environment fidelity in general terms (test doubles,
emulation, staging); it says little about the specific case where the *runtime* differs — a DOM
emulator versus a browser, a desktop browser versus a phone — and where each step of realism
has a measurable defect yield. §7.5 reports that yield for this project: nine defects, three of
them blocking, all found in the step above the green one.

A second, narrower gap bounds the claim of this paper. **We are not aware of a published
inspection tool that reproduces a corporate Word report attribute by attribute, offline, in the
browser.** The ingredients — a service worker, IndexedDB, an in-browser document generator — are
each documented individually; what is absent is their combination under an equality requirement,
and the verification method that makes such a claim testable rather than rhetorical.

---

---

# §4 Requirements and analysis

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

Requirements were elicited from the client's existing report and from two formal online
working sessions with the inspection group, then frozen in a traceability matrix. That matrix
holds **forty-six in-scope requirement rows** — forty-three implemented as specified, two
implemented with an agreed adaptation, one optional item not built (Table 8.1) — which is more
granular than a reader needs. Table 4.2 therefore groups those rows into the **fourteen
capabilities** that the rest of the paper refers to; each R-number below stands for one to four
matrix rows of the same capability. "Evidence" names the artifact that demonstrates the
requirement rather than asserting it.

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
| R13 | About page exposing product name, version, offline-cache fingerprint and issuing organization | E2E |
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
device integration: the camera, the file system and background behavior are all first-class,
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
behavior is unproven (stated as a limitation).

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

**R8 — file-system and permission behavior on Android 10+ (not logged).** Writing an export
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


# §5 System design

## 5.1 Architecture overview

The system is a single static artifact with four internal layers and no server process
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

![Figure 5.1 — System architecture. Left: the frozen Flask reference implementation that produced the accepted report. Right: the offline client that had to reproduce it. Both write the same Word document from the same layout specification; the difference is where the work and the data live.](deliverables/prp/architecture.png)

## 5.2 Data model

The database has six object stores: four business tables (`projects`, `records`,
`readings`, `defects`), the binary table `images`, and `meta` for schema version and the
inspector profile (Table 5.2). Business keys are auto-increment integers; `images` is keyed
by content-derived id; `meta` is keyed by name. `DB_VERSION` is 1, and the profile was
placed in `meta` specifically so that adding it did not require a schema migration.

**Table 5.2 — Object stores**

| Store | Key | Indexes | Referential behavior |
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
decomposes into three artifacts:

1. **A layout specification in JSON** (`report_layout.json`), language-neutral so that the
   Python reference implementation and the JavaScript production engine read the same
   numbers: page 11 907 × 16 839 twips with margins 1 440/1 843/907 and a document grid
   line pitch of 312; a fixed-layout table 10 833 twips wide, centered, with outer borders
   12 and inner borders 6 eighths of a point and a cell margin of 57 twips per side; eleven
   column widths measured from the client's column table, with an override set for the beam
   table; and the per-cell line spacing used in the header's continuation cells.
2. **A declarative builder** that maps domain records onto the table: one row group per
   detection face, vertical merge for the member columns, and a second merge pass that
   groups consecutive rows sharing the same requirement clause — so one clause is written
   once and centered across its block, while a change of clause starts a new cell.
3. **Eleven deterministic patches** applied to the serialised OOXML (Table 5.3). They exist
   because a general-purpose DOCX library emits *valid* markup, not *identical* markup.

**Table 5.3 — The eleven post-processing patches**

| # | Attribute family | Library output vs. approved template | Patch |
| --- | --- | --- | --- |
| ① | `w:docGrid` | line pitch differs | rewrite to the specified pitch |
| ② | `w:tblLook` | no `w:val`, booleans spelled `true`/`false` | insert `w:val`, normalise to `1`/`0` |
| ③ | `w:trHeight` | carries `w:hRule` | drop the attribute |
| ④ | `w:tblCellMar` | declares edges the template does not | keep only declared edges |
| ⑤ | Continuation cells of merged rows | bare `<w:p/>`, no vertical alignment | add `vAlign=center`, centered paragraph, header line spacing |
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

# §6 Implementation

## 6.1 Stack and repository layout

The product is served from a directory; there is no build step to run at deployment time and
no bundler at development time. `index.html` declares an import map mapping the two
third-party dependencies (`docx`, `jszip`) to vendored files, and every other module is a
native ES module fetched by the browser from the same paths a developer edits. This was a
deliberate trade: no bundler means no transpilation step, no source maps to trust, and a
stack trace in a phone's remote inspector that points at the file the developer wrote. The
cost is that the module graph must be explicit and that nothing minifies the payload — both
acceptable for a ~50-file, ~470 KB application.

Generated artifacts are the one exception to "the browser fetches what you edit". Some
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
converging 201 → 33 → 2 → 0 differences over four rounds; each round was committed
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
packaged by Capacitor, and exactly three behaviors diverge — exports are written to the
public Downloads folder through a small native plugin (with a share-sheet fallback and a
toast when no viewer is installed), the hardware back key navigates within the app and exits
only at a root screen, and the service worker is not registered because the assets already
come from the package.

## 6.7 Code-level lessons

Three practices earned their place. **Generated artifacts are checked in and diffed in CI**,
so a stale copy cannot ship. **Assertions that inspect source code must strip comments
first** — our "the service worker must not call `skipWaiting()`" check failed on its own
documentation comment that said "this is where we do not call `skipWaiting()`". And **a test
that waits for a selector must wait for a monotonically increasing signal**, not for a class
name that also exists on the previous page; the app now writes a render counter onto
`<body>` and tests wait for it to grow, which removed a whole class of false positives in
which a test read the previous page's DOM and concluded that a deletion had failed.

## 6.8 Issues encountered: an engineering post-mortem

§7.5 tells the story of the nine defects from the evaluation side — which environment found
each one, and what that says about verification. This section looks at the same nine from the
engineering side: what class of failure each belongs to, what the fix cost, and what rule the
codebase now enforces because of it. The classification matters more than the individual bugs,
because three of the six classes will recur in any project of this shape.

**Class 1 — a dependency captured at construction time.** The application opened with an empty
database handle because `boot()` constructed the application first and assigned its dependencies
afterwards, and the constructor had already closed over its argument. The fix took an hour; the
*rule* it produced is permanent: the render context resolves dependencies from the application
object at use time, and an entry point is itself a test target. This is the general shape of
"late initialisation", and it is invisible to any test that constructs the object with its
dependencies already present — which is every test written by the person who wrote the
constructor.

**Class 2 — a platform-provided global.** Export crashed only in browsers because the generator
was asked for an output type that requires a global `Buffer`. This is a subclass of Class 1 with
a twist: the dependency is provided by the *runtime*, not by the caller, so no amount of
construction discipline finds it. The rule: when a library offers an environment-specific
shortcut, take the portable branch and prove the two branches produce identical bytes — the
substitution is only safe because Gate A still reported zero differences afterwards. The
regression test now deletes the global before importing the module, which is the closest a test
can come to "run on a phone".

**Class 3 — a path that had never executed.** Backup import had no test at all, and its single
defect made the only data-recovery mechanism unusable. The fix was one line; the work was
eight test cases plus a real-browser case with a real `File` and a real `<dialog>`. The rule
adopted from that day: **any path that can destroy or restore data gets a test before it gets a
user interface.** It is a scheduling rule, not a technical one, and it is the cheapest rule in
this paper.

**Class 4 — precedence between the author and the platform.** Two defects belong here: author
CSS beat the `[hidden]` attribute, and an SVG element created in the HTML namespace existed but
was never painted. Both were invisible to assertions of the form "the element is present and has
the right attributes". The rule: **assert computed outcomes, not declarations** — computed
style rather than the attribute, `namespaceURI` rather than the tag name, a measured bounding
box rather than a class name.

**Class 5 — thresholds that only a body or a viewport reveals.** A 28 × 22 px cancel button and a
save bar hidden behind the soft keyboard are not logic errors; they are failures to model the
user's geometry. The rules are now explicit: interactive targets are at least 44 × 44 px, and
anything `position: fixed` at the bottom must be offset by the visual viewport's keyboard inset,
never by an assumption about `innerHeight` (which does not change when the keyboard opens).

**Class 6 — a boundary that was only in someone's head.** The delivery package once contained the
browser test scripts, because the packaging script copied a directory that had acquired a new
subdirectory. The rule: **a boundary that matters is a build assertion** — the packager now fails
rather than shipping a package that contains a test asset.

**Cost.** The three priority-0 defects cost roughly a day and a half of the project's four weeks
of integration time — not because the fixes were large (one was a single line, one deleted an
argument, one reordered two statements) but because each had to be reproduced, diagnosed and
then guarded by a test that would fail if it returned. Every one of the nine now has a positive
control: reverting the fix turns a specific test red with the production error text. That
practice is what distinguishes a fix from a hope.

---

# §7 Evaluation and quality assurance

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

The sixteen gates divide as follows: **five fidelity procedures** — Gate A run twice (report and
attachment pages), Gate B, Gate C and the sensitivity harness, which are the ones described in
§7.2–§7.3 — plus five Python-side baseline checks that guard the reference implementation, four
synchronisation and unit-test steps, and two generator steps. Appendix C lists all sixteen with
their re-run commands; only the fidelity five are argued in this chapter, because only they bear
on the claim the paper makes.

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
a cropped excerpt of the client's actual delivered report (`检测表_真实裁剪.docx`), obtained in
de-identified form through a former colleague at the institute because the project was executed
remotely, and reduced to the tables so that no client-identifying content is compared. The actual document is
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

![Figure 7.1 — Gate sensitivity. Each of the poisoned documents is injected into a known-good report and must be caught at a specific comparison path, not merely rejected.](deliverables/prp/gate-sensitivity.png)

Asserting the *path* of the failure, not merely that the run turned red, is what makes this
useful: it distinguishes "the gate noticed something" from "the gate noticed the right
thing". The `table_merge` poison is the most instructive of the seven, and it produced the
design rule discussed in §5.3 — the two comparators disagree about `val="continue"` versus an
absent `val`, so the patch chain emits the byte form that both accept.

## 7.4 Fidelity results

After four convergence rounds the diff count went 201 → 33 → 2 → 0, and all gates report
zero differences. The eleven residual discrepancies that were closed along the way were all
attribute-level; none required a semantic deviation, which is why no "declared deviation"
mechanism exists.

![Figure 7.2 — Fidelity gate A convergence: 201 → 33 → 2 → 0 differences over four rounds, closed by eleven attribute-level patches without loosening the comparison.](deliverables/prp/gate-convergence.png)

Zero differences in our own comparator is still a self-referential claim, so the artifacts
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

# §8 Results, discussion and limitations

## 8.1 Requirements coverage

The requirement set was frozen before implementation and audited at delivery. It contains
**forty-six in-scope requirement rows**: forty-three implemented as specified, two implemented
with an agreed adaptation (the report person is taken from a local profile instead of a login
session; the profile page carries no department code), and one optional item (single-report JSON
export) not built because no consumer existed — 46 = 43 + 2 + 1. A further two rows, plus three
modules (accounts, quick notes, statistics), were removed from scope in writing and are not part
of the forty-six. Table 8.1 summarises.

**Table 8.1 — Requirement coverage at acceptance**

| Category | Count | Note |
| --- | --- | --- |
| Implemented as specified | 43 | Verified by automated tests, gates or on-device checks |
| Implemented with agreed adaptation | 2 | Documented in the confirmed requirement set |
| Not built (optional) | 1 | Single-report JSON export; no consumer identified |
| **In-scope total** | **46** | 43 + 2 + 1 — the traceability matrix §4.2 groups into 14 capabilities |
| Out of scope by agreement | 2 rows + 3 modules | Accounts/login, quick notes, statistics; not counted above |

## 8.2 What worked, and why

Three mechanisms carried the project, and each is transferable.

**Treating the deliverable as the specification.** The decisive move was not technical: it was
deciding that the client's Word file *is* the requirement, and that any difference is a defect
until proven otherwise. That decision converted a vague acceptance conversation into a
diff list, and the diff list into a to-do list, converging 201 → 33 → 2 → 0 differences over
four rounds (Figure 7.2). It also produced the eleven patches, each of which is a named,
tested fact about the template rather than a folk remedy.

**Gates with disjoint domains.** Three comparisons were maintained instead of one, and the
maintenance cost was repaid twice: once when the frozen baseline and the real-report
comparison disagreed about a merge encoding (§5.3), and once when the JavaScript self-check
disagreed with both Python comparators over a property neither had normalised. A single gate
would have reported green in both cases.

**Moving the environment rather than widening the suite.** The nine defects in Table 7.5 were
not found by writing more unit tests; they were found by executing the same product in a
browser and then on a phone. In hindsight this is the cheapest defect-detection investment in
the project: two days of environment work produced three priority-0 fixes that a thousand
additional unit tests would not have located.

## 8.3 What we would do differently

**Introduce the real browser earlier.** The DOM-emulator suite was at 205 passing tests when
the browser round found that export crashed and that backup import had never worked. The
browser layer existed late because it was assumed to be a confirmation step; it is in fact a
detection step, and it should have existed from the first vertical slice.

**Test every destructive path on the day it is written.** The import defect was possible
because import had no test at all — and import is the mechanism by which a user recovers from
losing a phone. The rule now applied is blunt: a path that can destroy or restore data gets a
test before it gets a UI.

**Measure the template before writing the patches.** Several of the eleven patches were
written speculatively and later removed or reshaped once the diff tool existed. Building the
comparison first, and letting the diff enumerate the work, would have removed that detour.

**Keep the transaction module simpler.** The single-transaction discipline is correct, but the
first version tried to hide asynchrony in a helper, which is how the `TransactionInactiveError`
trap was discovered. An explicit, slightly verbose API would have made the constraint visible
at every call site from the start.

## 8.4 Limitations

**The gates do not render.** All three comparisons are structural. A document can be
attribute-identical and still paginate differently on a machine with different fonts or a
different Word version. The mitigation is environmental rather than technical: the deliverable
is opened in the same corporate Word installation that produced the template.

**No iOS device was available.** Safari differs from Chromium in storage eviction policy, PWA
installation and service-worker lifetime. The product compensates by requesting persistent
storage and by shipping an explicit backup, but parity is claimed for Android only.

**The data is device-local.** There is no synchronisation, no multi-inspector collaboration and
no server-side audit trail; a lost phone loses the work unless a backup was exported. This is a
consequence of the no-server constraint, acceptable for a single-inspector workflow and not
acceptable for a team.

**Plain-HTTP intranets lose offline capability and installation.** Offline caching and
"install as an app" require a secure context; on an intranet served over `http://192.168.x.x`
the business functions work but the application cannot install or work offline. This is a
browser rule, documented for the client, not a defect of the implementation.

**Touch gestures and hardware variation were not exercised.** Pinch, long-press and inertial
scrolling were not systematically tested, and the Android verification used one emulator
image, one WebView version and one physical keyboard layout.

**Quantified business impact is not established.** The tool removes three of the five
hand-offs and both manual minimum computations, and the client's team reported the workflow as
materially faster — but no controlled time measurement was conducted, so no percentage is
claimed here. That measurement is the first item of future work.

## 8.5 Discussion

The project's generalisable claim is about where verification effort belongs. In a system whose
value depends on fidelity to an external artifact, the expensive part is not building the
generator — it is establishing, continuously and cheaply, that the generator's output equals
the artifact that already has the client's trust. And in a system whose users are mobile
workers, the expensive part is not the feature list — it is the gap between the environment in
which the features were written and the environment in which they will be used. Both are
questions of *comparison against reality*, and both are answerable with gates, harnesses and
an honest ladder of environments.

## 8.6 Detailed project chronology and critique

The project ran from 10 September to 24 November 2026, eleven days inside its planned end of
5 December, and it ran on two clocks: the author in New York, the client in Shenzhen, twelve to
thirteen hours apart. One person held both roles. As project manager, that meant a charter, a
work-breakdown structure and baseline, monthly status reports, and the two acceptance documents;
as implementer, it meant the architecture, the engine, the verification gates, the delivery
package and the end-user manual. Remote delivery of that shape has a specific cost that a
co-located team never pays: every question costs a day of latency, so the requirements had to be
settled in writing early — which is, in retrospect, why treating the client's report as the
specification worked as well as it did. The chronology is worth setting out because the *order*
of the work, more than any single technique, explains both what went well and what was
expensive.

**Phase 1 — proof of concept (September).** The first task was not to build a form but to answer
one question: could the client's report be reproduced mechanically at all? A Flask reference
implementation was built with `python-docx`, driven by a layout specification extracted from the
client's real document, and compared against a cropped copy of that document. It reproduced the
tables closely enough to make the rest of the project worth attempting, and it established the
pattern that carried through to the end — the report as specification, the diff as the measure.

**Phase 2 — data model and the office workflow (late September to early October).** Projects,
records, faces, readings and defect reports were modelled and implemented against the reference
implementation, together with the image pipeline. This phase produced the part of the product
that a reviewer can see, and it produced almost none of the part that decides acceptance.

**Phase 3 — the migration decision and the port (October).** The client's constraints (no
server, no store, phones only) forced the decision recorded as ADR-1: the Flask application
became a frozen oracle, and the product became an offline-first client. The port was
substantial — data layer, engine, views — and it carried one asset that made it feasible: the
layout specification had been written as data, so the JavaScript engine could be driven by the
same numbers.

**Phase 4 — fidelity convergence (late October to early November).** The export engine was
brought to zero differences by working the diff list down, 201 → 33 → 2 → 0 over four rounds, with
a commit per round. Gate B (the client's real report) was built in this phase, and the eleven
patches were identified here.

**Phase 5 — the environment ladder (12–13 November).** Two days changed the project's self-image.
A real-browser round of 21 cases found the backup-import defect, the packaging leak and the
undersized cancel button; the Android round of 14 assertions found the export crash, the keyboard
occlusion and the secure-context constraint on offline installation; and a user-reported crash on
open produced the third priority-0 defect. Before these two days the suite had 205 passing tests
and the product could not start.

**Phase 6 — release engineering and handover (19–24 November).** Versioning, the delivery
package with its whitelist and checksums, the Android packaging channel with a pinned signature,
the end-user manual with annotated screenshots, and the sponsor acceptance documents.

**Critique — what went well.** Three things. Freezing the reference implementation early turned
every later disagreement into a diff. Treating the diff as a to-do list kept the hardest work
monotonic and measurable. And single-sourcing the version, the layout numbers and the cache
fingerprint prevented a class of release defects that would have been invisible until a client
hit them.

**Critique — where the project went wrong.** The most expensive mistake was **starting inside the
Flask frame**. The port itself was right, but doing the data model and the engine first, in a
runtime that is more permissive than a browser, meant that six weeks of work was validated in an
environment the user would never occupy. The second most expensive mistake was **deferring the
browser** until 205 unit tests were green; the two browser days found three defects that no
amount of additional unit testing would have found, and they should have been the first two days
of the port, not the last. Third, the eleven patches were written partly *before* the measurement
that justified them — several were speculative and were later reshaped, a detour that a
measure-first order would have avoided entirely. Fourth, the Android release path was
underestimated: the debug-signature instability and the Downloads-folder behavior were treated
as packaging details and cost roughly two days of rework, including one failed upgrade that could
only be recovered by uninstalling. Finally, documentation was written at the end; the manual and
the deployment guide exist, but they would have taken hours instead of a day if they had been
written beside the features.

**The moment that changed the definition of done.** At the end of Phase 4 the suite was green and
the product did not start on a phone. The sentence we wrote on the whiteboard that afternoon —
*"green means the compared things match, not that the product works"* — became the project's
working definition of done and, in retrospect, its most transferable result.

## 8.7 Lessons learned

**Lesson 1 — a green run answers a narrower question than it appears to.** It answers "the things
I compared agree". It does not answer "the things that matter were compared", and it does not
answer "they agree in the environment the user occupies". Both gaps were populated with blocking
defects in this project. The practical form of the lesson is two questions asked before any
release: *was this attribute actually compared, and is this environment the same as the user's?*

**Lesson 2 — when the deliverable is the requirement, the deliverable is the specification.** The
client's Word file was treated as executable, not as a style reference, and that single framing
decision converted an acceptance conversation into a diff and a diff into a task list. It also
changed what "done" meant at every step: a feature was not done when it worked, but when its
output was indistinguishable from the accepted document.

**Lesson 3 — test environments bound what can be discovered, and the ladder is cheap.** Two days
of browser and device work produced three priority-0 fixes; a thousand more unit tests would not
have produced any of them, because they tested a permissive environment. The generalisable
practice is to move one environment closer to the user at a time, and to treat each step's defect
yield as the justification for taking the next one.

**Lesson 4 — derived values should be recomputable, and that is what makes recovery possible.**
Thumbnails, minimums and page counts are all computed from stored originals, so they can be
rebuilt, verified and discarded. That discipline is why a backup containing only originals is
sufficient, and why the restore path could be tested by rebuilding rather than by trusting.

**Lesson 5 — boring constraints prevent spectacular failures.** One version number instead of
three; a packaging whitelist instead of a copy; a pinned keystore instead of a fresh one per
build; a cache name derived from content instead of a timestamp. None of these is intellectually
interesting, and each of them removed a failure mode that would have surfaced only at the client.

**Personal reflection.** I began this project believing the hard part would be building the
application, and finished it believing the hard part is establishing that the application is
right. My estimate for the report engine was wrong by roughly a factor of three: the engine
itself was a week, and proving it was five. The highest-leverage single act of the project was
asking the client for the *actual* delivered report rather than a description of it — an email
that cost ten minutes and defined the next six weeks. And the discipline I will carry forward is
the least glamorous one: when a suite is green, go and use the product the way the user will, on
the device the user has, before believing anything.

---

# §9 Conclusion and future work

## 9.1 Conclusions

**Fidelity can be engineered as an equality property.** By treating the client's report as an
executable specification, describing its geometry in a language-neutral artifact, and applying
eleven named post-processing patches, the generated document reaches zero differences against
the approved template across three independent comparisons — and a seven-case poisoning harness
demonstrates that those comparisons are sensitive to the attributes that matter.

**Test environments silently bound what can be found.** Nine defects reached a user-facing
environment while the cheaper layers were green; three of them were blocking, and each failed
either "was this compared?" or "is this the user's environment?". The transferable practice is
the ladder: move one environment closer to the user at a time, and treat each step's defect
yield as the justification for the next one.

**Server-less delivery is a viable architecture for this class of field tool, if its three
consequences are answered explicitly.** Durability becomes a user-facing backup, sharing
becomes writing to the device and handing the file to the operating system, and upgrading
becomes content-fingerprinted cache invalidation with deliberate activation. None of the three
is free; all three are implementable without a server.

## 9.2 Future work

**Quantified impact.** A controlled time study of report assembly before and after adoption,
including error-correction time, is the single most valuable next measurement.

**iOS validation.** A real-device Safari pass, focusing on storage eviction, installation and
service-worker lifetime, would extend the platform claim from one to two.

**Multi-inspector operation.** Collaboration, conflict resolution and an audit trail all
require the back-end this project deliberately avoided; the natural next step is an optional
synchronisation service that the app can run without, not one it depends on.

**Template configurability.** The layout specification is already data; exposing it as a
per-client configuration would let the same engine serve reports from other institutes,
turning a bespoke tool into a product.

**Signed reports.** The report is contractual evidence; an integrity signature over the
generated document (and a verifiable hash on the attachment pages) would close the last mile
between "generated faithfully" and "provably unaltered".

## 9.3 Recommendations for the institute

Five recommendations follow from what this project measured and from what it could not.

**Measure the saving before scaling the tool.** The mechanism that produces rework has been
removed, but its cost has not been quantified (§8.4). A four-week baseline-and-after study on one
inspection group — time per report, and the number of returned reports — would give the institute
the number it needs to decide whether to extend the tool to other groups, and this project has
deliberately not guessed it.

**Treat the layout specification as a controlled artifact.** The form of the report is now data
(`report_layout.json`) with a named set of eleven patches behind it. It should be versioned and
changed through a review, exactly like the Word template it replaces; if it is edited casually,
the guarantee that the report is unchanged disappears silently, which is the one failure mode the
client cannot afford.

**Put the backup in the procedure, not in the tool's documentation.** The tool can export a
whole-database backup and can import it, but it cannot make an inspector remember to do so. A
daily export at the end of a site visit, and a quarterly restore drill on a spare phone, convert a
capability into a control; the restore path is precisely where this project found its most serious
defect (§7.5.2).

**Configure HTTPS on the intranet if offline use matters.** Offline operation and installation as
a standalone application require a secure context; over plain HTTP the business functions work but
the application cannot cache or install (§8.4). If inspectors are expected to work without signal,
the deployment should be HTTPS, and that is an infrastructure decision rather than a product one.

**Reuse the engine before rebuilding the form.** The layout specification and the patch chain are
not specific to curtain walls: they encode *a report's geometry*, and the institute issues other
reports with the same discipline. The cheapest next project is the one where a second template is
described as data and the same three gates are pointed at it.

---

# References

Biørn-Hansen, A., Majchrzak, T. A., & Grønli, T. M. (2017). Progressive Web Apps: The possible
web-native unifier for mobile development. *Proceedings of the 13th International Conference on
Web Information Systems and Technologies (WEBIST)*, 344–351.
https://doi.org/10.5220/0006353703440351

Canny, S. (2013). *python-docx* [Computer software]. GitHub.
https://github.com/python-openxml/python-docx

Chen, T. Y., Cheung, S. C., & Yiu, S. M. (1998/2020). *Metamorphic testing: A new approach for
generating next test cases* (Technical Report HKUST-CS98-01; archived version). Hong Kong
University of Science and Technology. https://doi.org/10.48550/arXiv.2002.12543

Davies, R., & Harty, C. (2013). Implementing "Site BIM": A case study of ICT innovation on a
large hospital project. *Automation in Construction, 30*, 15–24.
https://doi.org/10.1016/j.autcon.2012.11.024

Ecma International. (2021). *ECMA-376: Office Open XML file formats* (5th ed.).
https://www.ecma-international.org/publications-and-standards/standards/ecma-376/

Feathers, M. (2004). *Working effectively with legacy code*. Prentice Hall.

Ma, Z., Cai, S., Mao, N., Yang, Q., Feng, J., & Wang, P. (2018). Construction quality
management based on a collaborative system using BIM and indoor positioning. *Automation in
Construction, 92*, 35–45. https://doi.org/10.1016/j.autcon.2018.03.027

Majchrzak, T. A., Biørn-Hansen, A., & Grønli, T. M. (2018). Progressive Web Apps: The definite
approach to cross-platform development? *Proceedings of the 51st Hawaii International
Conference on System Sciences (HICSS)*, 5735–5744. https://doi.org/10.24251/HICSS.2018.718

McKeeman, W. M. (1998). Differential testing for software. *Digital Technical Journal, 10*(1),
100–107.

Ministry of Construction, P.R. China. (2003). *Technical code for glass curtain wall
engineering* (JGJ 102-2003). China Architecture & Building Press.

Miu, D. (2024). *docx: Generate .docx files with JavaScript/TypeScript* [Computer software].
npm. https://www.npmjs.com/package/docx

Park, C. S., Lee, D. Y., Kwon, O. S., & Wang, X. (2013). A framework for proactive construction
defect management using BIM, augmented reality and ontology-based data collection template.
*Automation in Construction, 33*, 61–71. https://doi.org/10.1016/j.autcon.2012.09.010

Sacks, R., Eastman, C., Lee, G., & Teicholz, P. (2018). *BIM handbook: A guide to building
information modeling for owners, designers, engineers, contractors, and facility managers*
(3rd ed.). Wiley.

W3C. (2018). *Indexed Database API 2.0* (W3C Recommendation). World Wide Web Consortium.
https://www.w3.org/TR/IndexedDB-2/

Archibald, J. (2019). *The offline cookbook*. web.dev.
https://web.dev/articles/offline-cookbook

---

# Appendices

## Appendix A — Sponsor's acceptance documents

The signed Project Plan (document 07, Part 1) and Project Acceptance (document 07, Part 2)
follow as scanned pages, in the order the guideline requires: the plan that was agreed at
project start, then the results and acceptance recorded at delivery. Both documents were signed
by the sponsor, and the four pages reproduce the originals without retouching.

![Appendix A-1 — Project Plan (Part 1), page 1: project title, sponsor details, the project goal and the first two objectives with their metrics.](docs/release/final/signed-pages/part1-p1.jpg)

![Appendix A-2 — Project Plan (Part 1), page 2: Objectives 3 to 5, the sponsor's statement of agreement, signature, date and printed name.](docs/release/final/signed-pages/part1-p2.jpg)

![Appendix A-3 — Project Acceptance (Part 2), page 1: planned and actual dates, the goal recorded as achieved, and Objectives 1 to 3 recorded as met with the sponsor's initials against each.](docs/release/final/signed-pages/part2-p1.jpg)

![Appendix A-4 — Project Acceptance (Part 2), page 2: Objectives 4 and 5, the sponsor's evaluation, comments and acceptance statement, and both signatures — the sponsor's and the student's — with their dates.](docs/release/final/signed-pages/part2-p2.jpg)

## Appendix B — The eleven post-processing patches

Appendix B reproduces Table 5.3 with the exact OOXML attribute each patch rewrites, so that the
patch chain can be re-derived from the specification alone: document grid line pitch; table
look attributes and their boolean normalisation; row-height rule attribute; table cell margins;
continuation cells of merged rows (vertical alignment, paragraph justification and header line
spacing); styles and theme parts; section column spacing; page-size orientation attribute;
row-level justification; border spacing; and vertical-merge value encoding.

## Appendix C — Verification inventory and re-run commands

| Artifact | What it proves | Re-run |
| --- | --- | --- |
| Python suite (348 tests) | Data rules, layout extraction, export assembly, defect semantics | `python -m pytest -q` |
| Front-end suite (250 tests) | Data layer, engine, attachments, image pipeline, real-markup UI | `npm test` |
| Sixteen gates | Generated-asset synchronisation, four Python baselines, Gates A (both halves), B and C, poisoning harness, single-test suites | `python tools/verify_all.py` |
| Desktop E2E (21 cases) | Canvas, dialogs, service worker, downloads, viewports, keyboard | `npx playwright test` |
| Android assertions (14) | Camera, file manager, soft keyboard, installation, offline with traffic blocked | `node web/e2e/android-remote.mjs` |
| Delivery package | No test assets, version coherence, checksums | `python tools/make_release_zip.py` |

## Appendix D — Deployment and data-protection summary

The deliverable is a directory of static files. Deployment requires a static host (Nginx, IIS or
the bundled Python server) with a correct `text/javascript` MIME type for `.mjs`; offline
capability and installation additionally require a secure context (HTTPS or localhost). Data
resides only in the browser's storage on the inspector's device; durability is the
inspector's responsibility, mediated by a one-file backup that includes original photographs,
and the only destructive actions in the product state their blast radius before executing.

## Appendix E — Project plan, baseline and actual schedule

The baseline schedule was planned from 10 September 2026 to 5 December 2026. The actual
delivery completed on 24 November 2026, eleven days ahead of the planned end, with the
baseline work-breakdown structure unchanged; the deviation is a compression of the
integration and verification phases rather than a reduction in scope, and the sponsor
initialled the revised dates in Part 2 of the acceptance document.
