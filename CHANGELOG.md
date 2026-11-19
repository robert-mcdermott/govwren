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
