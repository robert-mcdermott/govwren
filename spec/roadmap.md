# Roadmap

GovWren ships in **waves**. Each wave is a release (wave 1 → v0.1.0, wave 2 → v0.2.0, …) and is split into **slices**: coherent chunks of related work. The last slice of every wave prepares the release. See [process.md](process.md) for how this works day to day.

The order follows the path of a request. Wave 1 gets a request in and decided. Wave 2 turns what was decided into a trustworthy inventory. Wave 3 keeps it true over time. Waves 4 and 5 add depth for the people who must assure and report. Waves 6 to 8 make it something another organization can adopt, connect, and depend on. Every wave ends with something that can be demonstrated on the demo organization.

| Wave | Version | Theme | The demo at the end |
|---|---|---|---|
| 1 | v0.1.0 | **Front door** | Install, sign in, and take a request from "may I use this?" through tiering, review, and a recorded decision; register a catalog tool in a minute |
| 2 | v0.2.0 | **System of record** | A connected inventory of use cases, systems, models, agents, datasets, and vendors; single sign-on; governance edits its own forms and rules |
| — | — | **Documentation site** | A product site with illustrated guides, screenshots of the demo organization, and an API reference |
| 3 | v0.3.0 | **Keeping watch** | The inventory stays current: re-reviews, attestation campaigns, change, exceptions, incidents, and committee sessions |
| 4 | v0.4.0 | **Assurance** | Risks, a control library with evidence, policies, and optional framework readiness |
| 5 | v0.5.0 | **Insight** | Leaders see the portfolio with defined measures; an auditor exports a complete dossier and a frozen report |
| 6 | v0.6.0 | **Adoption** | Another organization installs, brands, and runs GovWren in production, and moves its setup in as a pack |
| 7 | v0.7.0 | **Connected** | Other systems check a reference before they proceed; assistants read and draft; optional integrations |
| 8 | v1.0.0 | **Stable** | Any earlier release upgrades with nothing lost; the API, configuration, and packs carry a compatibility promise |

Status key: ☐ planned · ◐ in progress · ☑ done

---

## Wave 1: Front door (v0.1.0) ☑

**Goal:** prove the core loop. A person asks, the system tiers and routes, reviewers find, someone decides, and all of it is on the record.

| Slice | Name | Delivers | Status |
|---|---|---|---|
| 1 | Foundation | Project skeleton, configuration, data home, the ORM model and migrations on SQLite and PostgreSQL, the service layer with the event log and hash chain, command line and API skeletons, tooling and continuous integration | ☑ |
| 2 | Accounts, roles, and units | Local accounts and sessions, the six roles with scopes, the route policy table, the unit hierarchy, import of units and people | ☑ |
| 3 | Web app and design system | Vanilla JS shell, tokens, three palettes in light and dark, the wren mark, branding settings with live preview, command palette, core components | ☑ |
| 4 | Inventory core | Use cases, AI systems, and vendors with owners, lists, detail pages, and history | ☑ |
| 5 | Intake and tiering | The form engine and default form, the condition evaluator in Python and JavaScript, the scoring model, tier assessments with reasons, the live tier indicator | ☑ |
| 6 | Review and decisions | Routing rules, triage, parallel review tasks, discussion with the requester, the decision packet, decisions, conditions, in-app notifications | ☑ |
| 7 | Catalog and home | The catalog, one-minute registration with automatic approval by rule, the home page of what each person owes, the program dashboard | ☑ |
| 8 | Demo organization | The fictional institute, built through the services under a simulated clock, with storylines for every wave 1 screen | ☑ |
| 9 | Release prep | Guides, quickstart, changelog, accessibility check, version, release | ☑ |

Detail: [waves/wave-1.md](waves/wave-1.md)

## Wave 2: System of record (v0.2.0) ☑

**Goal:** make the inventory complete enough to rely on and the program editable by the people who run it, and let people sign in with the identity they already have.

