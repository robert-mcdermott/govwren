# Wave 1: Front door (v0.1.0)

**Goal:** prove the core loop. A person asks whether they may use AI for something; GovWren works out the risk tier and shows why; the right reviewers are asked; someone decides; and every step is on a record that cannot be quietly changed. Everything else in the roadmap builds on this loop being fast, clear, and trustworthy.

**Branch:** `wave-1` · **Target version:** `0.1.0` · **Status:** ◐ in progress (slices 1 to 4 of 9 done)

## Exit criteria

The wave is done when, on a fresh checkout:

1. `uv sync`, `uv run govwren init`, and `uv run govwren serve` produce a running system on SQLite with a first administrator, in under five minutes, with no other software installed (PLT-01).
2. The full test suite passes on SQLite and on PostgreSQL (PLT-02).
3. Signed in as each of the six roles, a person sees and can do exactly what [security.md](../security.md) says, in the API and in the web app; a test fails if any route lacks a policy (PLT-03, PLT-04).
4. A member finds a tool in the catalog, registers a use within its permitted data, and holds an approved use case with a tier and a review date in under a minute (FDR-01, FDR-02).
5. A member submits a request through the intake form; questions appear and disappear with their answers; the likely tier updates as they go; the submitted record shows its tier and the reason for every factor (INT-01 to INT-05, TIR-01 to TIR-03, TIR-08).
6. The request is routed by rule to the right review functions; reviewers record findings in parallel; a question to the requester pauses the clock; the decider sees one packet and issues a decision with a rationale and conditions (TIR-05, REV-01 to REV-08).
7. Nobody can decide or review their own request, and a stopped request cannot be approved.
8. Every change above appears in the record's history with who, when, and before and after; `govwren verify` confirms the chain, and reports the exact event after a row is altered by hand (INV-04, PLT-06).
9. An administrator sets the product name, logo, palette, and accent color in the app and sees them applied at once, in light and dark, with contrast checked (PLT-07, PLT-08).
10. `govwren demo` builds the demo organization in under a minute, and every wave 1 screen has convincing data (PLT-09).
11. The app passes the automated accessibility checks in every palette and mode (PLT-14); lint and the private-terms check are clean.

Requirements delivered: FDR-01 to FDR-04; INT-01 to INT-05; TIR-01 to TIR-08; REV-01 to REV-08; INV-01 to INV-04; RPT-01; PLT-01 to PLT-09, PLT-12, PLT-14; DOC-01.

## Decisions needed from the maintainer

None block the start. These defaults have been taken and can be changed before the slice that depends on them:

- **Tier names:** Minimal, Moderate, High, Critical (slice 5).
- **Default palette:** Wren, with a juniper-green accent (slice 3).
- **Demo organization name:** Alderpoint Institute for Medical Research (slice 8).
- **Member visibility default:** Summary (slice 4).
- **Repository hosting and continuous integration:** GitHub with a workflow that runs the suite on both databases (slice 1).

---

## Slice 1: Foundation ☑

**Goal:** a skeleton in which the rules of the architecture are already enforced.

