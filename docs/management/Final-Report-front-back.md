# §1 Front matter, §2, §3, §8, §9, References, Appendices

## 1.1 Title page

**Faithful by Construction: An Offline-First Field Tool that Reproduces Corporate Inspection
Reports Attribute by Attribute**

A paper submitted in partial fulfillment of the requirements for the degree of

Master of Science

at the

Division of Programs in Business
School of Professional Studies
New York University

Zeyu Jin
Fall, 2026

Sponsoring organization: MCC Central Research Institute of Building and Construction
(Shenzhen) Co., Ltd.

## 1.2 Abstract

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

## 1.3 Front matter

# List of figures

<!--LOF-->

# List of tables

<!--LOT-->


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

# §8 Results, discussion and limitations

## 8.1 Requirements coverage

The requirement set was frozen before implementation and audited at delivery. It contains
**forty-six in-scope requirement rows**: forty-three implemented as specified, two implemented
with an agreed adaptation (the report person is taken from a local profile instead of a login
session; the profile page carries no department code), and one optional item (single-report JSON
export) not built because no consumer existed — 46 = 43 + 2 + 1. A further two rows, plus three
modules (accounts, quick notes, statistics), were removed from scope in writing and are not part
of the forty-six. Table 8-1 summarises.

**Table 8-1 — Requirement coverage at acceptance**

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
four rounds (Fig. 7-2). It also produced the eleven patches, each of which is a named,
tested fact about the template rather than a folk remedy.

**Gates with disjoint domains.** Three comparisons were maintained instead of one, and the
maintenance cost was repaid twice: once when the frozen baseline and the real-report
comparison disagreed about a merge encoding (§5.3), and once when the JavaScript self-check
disagreed with both Python comparators over a property neither had normalised. A single gate
would have reported green in both cases.

**Moving the environment rather than widening the suite.** The nine defects in Table 7-5 were
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

Appendix B reproduces Table 5-3 with the exact OOXML attribute each patch rewrites, so that the
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
