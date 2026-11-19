# Vision

## The idea

A wren is one of the smallest birds in the garden and one of the easiest to hear. It lives close to people, in hedges and under eaves, and it misses very little of what happens around it.

That is the kind of AI governance most organizations need and few have. Governance is usually a heavy thing that sits far from the work: a committee, a long form, a spreadsheet nobody trusts, and a queue that takes months. So people route around it. A lab signs up for a tool with a credit card. A department turns on an AI feature in software it already owns. A graduate student pastes interview transcripts into a chatbot. None of this is malicious. It is simply faster than asking.

**GovWren makes asking the faster path.** It gives an organization one front door for every AI request, a review that is proportionate to the risk, a living inventory of what is in use and who answers for it, and a record of every decision with the evidence behind it. It is small enough to run on one machine, plain enough that a busy researcher will use it, and thorough enough that an auditor can rely on it.

## Positioning

> GovWren is an open system of record for AI governance: one front door for AI requests, review in proportion to risk, a living inventory, and evidence behind every decision.

GovWren is a workflow and records product. It manages the governance *process*: intake, triage, review, approval, inventory, oversight, and reporting. It is **passive by design**: everything it knows comes from people, documents, and (optionally, later) metadata an organization chooses to send it. It never scans a network, reads a log, or sits in the path of an AI request.

## Who it is for

GovWren is built first for **research organizations**: research institutes, universities, academic medical centers, and national laboratories. These organizations share a shape that general-purpose governance tools handle poorly:

- **Many semi-autonomous groups.** Dozens or hundreds of labs, cores, and departments, each with its own funding, its own tools, and a principal investigator who is used to deciding things.
- **Spending that bypasses procurement.** Grant funds, purchasing cards, free tiers, and open-source models mean a new AI tool rarely passes a central checkpoint.
- **Sensitive data next to open science.** Human-subjects data, health records, unpublished results, and export-controlled work sit beside projects whose whole purpose is to be shared.
- **Obligations that are specific to research.** Ethics board protocols, data use agreements, funder rules on AI in applications and peer review, and journal disclosure requirements.
- **A small governance team.** Often one or two people and a committee that meets monthly.

Nothing in GovWren is specific to research, though. The vocabulary, forms, risk tiers, review tracks, and frameworks are all configuration, and any organization that wants a lightweight, self-hosted governance system can adopt it.

| Persona | What they need from GovWren |
|---|---|
| **Researcher or staff member** | A quick answer to "may I use this tool with this data?", and a short form when the answer is not already known |
| **Principal investigator or AI owner** | One place that lists what their group uses, what is approved, and what they owe: a condition to close, an attestation, a review coming due |
| **Lab manager or unit steward** | A view of their unit's AI use and a simple way to confirm it is complete and current |
| **Governance lead** | A triage queue, risk tiers they control, reviewers they can route to, deadlines that track themselves, and an inventory they can trust |
| **Reviewer** (privacy, security, legal, ethics, clinical safety, data stewardship, architecture) | A focused queue showing only what needs their judgment, with the facts on one screen and a place to record a finding |
| **Committee chair or approver** | A clear decision packet: what is proposed, what each reviewer found, what conditions apply, and what is being accepted |
| **Auditor or compliance officer** | Read-only access to every record, decision, and change, with exports that verify |
| **Executive or board member** | A portfolio view: how much AI, of what kind, at what risk, how fast decisions are made, and what is overdue |
| **Administrator at an adopting organization** | A system that installs in minutes, signs people in with the identity they already have, carries the organization's own name and colors, and keeps its data portable |

## What makes GovWren different

These are the product bets. Each is a deliberate design choice.

1. **A front door, not a gate.** Most people arrive with one question: *may I?* GovWren answers it in the fewest steps the risk allows. A catalog of tools the organization has already reviewed says which data each may be used with, and registering a use of one takes under a minute. Anything new starts with a short form that grows only when the answers call for it. Low-risk requests can be approved by rule, with conditions, the moment they are submitted.

2. **Proportionate by construction.** Risk tier decides everything downstream: which questions are asked, who reviews, who decides, how often the record is revisited, and which controls apply. The burden on a low-risk use is measured in minutes; depth is spent where harm is possible.

3. **Passive by design.** GovWren has no scanners, agents, or log collectors, and needs no access to anything else on the network. It reaches coverage through process instead: a front door that is easier than avoiding it, periodic attestations from every unit, checkpoints that other processes can cite (a record ID on a purchase request or an ethics protocol), and reminders tied to renewals. This makes it safe to deploy anywhere, quick to approve, and honest about what it knows.

4. **Built for federated organizations.** Units form a hierarchy with as many levels as the organization has. Every record belongs to a unit and has named owners. Stewards see and attest for their own unit; leaders see roll-ups; nobody needs a central team to type records in for them.

