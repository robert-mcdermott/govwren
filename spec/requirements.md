# Requirements

The capability catalog. IDs are stable: code, tests, and changelog entries can cite them.

**Priority:** **M**ust (required for the capability to ship), **S**hould (high value, next in line), **C**ould (optional expansion).
**Wave:** the release that delivers it (see [roadmap.md](roadmap.md)). `—` means not yet scheduled.

## Front door (FDR)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| FDR-01 | M | Catalog of evaluated AI systems | Anyone signed in can search the catalog and see each system's standing, the data it may be used with, and its terms of use | 1 |
| FDR-02 | M | Register a use of a catalog system | A use within a system's permitted data is registered and approved in one short form, producing a use case with an owner, a tier, and a review date | 1 |
| FDR-03 | M | Fall through to intake | A registration that exceeds what the system permits continues into the intake form with its answers carried forward | 1 |
| FDR-04 | M | Home page of what I owe | Each person sees their requests, records, conditions, tasks, and attestations in one list, overdue first | 1 |
| FDR-05 | S | "May I use…" lookup | Typing a tool name and choosing a data class answers yes, yes with terms, no, or not yet evaluated, without creating anything | 2 |
| FDR-06 | S | Request an evaluation | Anyone can ask for a system to be evaluated for the catalog; duplicates are joined to the existing request | 2 |
| FDR-07 | C | Submit without an account | An organization can open intake to people who have not signed in, behind a link, with submissions held for triage | — |

## Intake (INT)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| INT-01 | M | Forms defined as data | A form is a versioned document of sections and questions; publishing never alters an earlier version | 1 |
| INT-02 | M | Adaptive questions | A question or section appears only when earlier answers meet its condition | 1 |
| INT-03 | M | Save and resume | A draft is saved as it is filled and can be resumed on another device | 1 |
| INT-04 | M | Answers fill the record | Mapped answers populate record fields; unmapped answers stay with the response and show on the record | 1 |
| INT-05 | M | Responses render as asked | An old response always displays with the questions and options of its own form version | 1 |
| INT-06 | M | Ask once | Facts already on a linked record are prefilled and not asked again | 2 |
| INT-07 | M | Form builder | Governance edits a draft form in the app, previews it against sample answers, and publishes it | 2 |
| INT-11 | S | Questions for those who run or train models | When a requester says they will run a model themselves or train one, a section asks for its source, license, where it runs, and what it is trained on | 2 |
| INT-08 | S | Several forms | Separate forms for use cases, system evaluations, vendor questionnaires, change declarations, incident reports, and attestations | 3 |
| INT-09 | S | Attach files to answers | A question can take a file, stored as evidence | 2 |
| INT-10 | C | Assisted drafting | With an assistant enabled, a requester can have a draft prefilled from a description, every field marked as suggested until they confirm it | 7 |

## Tiering and rules (TIR)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| TIR-01 | M | Scored factors | A scoring model defines factors, levels, and which answers set them; each factor takes its highest contributed level | 1 |
| TIR-02 | M | Tiers, floors, and stops | Totals map to tiers; floors set a minimum tier; stops mark a prohibited use that cannot be approved without an exception | 1 |
| TIR-03 | M | Every tier explains itself | A record shows each factor's level, the answer that set it, and any floor that applied | 1 |
| TIR-04 | M | Reasoned override | A permitted person can change the tier with a written reason; computed and final tiers are both kept | 1 |
| TIR-05 | M | Routing rules | Rules over tier, fields, and answers require review functions, set who decides, set due dates and cadence, attach conditions, and approve automatically | 1 |
| TIR-06 | M | One declarative condition language | Form conditions, scoring, routing, and control applicability use the same data-only structure; nothing is evaluated as code | 1 |
| TIR-07 | M | Decisions keep their rules | Each assessment and review records the version of the scoring model and rules it was made under | 1 |
| TIR-08 | M | Live tier indicator | While a form is being filled, the likely tier and required reviews are shown | 1 |
| TIR-09 | S | Editors with impact preview | Governance edits the scoring model and rules in the app; before publishing, the app lists existing records whose tier or route would change | 2 |
| TIR-10 | S | Sampled automatic approvals | A configurable share of automatic approvals is queued for a person to check; results are reported | 3 |