- [x] Project: `pyproject.toml` with the six runtime dependencies, `uv.lock`, `.python-version`, `src/govwren` layout, `govwren` entry point, ruff and pytest configuration, Apache 2.0 `LICENSE` and `NOTICE`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`
- [x] Configuration: `govwren.toml` read with the standard library into frozen typed settings; unknown keys are errors; all problems reported together; environment overrides; secrets refused in the file
- [x] Data home: creation, marker, and checks
- [x] Database: engine for SQLite (write-ahead log, foreign keys on) and PostgreSQL; portable JSON and UTC date-time types; a naming convention for constraints; declarative ORM base; one session per request
- [x] Migrations: Alembic inside the package with no `alembic.ini`; revision `0001`; `govwren db upgrade | current`; `serve` refuses a schema that is behind
- [x] History: the `event` table; sessions that record every change to an audited row, with before and after values, in the same transaction; refusal of writes with no actor and of bulk statements on audited tables; the hash chain; `govwren verify`; triggers on both databases refusing update and delete
- [x] References: per-prefix counters that never reuse a number
- [x] Command line: `init`, `serve`, `db`, `verify`, `doctor`, with a reference page generated from the parser
- [x] API: the app factory, the envelope and problem-document conventions, security headers, health and `meta` endpoints, the static shell with a fallback route, `docs/openapi.json` kept current by a test
- [x] Tests on both databases: fixtures, a script to start a local PostgreSQL, `scripts/test-both.sh`
- [x] Continuous integration: lint, format check, tests on SQLite and PostgreSQL (the private-terms check runs locally, from git hooks, because its list is never published)
- [x] `scripts/check_terms.py` with pre-commit and commit-message hooks

**Acceptance (met):** a fresh clone initializes and serves an empty shell; the suite passes on both databases; altering an event row by hand is caught by `govwren verify`; a write that bypasses the service helper fails a test that compares table changes with events. 102 tests pass on SQLite and 98 on PostgreSQL (four are about the SQLite file); history tests cover altered, removed, truncated, and re-hashed events, and four writers at once.

## Slice 2: Accounts, roles, and units ☑

**Goal:** people can sign in, and the system knows who may do what, where.

- [x] `account`, `credential`, `membership`, `role_grant`, `session_token`, `failed_sign_in` (migration 0002); scrypt hashing; password rules; throttling per account and address; `HttpOnly`, `SameSite=Strict` cookies; CSRF token and origin checks
- [x] `govwren init` creates the first administrator; `govwren users add | list | disable | enable | reset-password | roles`; `serve` refuses to start with no administrator
- [x] `role_grant` with unit scope and review function; the principal, with the units a steward covers worked out at sign-in; the policy table as an app-wide dependency; refusal of any route without a policy
- [x] `org_unit` tree and `membership`; import of units and people from CSV with a dry run that lists every problem by row
- [x] API: session, accounts, roles, units, and imports
- [ ] Moved to slice 3, where the design system they need arrives: the sign-in page, user menu, password change, and Admin → People and units
- [ ] Moved to slice 6, where there is something to separate: the separation-of-duties checks on reviews and decisions

**Acceptance (met):** the role-by-route matrix test signs in as each role and exercises every route, and a second test fails when a route has no policy or a policy has no route; a steward of a division covers its labs and no others; the last administrator can be neither demoted nor disabled, in the app or at the command line; CSRF, cross-site requests, throttling, idle and absolute expiry, sign-out, and the ending of sessions on disablement and password change are tested. 157 tests pass on SQLite and 153 on PostgreSQL.

## Slice 3: Web app and design system ☑

**Goal:** a shell that already looks and behaves like a finished product.

- [x] From slice 2: the sign-in page, user menu, password change, and Admin → People and units (accounts, roles, units, and the import screens)
- [x] `tokens.css`, `palettes.css` (Wren, Slate, Garnet), `base.css`, `components.css`, `pages.css`; light, dark, and system modes; a palette can be applied to part of a page, which the Appearance preview uses
- [x] The wren mark as SVG: mark, mark with wordmark, single color; the default favicon
- [x] Core modules: DOM helper, router with URL state, API client with CSRF and caching, session and permissions, preferences
- [x] Components: shell, sidebar, top bar, page header, tabs, drawer, dialog, table, record chip, tier badge, standing pill, stat tile, toast, form fields with server errors on their fields, empty and error states, skeletons
- [x] Command palette (⌘K, Ctrl-K, or `/`) and Escape to close anything open
- [x] Branding: the `setting` table (migration 0003), `/theme.css` generated from it, logo and tab-icon upload with type sniffing and SVG sanitizing, Admin → Appearance with a live preview in both modes and contrast results before saving
- [x] Home: for a new installation's administrator, a setup checklist that ticks itself off
- [x] Tests: no inline script or style, no third-party origins, no parsing of data as HTML, every import and route resolves, every script parses, size budgets, and contrast for 30 token pairs in every palette and mode

**Acceptance (met, with two limits noted):** an administrator changed the organization name, palette, and accent in the browser and saw them applied at once, with no file touched; every palette passes AA for text, status, tier, and control-border tokens in both modes; the shell is 26 KB gzipped against a budget of 100 KB. The limits: contrast is checked on the tokens, not yet by sampling rendered pages (that arrives with the accessibility audit in slice 9); and keyboard use was checked for sign-in, the command palette, menus, and drawers, not yet by a full walk of every screen. The import screens' file picker was exercised through the API, not by hand in a browser.

## Slice 4: Inventory core ☑

**Goal:** the three records a request needs, done properly.

- [x] Models and services for use cases, AI systems (with catalog standing, edition, access path, permitted data class, excluded kinds of data, and terms), and vendors; owners in three capacities; typed links, with *uses* from a use case to a system; tags (migration 0004)
- [x] Vocabularies as settings, with defaults: data classes (Public, Internal, Protected, Restricted, each with a definition and examples by kind of data), data categories, domains, stages, decision roles, affected groups, uses of outputs, owner kinds, system kinds, hosting, access paths, review functions, and unit kinds. A value in use can be relabelled or retired, never removed
- [x] List pages with search, filters, sort, and paging, all in the URL; detail pages with a shared header and tabs
- [x] The History tab as a readable timeline: who did what, and each changed field with what it was and what it became, in the organization's own labels
- [x] Visibility: open, summary, and unit settings; restricted records; drafts seen only by their author; one rule used for single records and for lists
- [x] Optimistic concurrency on edits: a change made against an older version is refused
- [x] Catalog standing and vendor standing can be set only by governance; whoever added a record may keep shaping it until governance takes it up
- [ ] Moved to wave 2 (program editors): screens for editing vocabularies and the visibility setting. Both can be changed through the API now

**Acceptance (met):** each record type can be created, edited, and found; every edit is in its history under a named operation; a table of what each of the six roles sees of five use cases under each of the three settings is tested for single records and for lists, which must agree; a stale edit is refused and an invalid one leaves the record as it was. 202 tests pass on SQLite. Checked in the browser: lists, filters, record pages, the history timeline, and the edit forms.

## Slice 5: Intake and tiering ☐

**Goal:** a form that adapts, and a tier that explains itself.

- [ ] The condition evaluator in Python and its JavaScript twin, with one shared file of test cases run by both
- [ ] Form definitions and versions; the default staged intake form; validation of responses against their version; answers mapped to record fields
- [ ] The form renderer: every question type, conditional sections, validation, autosave, resume
- [ ] The scoring model: factors, contributions, tiers, floors, stops; the default six-factor model
- [ ] `tier_assessment` with factor levels and reasons; override with a reason
- [ ] The live tier panel beside the form; the "why this tier" panel on the record
- [ ] The default program pack as a file, loaded by `init`; `govwren program export | import`

**Acceptance:** the two evaluators agree on every shared case; a response always renders with its own form version after the form changes; the server's tier matches the browser's preview for the same answers; a floor raises a tier and says so; a stop is shown as a stop.

## Slice 6: Review and decisions ☐

**Goal:** the right people see a request, and their judgment is recorded.

- [ ] From slice 2: separation of duties in the service layer (nobody reviews or decides their own request, or overrides its tier)
- [ ] Routing rules and rule sets; the default tracks for four tiers; function triggers
- [ ] Reviews, review tasks, assignment and claiming, due dates in working days, the paused clock
- [ ] The review queue as a split view with keyboard flow
- [ ] Findings; discussion with requester-visible and internal comments
- [ ] The decision packet; decisions with required rationale; conditions with the standard library; before-use conditions holding an approval
- [ ] Automatic approval as a rule effect, marked on the record with the rule that made it
- [ ] In-app notifications for assignments, questions, and decisions

**Acceptance:** a request of each tier follows its default track; adding a review function at triage requires a reason; time with the requester is excluded from reviewer turnaround; a decision cannot be edited, only superseded; the separation-of-duties cases are refused.

## Slice 7: Catalog and home ☐

**Goal:** the fastest path, and one place to see what you owe.

- [ ] The catalog: search, cards with standing, permitted data, and terms
- [ ] Registration from the catalog: three questions, the automatic-approval rule, fall-through to intake with answers carried forward
- [ ] Home: one list of what the person owes, overdue first, with queue summaries for reviewers and governance
- [ ] The program dashboard: counts by tier, standing, stage, unit, and domain; open reviews by age; overdue items; each tile linked to its records

**Acceptance:** registration of a permitted use completes in under a minute by a first-time user; a use beyond what the system permits lands in intake with nothing retyped; every dashboard figure opens the list that produced it.

## Slice 8: Demo organization ☐

**Goal:** a believable institute that exercises everything in the wave.

- [ ] The generator: units, people, vendors, systems, and use cases, built through the services under a simulated clock, deterministic by seed
- [ ] The wave 1 storylines from [demo-organization.md](../demo-organization.md)
- [ ] Sample accounts for each role, one-click sign-in on the demo's sign-in page, the "Demo data" marker, and the local-only guard
- [ ] `govwren demo [PATH] [--seed N] [--force]`
- [ ] A test that builds the demo and checks every wave 1 screen has data and the history verifies

**Acceptance:** the same seed gives an identical organization; the build takes under a minute; no invented name collides with the private-terms list.

## Slice 9: Release prep ☐

**Goal:** something a stranger can install and understand.

- [ ] `README.md` with a quickstart; guides for getting started, requesting, reviewing, running the program, configuration, and the API
- [ ] The automated accessibility audit over the wave's screens
- [ ] Changelog, version, lock file, fresh-clone check on both databases
- [ ] Release

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-18 | Wave planned. Both databases are supported from the first slice instead of being added later, because retrofitting a second database costs more than never letting it drift |
| 2026-11-18 | Slice 1: events are recorded by the session after each flush instead of by a helper that services call, so a change cannot be made without one. Append-only triggers were added on SQLite as well as PostgreSQL |
| 2026-11-19 | Slice 3: form-field borders got their own token (`--control-border`) at 3:1 against the page, because the general border token is too faint to mark where a field is. Tier colors use one plum hue and are tested to sit at least 40° from green, amber, and red |
| 2026-11-19 | Slice 4: the default data classes are Public, Internal, Protected, and Restricted, each with a definition and examples grouped by kind of data, shown beside the question in forms. An AI system's vendor is a column on the system; the general link table carries *uses* for now and the other relations in wave 2 |
| 2026-11-18 | The catalog and one-minute registration are in wave 1 and not later, because the product's main bet is that the easy path must exist before anyone is asked to use the system |