5. **One connected record.** Use cases, AI systems, models, agents, datasets, and vendors are separate records with typed links between them. A finding on a shared model is visible on everything that depends on it. Any record is one click from its neighbors.

6. **Rules are data, and the rules are visible.** Intake forms, scoring factors, tier thresholds, review tracks, cadences, and vocabulary are versioned configuration that the governance team edits in the app. Every tier shows the answers that produced it. A reviewer may override a tier, with a reason, and the override is on the record.

7. **Evidence and an unbroken history.** Every change to every record is written to an append-only log with who, when, and what changed. Decisions carry their rationale, conditions, and the version of the rules in force. Any record can be shown as it stood on any past date.

8. **Controls you can actually run, frameworks only if you need them.** GovWren comes with a short library of practical controls in plain words, implemented once and backed by evidence. It does not make anyone work through a standard clause by clause. An organization that must show alignment with a named framework loads it as a content pack, and readiness follows from a mapping to controls already in place.

9. **Open, portable, and yours.** Apache 2.0 licensed, with no paid edition and no license keys. Runs on a laptop with SQLite or on a server with PostgreSQL. Everything exports in open formats. Name, logo, colors, and wording are settings, so an adopting organization presents it as its own.

## Scope

### GovWren does

- Give everyone a catalog of reviewed AI tools and the data each may be used with
- Take in AI requests through configurable forms that adapt to the answers
- Assign a risk tier from transparent, configurable scoring, with reasoned overrides
- Route each request to the reviewers its tier and attributes require, in parallel, with due dates
- Record decisions, rationale, conditions, exceptions, and risk acceptance
- Keep an inventory of use cases, AI systems, models, agents, datasets, and vendors, with ownership, lifecycle, and links
- Hold evidence (files, links, attestations) with owners and expiry dates
- Schedule re-reviews, owner and unit attestations, and renewals, and chase what is overdue
- Track AI incidents and corrective actions to closure
- Track risks and a library of controls with evidence, and, optionally, report readiness against a framework
- Report the portfolio to leadership, and produce a complete dossier for any record
- Publish an optional transparency register of approved AI uses

### GovWren does not (non-goals)

- **Discover AI by scanning.** No network inspection, log ingestion, endpoint agents, code scanning, or cloud tenant crawling.
- **Enforce anything at runtime.** No gateways, guardrails, content filtering, blocking, or kill switches.
- **Test or monitor models.** It does not run evaluations, red-team exercises, bias tests, or drift detection. It records the results of work done elsewhere.
- **Replace other systems of record.** It is not a model registry, a data catalog, a contract system, an ethics board system, or a ticketing system. It links to them by reference.
- **De-identify, classify, or move data.** It records what people say about their data; it never touches the data itself.
- **Give legal advice or certify compliance.** Framework content is a working aid. Conclusions belong to the people who sign them.
- **Require an AI provider.** Optional AI assistance may come later; the core never depends on one.

## Guiding principles

1. **The fastest safe path.** Every screen is judged by how quickly an honest person can do the right thing.
2. **Ask once.** Anything GovWren already knows is never asked again. Facts entered on one record are reused on the next.
3. **Show the reasoning.** A tier, a route, or a required control always shows the rule and the answers that produced it.
4. **People decide.** Rules propose and route; named people review, approve, and accept risk.
5. **The record is permanent.** History is append-only. Corrections are new entries, never erasures.
6. **Stand alone.** Every capability works on one machine with no other system. Integrations are optional additions.
7. **Few dependencies, well chosen.** Each runtime dependency is justified in a decision record. The browser gets no frameworks.
8. **Generic by default.** Nothing in the code or documentation assumes a particular institution. Vocabulary and branding are configuration.
9. **Accessible and fast.** WCAG 2.2 AA, keyboard-friendly, light and dark themes, and pages that load instantly on modest hardware.
10. **Unknown is not zero.** A missing answer is shown as missing. Coverage and completeness are measured and displayed, never assumed.

## What success looks like

- **Wave 1:** A governance lead installs GovWren, signs in, and within an afternoon has their organization's units, an intake form, and risk tiers in place. A researcher submits a request in five minutes, it is tiered and routed automatically, reviewers record findings, and a decision is issued with conditions. Every step is in the history.
- **Wave 3:** The inventory keeps itself current. Owners confirm their records on schedule, units attest that their list is complete, and nothing overdue goes unnoticed.
- **Wave 5:** A leader opens one page and sees the whole AI portfolio by risk, unit, and status, and an auditor exports a complete, verifiable dossier for any record.
- **v1.0:** Another organization adopts GovWren, re-brands it, connects single sign-on, and runs its governance program on it without help from the original team.