## Review and decisions (REV)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| REV-01 | M | Triage | Governance sees each new request with its tier and required reviews, and can confirm, adjust with a reason, or return it | 1 |
| REV-02 | M | Parallel review tasks | One task per required function, assigned or claimable, each with a due date | 1 |
| REV-03 | M | Findings | A reviewer records no concerns, acceptable with conditions, or an objection, with notes | 1 |
| REV-04 | M | Discussion with the requester | Comments are requester-visible or internal; a question to the requester pauses the clock until they reply | 1 |
| REV-05 | M | Decision with rationale | Every decision records outcome, rationale, decider, authority, and time; a decision is never edited, only superseded | 1 |
| REV-06 | M | Conditions tracked to closure | Conditions have a kind, an owner, and a due date; before-use conditions hold the approval until met | 1 |
| REV-07 | M | Standard condition library | Conditions can be chosen from reusable templates so wording is consistent and reportable | 1 |
| REV-08 | M | Decision packet | One screen gathers the request, tier reasons, findings, proposed conditions, and related history for the decider | 1 |
| REV-09 | M | Named risk acceptance | For tiers that require it, approval completes only when the named acceptor confirms in their own session | 3 |
| REV-10 | S | Reminders and escalation | Tasks nearing or past due notify the assignee and then governance | 3 |
| REV-11 | S | Committee sessions | Reviews awaiting a body are gathered into an agenda; decisions made in the meeting record the session; minutes are kept | 3 |
| REV-12 | S | Resubmission | A declined or returned request can be resubmitted; the new review links to the old and starts from its answers | 2 |
| REV-13 | C | Recorded votes | A session can record each member's vote and recusals | — |

## Inventory (INV)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| INV-01 | M | Use cases, AI systems, and vendors | Each is a record with a permanent reference, a unit, owners, status, and a detail page | 1 |
| INV-02 | M | Named ownership | Every active record has an accountable owner; records whose owner has left are flagged as orphaned | 1 |
| INV-03 | M | Lists that filter, sort, and share | Every list filters by any shown field, sorts, pages, and keeps its state in the URL | 1 |
| INV-04 | M | History on every record | A record's page shows every change with who, when, and before and after | 1 |
| INV-05 | M | Models and datasets | Records for models (with model cards) and datasets (with classification and identifiability) | 2 |
| INV-18 | M | Locally run and fine-tuned models | A model the organization runs or trains itself records where its weights came from and their checksum, format, license restrictions, where it runs, and its base model; a fine-tune is at least as sensitive as the most sensitive data it was trained on, and shows which dataset set that | 2 |
| INV-19 | S | Models in the catalog | Reviewed models, including open-weight ones, have a catalog standing and permitted data class, and a use of one registers as quickly as a use of an approved tool | 2 |
| INV-06 | M | Agent profiles | Systems that act carry autonomy level, actions, tools, identity, reversibility, human override, and limits | 2 |
| INV-07 | M | Typed links and the dependency graph | Records are linked with typed relations; each record shows what it depends on and what depends on it, as a list and as a graph | 2 |
| INV-08 | M | Inherited findings | Risks, incidents, and exceptions on a record are shown on its dependents, marked as inherited | 3 |
| INV-09 | M | Agreements and renewals | Vendor agreements carry kind, dates, and notice periods; expiries produce reminders | 2 |
| INV-10 | M | External references | Records point to protocols, grants, agreements, purchases, tickets, and repositories in other systems | 2 |
| INV-11 | M | Search | One search across all record types by reference, name, and text, restricted to what the searcher may see | 2 |
| INV-12 | S | Completeness | Each record shows which expected fields are missing; lists and reports show completeness by type and unit | 2 |
| INV-13 | S | Possible duplicates | Similar records are suggested for merging; merging keeps both references resolvable | 2 |
| INV-14 | S | Bulk import | A spreadsheet of existing records imports through a mapping screen with a dry run that reports every problem first | 2 |
| INV-15 | S | Saved views | A person saves a list's filters and columns under a name | 2 |
| INV-16 | S | Custom fields | An organization adds its own fields to a record type; they appear in forms, lists, filters, and exports | 6 |
| INV-17 | C | Embedded AI sweep | A campaign asks the owner of each registered software product whether it has gained AI features | 3 |

