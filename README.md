# GovWren

**AI governance people actually use.**

GovWren is an open system of record for AI governance: one front door for AI requests, review in proportion to risk, a living inventory, and evidence behind every decision. It is built first for research organizations, where many semi-autonomous labs adopt AI tools faster than any committee can track, and it can be adopted and re-branded by any organization.

- **A front door, not a gate.** A catalog of reviewed tools answers "may I use this?" in seconds, and registering a use takes under a minute. Anything new starts with a short form that grows only when the answers call for it.
- **Proportionate.** A transparent risk tier decides who reviews, who decides, and how often a record is revisited. Every tier shows the answers that produced it.
- **Passive by design.** No scanners, agents, or log collectors. GovWren knows what people tell it, and makes telling it the easy path.
- **Built for federated organizations.** Every record belongs to a unit and has named owners. Units attest that their list is complete.
- **An unbroken record.** Every change is written to an append-only, verifiable history.
- **Open and yours.** Apache 2.0. Runs on a laptop with SQLite or on a server with PostgreSQL. Name, logo, colors, forms, and rules are settings.

## Quickstart

You need [uv](https://docs.astral.sh/uv/), which provides the right Python (3.12 or later). Clone this repository, then run these from its directory:

```bash
uv sync                  # install GovWren
uv run govwren init      # write govwren.toml, create ./var and the database, create your administrator
uv run govwren doctor    # check the installation
uv run govwren serve     # run it at http://127.0.0.1:8000
```

`init` asks for your email address, your name, and a password of at least 12 characters. Open the address `serve` prints and sign in. Home then shows a short setup checklist: units, people, appearance.

The administrator account sets the installation up. To triage and decide requests, give someone the governance role, under Admin → People. [Getting started](docs/getting-started.md) walks through all of it.

## Try the demo

To see GovWren with data in it before you set anything up, build the demo organization:

```bash
uv run govwren demo                                # builds ./demo
uv run govwren --config demo/govwren.toml serve    # runs it at http://127.0.0.1:8010
```

The demo is the Alderpoint Institute for Medical Research, a fictional institute with thirty months of history: 66 units, about 260 people, 40 vendors, 90 AI systems, and 60 models, 70 datasets, and 300 use cases, with their reviews, decisions, conditions, and evidence. Nothing in it is real.

Its sign-in page offers nine sample people and asks for no password. Try a few:

| Sign in as | To see |
|---|---|
| Tomas Lind, a researcher | Home, the catalog, registering a use, and making a request |
| Sam Reyes, the governance lead | The review queue, triage, decisions, and the dashboard |
| Wei Chen, the privacy reviewer | Review tasks and findings |
| Ruth Abara, the auditor | Everything, read-only, with the full history |
| Dana Okafor, the administrator | People, units, and appearance |

A demo listens only on the machine it runs on. See [Configuration](docs/configuration.md#the-demo-and-the-network) before changing that.

## What is in this release

Version 0.7.0 takes a request from "may I use this?" to a recorded decision, keeps what was decided as a connected inventory, keeps that inventory true as time passes, lets you show that the safeguards exist and work, answers questions about the whole program from the record, gives an organization what it needs to adopt it and run it in production, and connects it to the systems around it.

**The front door**

- **A catalog** of evaluated AI tools and models, searchable from Home, with one-minute registration of an everyday use, and a way to ask for a tool to be evaluated.
- **A request form** that asks only what each request needs and shows the likely risk tier as you answer.
- **Risk tiers that explain themselves:** six factors, four tiers, floors for serious cases, and stops for prohibited uses.
- **Review by rule:** routing to review functions, a review queue, findings, discussion with the requester, decisions with reasons, and conditions with owners.

**The system of record**

- **An inventory** of use cases, AI systems, models, datasets, and vendors, each with a permanent reference, named owners, and a readable history.
- **Models you run yourselves:** where the weights came from, their checksum and license, where they run, and a model card. A model is never less sensitive than the data it was trained on.
- **Links and a dependency graph:** what each record relies on and what relies on it, as a picture and as a list.
- **Evidence:** files, links, and notes attached to records, conditions, and reviews, stored once by their content, with dates they are good until.
- **Agent profiles, vendor agreements, and references** to protocols, grants, and tickets in other systems.
- **Search, saved views, completeness, and duplicate merging.**
- **Import and export:** bring existing records in from a spreadsheet with a dry run, and take any list out as CSV or JSON.

**Keeping watch**

- **Periodic reviews:** before an approval ends, its owner confirms the earlier answers. Unchanged, low-risk uses are approved again at once. An approval nobody renews is marked lapsed.
- **Attestation campaigns:** owners confirm their records in a few clicks, stewards attest that their unit's list is complete, and coverage is counted by unit.
- **Change and retirement:** an owner declares a change and the rules judge whether it is material. A retired record keeps its history, and its dependents are told.
- **Exceptions:** time-limited, with a reason and something done instead, and an end date that always comes.
- **Incidents and actions:** anyone reports; governance triages, may suspend an approval, and sets actions. One list holds everything someone must do.
- **Inherited findings:** an incident on a model shows on every system built on it and every use of those systems.
- **Committee sessions, risk acceptance, and spot checks** of the approvals that rules made by themselves.

**Assurance**

- **A risk register:** risks on a record or on the organization, drawn from a library of forty, scored before and after treatment, owned, and reviewed on a date.
- **A control library** of more than forty safeguards, each applying to the program or to the records its rule picks out, with a standing, an owner, evidence, and a next check.
- **Evidence that stays fresh:** owners are told before it expires, and a control whose evidence has run out is an action in someone's list.
- **Policies** with versions, review dates, linked controls, and a record of who has acknowledged them.
- **Assessments:** an impact assessment required by rule before approval at the highest tier, and a due-diligence questionnaire for each vendor.
- **Frameworks, if you need one:** the NIST AI RMF, ISO/IEC 42001, and HIPAA come with it, and your own load as data, with readiness worked out from how the controls stand, and a statement of applicability to export.

**Insight**

- **Measures that explain themselves:** turnaround, throughput, coverage, currency, and completeness, each with the sentence that defines it and a trend stored day by day.
- **The portfolio** by unit, tier, area, data class, or supplier, where every figure opens the records it counts, and a one-page report for each unit.
- **Reports to leadership,** worked out once and frozen, so that a report reopens exactly as it was made.
- **Any day in the past:** a record, or the whole list of uses, as it stood on a chosen date, worked out from the history.
- **A dossier for any record:** everything about it on a page to print, and as a package with its evidence and a manifest that verifies.
- **Open formats and a transparency register:** the models as a bill of materials, a model card for each, and chosen approved uses published as plain pages.

**Adopting it**

- **Starter programs** for a research institute, a university, and an academic medical center, and content packs of risks and controls for research and for work near patient care.
- **A brand kit:** your sign-in message and picture, your links, your accent by day and after dark, and your own words for unit, vendor, and the kinds of record.
- **Fields of your own** on any kind of record.
- **For other systems:** API tokens with scopes, a checkpoint that says whether a reference is approved, and signed webhooks.
- **For production:** a container image, a compose file, a sandboxed systemd unit, backup and restore in one file that also moves you between SQLite and PostgreSQL, `doctor --production`, and an operations view.
- **Measured and reviewed:** response times at 10,000 use cases on both databases, a security review whose findings are fixed and recorded, and a keyboard check over every screen.

**Connecting it**

- **Recipes and example programs** for citing and checking a GovWren reference in purchasing, ethics review, and data access, and for sending tickets and chat messages.
- **Signals:** an evaluation harness or a monitor pushes a result onto a record, where it is kept as evidence and its owners are told of a failure.
- **A tool server for AI assistants:** a person's own assistant can read GovWren and draft a request for them. It cannot submit or decide.
- **Model details from your registry,** if you name one: read once a day, and shown as suggestions that a person accepts or dismisses.
- **An optional assistant,** off and invisible unless you configure it: it suggests answers on the request form and summarizes a review, with every exchange kept.

**Running it**

- **The program, edited in the app:** the form, the tiers, the routing rules, and the vocabularies, with a preview of what a change would have done to past requests.
- **Single sign-on** through any OpenID Connect provider, with groups mapped to roles.
- **Email:** notices as they happen or as a daily summary, as each person chooses.
- **A program dashboard** whose totals and bars open the records they count.
- **Roles and units:** six roles, a unit hierarchy of any depth, and CSV import of units and people.
- **An append-only history** chained by hash, checked with `govwren verify`.
- **Branding and themes:** your name, logo, and accent color; light and dark modes; three palettes.
- **A JSON API** under `/api/v1`, and a command line for setup and recovery.

Stability comes next: every earlier release upgrading cleanly, a compatibility promise for the API and the file formats, and a second, harder security review, on the way to 1.0. The [roadmap](spec/roadmap.md) says what is planned, and the [changelog](CHANGELOG.md) lists everything in this release.

## Documentation

Start with the [guide index](docs/README.md), or go straight to the guide for your part:

| Guide | For |
|---|---|
| [Getting started](docs/getting-started.md) | Whoever installs GovWren and sets it up |
| [Adopting GovWren](docs/adopting.md) | Whoever is bringing GovWren into an organization |
| [Requesting](docs/requesting.md) | Researchers and staff who want to use an AI tool |
| [Reviewing](docs/reviewing.md) | Reviewers, governance, and auditors |
| [Running the program](docs/running-the-program.md) | Governance leads and administrators |
| [Keeping watch](docs/keeping-watch.md) | Owners, stewards, and governance, once things are approved |
| [Assurance](docs/assurance.md) | Governance, owners, and reviewers |
| [Standards alignment](docs/standards.md) | Whoever is asked how GovWren relates to a standard |
| [Insight](docs/insight.md) | Governance, auditors, and administrators |
| [Configuration](docs/configuration.md) | Whoever runs the server |
| [Deployment](docs/deployment.md) | Whoever puts it into production |
| [Operations](docs/operations.md) | Whoever keeps the server running |
| [Single sign-on](docs/single-sign-on.md) | Whoever connects an identity provider |
| [Email](docs/email.md) | Whoever sets up mail |
| [Connecting other systems](docs/connecting.md) | Whoever connects purchasing, ethics, data access, tickets, or chat |
| [API](docs/api.md) | Anyone connecting another system |
| [Command reference](docs/cli.md) | Every `govwren` command and option |

The design behind the product is in [`spec/`](spec/README.md): the [vision](spec/vision.md), the [governance engine](spec/governance-engine.md), and the [roadmap](spec/roadmap.md).

## Development

```bash
uv sync                          # install GovWren and its development tools
uv run govwren serve --reload    # restart when the code changes
uv run pytest                    # the tests, on SQLite
uv run ruff check                # lint
uv run ruff format --check       # formatting
scripts/test-both.sh             # the tests on SQLite, then on a disposable PostgreSQL
```

`docs/cli.md` and `docs/openapi.json` are written from the code, and a test fails when either is out of date. Regenerate them with `UPDATE_DOCS=1 uv run pytest tests/test_docs.py`.

[CONTRIBUTING.md](CONTRIBUTING.md) covers the checks every change must pass and how the code is arranged. To report a security problem, see [SECURITY.md](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
