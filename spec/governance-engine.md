# The governance engine

This document specifies how a request moves through GovWren: how it is taken in, how its risk tier is worked out, how it is routed, how a decision is made and recorded, and how the record is kept current afterward. Everything described here as a default is configuration the governance team can change in the app without touching code.

## The path of a request

```text
  "May I use this?"
        │
        ▼
  ┌──────────────┐  listed and permitted   ┌───────────────────────┐
  │   Catalog    │────────────────────────▶│ Register use (1 min)  │──┐
  └──────┬───────┘                          └───────────────────────┘  │
         │ not listed, or not permitted for this data                   │
         ▼                                                              │
  ┌──────────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐      ▼
  │ Intake form  │───▶│  Tiering │───▶│ Routing │───▶│  Review  │──▶ Decision
  │ (adaptive)   │    │ (scored) │    │ (rules) │    │ (tasks)  │      │
  └──────────────┘    └──────────┘    └─────────┘    └──────────┘      ▼
                                                              Conditions · record in
                                                              the inventory · schedule
                                                                       │
                                                                       ▼
                               Oversight: attest · re-review · change · incident · retire
```

## Two ways in

### The catalog

The catalog lists every AI system the organization has evaluated, with a plain statement of standing: *approved*, *approved with restrictions*, *not approved*, or *under evaluation*. For an approved system it shows the highest data class it may be used with, the data categories that are excluded, and the standard terms of use.

A person who finds their tool in the catalog answers three things: what they will use it for, which unit the use belongs to, and what data is involved. If the data is within what the system permits and no stop applies, the use is registered and approved on the spot under the catalog terms. The result is a real use case record with an owner, a tier, and a review date. This is the path most everyday use should take, and it is designed to take less than a minute.

If the data exceeds what the system permits, or the answers trip a rule, the registration continues into the intake form with what has already been answered carried forward.

### The intake form

Anything not covered by the catalog starts with the intake form. The form is staged so that nobody answers more than their request needs:

1. **Basics** (everyone): what it is for, which unit, who is accountable, which tool or model, and what stage the work is at.
2. **Screening** (everyone): about ten closed questions, each mapped to a scoring factor. They cover who is affected, how outputs are used, whether the system can act on its own, what data goes in, where that data goes, and how widely it will be used.
3. **Detail** (shown only when screening answers call for it): sections for personal and health data, human-subjects research, vendor and contract terms, agents and automation, model development and training, and use in publications or funding applications. The section on models asks, of anyone running a model themselves or training one, where the weights came from, under what license, where it will run, and what data it is tuned on.

The form saves as it goes and can be left and resumed. A running indicator shows the likely tier and which reviews it would require, so the consequence of each answer is visible while it can still be reconsidered. Questions answered on a linked record (a system already described, a dataset already registered) are prefilled and not asked again.

