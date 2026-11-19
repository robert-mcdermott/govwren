# GovWren documentation

These guides describe the version of GovWren they ship with. Read them in this order if you are new, or go straight to the one for your part.

## The guides

| | Guide | For | Covers |
|---|---|---|---|
| 1 | [Getting started](getting-started.md) | Whoever installs GovWren | Installing, `init`, `doctor`, `serve`, first sign-in, the setup checklist, the demo organization, SQLite or PostgreSQL |
| 2 | [Requesting](requesting.md) | Researchers and staff | Looking a tool up, registering a use, making a request, the tier, questions, decisions, and conditions |
| 3 | [Reviewing](reviewing.md) | Reviewers, governance, auditors | The review queue, triage, findings, discussion, changing a tier, deciding, and conditions |
| 4 | [Running the program](running-the-program.md) | Governance leads and administrators | Roles, units, imports, the catalog, data classes, tiers, routing rules, program packs, the dashboard, the history, appearance |
| 5 | [Configuration](configuration.md) | Whoever runs the server | `govwren.toml`, environment overrides, the data home, PostgreSQL, reverse proxies, the demo guard |
| 6 | [Single sign-on](single-sign-on.md) | Whoever runs the server | Connecting an identity provider, Microsoft Entra ID step by step, groups and roles, turning off passwords |
| 7 | [API](api.md) | Anyone connecting another system | Sign-in, the CSRF token, responses, errors, lists, and a table of routes |

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
| How do I change the form, the tiers, or the rules? | [Change the program with a pack](running-the-program.md#change-the-program-with-a-pack) |
| What does a dashboard figure count? | [Read the dashboard](running-the-program.md#read-the-dashboard) |
| How do I move to PostgreSQL? | [Use PostgreSQL](configuration.md#use-postgresql) |
| How do I put it behind a proxy? | [Run behind a reverse proxy](configuration.md#run-behind-a-reverse-proxy) |
| Nobody can sign in. How do I get back in? | [`govwren users`](cli.md#govwren-users) |

## What this release does not do yet

This release signs in with local accounts and tells people things through in-app notices. Single sign-on, email, records for models and datasets, and editing the form and rules inside the app are planned. The [roadmap](../spec/roadmap.md) says what comes next and in what order, and the [changelog](../CHANGELOG.md) lists what is in each release.

## More

- The design behind the product is in [`spec/`](../spec/README.md).
- To work on GovWren itself, see [CONTRIBUTING.md](../CONTRIBUTING.md).
- To report a security problem, see [SECURITY.md](../SECURITY.md).
