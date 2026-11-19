# Changelog

GovWren follows semantic versioning. Each wave of the [roadmap](spec/roadmap.md) is a
release. Before 1.0, a release may contain breaking changes; they are listed under
**Breaking**.

## Unreleased

Wave 2, *System of record*, in progress.

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