Forms are versioned documents (see [data-model.md](data-model.md#form)). The form builder in Admin edits a draft, previews it against sample answers, and publishes it as a new version; responses always render with the version they were given on.

## Risk tiering

Tiering is a transparent calculation, never a judgment hidden in software. It has four parts.

### Factors

Each factor is scored 0 to 3. The default model has six.

| Factor | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| **Impact on people** | No effect on anyone outside the team | Minor, easily corrected effects | Affects someone's opportunities, standing, or access to services | Could affect health, safety, legal rights, or livelihood |
| **Decision role** | Background or exploratory; nothing relies on it | Informs a person, who decides independently | A person usually accepts its recommendation | Decides or acts without a person reviewing each case |
| **Autonomy** | Produces output only | Takes actions a person approves one by one | Acts on its own within set limits; actions reversible | Acts on its own with effects that are hard to reverse |
| **Data sensitivity** | Public data | Internal data | Protected data | Restricted data |
| **Data exposure** | Stays on the organization's own equipment | Organization's own cloud tenant | Supplier, under an agreement that covers the data | Supplier without a covering agreement, or one that may train on inputs |
| **Reach** | One person or one team | One unit | Many units, or people outside the team affected | Organization-wide or public-facing |

Each factor takes the highest level that any contributing answer gives it. A request that involves both internal and restricted data scores 3 for data sensitivity, never an average.

### Tiers

The total (0 to 18 in the default model) maps to a tier.

| Tier | Default band | What it means |
|---|---|---|
| **Minimal** | 0–4 | Everyday use with little that can go wrong |
| **Moderate** | 5–8 | Some sensitivity; a focused check is enough |
| **High** | 9–12 | Real potential for harm; full review |
| **Critical** | 13–18 | Serious potential for harm; full review and named risk acceptance |

Tier names, bands, and colors are configuration. An organization that prefers three tiers, or five, edits the scoring model.

### Floors and stops

Totals alone can understate a single severe factor, so the model also has rules that act regardless of the total.

- **Floors** set a minimum tier. Defaults: impact on people at level 3 is at least *High*; restricted data sent to a supplier without a covering agreement is at least *High*; autonomy at level 3 is at least *High*; any use that makes decisions about individual people without review is at least *High*.
- **Stops** mark a request as a prohibited use under the organization's policy. Defaults are deliberately few and are meant to be replaced with the organization's own: entering restricted data into a system whose supplier may train on it; using generative AI to carry out confidential peer review; fully automated decisions on admission, hiring, or discipline. A stopped request cannot be approved. It can only be changed, withdrawn, or granted a time-limited exception by the authority the rules name.

### Showing the work

Every tier assessment is stored with its factor levels, the answers that set each one, the floors that applied, and the version of the scoring model. The record shows this as a small table: factor, level, and the reason. When the model changes, existing records keep the assessment they were decided under, and the app can report which records would land in a different tier under the new model before it is published.

A governance lead or reviewer can **override** the computed tier, up or down, with a written reason. The record shows both the computed and the final tier, who changed it, and why. Overrides are reportable, so a pattern of them is a signal to adjust the model.

## Routing

Routing rules turn a tiered request into a review. Each rule has a condition and effects, and rules are evaluated in order.

**Conditions** test the tier, record fields, and form answers with a small declarative structure (`all`, `any`, `not`, and comparisons such as equals, in, contains, at least). The same structure is used for a form's `show_when`, for scoring contributions, and for control applicability, so there is one evaluator, it is pure data, and nothing is ever executed as code.

**Effects** can:

- require a review function (for example, privacy),
- set who may decide,
- set the review's due date in working days,
- attach a standard condition,
- set the re-review cadence,
- apply a record-scoped control,
- approve automatically.

### Default review tracks

| Tier | Reviews required | Who decides | Target time | Re-review |
|---|---|---|---|---|
| **Minimal** | None; governance spot-checks a sample | By rule, automatically, with standard conditions | Immediate | Owner attests yearly |
| **Moderate** | Governance triage, plus any function the answers trigger | Governance lead | 5 working days | Every 2 years; owner attests yearly |
| **High** | Privacy, information security, and every triggered function | Governance committee | 15 working days | Yearly |
| **Critical** | As High, plus legal | Governance committee, with a named executive accepting the risk | 30 working days | Every 6 months |

Function triggers add reviewers by what the request involves, whatever its tier. Defaults: human-subjects research data adds *research ethics*; health information adds *privacy*; a new supplier or new contract terms adds *legal and contracts*; use that informs care of patients adds *clinical safety*; agents with write access to systems add *information security* and *architecture*; outputs used in publications or funding applications add *research integrity*; a new connection to an institutional data source adds *data stewardship*.

Automatic approval is only ever an effect of a rule the governance team has written, and every automatically approved record says so, names the rule, and is included in a periodic sample for a person to spot-check.

## Review

A review opens in **triage**. The governance lead sees the request, the tier and its reasons, and the reviews the rules require. They can confirm, add or remove a review function with a reason, override the tier, or return the request to the requester for more information.

Each required function gets a **review task**. Tasks run in parallel. A task is assigned to a named reviewer or left for anyone holding that function to claim. A reviewer sees the whole request, the answers relevant to their function highlighted, the linked records, earlier decisions on the same system, and the discussion. They record one of three findings:

- **No concerns.**
- **Acceptable with conditions**, naming the conditions, chosen from the standard library or written for the case.
- **Objection**, with the reason.

**Discussion** is a thread on the review. Each comment is either visible to the requester or internal to reviewers. Sending a question to the requester moves the review to *with requester* and pauses the clock; their reply resumes it. Time with the requester and time with reviewers are measured separately, so turnaround figures are fair to both.

**Reminders and escalation.** Assignees are reminded as a task's due date approaches; a task that goes overdue is raised to the governance lead. All of this is in-app, and by email when mail is configured.

## Decisions

When every task is complete the review is **ready for decision** and goes to whoever the rules named: the governance lead's queue, or the agenda of the next committee session.

The decision screen is the **decision packet**: the request in summary, the tier and its reasons, each reviewer's finding, the proposed conditions gathered into one list, open risks, and any related history. The outcomes are:

| Outcome | Effect |
|---|---|
| **Approved** | The use case becomes approved; approval runs until the date set by its cadence |
| **Approved with conditions** | As approved, with conditions tracked to closure |
| **Returned** | Goes back to the requester with what is needed |
| **Declined** | Closed; the reason is required and is shown to the requester |
| **Withdrawn** | Closed by the requester |

A rationale is required for every outcome. An open objection does not block a decision, but the decider must address it in the rationale, and the record shows that a decision was made over an objection. For tiers that require it, the decision is not complete until the named risk acceptor has confirmed their acceptance in their own session.

**Conditions** are of three kinds. *Before use* conditions hold the approval in a pending state until they are met. *By date* conditions have a deadline. *Ongoing* conditions last as long as the approval and are reconfirmed at each attestation. Each condition has an owner, and closing one requires a note or linked evidence, verified by governance when the rule says so.

**Committee sessions.** A session gathers the reviews awaiting a body's decision into an agenda. During the meeting each item is opened as its decision packet and decided; afterward the session holds the minutes and the list of decisions. A decision made in a session records the session, not the individual votes, unless the organization chooses to record them.

**Appeals and reconsideration.** A declined or conditioned request can be resubmitted with changes; the new review links to the earlier one and starts with its answers.

## Keeping the record true

A passive system is only as good as its upkeep, so oversight is treated as a first-class part of the engine.

### Scheduled re-review

Each approval sets `approved_until` and `next_review_on` from its tier's cadence. Before the date, the owner is asked to confirm or update the record, and a periodic review opens with the previous answers in place, so re-review is a matter of confirming what has not changed and answering for what has. An approval that passes its date without a completed re-review becomes **lapsed**, which is visible wherever the record appears and in every report.

### Attestation campaigns

A campaign asks a set of people to confirm something by a date, and tracks who has.

- **Record confirmation.** Each owner sees their records and answers for each: still in use and unchanged; changed (which opens a change request); or no longer in use (which opens retirement). Confirming several unchanged records takes one action.
- **Unit completeness.** Each unit's steward sees the unit's registered AI use and is asked: *is this everything?* They can add what is missing on the spot, in a short form, and then attest. This is GovWren's substitute for discovery: a regular, attributable statement from every unit, with coverage reported as the share of units that have attested within the period.
- **Policy acknowledgment** and **vendor reconfirmation** work the same way for policies and for facts supplied by vendors.

### Change

An owner who changes something declares it. The change form asks a few closed questions: is there a new kind of data, a new model or supplier, a new group of people affected, more autonomy, or a new purpose? Rules decide from the answers whether the change is **material**. A material change opens a change review limited to what changed; an immaterial one is recorded and the approval stands. Editing a field that scoring depends on prompts the same declaration, so a record cannot quietly drift out of its tier.

### Exceptions

An exception is an approved, time-limited departure from a policy, a control, a condition, or a stop. It names what is excepted, why, the compensating measures, who approved it, and when it expires. Exceptions always expire, are listed in one register, and show on the record they apply to. Renewal is a new decision.

### Incidents

Anyone can report an incident or a near miss in a short form. Governance triages it, sets severity, links the records involved, and records containment, cause, and lessons. An incident can suspend the approvals of the records involved, open an incident-triggered review, and create corrective actions with owners and dates. Incidents on a shared system or model are visible on every record that depends on it.

### Retirement

Retiring a use case, system, or model asks what replaces it, what happens to the data and access involved, and whether anything depends on it. Dependents are listed and their owners are notified. A retired record stays in the inventory, marked as retired, with its full history.

### Actions

Conditions, corrective actions, review follow-ups, and control gaps all land in one list of **actions**, each with an owner and a due date. Everyone's open actions are on their home page, and overdue ones roll up to unit stewards and governance.

## Measures

The engine keeps the figures a governance program is judged by, each with its definition shown beside it:

- **Turnaround:** time from submission to decision by tier, split into time with reviewers and time with requesters; share decided within target.
- **Throughput:** requests received, decided, and open, by period, tier, unit, and domain.
- **Coverage:** share of units with a current completeness attestation; share of records with a current owner confirmation.
- **Currency:** lapsed approvals, overdue reviews, open conditions past due, expiring agreements and evidence.
- **Quality of the rules:** tier overrides by direction and reason; automatic approvals sampled and the share upheld.
- **Completeness:** share of required fields filled, by record type and unit.

Counts of one or two are shown as counts, not percentages, and an empty measure says there is no data rather than showing zero.
