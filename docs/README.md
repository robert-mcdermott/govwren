# GovWren documentation

These guides describe the version of GovWren they ship with. Read them in this order if you are new, or go straight to the one for your part.

## The guides

| | Guide | For | Covers |
|---|---|---|---|
| 1 | [Getting started](getting-started.md) | Whoever installs GovWren | Installing, `init`, `doctor`, `serve`, first sign-in, the setup checklist, the demo organization, SQLite or PostgreSQL |
| 2 | [Requesting](requesting.md) | Researchers and staff | Looking a tool up, registering a use, making a request, the tier, questions, decisions, and conditions |
| 3 | [Reviewing](reviewing.md) | Reviewers, governance, auditors | The review queue, triage, findings, discussion, changing a tier, deciding, and conditions |
| 4 | [Running the program](running-the-program.md) | Governance leads and administrators | Roles, units, imports, the catalog, data classes, tiers, routing rules, program packs, the dashboard, the history, appearance |
| 5 | [Keeping watch](keeping-watch.md) | Owners, stewards, and governance | Periodic reviews, lapsed approvals, attestation campaigns, declaring a change, retiring a record, exceptions, incidents, actions, committee sessions, risk acceptance, spot checks |
| 6 | [Assurance](assurance.md) | Governance, owners, and reviewers | The risk register, the control library, evidence freshness, policies, assessments, frameworks, and the statement of applicability |
| 7 | [Insight](insight.md) | Governance, auditors, and administrators | The program's measures, the portfolio grouped five ways, the unit report, reports to leadership, any day in the past, the dossier, open formats, and the transparency register |
| 8 | [Configuration](configuration.md) | Whoever runs the server | `govwren.toml`, environment overrides, the data home, PostgreSQL, reverse proxies, the demo guard |
| 9 | [Deployment](deployment.md) | Whoever puts it into production | A container image, compose with PostgreSQL, a systemd service, reverse proxies, `doctor --production`, and the operations view |
| 10 | [Operations](operations.md) | Whoever runs the server | Measured size, server processes, backup, restore, and moving between SQLite and PostgreSQL |
| 11 | [Single sign-on](single-sign-on.md) | Whoever runs the server | Connecting an identity provider, Microsoft Entra ID step by step, groups and roles, turning off passwords |
| 12 | [Email](email.md) | Whoever runs the server | Setting up SMTP, what people receive, how sending works, and what to check when mail does not arrive |
| 13 | [API](api.md) | Anyone connecting another system | Sign-in, the CSRF token, responses, errors, lists, and a table of routes |

## Reference

These two are written from the code, so they always match the version they ship with.

| Reference | What it is |
|---|---|
| [Command reference](cli.md) | Every `govwren` command and option |
| [openapi.json](openapi.json) | The OpenAPI document for the API. A running server also serves it at `/api/openapi.json` |

## Find the answer to a question

| Question | Where |
|---|---|
| How do I try it without setting anything up? | [Explore the demo organization](getting-started.md#explore-the-demo-organization) |
| May I use this AI tool? | [Read the catalog](requesting.md#read-the-catalog) |
| Why does my request have this tier? | [What the tier means](requesting.md#what-the-tier-means) |
| A reviewer asked me something. What now? | [Answer a reviewer's question](requesting.md#answer-a-reviewers-question) |
| What do I do with a review task? | [Do a review task](reviewing.md#do-a-review-task) |
| Who can see what reviewers write? | [The two rules that always hold](reviewing.md#the-two-rules-that-always-hold) |
| How do I add a tool to the catalog? | [Build the catalog](running-the-program.md#build-the-catalog) |
| How do I bring in my units and people? | [Import units and people from CSV](running-the-program.md#import-units-and-people-from-csv) |
| How do I change the form, the tiers, or the rules? | [Change the program](running-the-program.md#change-the-program) |
| What does a dashboard figure count? | [Read the dashboard](running-the-program.md#read-the-dashboard) |
| My approval is about to end. What do I do? | [Confirm your answers](keeping-watch.md#confirm-your-answers) |
| What I use the tool for has changed. | [Declare a change](keeping-watch.md#declare-a-change) |
| Something went wrong. Who do I tell? | [Report an incident](keeping-watch.md#report-an-incident) |
| We cannot meet a requirement yet. | [Ask for an exception](keeping-watch.md#ask-for-an-exception) |
| How do I ask owners to confirm their records? | [Start a campaign](keeping-watch.md#start-a-campaign) |
| What runs by itself, and when? | [What GovWren does by itself](keeping-watch.md#what-govwren-does-by-itself) |
| What could go wrong with this use, and who owns that? | [The risk register](assurance.md#the-risk-register) |
| Which safeguards apply to my record? | [The controls of a record](assurance.md#the-controls-of-a-record) |
| How do we show readiness against a framework? | [Read readiness](assurance.md#read-readiness) |
| How do I move to PostgreSQL? | [Use PostgreSQL](configuration.md#use-postgresql) |
| How do I put it behind a proxy? | [Run behind a reverse proxy](configuration.md#run-behind-a-reverse-proxy) |
| Nobody can sign in. How do I get back in? | [`govwren users`](cli.md#govwren-users) |

## What comes next

Adoption comes next: measured performance at scale, a brand kit, starter packs, tokens and webhooks for other systems, and packaging for production. The [roadmap](../spec/roadmap.md) says what is planned and in what order.

## More

- The design behind the product is in [`spec/`](../spec/README.md).
- To work on GovWren itself, see [CONTRIBUTING.md](../CONTRIBUTING.md).
- To report a security problem, see [SECURITY.md](../SECURITY.md).