## Oversight (OVR)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| OVR-01 | M | Approval periods and re-review | Each approval has an end date from its tier's cadence; a periodic review opens beforehand with earlier answers in place | 3 |
| OVR-02 | M | Lapsed approvals | An approval past its date without re-review is marked lapsed everywhere it appears | 3 |
| OVR-03 | M | Owner confirmation campaigns | Owners confirm each record as unchanged, changed, or no longer in use; several can be confirmed at once | 3 |
| OVR-04 | M | Unit completeness attestation | A steward reviews their unit's list, adds what is missing, and attests; coverage is reported by unit | 3 |
| OVR-05 | M | Change declaration | An owner declares a change through a short form; rules decide whether it is material and open a limited review if so | 3 |
| OVR-06 | M | Exceptions | Time-limited, approved departures with justification and compensating measures; one register; always expire | 3 |
| OVR-07 | M | Incident register | Anyone can report; governance triages, links records, and records containment, cause, and lessons | 3 |
| OVR-08 | M | Actions | Conditions, corrective actions, and follow-ups are tracked in one list with owners and due dates | 3 |
| OVR-09 | M | Retirement | Retiring a record captures replacement and disposal, lists dependents, and notifies their owners | 3 |
| OVR-10 | S | Suspension | Governance can suspend an approval, with a reason, pending review | 3 |
| OVR-11 | S | Policy acknowledgment | A campaign records who has acknowledged a policy version | 4 |
| OVR-12 | C | Training records | Record who has completed which AI training, with expiry | — |

## Assurance (ASR)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| ASR-01 | M | Evidence store | Files, links, and notes with an owner, a collected date, and an expiry; one item can support many things | 2 |
| ASR-02 | M | Risk register | Risks on any record or on the organization, with inherent and residual likelihood and impact, treatment, and owner | 4 |
| ASR-03 | M | Risk library | A catalog of reusable risk statements to draw from, shipped as a content pack | 4 |
| ASR-04 | M | Control library | Controls are defined once, scoped to the program or to records, with applicability rules; never copied per record | 4 |
| ASR-05 | M | Control implementation with evidence | Each applicable control has a status, an owner, linked evidence, and a next check date | 4 |
| ASR-06 | S | Frameworks as optional content packs | A framework is a data file of requirements with identifiers, versioned and loaded without code changes; the program works fully with none loaded | 4 |
| ASR-07 | S | Crosswalks | A control maps to requirements in any number of frameworks | 4 |
| ASR-08 | S | Readiness by framework | Each requirement shows as covered, partly covered, a gap, not mapped, or not applicable, with the controls and evidence behind it | 4 |
| ASR-09 | M | Evidence freshness | Expiring and expired evidence is flagged on everything it supports and in reports | 4 |
| ASR-10 | S | Policies | Versioned policies with owners, review dates, and links to the controls that implement them | 4 |
| ASR-11 | S | Impact assessments | A structured impact assessment can be required by rule and is kept with the review | 4 |
| ASR-12 | S | Vendor due diligence | A questionnaire per vendor with answers, supplied assurances, and a reviewed status | 4 |
| ASR-13 | S | Statement of applicability | An exportable list of every control with its applicability, justification, and status | 4 |
| ASR-14 | C | Custom frameworks | An organization defines its own framework in the app or by import | 6 |

## Reporting (RPT)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| RPT-01 | M | Program dashboard | Counts by tier, standing, stage, unit, and domain; open reviews by age; what is overdue | 1 |
| RPT-02 | M | Export any list | CSV and JSON, with the filters that produced it recorded in the file | 2 |
| RPT-03 | M | Defined measures | Turnaround, throughput, coverage, currency, and completeness, each showing its definition, period, and cohort | 5 |
| RPT-04 | M | Portfolio views | The portfolio by unit, tier, domain, vendor, and data class, over a chosen period, drilling down to the records | 5 |
| RPT-05 | M | Record dossier | A printable, complete package for one record: description, tier reasons, reviews, decisions, conditions, risks, controls, evidence list, and history | 5 |
| RPT-06 | M | Leadership report | A periodic report of the portfolio, decisions, incidents, exceptions, and overdue items, frozen as a snapshot that can be reopened unchanged | 5 |
| RPT-07 | S | As-of views | Any record, and the inventory as a whole, shown as it stood on a chosen date | 5 |
| RPT-08 | S | Standard formats | Models and their dependencies export as a machine-readable bill of materials; model cards export in a common format | 5 |
| RPT-09 | S | Transparency register | A chosen subset of approved use cases publishes as static pages, for internal or public reading | 5 |
| RPT-10 | S | Unit report | A steward or leader gets their unit's records, obligations, and standing on one page | 5 |
| RPT-11 | C | Scheduled delivery | A report is emailed to named people on a schedule | 6 |

