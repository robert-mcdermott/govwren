# Changelog

GovWren follows semantic versioning. Each wave of the [roadmap](spec/roadmap.md) is a
release. Before 1.0, a release may contain breaking changes; they are listed under
**Breaking**.

## Unreleased

### Added

- The risk register: risks on a record or on the organization, scored before and after treatment on two five-point scales, owned, and looked at again on a date. A grid counts open risks by likelihood and impact.
- A risk library of about forty statements written for research and health settings, loaded as a pack. A risk drawn from it keeps its source.
- A control library of about thirty safeguards, loaded as a pack. A control applies to the program, or to every record its rule picks out; it is never copied per record. Each applicable control has a standing, an owner, and a date it is next checked, and each names the risks it answers.
- Evidence attached to a control's standing. Owners are told before evidence expires and when it has, and the action list shows controls whose check is due and controls whose evidence has all expired.
- Policies: each with versions that are never edited once published, an owner, a review date, and the controls that carry it out. People in a unit, or everyone, can be asked to acknowledge the version in force, and coverage is counted by unit.
- Assessments on templates from a pack. An impact assessment of a use is required by rule at the critical tier before approval, and is kept with the review. A due-diligence questionnaire is kept with each vendor, and its review completes the vendor's due diligence.
- Frameworks as optional packs: requirements with stable codes and a crosswalk from the control library, checked on load and refused whole if anything is wrong. Readiness shows each requirement as covered, partly covered, a gap, not mapped, or not applicable, worked out from how the controls stand. One framework is built in, in summary.
- The statement of applicability: every control with whether it applies, why, its status, owner, and evidence, as CSV or JSON.
- A reviewer can record a risk from a review. An open risk at the two highest levels is a finding on its record and on what relies on it.

## 0.3.0 (2026-11-19)

Wave 3, *Keeping watch*: the inventory stays true as time passes. GovWren now acts when
something is due, asks the people closest to the work whether the record is still right,
and records what goes wrong and what is done about it.

### Upgrading from 0.2.0

Run `govwren db upgrade` (migrations 0013 to 0017). Every row is kept and the history still
verifies.

The server now does scheduled work by itself. The first time it runs after the upgrade it
catches up on everything that is already due:

- Every approval whose end date has passed is marked lapsed.
- A periodic review opens for every approval that ends within sixty days, or has ended.
- One reminder goes out for each review task, condition, and confirmation that is nearly due
  or overdue.

On an installation that has run for some time this can be many notices at once. To see what
is waiting before the server acts, set `scheduler = false` under `[server]`, start the
server, and look at the use cases by their approval end date. Then set it back, or run
`govwren jobs run` yourself.

Requests in the highest tier now need a named person to accept the risk before they can be
approved, as the default routing rules have always said. Reviews of such requests that are
open when you upgrade need an acceptance too.

### Changed

- The mailer is now one of the scheduled jobs. `govwren mail run` still works.
- Once a request has been decided, its owners change what it says by declaring a change, where before they had to ask governance.
- The side menu has a new group, Keeping watch, for actions, incidents, attestations, and exceptions.
- `[server] scheduler`, which is `true` unless set otherwise, says whether the server runs scheduled work.

### Added

- A scheduler in the server, with `govwren jobs` and an Admin page. A job is claimed in the database before it runs, so several processes never run the same one at once.
- Periodic reviews: sixty days before an approval ends, a review opens with the owner, who confirms or corrects the earlier answers. Unchanged, low-risk uses are approved again on the spot; the rest go to reviewers.
- Lapsed approvals: an approval that passes its end date without renewal is marked lapsed, with the reason in its history, and comes back when a periodic review approves it.
- Reminders before review tasks, conditions, and confirmations are due, and escalation after: to governance for a review task, to the unit's steward for an owner's work.
- Attestation campaigns. Owners confirm their records in a few clicks, several at once, or report one as changed or no longer in use. Stewards attest that their unit's list is complete. Coverage is shown by unit, with who has yet to answer, and reminders go out before and after the date.
- Retiring a record, with a reason, from a campaign.
- Change declarations. An owner says what is changing and corrects the earlier answers; the rules decide whether the change is material. If it is not, it is recorded and the approval stands. If it is, a change review opens that shows each answer before and after.
- Retiring any record from its page, with a reason. The owners of the records that rely on it are told.
- Inherited findings: a record shows what is known about everything it relies on, such as a tool that is not approved or a model that has been retired, marked with where it comes from.
- Exceptions: a time-limited departure from a requirement, asked for with a justification and what is done instead, decided by governance, shown on the record and on what relies on it, and ended by itself on its date. A register lists them all; a renewal is a new request that points back.
- Incidents. Anyone reports one, or a near miss. Governance triages it with a category and severity, links the records involved, may suspend an approval or open an incident review, and closes it with the cause and what was learned. An open incident shows on its records and on everything that relies on them.
- Actions: one list of what must be done, by whom, and by when, holding the actions set after incidents together with the conditions of decisions. Owners are reminded before the date; governance is told after it.
- Committee sessions: an agenda of the reviews a committee decides, decisions recorded as made in the session, attendance and minutes, and a closed record that cannot be changed.
- Named risk acceptance: where the rules require it, a request cannot be approved until a named person has accepted its risk in their own words.
- Spot checks: a sample of the approvals that rules made by themselves is drawn for a person to check, by the scheduler and on request. Disagreeing calls the approval in for review.
- A documentation site built from the guides, with screenshots of the demo organization in light and dark, search, and an API reference generated from the OpenAPI document.

