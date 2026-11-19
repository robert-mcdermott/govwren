# Data model

GovWren keeps everything in one relational database, SQLite by default and PostgreSQL in production, behind one SQLAlchemy model and one Alembic migration history. Files (evidence, attachments, logos) live on disk in the data home, addressed by their hash; the database holds their metadata.

This document describes the entities, how they relate, and the rules that apply to all of them. Column-level detail lives in the models and migrations; when they change, this document changes in the same commit.

## Conventions

- **Two identifiers per record.** Every row has an integer primary key used for joins. Every record a person might cite also has a **reference**: a short, permanent, human-readable key with a type prefix and a sequence number (`UC-0142`). References never change and are never reused. They are what a purchase request, an ethics protocol, or an email cites.
- **Timestamps** are UTC, stored as timezone-aware values, shown in the viewer's time zone.
- **Vocabularies are data.** Any field described below as "a vocabulary" (domain, data class, lifecycle stage, review function, incident category, and so on) draws its values from a settings-backed list the organization can rename, extend, and retire. Rows keep the stable key of the value, never its label, so renaming a value never rewrites history.
- **JSON columns** hold structured values whose shape is defined by configuration (form answers, scoring detail, rule conditions). They are stored through SQLAlchemy's portable JSON type and never queried with database-specific operators; anything that needs filtering or sorting is a real column.
- **Soft deletion only.** Records are archived or retired, never deleted, so references and history stay valid. Drafts that were never submitted can be discarded by their author.
- **Every write is an event.** No table is written except through the service layer, which records an event in the same transaction (see [History](#history)).

| Prefix | Record | Prefix | Record |
|---|---|---|---|
| `UC` | Use case | `RV` | Review |
| `SYS` | AI system | `EXC` | Exception |
| `MDL` | Model | `INC` | Incident |
| `DS` | Dataset | `ACT` | Action |
| `VND` | Vendor | `RSK` | Risk |
| `EV` | Evidence | `CTL` | Control |
| `POL` | Policy | `CR` | Change request |

## Overview

```text
                      ┌────────────┐
                      │  Org unit  │◀── parent
                      └─────┬──────┘
             belongs to     │      owners, stewards
        ┌───────────────────┼──────────────────────┐
        ▼                   ▼                      ▼
  ┌───────────┐  uses  ┌───────────┐  built on ┌─────────┐
  │ Use case  │───────▶│ AI system │──────────▶│  Model  │
  └─────┬─────┘        └─────┬─────┘           └────┬────┘
        │ processes          │ supplied by          │ trained on
        ▼                    ▼                      ▼
  ┌───────────┐        ┌───────────┐          ┌───────────┐
  │  Dataset  │        │  Vendor   │──────────│ Agreement │
  └───────────┘        └───────────┘          └───────────┘

  Any record above can be the subject of:
    Review ─▶ Review task ─▶ Decision ─▶ Condition
    Risk · Control implementation · Evidence · Exception
    Incident · Action · Change request · Attestation · Comment
```

## Organization and people

### Org unit

The organization as a tree: `org_unit(id, parent_id, kind, name, code, status)`. `kind` is a vocabulary (by default: organization, division, department, center, core facility, lab, office). There is one root. A unit may be closed, which keeps its records and history but removes it from pickers.

Units are the backbone of scoping. Every use case, AI system, and dataset belongs to exactly one unit, and a role can be granted for a unit, which then covers every unit beneath it.

### Account

`account(id, email, display_name, title, status, time_zone)` is a person who can sign in or be named on a record. An account can exist before its person has ever signed in (created by an import or by being named as an owner), in which case it is *invited*.

- `credential` holds a local password hash for accounts that have one.
- `identity(account_id, issuer, subject)` links an account to a single sign-on identity.
- `membership(account_id, org_unit_id, title, is_primary)` records which units a person works in. It drives defaults and what a member can see; it grants nothing else.

### Roles

`role_grant(account_id, role, org_unit_id?, review_function?, source)`.

| Role | What it allows |
|---|---|
| `admin` | Everything, including accounts, sign-in settings, branding, and system configuration |
| `governance` | Run the program: triage, route, decide, edit any record, manage forms, tiers, rules, content, and campaigns |
| `reviewer` | Complete review tasks for the review functions they are granted; read the records under review |
| `auditor` | Read every record, decision, and the full history; export; change nothing |
| `steward` | For a unit and those beneath it: see every record, edit them, respond to unit attestations, and act for an owner |
| `member` | Everyone who signs in: browse the catalog and register, submit requests, and manage the records they own |

`source` says whether a grant was made in GovWren or mapped from the identity provider; provider grants are replaced at each sign-in and local ones are left alone. Ownership is not a role: being named as an owner on a record gives edit rights to that record. The full permission table is in [security.md](security.md).

## The inventory

Six record types make up the inventory. They share a common header: `ref`, `name`, `summary`, `org_unit_id`, `status`, `created_by`, timestamps, a completeness score, tags, and owners.

**Owners** are rows in `record_owner(record_type, record_id, account_id, kind)`. `kind` is a vocabulary; the defaults are *accountable owner* (the person who answers for it, such as the principal investigator), *technical owner*, and *contact*. Every active record must have an accountable owner; a record whose only accountable owner's account is disabled is flagged as orphaned.

### Use case

**What AI is being used for, by whom, on what.** This is the unit of governance: the thing that is requested, tiered, reviewed, approved, and revisited.

| Field | Notes |
|---|---|
| `purpose` | What the AI does and the problem it addresses, in the requester's words |
| `domain` | Vocabulary: research, clinical care, education, operations, software development |
| `stage` | Where the work is: *proposed*, *pilot*, *in use*, *paused*, *retired* |
| `status` | Its standing with governance (see [Standing](#standing)) |
| `tier`, `tier_source` | Current risk tier, and whether it was computed or overridden |
| `decision_role` | How outputs are used: *informational*, *assists a person's decision*, *makes or executes decisions* |
| `human_oversight` | Who checks outputs, and how, before they are relied on |
| `affected_groups` | Who is affected: nobody outside the team, staff, students, research participants, patients, the public |
| `data_classes`, `data_categories` | Highest classification of data involved, and category tags (see [Data vocabulary](#data-vocabulary)) |
| `outputs_used_for` | Tags: publications, grant applications, peer review, analysis of record, software in production, communications, decisions about people |
| `approved_until`, `next_review_on` | When the current approval lapses and when the record is next revisited |
| `intake` | The form version and answers the record was created from |

Links: the AI systems it uses, the datasets it processes, and external references (below).

### AI system

**A tool, product, service, or application that uses AI**, whether bought, embedded in other software, open source, or built in-house. A use case *uses* systems; a system can serve many use cases.

| Field | Notes |
|---|---|
| `kind` | Vocabulary: vendor product, feature embedded in another product, model API or service, open-source tool, internally built application, agent |
| `vendor_id`, `embedded_in` | Who supplies it, and the host product for an embedded feature |
| `hosting` | Local device, on premises, organization's cloud tenant, vendor-hosted |
| `edition`, `access_path` | The exact plan or license tier, and how it is reached (web app, desktop app, API, plug-in). A catalog standing applies to one edition and access path: the enterprise plan under contract and the free consumer plan of the same product are different records |
| `version`, `url` | As known |
| `catalog_status` | *Not listed*, *under evaluation*, *approved*, *approved with restrictions*, *not approved*, *retired* |
| `permitted_data_classes` | The highest data class it may be used with, and any category exclusions |
| `terms` | Standard conditions that apply to every use (shown in the catalog) |
| `data_handling` | Does the supplier train on inputs; retention period; processing regions; sub-processors known |
| `regulatory_status` | Free vocabulary for regulated products (for example, cleared as a medical device) |

An AI system with `kind = agent`, or any system that takes actions, also has an **agent profile**: `autonomy_level` (suggests only, acts with approval, acts within limits, fully autonomous), `actions` (what it can change, and where), `tools` (connected tools and servers, each with name, purpose, and access), `identity` (the account or credentials it acts under), `reversibility`, `human_override` (how a person stops or corrects it), `memory` (what it retains between runs), and `limits` (spending, rate, and scope limits).

### Model

**A specific model**, identified well enough to tell versions apart: `provider`, `family`, `version`, `kind` (foundation language model, fine-tuned model, embedding model, classical machine learning, vision, speech, other), `modality`, `license`, `origin` (commercial API, open weights, built in-house), `base_model_id` for fine-tunes, `weights_location`, `release_date`, and `deprecation_date`.

A model can carry a **model card**: intended use, out-of-scope use, training data summary, evaluation summary with metrics and populations, known limitations, and a link or attached file for the source card. The card's fields follow widely used public model card conventions so cards can be imported and exported.

**Models an organization runs or trains itself** need more than a commercial API does, because nobody else is answering for them:

| Field | Notes |
|---|---|
| `weights_source`, `weights_checksum` | Where the weights were obtained, and a hash that identifies exactly which file is in use |
| `weights_format` | The file format. Some formats can run code when loaded, which is a security review question in itself |
| `parameters`, `quantization` | Size and any reduction applied, which affect both capability and where it can run |
| `license`, `license_restrictions` | The license, and what it limits: commercial use, redistribution, fields of use, acceptable-use terms |
| `runs_on` | The machine, cluster, or service it is served from, and who can reach it |
| `tuning_method` | For a fine-tune: full fine-tuning, adapters, or another method, with the base model linked by `derived_from` |
| `data_class` | The sensitivity of the model itself (see below) |
| `sharing` | Whether the weights may leave the unit, the organization, or be published |

A fine-tuned model **inherits the sensitivity of what it was trained on**. Weights can reproduce their training data, so a model tuned on Protected or Restricted data is itself at least that class, and any agreement that covers the training data (a data use agreement, an ethics protocol) covers the weights as a derivative. GovWren computes the model's minimum data class from its `trained_on` links and shows the datasets that set it; a person can raise it, never lower it below that floor without an exception.

Models have a **catalog standing** like AI systems do, so an organization can keep a list of open-weight models it has reviewed, and a lab can register its use of one as quickly as it registers a use of an approved tool.

### Dataset

**Data that AI is trained on, tuned with, or given.** `description`, `steward`, `data_class`, `data_categories`, `subjects` (who the data is about), `identifiability` (identified, coded, de-identified, anonymous, not about people), `deidentification_method`, `source`, `permitted_uses`, `restrictions`, `retention`, and `location`.

GovWren never holds the data. A dataset record is a description, with external references to wherever the data and its agreements actually live.

### Vendor

**An outside supplier.** `legal_name`, `website`, `contacts`, `status` (prospective, active, offboarding, former), `due_diligence_status`, and `assurances` (certifications and reports the vendor has supplied, each with a date and an evidence link).

`agreement(vendor_id, kind, title, reference, effective_on, expires_on, auto_renews, notice_days, owner, evidence_id)` records each contract or legal instrument. `kind` is a vocabulary (master agreement, data processing agreement, business associate agreement, data use agreement, license, terms of service accepted). Expiry dates feed reminders.

### Links

`record_link(from_type, from_id, relation, to_type, to_id, note)` connects any two inventory records. Relations are a fixed, typed set so the graph can be reasoned about:

| Relation | From → to |
|---|---|
| `uses` | Use case → AI system |
| `processes` | Use case → dataset; AI system → dataset |
| `built_on` | AI system → model |
| `derived_from` | Model → model (fine-tune of, distilled from) |
| `trained_on`, `evaluated_on` | Model → dataset |
| `supplied_by` | AI system → vendor; model → vendor |
| `embedded_in`, `depends_on` | AI system → AI system |
| `replaces` | Any record → the record of the same type it supersedes |

The **dependency graph** is this table. "Everything that depends on this model" and "everything this use case relies on" are walks over it. Risks, incidents, and exceptions attached to a record are *shown* on its dependents as inherited; they are never copied.

### External references

`external_ref(record_type, record_id, kind, identifier, url, note)` points to things that live in other systems: an ethics board protocol, a grant, a data use agreement, a purchase request, a ticket, a source repository, an entry in a model registry. `kind` is a vocabulary. GovWren stores the pointer and nothing else.

### Data vocabulary

Two vocabularies describe data, and both are the organization's to define.

- **Data classes** are ordered levels. Order matters: rules compare a use case's highest class with what a system is permitted to handle. The defaults are four:

  | Class | Meaning |
  |---|---|
  | **Public** | Poses little or no risk if disclosed, and may be shared with anyone: published results, public web content, job postings |
  | **Internal** | Meant for use inside the organization by its own people: drafts, preliminary analysis, internal procedures, aggregate figures, most correspondence |
  | **Protected** | Could harm people or the organization if seen by the wrong person, inside or out; access is limited to those who need it: unpublished research data and manuscripts, study protocols, de-identified participant data, personnel and student records, budgets, security documentation, data held under an agreement |
  | **Restricted** | Governed by specific legal, regulatory, or contractual obligations, where loss or disclosure may require notifying people or authorities: identifiable health information, identifiers such as government ID numbers, identifiable participant data and recordings, identifying genomic data, export-controlled information, payment and bank details, passwords and keys, legally privileged material |

  Each class carries a definition and examples grouped by kind of data (personal, research, health, financial, administrative). The intake form shows them beside the question, because most misclassification comes from people not recognizing their own data in an abstract definition.
- **Data categories** are unordered tags that trigger specific obligations. The defaults include personal data, health information, human-subjects research data, genetic data, student records, unpublished research, third-party data under agreement, proprietary source code, credentials and secrets, and export-controlled information.

## Intake

### Form

`form(key, kind)` and `form_version(form_id, version, status, schema, published_at, published_by)`. `kind` says what the form creates or collects: a use case, an AI system evaluation, a vendor questionnaire, a change declaration, an incident report, or an attestation.

A form's `schema` is a document of sections and questions. Each question has a stable `key`, a type (short text, long text, single choice, multiple choice, yes/no, number, date, person, unit, record reference, file), help text, `required`, an optional `show_when` condition over earlier answers, and an optional `maps_to` naming the record field it fills. A published version is immutable; editing creates a new draft version.

`form_response(form_version_id, subject_type, subject_id, answers, submitted_by, submitted_at)` stores answers by question key. Because it names the exact version, an old response always renders with the questions that were asked.

### Scoring model

`scoring_model(version, status, definition)`. The definition holds:

- **Factors**, each with levels 0 to 3 and a plain description of every level.
- **Contributions**: which answers and record fields set which factor to which level. A factor takes the highest level any of its contributions gives it.
- **Tiers**: named, ordered bands over the total score.
- **Floors**: conditions that set a minimum tier regardless of the total.
- **Stops**: conditions that mark a request as a prohibited use, which cannot be approved without an exception.

`tier_assessment(subject_type, subject_id, scoring_model_version, factor_levels, total, computed_tier, floors_applied, final_tier, override_reason, overridden_by, assessed_at)` records each result, so a tier can always be traced to the answers and the rules that produced it. The scoring method is specified in [governance-engine.md](governance-engine.md).

### Rules

`rule(id, kind, name, order, when, then, status)` and versioned `rule_set`. A rule is a condition over a record's fields, answers, and tier (`when`) and one or more effects (`then`): require a review function, set the decision authority, add a standard condition, set the review cadence, apply a control, or approve automatically. Conditions are a small declarative structure, never code.

## Review and decisions

### Review

`review(ref, subject_type, subject_id, kind, status, tier_at_open, rule_set_version, opened_at, due_on, clock_paused_at, closed_at)`.

- `kind`: initial, periodic, change, incident-triggered, catalog evaluation, retirement.
- `status`: *triage*, *in review*, *with requester*, *ready for decision*, *decided*, *cancelled*.

A record can have many reviews over its life and at most one open at a time.

### Review task

`review_task(review_id, review_function, assignee_id, status, finding, notes, recommended_conditions, due_on, completed_at)`. One task per required review function. `review_function` is a vocabulary; the defaults are privacy, information security, legal and contracts, research ethics, research integrity, clinical safety, data stewardship, and architecture. `finding` is one of *no concerns*, *acceptable with conditions*, or *objection*.

### Decision

`decision(review_id, outcome, rationale, decided_by, authority, decided_at, tier, approved_until, risk_acceptance, session_id?)`.

- `outcome`: approved, approved with conditions, declined, returned, withdrawn.
- `authority`: who the rules said could decide (governance lead, committee, executive risk acceptor).
- `risk_acceptance`: for the tiers that require it, the named person who accepts the residual risk and their statement.

A decision is never edited. A later decision supersedes it.

### Condition

`condition(decision_id, subject_type, subject_id, text, kind, owner_id, due_on, status, evidence_id, closed_by, closed_at)`. `kind` is *before use* (blocks the approval from taking effect), *by date*, or *ongoing*. `status` is open, met, or waived. Standard conditions come from a library (`condition_template`) so the same wording is used every time and can be reported on.

### Committee session

`session(id, body, held_on, status, minutes)` and `session_item(session_id, review_id, order, outcome_note)`: a meeting of a decision-making body, the reviews on its agenda, and what was decided. Decisions made in a session point back to it.

### Standing

A use case's `status` is its standing with governance:

```text
 draft ─▶ submitted ─▶ in review ─▶ approved ───────────────┐
              ▲            │       ─▶ approved with conditions ┤
              │            ▼                                  ├─▶ suspended ─▶ (review)
              └──── returned (with requester)                 ├─▶ lapsed    ─▶ (review)
                           │                                  └─▶ retired
                           ├─▶ declined
                           └─▶ withdrawn
```

*Lapsed* means an approval ran past `approved_until` without a completed re-review. *Suspended* is set by governance, usually after an incident. Both are visible everywhere the record appears.

## Oversight

- **Attestation.** `campaign(kind, title, period, opens_on, due_on, scope, status)` and `attestation(campaign_id, subject_type, subject_id, assignee_id, response, note, responded_at)`. Kinds: *record confirmation* (an owner confirms a record is still accurate), *unit completeness* (a steward confirms the unit's list is complete), *policy acknowledgment*, and *vendor reconfirmation*. Responses are confirmed, changed (which opens a change request), no longer in use (which opens a retirement), or, for a unit, the new records added.
- **Change request.** `change_request(ref, subject_type, subject_id, declared_by, answers, material, status, review_id)`. The owner answers a short material-change form; rules decide whether a re-review is required.
- **Exception.** `exception(ref, subject_type, subject_id, scope, justification, compensating_measures, requested_by, approved_by, starts_on, expires_on, status)`. A time-limited, approved departure from a policy, control, condition, or stop. Exceptions always expire.
- **Incident.** `incident(ref, title, category, severity, occurred_on, detected_on, reported_by, description, affected_groups, immediate_actions, root_cause, external_reporting, lessons, status)`, linked to the records involved through `incident_subject`. Categories are a vocabulary: data exposure, harmful or incorrect output, unfair outcome, security, misuse, research integrity, unapproved use, and near miss. Status runs reported, triaged, investigating, contained, resolved, closed.
- **Action.** `action(ref, source_type, source_id, title, detail, owner_id, due_on, status, evidence_id)`. One table for everything someone must do: a corrective action from an incident, a follow-up from a review, a gap against a control, a task from a session.

## Assurance

- **Risk.** `risk(ref, subject_type, subject_id, library_id?, title, description, category, inherent_likelihood, inherent_impact, treatment, residual_likelihood, residual_impact, owner_id, status, review_on)`. Likelihood and impact are 1 to 5. A risk may be attached to a record or to the organization. `risk_library` holds the catalog of reusable risk statements a risk can be drawn from.
- **Control.** `control(ref, title, statement, guidance, scope, owner_function, applicability, status)`. `scope` is *program* (implemented once for the organization) or *record* (implemented per use case or system). `applicability` is a rule condition that decides which records a record-scoped control applies to.
- **Control implementation.** `control_impl(control_id, subject_type?, subject_id?, status, not_applicable_reason, owner_id, verified_on, next_check_on)`. Status is not started, in progress, implemented, or not applicable.
- **Framework.** `framework(key, title, version, publisher, license_note, source_url)` and `requirement(framework_id, parent_id, code, title, text, order)`, a tree of whatever depth the framework has. `control_requirement(control_id, requirement_id, coverage)` is the crosswalk: one control can address requirements in many frameworks.
- **Policy.** `policy(ref, title, owner_id, status)` and `policy_version(policy_id, version, body, effective_on, review_on, approved_by)`. Policies link to the controls that implement them.
- **Evidence.** `evidence(ref, kind, title, description, owner_id, collected_on, valid_until, data_class, file_id?, url?, status)` and `evidence_link(evidence_id, target_type, target_id)`. One piece of evidence can support any number of control implementations, conditions, reviews, vendors, or records. `file(id, sha256, size, media_type, original_name)` describes a stored file; the bytes are in the data home at a path derived from the hash.

## Platform

### History

`event(id, at, actor_kind, actor_id, actor_label, action, subject_type, subject_id, subject_ref, parent_type, parent_id, changes, context, prev_hash, hash)`.

Every write goes through a session that records events by itself: after each flush it turns every new, changed, and deleted row of an audited model into an event, in the same transaction. A service cannot forget to log a change, and the two ways around the session (writing with no actor, and bulk statements against audited tables) are refused. `changes` records each changed field with its value before and after. `context` carries what the change was part of (a named operation, a review, a campaign, an import). Child rows name the record they belong to, so a change to an owner or a link shows in that record's history. The table is append-only: the application never updates or deletes a row, and a trigger in the database refuses both.

Each event's `hash` covers its own content and the previous event's hash, forming a chain. `govwren verify` recomputes the chain and reports the first break, so tampering with history outside the application is detectable.

A record **as it stood on a date** is rebuilt by replaying its events up to that date. The current tables are the fast path for today; the event log is the authority for the past.

### Everything else

| Table | Purpose |
|---|---|
| `setting` | Program settings as keyed JSON values, each change an event: vocabularies, branding, cadences, notification rules |
| `comment` | Discussion on any record or review, with mentions; requester-visible or internal |
| `notification`, `outbox` | In-app notices and queued email |
| `watch` | Who follows which records |
| `saved_view` | A person's saved filters and columns for a list |
| `session_token`, `api_token` | Sign-in sessions and tokens for the API, stored as hashes |
| `oidc_state` | Single-use sign-in state |
| `job`, `job_run` | Scheduled work (reminders, lapses, digests) and its outcomes |
| `search_doc` | Search text for every record, kept current by the service layer |
| `counter` | The sequence behind each reference prefix |

## Portability

- `govwren export` writes every table as JSON Lines plus the stored files, with a manifest of counts and hashes; `govwren import` reads it into an empty database of either kind. This is also how an installation moves from SQLite to PostgreSQL.
- Every list in the app exports as CSV and JSON, with the filters that produced it recorded in the file.
- Program configuration (forms, scoring model, rules, vocabularies, condition templates, controls, framework mappings) exports and imports as a single **program pack**, so one organization's setup can be versioned, reviewed, and shared with another.
