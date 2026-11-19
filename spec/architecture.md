# Architecture

GovWren is a **modular monolith**: one Python package, one web process, one database, and a command-line tool that runs the same code. There are no message brokers, caches, search clusters, or worker fleets. A single machine is the reference deployment, and a laptop is enough to try it.

## System overview

```text
                              PEOPLE
        browser (vanilla JS app)          scripts and other systems
                 │                                   │
                 │ HTTPS / JSON                      │ API tokens, webhooks (wave 6)
                 ▼                                   ▼
  ┌────────────────────────────────────────────────────────────────┐
  │ Web API (FastAPI + uvicorn)                                     │
  │ /api/v1 · static web app · generated theme · access policy      │
  └───────────────────────────────┬────────────────────────────────┘
                                  │
  ┌───────────────────────────────▼────────────────────────────────┐
  │ Services  (the only code that writes)                           │
  │ inventory · intake · tiering · review · oversight · assurance   │
  │ reporting · program settings · notifications                    │
  │        every write ──▶ permission check ──▶ event               │
  └──────┬───────────────────────┬───────────────────────┬─────────┘
         │ SQLAlchemy ORM        │ files by hash         │ queued mail
         ▼                       ▼                       ▼
  ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
  │ Database     │        │ Data home    │        │ SMTP         │
  │ SQLite, or   │        │ files/       │        │ (optional)   │
  │ PostgreSQL   │        │ exports/     │        └──────────────┘
  └──────▲───────┘        └──────────────┘
         │
  ┌──────┴───────────────────────────────────────────────────────┐
  │ Command line (govwren)                                        │
  │ init · serve · db · users · demo · jobs · program · export    │
  │ import · verify · doctor                                      │
  └───────────────────────────────────────────────────────────────┘
```

Nothing in this picture reaches out to the rest of the network. The only outbound connections GovWren ever makes are to the mail server and identity provider an administrator configures, and, from wave 6, to webhook addresses an administrator registers.

## Layers

| Layer | Package | Rule |
|---|---|---|
| **API** | `govwren.api` | Parses requests, calls one service function, shapes the response. No business rules, no queries |
| **Services** | `govwren.inventory`, `.intake`, `.review`, … | All business rules. Every function that changes data takes the acting principal, checks permission, and writes through an audited session, which records an event for each change in the same transaction |
| **Model** | `govwren.db` | SQLAlchemy ORM models, portable column types, the engine and session, and migrations |
| **Core** | `govwren.core` | Shared, dependency-free pieces: the condition evaluator, clock, errors, references |

The one rule that matters most: **only services write.** The API, the command line, the demo generator, imports, and scheduled jobs all go through the same service functions, so permission checks, validation, and history cannot be bypassed by taking a different door.

## Components

- **Program settings** (`govwren.program`). Everything the governance team configures: vocabularies, forms, the scoring model, rules, condition templates, cadences, and branding. Stored in the database, versioned, edited in the app, and exported or imported as a program pack. A built-in default pack is loaded by `govwren init`.
- **Condition evaluator** (`govwren.core.conditions`). One small interpreter for the declarative conditions used by form visibility, scoring contributions, routing rules, and control applicability. Data in, boolean out; no expression strings and no evaluation of code. The same definitions are sent to the browser, where a JavaScript twin of the evaluator drives the adaptive form and the live tier indicator; a shared set of test cases keeps the two in agreement.
- **Intake and tiering** (`govwren.intake`). Renders nothing itself: it validates responses against a form version, maps answers to record fields, and computes tier assessments from the scoring model.
- **Review** (`govwren.review`). Applies routing rules, opens reviews and tasks, tracks the clock, records findings, decisions, and conditions, and runs committee sessions.
- **Inventory** (`govwren.inventory`). The six record types, owners, links, external references, the dependency graph, completeness, and duplicates.
- **Oversight** (`govwren.oversight`). Schedules, campaigns and attestations, change requests, exceptions, incidents, actions, and retirement.
- **Assurance** (`govwren.assurance`). Risks, controls and their implementations, frameworks and crosswalks, policies, and evidence.
- **Reporting** (`govwren.reporting`). Measures with their definitions, portfolio queries, dossiers, snapshots, and exports.
- **History** (`govwren.events`). The append-only event log, its hash chain, verification, and as-of reconstruction.
- **Access** (`govwren.auth`, `govwren.access`). Local accounts, sessions, single sign-on, role grants, and the policy table that every route and service call is checked against.
- **Files** (`govwren.files`). Content-addressed storage in the data home, with size and type limits, and downloads that are always served as attachments.
- **Notifications** (`govwren.notify`). In-app notices, an email outbox, digests, and per-person preferences. Mail is sent with the standard library.
- **Jobs** (`govwren.jobs`). A small scheduler for daily work: reminders, lapses, campaign openings, evidence expiry, digests. Jobs are rows with a lease, so exactly one process runs each. The web process ticks the scheduler itself; `govwren jobs run` does the same from cron or a systemd timer for installations that prefer it.
- **Search** (`govwren.search`). One `search_doc` row per record, maintained by the services, queried the same way on both databases, and always filtered by what the searcher may see.
- **Demo** (`govwren.demo`). Builds the fictional organization by calling the services in order with a simulated clock, so every record, review, and event in the demo is real output of the real code. See [demo-organization.md](demo-organization.md).
- **Operations** (`govwren.ops`). Export and import of a whole installation, `doctor`, and status.