## 0.2.0 (2026-11-19)

Wave 2, *System of record*: a connected inventory of use cases, systems, models, agents,
datasets, and vendors; single sign-on; email; and a program that governance edits itself.

### Upgrading from 0.1.0

Run `govwren db upgrade` (migrations 0007 to 0012). Every row is kept and the history still
verifies. Two things stay as they were until you choose otherwise:

- **The request form.** An installation keeps the form it has. The questions about models
  people run or train themselves are in the default program shipped with this release; add
  them under Governance, Program, or load the default pack.
- **Email and single sign-on** are off until you give them settings.

No runtime dependency was added in this release.

### Added

- **Single sign-on.** Sign-in through any OpenID Connect provider, using the authorization
  code flow with PKCE. ID tokens are checked for signature (RS256), issuer, audience, expiry,
  and nonce. Accounts are created at first sign-in and recognized afterwards by the
  provider's own identifier, never by an unverified address. An administrator maps the
  provider's groups or application roles to roles, unit stewardship, unit membership, and
  review functions under Admin, Single sign-on; mapped roles are set again at every sign-in
  and roles given by hand are left alone. A mapping never removes the last administrator.
  Password sign-in can be kept for administrators only. `govwren doctor` checks the
  connection. A guide covers Microsoft Entra ID step by step, and a stand-in provider for
  development is in `scripts/` (migration 0007).
- **Models and datasets.** Models are records: a supplier's model, open weights the
  organization runs itself, or a model it fine-tuned or trained. A self-run model records
  where its weights came from, their checksum and format, its license and what the license
  limits, where it runs, and who the weights may go to, and carries a model card. Datasets
  are records too: data class, kinds of data, who it is about, identifiability, source, and
  terms. Reviewed models have a catalog standing, and a use of an approved model registers
  as quickly as a use of an approved tool (migration 0008).
- **A model is as sensitive as its training data.** Linking a model to the data it was
  trained on raises its sensitivity to match, through any number of fine-tunes, and nobody
  can set it lower.
- **Links between records.** Typed links (uses, processes, built on, derived from, trained
  on, evaluated on, embedded in, depends on, replaces), each allowed only between the kinds
  of record it makes sense for, and never in a loop. Every record shows what it is
  connected to.
- **The dependency graph.** Every record has a Connections tab that follows its links in
  both directions for a chosen number of steps: what relies on it, and what it relies on.
  It is drawn as a graph in which every node is a link, and listed beneath as tables with
  how each record is connected and how far away. A model with a withdrawal date leads
  straight to everything built on it. Records a person may not see are counted, not shown.
- **Email.** Notices go out over SMTP, as they happen or as a daily summary, as each person
  chooses under Your account. Messages are written to an outbox in the database and sent
  from there by a mailer that runs inside the server, so a restart loses nothing, a mail
  server that is down is tried again, and several processes never send a message twice.
  Messages carry a line and a link, never the content of a request. `govwren mail test`
  and `govwren mail run`, a `doctor` check, and an Admin page that shows what is waiting
  and the most recent problem (migration 0012).
- **Program editors.** Governance edits the program in the app, on a working copy that is
  not in force until published: the request form (sections, questions, kinds of answer,
  choices, which field an answer fills, and when a question is asked), with a live preview;
  the tiers, the rules that raise each factor, floors, and prohibited uses; the routing
  rules and standard conditions; and every vocabulary. Conditions are built as sentences.
  A check lists every mistake and previews what the change would have done to the requests
  already submitted. Each published part becomes a new version, earlier versions are kept,
  and what was decided is never rewritten.
