# Changelog

GovWren follows semantic versioning. Each wave of the [roadmap](spec/roadmap.md) is a
release. Before 1.0, a release may contain breaking changes; they are listed under
**Breaking**.

## Unreleased

Wave 1, *Front door*, in progress.

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