## Request flow: submitting a request

1. The browser loads the published intake form and the scoring model from `/api/v1`. As the requester answers, the JavaScript evaluator shows and hides questions and updates the likely tier.
2. Drafts are saved as they change with `PUT /api/v1/use-cases/{ref}/draft`.
3. On submit, `POST /api/v1/use-cases/{ref}/submit` calls `intake.submit()`. In one transaction it validates the response against the form version, fills the record, computes the tier assessment on the server (the browser's figure is only ever a preview), applies the routing rules, opens the review and its tasks, queues notifications, and appends an event for each change.
4. The response carries the tier, its reasons, the reviews required, and the target date, which the requester sees at once.

## Storage

- **Database.** SQLAlchemy 2 ORM with a synchronous engine and one session per request. SQLite is the default: a single file in the data home, in write-ahead-log mode, with foreign keys on. PostgreSQL is selected by a URL. The model uses only portable types (a JSON type that becomes `JSONB` on PostgreSQL, and a UTC date-time type that refuses naive values), a fixed naming convention for constraints, and no database-specific SQL in application code.
- **Migrations.** Alembic, driven from inside the package with no `alembic.ini`. Revisions are numbered in order and written to run on both databases (batch mode on SQLite). Migrations run when an administrator says so (`govwren init`, `govwren db upgrade`), never silently at startup; `govwren serve` refuses to start against a schema that is behind and says what to run.
- **Both databases from the first commit.** The whole test suite runs on SQLite and on PostgreSQL in continuous integration. Supporting a second database is cheap when it is never allowed to drift and expensive to retrofit.
- **Data home.** One directory holds everything that is not in the database: `files/` (evidence and attachments, stored by SHA-256), `brand/` (uploaded logos), `exports/`, and `logs/`. With SQLite the database file is here too, so backing up an installation is copying one directory.

## Web app

- **A static shell and a JSON API.** There are no server-side templates. `index.html` loads CSS and one ES module; the app fetches `/api/v1/meta` and `/api/v1/session`, then renders. Unknown paths return the shell so that the client-side router can handle them.
- **No build step, no frameworks.** Plain ES modules, a 40-line DOM helper, a History API router in which the URL holds all view state, and one module per page. What is in the repository is what the browser runs.
- **Strict content security policy.** `default-src 'self'` with no inline script or style and no third-party origins. The DOM helper only ever inserts data as text.
- **Generated theme.** `/theme.css` is produced by the server from the branding settings and loaded after the built-in palettes, so an organization's colors apply without touching a file. See [ux.md](ux.md).
- **Charts and graphs** are drawn as SVG by small modules in the app. No charting library.
- **Budgets.** The gzipped app shell stays under 100 KB and each lazily loaded part under 40 KB; tests enforce both, along with the rules above.

## API

- Everything the web app does, it does through `/api/v1`. There is no private back channel.
- Success responses are `{"data": …, "meta": …}`. Lists take `limit` and an opaque `cursor`. Errors are `application/problem+json`.
- Every route appears in one **policy table** that names the permission it requires. A route missing from the table is refused, and a test fails the build if one is added without a policy.
- The OpenAPI document is generated, committed as `docs/openapi.json`, and kept current by a test. The documentation site renders the API reference from it.
- Uploads are sent as the raw request body with the file name in a header, which avoids a multipart parser.

## Configuration

GovWren separates two kinds of configuration by one rule: **the deployment lives in a file; the program lives in the database.**

| | Deployment | Program |
|---|---|---|
| **What** | Server address and port, database URL, data home, sign-in providers, mail server, session lifetimes | Vocabularies, forms, scoring, rules, cadences, condition templates, controls, branding |
| **Where** | `govwren.toml`, with environment overrides (`GOVWREN_<SECTION>_<KEY>`) | The database |
| **Who** | The administrator who runs the server | Governance and admin roles, in the app |
| **Changes** | Take effect on restart | Take effect at once, on every worker, and are recorded as events |
| **Moves by** | Copying the file | Exporting and importing a program pack |

The file is read with the standard library's TOML parser into typed, frozen settings. Unknown sections and keys are errors, every problem is reported in one pass, and relative paths resolve against the file's own directory so an installation moves as a unit. **Secrets never go in the file**: a key that looks like a secret is rejected, and the file instead names the environment variable that holds it (`client_secret_env = "GOVWREN_OIDC_CLIENT_SECRET"`).

## Runtime and deployment

- `govwren serve` runs uvicorn with one or more workers. All state is in the database, so workers share nothing in memory that matters.
- Sign-in is always required. `govwren init` creates the first administrator, and the server refuses to start without one.
- Behind a reverse proxy that terminates TLS, GovWren reads `X-Forwarded-Proto` and `X-Forwarded-Host` to set secure cookies, check request origins, and build sign-in redirects.
- Health endpoints: `/api/v1/health/live` and `/api/v1/health/ready` (database reachable and schema current).
- Deployment recipes (a container image, a compose file with PostgreSQL, a hardened systemd unit, and proxy examples) arrive in wave 6 under `deploy/`.

## Directory layout

```text
govwren/
├── pyproject.toml · uv.lock · .python-version
├── README.md · CHANGELOG.md · CONTRIBUTING.md · SECURITY.md · LICENSE · NOTICE
├── govwren.example.toml
├── spec/                      this folder
├── docs/                      guides (the site's source), images, capture/, site/
├── deploy/                    container, systemd, proxy (wave 6)
├── scripts/                   check_terms.py, dev-postgres.sh, test-both.sh
├── tests/                     pytest suite, js/ tests, fixtures
└── src/govwren/
    ├── __init__.py · __main__.py · config.py · home.py
    ├── core/                  conditions, clock, errors, refs, log
    ├── db/                    engine, session, types, models/, migrations/
    ├── auth/                  passwords, sessions, accounts, oidc, sso
    ├── access/                roles, principal, policy table
    ├── events/                event log, chain, as-of
    ├── program/               settings, vocabularies, forms, scoring, rules, packs
    ├── inventory/ · intake/ · review/ · oversight/ · assurance/ · reporting/
    ├── files/ · search/ · notify/ · jobs/ · ops/
    ├── demo/                  the fictional organization
    ├── api/                   app factory, routers/, problems, security headers, static
    ├── cli/                   argparse commands, doctor, generated reference
    ├── resources/             example config, default program pack, framework packs
    └── web/static/            index.html, css/, js/core, js/components, js/pages, img/
```

## Cross-cutting concerns

| Concern | Approach |
|---|---|
| **Time** | UTC everywhere in storage; an injectable clock, so tests and the demo can run at any date |
| **Identifiers** | Integer keys inside; permanent prefixed references outside ([data-model.md](data-model.md#conventions)) |
| **Errors** | One exception hierarchy; the API maps it to problem documents and the command line to messages and exit codes |
| **Validation** | At the service boundary, so the API, imports, and the command line get the same answers |
| **Concurrency** | Optimistic: records carry a version, and a stale edit is refused with the current values, never silently overwritten |
| **Logging** | Standard library logging to the console and the data home; no request bodies or answers are logged |
| **Security** | [security.md](security.md) |
| **Testing** | pytest, offline, on both databases; a role-by-route matrix test; JavaScript tests with Node's built-in runner; the demo build as an end-to-end test |
| **Private terms** | A script checks committed content against a local, untracked list of words that must not appear |

## Dependency budget

Every runtime dependency must justify itself, and adding one requires a decision record.

| Package | Why |
|---|---|
| `fastapi` | The web framework and OpenAPI generation (brings `pydantic` and `starlette`) |
| `uvicorn` | The server |
| `sqlalchemy` | The ORM, and one model for two databases |
| `alembic` | Migrations |
| `httpx` | Calls to the identity provider and, later, webhooks; also the test client |
| `psycopg` *(optional extra)* | The PostgreSQL driver, installed only when PostgreSQL is used |

Deliberately absent, with what is used instead:

| Not used | Instead |
|---|---|
| A template engine | A static shell and the JSON API |
| A password-hashing package | `hashlib.scrypt` from the standard library |
| A JOSE or OpenID Connect package | A few hundred lines over the standard library and `httpx` ([ADR-0008](decisions/0008-accounts-and-single-sign-on.md)) |
| A multipart parser | Raw-body uploads |
| A task queue or broker | Leased job rows in the database |
| A search engine | A search table in the same database |
| A PDF library | Print styles; the browser prints to PDF |
| A YAML parser | TOML for the deployment file and JSON for packs, both in the standard library |
| Any JavaScript package | Hand-written ES modules |

Development adds only `pytest` and `ruff`. The documentation site and screenshot capture need Node 22 and no packages ([ADR-0009](decisions/0009-documentation-toolchain.md)).
