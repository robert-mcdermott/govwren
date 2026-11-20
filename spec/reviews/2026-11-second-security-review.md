# Second security review, November 2026

Done in wave 9, before version 0.9.0, against the code on the `wave-9` branch. The first review, in wave 6, is in [2026-11-security-and-accessibility.md](2026-11-security-and-accessibility.md); its findings were all fixed in 0.6.0 and were not looked for again.

This is a record of what was looked at, how, what was found, and what was done about it. It also says plainly what was not done.

## How it was done

Two reviewers who had taken no part in writing the code read it, each with one area and the same brief: find concrete weaknesses, confirm each in the code path, reproduce it where possible, and report nothing speculative. Both concentrated on what was added since 0.6.0, and looked at older code where something new touched it.

| Reviewer | Area |
|---|---|
| A | The web application and its data: access to records, reviews, assessments, exceptions, agreements, reports, dossiers, the register, and past views; HTML and spreadsheets the server writes; files and branding; the rule on agreements covering health information |
| B | What connects GovWren to other systems or reaches outward: API tokens and scopes, the checkpoint, signals, webhooks, the model registry, the assistant, the tool server, single sign-on, the demo's sign-in, headers, and secrets |

Most findings were reproduced against a running demo installation or in a test; the rest were confirmed by reading. Every fix below has a test that fails without it, in `tests/test_second_review.py`, `tests/test_health_agreements.py`, `tests/test_integration.py`, and `tests/test_examples.py`.

## What was found, and what was done

| # | Finding | Severity | Since | Fix |
|---|---|---|---|---|
| A1 | An owner could swap the AI systems a decided use relied on, even for one not approved, with no review and the checkpoint still saying approved | Medium | 0.1.0 | What a submitted use relies on changes only as part of a declared change or a renewal, which the rules judge, or by governance |
| A2 | The rule that health information needs a covering agreement rested on fields the people it binds could change: a tool's hosting, its vendor, and agreements on a vendor they had added | Medium | 0.8.0 | Only governance records an agreement covering health information or says what any agreement covers. Once a tool or model is in the catalog, only governance changes its hosting, origin, or vendor |
| A3 | A supplier's model was not held to that rule at all | Medium | 0.8.0 | An agreement can name the models it covers. A model reached through a supplier's service needs one, in the catalog, at decision, and in the checkpoint's answer |
| A4 | Any approved exception on a use set that rule aside, whatever requirement it was granted for | Low | 0.8.0 | An exception says whether it departs from the rule, and only one that does sets it aside |
| A5 / B1 | Anyone could make a signal token, which could push onto any record, including restricted records and other people's drafts, and tell whether a reference existed | Medium | 0.7.0 | A signal pushes only onto records its account sees in full, unless the account reads everything. A record it may not push onto answers as one that does not exist |
| A6 | The names of restricted records showed through links: the history, a model card, a past view, a vendor's agreements, a use's systems | Low | 0.2.0 | A linked record is named only to someone who may see it, and otherwise shown as "a record you cannot see" |
| A7 | An agent's assessment and a vendor's due diligence, which describe security, were readable by everyone signed in | Low to medium | 0.4.0 | They are shown to those responsible for the record, reviewers, and those who read everything |
| A8 | The statement of applicability wrote cells without the guard against spreadsheet formulas that list exports have | Low | 0.4.0 | Every cell is guarded |
| A9 | A line break in a notice's title stopped email for that message and every one after it in the batch | Low | 0.2.0 | Subjects are one line, and a message that cannot be built fails alone |
| A10 | A model card wrote owner-entered text as Markdown, so markup could pass through a renderer that allows it | Informational | 0.5.0 | Text is escaped |
| A11 | An SVG named in the configuration file was not cleaned, unlike an uploaded one | Informational | this wave | It is checked when the file is read and cleaned when it is served |
| B2 | The assistant's data-class limit was checked against the record, while what it was shown could come from a draft change with a more sensitive class | Medium | 0.7.0 | Every class the request has stated, on the record, in what was submitted, and in a draft, is checked |
| B3 | On SQLite, the assistant and webhook deliveries asked another server while holding the database's write lock, so a slow server made everyone else's requests fail | Medium on SQLite | 0.6.0 | The other server is asked with no session open, and the result is recorded afterwards. Email is sent the same way |
| B4 | A model's registry name could steer the registry request, with its key, to any path on the registry's server | Low to medium | 0.7.0 | A registry name must be letters, digits, and a few marks between slashes, checked when it is entered and when it is used |
| B5 | The assistant, and the tool server, followed redirects, which would carry their key to wherever they pointed | Low | 0.7.0 | Neither follows a redirect |
| B6 | Waits on other servers were per read, not in total, so a server answering a byte at a time could hold a call, and the scheduled work behind it, indefinitely | Low | 0.6.0 | Every call to another server has a limit on its whole length |
| B7 | The nginx example passed on the client's own `X-Forwarded-For`, so with `trusted_proxies = "*"` a client could choose the address its sign-in attempts counted against | Low to medium | 0.6.0 | The example replaces the header with the address nginx saw, and the guide says why that matters |
| B8 | The demo's passwordless sign-in could be reached from a web page by DNS rebinding | Low | 0.2.0 | From the machine itself, the page must have been reached by a name for that machine |
| B9 | The tool server's draft tool, or any save of a draft change, renamed an approved use at once | Low | 0.7.0 | An approved use keeps its name and unit until the change is submitted and judged |
| B10 | The checkpoint told anyone the standing of a restricted record | Low | 0.6.0 | It answers 404 for a restricted record the account may not see, as for someone else's draft |
| B11 | The example webhook receiver dropped repeats by the delivery number, which the signature does not cover | Low | 0.6.0 | It drops repeats by the signed event and topic |
| B12 | API tokens need not end | Low | 0.6.0 | Every token ends, a year at most from the day it is made |
| B13 | A long registry address could fail on PostgreSQL and stop the registry job for every later model | Low | 0.7.0 | What is stored is cut to length, and one model's trouble no longer stops the rest |
| B14c | A webhook message named a restricted use, and receivers often post to shared channels | Informational | 0.6.0 | A restricted use's name is left out |
| B14d | The checks on the assistant's and the registry's addresses matched the start of the text, so `http://localhost.attacker.example` passed | Informational | 0.7.0 | The parsed host name is compared |