- **Asking for a tool.** Anyone can ask for a tool that is not in the catalog to be
  evaluated. Requests for the same tool are gathered, governance sees the most asked-for
  first, and everyone who asked is told the answer (migration 0011).
- **Import and export.** Governance imports AI systems, models, datasets, and vendors from
  a spreadsheet saved as CSV: map each column to a field, run it dry, read every problem
  with its row, and import only when every row is good. Rows match existing records by
  name (and edition or version), so an import can be run again. Every list exports as CSV
  or JSON with the filters that produced it recorded in the file, limited to what the
  person may see, and safe to open in a spreadsheet.
- **Find and tidy.** The command palette searches records of every kind as you type, and a
  whole reference goes straight to its record. Any list's filters and sort can be saved as a
  view of your own. Every record shows how complete it is and what is still to record, by
  what is expected of that kind of record, and the dashboard shows the average for each
  kind. Governance sees likely duplicates and can merge one record into another: links,
  evidence, references, and helpers move, a vendor's systems and agreements follow, and the
  old reference keeps working (migration 0010).
- **Evidence and files.** Any record, condition, or review task can carry evidence: a file,
  an address, or a note, with a kind, an owner, a date, and a date it is good until. Files
  are judged by their content, stored once under the SHA-256 of that content, refused if a
  browser could run them, and only ever handed back as downloads. The checksum is in the
  history. Evidence is withdrawn, never deleted. An Evidence page lists it soonest to
  expire first, and the dashboard counts what has expired or is about to, along with
  vendor agreements that are ending (migration 0009).
- **Agent profiles.** A system that acts records how much it does by itself, what it can
  change, the tools it is connected to, who it acts as, whether its actions can be undone,
  how a person stops it, and its limits.
- **Vendor agreements.** Kind, dates, notice period, renewal, and who looks after each one,
  with its standing today: current, ending soon, in its notice period, or ended.
- **References to other systems.** Any record can point to its protocol, grant, agreement,
  purchase, ticket, or repository.
- **Questions for people who run or train models.** The default request form asks whether
  you will run or train a model yourselves and, if so, where its weights come from, where
  it runs, what it is trained on, and who it is shared with. Training on Protected or
  Restricted data raises the tier, and such requests are routed to information security
  and data stewardship.
- **A larger demo.** The demo organization now has about 60 models with lineage, 75
  datasets of every class, agent profiles, and 70 vendor agreements at every stage.

## 0.1.0 (2026-11-19)

Wave 1, *Front door*: install, sign in, and take a request from "may I use this?" through
tiering, review, and a recorded decision; register a catalog tool in a minute.

### Added

- **Foundation.** `govwren init`, `serve`, `db upgrade`, `db current`, `verify`, and `doctor`.
  Deployment settings in `govwren.toml` with environment overrides; secrets are refused in
  the file. A data home for files. SQLite by default and PostgreSQL by address, on one model
  and one set of migrations (migration 0001).
- **History.** Every change to a record is written to an append-only history in the same
  transaction, with who, when, and each value before and after. Events are chained by hash;
  `govwren verify` finds the first event that has been altered, removed, or cut from the end.
  The database itself refuses updates and deletes on the history.
- **API.** `/api/v1` with health and product information, problem-document errors, and
  strict security headers; the OpenAPI document at `/api/openapi.json`.
- **Accounts and roles.** Local accounts with scrypt-hashed passwords, server-side sessions
  in `HttpOnly`, `SameSite=Strict` cookies, a CSRF token on every change, refusal of requests
  from other sites, and throttled sign-in. Six roles: admin, governance, reviewer (by review
  function), auditor, steward (of a unit and those beneath it), and member. Every API route
  is checked against one policy table, and a route with no policy is refused. The last
  active administrator cannot be removed. `govwren init` creates the first administrator,
  and `govwren users` manages accounts from the command line (migration 0002).
- **Units.** The organization as a hierarchy of any depth, with CSV import of units and
  people that can be run dry first and reports every problem by row.
- **The web app.** A sign-in page, an app shell with a sidebar and a command palette (⌘K),
  your account and password, and admin screens for people, roles, units, and imports. Plain
  ES modules with no build step, under a strict content security policy.