| Slice | Name | Delivers | Status |
|---|---|---|---|
| 1 | Single sign-on | OpenID Connect with discovery, PKCE, and verified tokens; accounts created at first sign-in; groups or application roles mapped to roles, unit scopes, and review functions; a guide for Microsoft Entra ID | ☑ |
| 2 | Models, datasets, and agents | Model records with model cards and lineage, including open-weight models run locally and models fine-tuned in-house (weights provenance, license restrictions, where they run, and sensitivity inherited from training data); models in the catalog; dataset records; agent profiles; vendor agreements with renewal dates; external references | ☑ |
| 3 | Links and the graph | Typed links, "depends on" and "used by" on every record, the focused dependency graph with a list fallback | ☑ |
| 4 | Evidence and files | Content-addressed file storage, evidence items with owners and expiry, attachments on answers and conditions | ☑ |
| 5 | Find and tidy | Search across all records, saved views, completeness scoring, possible duplicates and merging | ☑ |
| 6 | Import and export | Spreadsheet import with mapping and a dry run; CSV and JSON export of every list; program packs | ☑ |
| 7 | Program editors | Form builder with preview, scoring model and rules editors with impact preview, vocabularies, condition templates; the "may I use…" lookup and requests for evaluation | ☑ |
| 8 | Email | SMTP delivery, digests, per-person preferences | ☑ |
| 9 | Release prep | Guides, changelog, dependency review, release | ☑ |

Detail: [waves/wave-2.md](waves/wave-2.md)

## Documentation site (between v0.2.0 and v0.3.0) ☑

**Goal:** a product site that lets someone outside the project find GovWren, see it, and try it.

It waits until the main screens have settled; screenshots taken during wave 1 would be stale within weeks. Until then the Markdown in the repository is the documentation, written so that the site can be built from it unchanged.

- **The guides stay the source.** `README.md` and `docs/*.md` are what the repository shows and what the site is built from, so the two never disagree.
- **Site generator:** a script needing Node 22 and no packages. It builds a home page and one page per guide, with a menu in reading order, client-side search, light and dark themes from GovWren's own design tokens, the changelog, and an API reference generated from the OpenAPI document. The build checks every link, anchor, and image and fails on a broken one.
- **Screenshots of the real app.** A capture script drives headless Chrome over its debugging protocol. It builds a fresh demo organization in a temporary directory, starts GovWren on it, signs in as the right sample person for each scene, and saves each scene in both themes. Each scene is one line: a URL, who is signed in, a size, and an optional step. Named scenes can be retaken alone.
- **An accessibility audit** runs over the same scenes and fails on any finding.
- **Diagrams** drawn as SVG in both themes from one color table are left for a later release; the screenshots carry the site for now.
- **Publishing:** the site is whatever is committed on the `gh-pages` branch. The build writes into a worktree of that branch only when asked to publish, so nothing is published by accident. The site states the version it describes.
- **Each release from then on:** retake screenshots for screens that changed, check the guides against the changelog, review in both themes and at phone width, then publish.

Decision record: [ADR-0009](decisions/0009-documentation-toolchain.md)

## Wave 3: Keeping watch (v0.3.0) ☑

**Goal:** an inventory that stays true without a central team chasing it.

| Slice | Name | Delivers | Status |
|---|---|---|---|
| 1 | Schedules | The job scheduler, approval periods and cadences by tier, periodic reviews opened with earlier answers, lapsed standing, reminders and escalation | ☑ |
| 2 | Attestation campaigns | Owner confirmation and unit completeness campaigns, bulk confirmation, coverage by unit | ☑ |
| 3 | Change and retirement | Change declarations with material-change rules and limited reviews; retirement with dependents notified; inherited findings on dependents | ☑ |
| 4 | Exceptions | Requests, approval, compensating measures, expiry and renewal, the register | ☑ |
| 5 | Incidents and actions | Reporting, triage, linked records, suspension, incident-triggered reviews, one list of actions | ☑ |
| 6 | Sessions and acceptance | Committee sessions with agendas and minutes; named risk acceptance; sampled checks of automatic approvals | ☑ |
| 7 | Release prep | Guides, changelog, release | ☑ |

Detail: [waves/wave-3.md](waves/wave-3.md)

## Wave 4: Assurance (v0.4.0) ☑

**Goal:** show that the program's safeguards exist and work, with evidence, and without turning governance into a checklist exercise.

| Slice | Name | Delivers | Status |
|---|---|---|---|
| 1 | Risks | The risk register with inherent and residual scoring, the risk library, risks from review findings | ☑ |
| 2 | Controls | The control library, program and record scope, applicability rules, implementation status, owners | ☑ |
| 3 | Evidence freshness | Evidence linked to controls and conditions, expiry and renewal prompts, gaps surfaced as actions | ☑ |
| 4 | Policies | Versioned policies, review dates, links to controls, acknowledgment campaigns | ☑ |
| 5 | Assessments | Impact assessments required by rule; vendor due-diligence questionnaires and assurances | ☑ |
| 6 | Frameworks | The pack loader, the optional built-in framework with its crosswalk, readiness views, the statement of applicability | ☑ |
| 7 | Release prep | Guides, changelog, release | ☑ |