## Looked at and found sound

API tokens: random, stored only as a hash, revoked at once, held to their scope, and unable to make tokens or change a password. Webhook secrets, signatures, and the refusal of redirects and private addresses. The registry's limits on what it reads, and that what it returns is only a suggestion a person must accept. The assistant's place: it is off unless configured, never submits or decides, is refused to requesters, and its exchanges are readable only by those who read everything. The tool server, which acts as its token's account with every check made by the server. The pages the server writes: the register, the dossier, email, and CycloneDX output escape what they show. Branding from the configuration file. Backup, restore, and evidence files. Every route added since 0.6.0 is in the policy table, and the services check the record. Security headers and the content security policy on every page added since 0.6.0.

## Left as it is, on purpose

- **A webhook's address is resolved twice**: once when it is checked and again when the connection is made, so a name that changes its answer in between could reach an address on the machine's own network. Certificate checking stops anything being sent over https to a server that is not the one named. Connecting to the address that was checked would also mean checking certificates by hand, which is a larger change than the risk warrants before adopters have seen GovWren.
- **An administrator may point a webhook at this machine**, for testing. Only an administrator can create a webhook.
- **Change reviews are never approved by rule, and a change that is not material keeps the approval.** By default the systems, the kinds of data, and whether data is de-identified all count as material, so the rule on agreements is applied again. An organization that edits `material_changes` takes that on.

## What this was not

It was a review of the code by two reviewers, reading and running it on one machine, on SQLite. It was not a penetration test of a deployed installation, no outside firm has examined GovWren, and nothing was tested against a real identity provider, a real model server, a real registry, or real nginx. An organization with its own security team should have that team look before it relies on GovWren for anything sensitive.