- **Themes.** Light, dark, and system modes, and three palettes (Wren, Slate, Garnet), each
  checked for readable contrast in both modes. Each person's choice is remembered.
- **Branding.** Admin → Appearance sets the product name, organization name, default
  palette, accent color, logos, and tab icon, with a live preview. An accent is lifted
  automatically for dark mode and refused if it cannot be read. Uploaded SVG is reduced to
  drawing and served so that it cannot run anything (migration 0003).
- **Inventory.** Use cases, AI systems, and vendors, each with a permanent reference
  (`UC-0142`), named owners, and a page of its own. Lists search, filter, sort, and page,
  with their state in the address so any view can be shared. An AI system's standing in the
  catalog applies to one edition of a product, with the highest class of data it may be used
  with (migration 0004).
- **Data classes and other vocabularies.** Four default data classes (Public, Internal,
  Protected, Restricted) with definitions and examples, and vocabularies for domains, stages,
  kinds of data, and more. All are the organization's to relabel, extend, and retire.
- **History you can read.** Every record has a History tab: who changed what, and each
  field's value before and after, in plain words.
- **Who sees what.** An organization chooses whether everyone sees approved use cases in
  full, in summary, or only within their own units. Restricted records and drafts stay
  private. Two people editing the same record cannot overwrite each other.
- **Requests.** A "New request" form that asks only what each request needs: sections for
  data about people, suppliers, automation, and publications appear when the answers call
  for them. Answers are saved as you go and can be picked up on another device.
- **Risk tiers that explain themselves.** Six factors scored 0 to 3 give one of four tiers
  (Minimal, Moderate, High, Critical). Floors set a minimum tier for serious cases, and stops
  mark prohibited uses. The likely tier and its reasons are shown beside the form as it is
  filled in, and the recorded tier is shown on the use case with the answer behind each
  factor. A reviewer or governance can change a tier with a written reason.
- **The program as a file.** The intake form and scoring model are data. `govwren program
  export` writes them out with every vocabulary, and `govwren program import` loads a pack
  after checking all of it. Earlier versions are kept, so a past request still shows the
  questions it was asked and the rules it was tiered under (migration 0005).
- **Review by rule.** Routing rules send each request to the review functions its tier and
  answers call for, set who decides and by when, and attach standard conditions. A minimal
  request that needs no review is approved on the spot, by a named rule. The request form
  says what will happen before it is submitted.
- **The review queue.** Governance triages, reviewers take tasks and record findings, and
  everything about a request is on one screen for whoever decides. A question to the
  requester stops the clock. A decision needs a reason, is never edited, and says so if it
  was made over an objection.
- **Conditions.** Approvals carry conditions with owners. Those marked *before use* hold the
  approval until they are met.
- **Two rules that always hold.** Nobody triages, reviews, or decides their own request,
  whatever their role. And what reviewers say among themselves is never shown to the
  requester.
- **Notices.** A bell in the top bar, and a home page that lists what is waiting on you,
  overdue first (migration 0006).
- **Catalog and dashboard.** A catalog of the AI tools that have been evaluated, with each
  one's standing, the data it may be used with, and its terms of use, searchable from Home.
  A use of an approved tool for everyday work, with data the tool is approved for, is
  registered in a minute and approved at once under the tool's terms; anything else begins a
  request with what was entered carried forward. A program dashboard for those who may read
  everything: approved uses by tier, unit, area, stage, and status, open reviews by state and
  age, what is overdue, and decisions over the last 90 days with the median time defined
  beside it. The totals and every bar open the records they count.
- **Demo organization.** `govwren demo` builds the Alderpoint Institute for Medical
  Research, a fictional institute with thirty months of history: 66 units four levels deep,
  about 260 people, 40 vendors, 90 AI systems, and 300 use cases at every stage, tier, and
  standing, with reviews, findings, questions, decisions, and conditions. It is made by
  calling the same services the app uses under a simulated clock, so its history verifies.
  The same seed gives the same organization. A demo marks itself on every page, offers
  sign-in as any of nine sample people without a password, and listens only on the machine
  it runs on unless started with `--demo-on-network`.
- **Guides and checks.** A quickstart, and guides for getting started, requesting, reviewing,
  running the program, configuration, and the API, under `docs/`. An automated accessibility
  audit (`node scripts/a11y-audit.mjs`) builds a fresh demo and checks every screen in every
  palette, by day and after dark: names on controls, labels, headings, landmarks, target
  sizes, and the contrast of all text.