Detail of the content: [content-packs.md](content-packs.md)

## Wave 5: Insight (v0.5.0) ☑

**Goal:** answer leadership's questions from the record, with figures that explain themselves.

| Slice | Name | Delivers | Status |
|---|---|---|---|
| 1 | Measures | Turnaround, throughput, coverage, currency, and completeness, each with its definition, period, and cohort; daily snapshots for trends | ☑ |
| 2 | Portfolio | Views by unit, tier, domain, vendor, and data class over a chosen period, drilling down to records; the unit report | ☑ |
| 3 | Dossier | A complete, printable package for any record, with a manifest that verifies | ☑ |
| 4 | Leadership report | A periodic report frozen as a snapshot that reopens unchanged | ☑ |
| 5 | As of | Any record, and the inventory, as it stood on a chosen date | ☑ |
| 6 | Open formats and the register | Bill-of-materials and model card export; the transparency register as static pages | ☑ |
| 7 | Release prep | Guides, changelog, release | ☑ |

## Wave 6: Adoption (v0.6.0) ☑

**Goal:** an organization that has never seen GovWren installs it, makes it its own, and runs it in production.

| Slice | Name | Delivers | Status |
|---|---|---|---|
| 1 | Production | Measured performance at 10,000 records and many people at once; several workers; backup, restore, and moving between SQLite and PostgreSQL | ☑ |
| 2 | Brand kit | A custom palette, sign-in page message and image, email header, footer links, the organization's own terms for key words, contrast checks | ☑ |
| 3 | Starter packs | Program packs for a research institute, a university, and an academic medical center; research and health content packs; custom fields; custom frameworks | ☑ |
| 4 | API for others | Scoped tokens, signed webhooks, the checkpoint endpoint, a recorded API contract | ☑ |
| 5 | Deployment | A container image, a compose file, a hardened systemd unit, proxy examples, the operations view, `doctor --production` | ☑ |
| 6 | Security and accessibility review | The standard security verification review; the full accessibility audit and screen-reader check | ☑ |
| 7 | Adopter's guide | Planning a rollout from units and roles to the first campaign | ☑ |
| 8 | Release prep | Guides, changelog, release | ☑ |

## Wave 7: Connected (v0.7.0) ◐

**Goal:** fit into the systems around it while staying passive: others ask GovWren, or push to it; it never goes looking.

| Slice | Name | Delivers | Status |
|---|---|---|---|
| 1 | Checkpoints in practice | Recipes for citing and checking a GovWren reference from purchasing, ethics review, and data access processes; ticket and chat notifications by webhook | ☑ |
| 2 | Tool server for assistants | An optional server through which an AI assistant reads records and drafts requests and updates that a person confirms | ☐ |
| 3 | Signal intake | Other tools push a summary (an evaluation, a monitoring report) onto a record as evidence | ☐ |
| 4 | Metadata sync | Opt-in, read-only, scheduled pulls of model metadata from a registry the organization names; suggestions only, a person confirms | ☐ |
| 5 | Optional assistant | Off and invisible by default; drafts intake answers and summarizes decision packets, with any compatible provider including a local one; every exchange logged | ☐ |
| 6 | Release prep | Guides, changelog, release | ☐ |

## Wave 8: Stable (v1.0.0) ☐

**Goal:** something an organization can build on.

| Slice | Name | Delivers | Status |
|---|---|---|---|
| 1 | Upgrades | An installation of every earlier release upgrades with every row and file kept, on both databases, checked by script | ☐ |
| 2 | The 1.0 promise | A compatibility statement for the API, configuration file, pack formats, and data home; deprecation rules | ☐ |
| 3 | Hardened | The security review repeated; the threat table walked by a second person; load and soak tests | ☐ |
| 4 | Release prep | Guides, changelog, release | ☐ |

## Later

Ideas that are deliberately not scheduled. Each needs evidence from adopters before it earns a wave.

- **Localization** of the interface.
- **Several organizations in one installation**, for consortia and shared service centers.
- **Open intake** for people without accounts.
- **Training records**: who has completed which AI training.
- **Directory provisioning** of accounts and units from an identity system.
- **Object storage** for files.
- **Recorded committee votes** and recusals.
- **A shared pack library** where organizations publish and reuse program and content packs.

## Never

Kept here so the question does not need to be asked again. These would change what GovWren is. See [ADR-0003](decisions/0003-passive-by-design.md).

- Network, log, endpoint, code, or cloud scanning to discover AI.
- Gateways, guardrails, or anything else in the path of an AI request.
- Running evaluations or monitoring against live models.