## Platform (PLT)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| PLT-01 | M | One-command start | `uv sync`, `govwren init`, and `govwren serve` give a working system on SQLite with a first administrator | 1 |
| PLT-02 | M | SQLite and PostgreSQL | The same code and migrations run on both; the test suite passes on both | 1 |
| PLT-03 | M | Local accounts | Passwords hashed with a memory-hard function, server-side sessions, throttled sign-in, password reset by an administrator | 1 |
| PLT-04 | M | Roles and scopes | Admin, governance, reviewer, auditor, steward, and member; steward scoped to units, reviewer to functions; one policy table checked on every route | 1 |
| PLT-05 | M | Units | A hierarchy of any depth, imported from a spreadsheet or edited in the app | 1 |
| PLT-06 | M | Append-only history | Every write records an event; events are hash-chained and verifiable from the command line | 1 |
| PLT-07 | M | Themes | Light, dark, and system modes; several built-in palettes; each person's choice remembered | 1 |
| PLT-08 | M | Branding | Product name, organization name, logo, default palette, and accent color are settings, changed in the app with a live preview | 1 |
| PLT-09 | M | Demo organization | One command builds a fictional medical research institute with enough history to show every feature | 1 |
| PLT-10 | M | Single sign-on | OpenID Connect with any standards-based provider, tested with Microsoft Entra ID; accounts created at first sign-in | 2 |
| PLT-11 | M | Roles from the identity provider | Groups or application roles map to roles, unit scopes, and review functions, refreshed at every sign-in | 2 |
| PLT-12 | M | JSON API | Everything the web app does goes through a documented `/api/v1`; the OpenAPI document is published | 1 |
| PLT-13 | M | Email | Notifications and digests over SMTP, with per-person preferences; the app is fully usable without mail | 2 |
| PLT-14 | M | Accessibility | WCAG 2.2 AA in every palette and mode, checked by tests and by a manual script | 1 |
| PLT-15 | M | Backup, restore, and move | Export and import the whole installation, including between SQLite and PostgreSQL | 6 |
| PLT-16 | M | Program packs | Forms, scoring, rules, vocabularies, templates, and controls export and import as one reviewable file | 2 |
| PLT-17 | S | Brand kit | An organization's own palette, favicon, email header, sign-in page message, footer links, and terminology | 6 |
| PLT-18 | S | API tokens and webhooks | Scoped tokens for scripts; signed webhooks on record and review events | 6 |
| PLT-19 | S | Checkpoint endpoint | Another system can ask whether a reference is approved, for what data, and until when | 6 |
| PLT-20 | S | Deployment recipes | A container image, a compose file, a systemd unit, and a reverse-proxy example | 6 |
| PLT-21 | S | Operations view | Scheduled jobs, mail queue, failures, and database health in the admin area and the command line | 6 |
| PLT-22 | S | Tool server for AI assistants | An optional server lets an assistant read records and draft changes that a person must confirm | 7 |
| PLT-23 | C | Optional assistant | Off and invisible by default; any compatible provider, including a local one; every exchange logged | 7 |
| PLT-24 | C | Optional metadata sync | Opt-in, read-only, scheduled pulls of model metadata from a registry the organization names | 7 |
| PLT-25 | C | Signal intake | Other tools can push a summary (an evaluation result, a monitoring report) onto a record as evidence | 7 |
| PLT-26 | C | Localization | Interface text in more than one language | — |
| PLT-27 | C | Several organizations in one installation | Separate tenants with separate data | — |

## Documentation (DOC)

| ID | Pri | Requirement | Acceptance | Wave |
|---|---|---|---|---|
| DOC-01 | M | Guides in the repository | Getting started, each role's guide, configuration, operations, and the API, as Markdown beside the code | 1 |
| DOC-02 | M | Product website | A site built from those guides, with a home page, search, both themes, and an API reference | after 2 |
| DOC-03 | M | Screenshots of the real app | Captured automatically from the demo organization in both themes; never from a real organization | after 2 |
| DOC-04 | S | Adopter's guide | Planning a rollout: units, roles, forms, tiers, single sign-on, branding, and the first campaign | 6 |
| DOC-05 | S | Starter packs | Ready-made program packs for a research institute, a university, and an academic medical center | 6 |
