# Content packs

GovWren ships its governance content as **packs**: data files that are loaded into the database, versioned, and replaceable. Whole program configurations, risk and control libraries, and optional framework mappings are all packs. A revised form, a new set of controls, or another organization's way of working arrives as a pack update, never as a code change.

This document defines the pack format, the rules for what text may be shipped, the packs planned, and how readiness against a framework is worked out.

## Kinds of pack

| Kind | Holds | Loaded into |
|---|---|---|
| **Program** | Vocabularies, forms, the scoring model, rules, cadences, condition templates | Program settings |
| **Framework** | A tree of requirements with stable codes | `framework`, `requirement` |
| **Control library** | Controls with statements, guidance, scope, applicability, and crosswalks to framework requirement codes | `control`, `control_requirement` |
| **Risk library** | Reusable risk statements with categories and suggested controls | `risk_library` |

## Format

A pack is one JSON document. JSON is chosen because the standard library reads and writes it, it diffs well enough in review, and it needs no parser dependency.

```json
{
  "pack": {
    "key": "nist-ai-rmf",
    "kind": "framework",
    "title": "NIST AI Risk Management Framework",
    "version": "1.0",
    "pack_version": "1.0.0",
    "publisher": "National Institute of Standards and Technology",
    "source_url": "https://www.nist.gov/itl/ai-risk-management-framework",
    "license": "Public domain (United States government work)",
    "text_policy": "verbatim",
    "attribution": "…"
  },
  "requirements": [
    { "code": "GOVERN", "title": "Govern", "children": [
      { "code": "GOVERN 1", "title": "…", "children": [
        { "code": "GOVERN 1.1", "text": "…" }
      ]}
    ]}
  ]
}
```

- `version` is the version of the source document; `pack_version` is the version of this pack, which also changes when mappings or wording are corrected.
- Every requirement has a `code` that is stable across pack versions. Codes are how crosswalks, implementation records, and evidence stay attached when a pack is updated.
- Packs are validated on load against a schema. A pack that fails validation is rejected whole, with every problem listed.

Built-in packs live in `src/govwren/resources/packs/`. An organization can load its own from a file or, from wave 6, build one in the app.

## What text may be shipped

GovWren is Apache 2.0 licensed, and nothing in the repository may compromise that. Source documents come under very different terms, so every pack declares a **text policy**, and the policy decides what the pack may contain.

| Text policy | Applies to | What the pack contains |
|---|---|---|
| `verbatim` | Public-domain works and works under permissive licenses: United States government publications, the text of laws and regulations | Codes, titles, and the source text itself |
| `attributed` | Works under attribution licenses | Codes, titles, and text, with the required attribution shown wherever the content appears in the app and in every export |
| `separate` | Works under share-alike licenses | The same, but distributed as a separately licensed pack file, loaded on request, and never merged into Apache-licensed content |
| `identifiers` | Copyrighted standards and guidance with no open license | Only the codes, a short neutral label, and GovWren's own plain-language summary of what the requirement is about. Never the source's wording |

For an `identifiers` pack, an organization that holds a license to the source can **import the official text locally**. Imported text is marked as licensed, is shown only inside that installation, and is excluded from every pack export and from the transparency register.

The policy is enforced in two places: a test checks every built-in pack against its declared policy (an `identifiers` pack with long text fields fails the build), and each pack's license and attribution are displayed on the framework's page in the app.

## Planned packs

### With wave 1: the default program

A complete, working program so that a new installation can take requests on its first day: default vocabularies, a staged intake form, the six-factor scoring model, routing rules for four tiers, cadences, and about thirty standard conditions. It is written for a research organization and is meant to be edited.

### With wave 4: assurance content

| Pack | Text policy | Shape |
|---|---|---|
| **GovWren control library** | Original, Apache 2.0 | About 45 controls in GovWren's own words, split between program and record scope |
| **GovWren risk library** | Original, Apache 2.0; taxonomy `attributed` | About 80 risk statements written for research and health settings, organized under a published, openly licensed risk taxonomy of 7 domains and 24 subdomains |
| **NIST AI Risk Management Framework 1.0** *(optional)* | `verbatim` | 4 functions, 19 categories, 72 subcategories, with a crosswalk from the control library |
| **NIST Generative AI Profile (AI 600-1)** *(optional)* | `verbatim` | 12 risk areas, each with suggested actions keyed to framework subcategories |

**The control library is the center of the design, and it stands on its own.** An organization can run its whole program on GovWren's controls and never load a framework. The controls are written from what a governance program actually has to do (know what is in use, name who answers for it, match review to risk, keep data where it is allowed to be, keep people in the loop, respond when something goes wrong, and keep the record) and not as a restatement of any one standard.

Frameworks are an optional layer on top, for organizations whose auditors, funders, or boards ask how the program lines up with a named reference. One framework is built in, because it is voluntary, widely recognized, and in the public domain. When a framework is loaded, readiness against it follows from the crosswalk: an organization implements a few dozen controls once, attaches evidence, and the mapping does the rest. Nobody fills in a checklist per framework, and no rows are copied per record.

Other standards, including certifiable management-system standards whose text is copyrighted, are not built in. The format supports them under the `identifiers` policy, and an organization pursuing one can load or build its own pack.

### With wave 6: starter packs

Program packs tuned for three kinds of organization (a research institute, a university, and an academic medical center), differing in vocabulary, default review functions, intake detail sections, and standard conditions. Alongside them:

- **A research pack.** Controls and standard conditions for funder rules on AI in applications and peer review, journal disclosure, human-subjects protocols, and data use agreements, written in GovWren's own words with references to the sources.
- **A health pack.** Model card fields aligned with health-sector conventions, clinical safety review questions, and controls for privacy and health-data agreements. Health-sector guidance from standards and accreditation bodies is covered under the `identifiers` policy unless its publisher grants more.
- **An agent security pack.** A published threat list for language model and agent applications, shipped under the `separate` policy because of its share-alike license.

### Not planned as built-in content

Packs that track individual laws and regulations change too often for a small project to keep correct. The format supports them, and they are welcome as community-maintained packs with a named maintainer. What GovWren does build in is the record-keeping those laws tend to ask for: who was told, who reviewed, what was decided and why, and how long the record is kept.

## Readiness

Readiness against a framework is derived, never typed in.

1. Each **requirement** is linked to zero or more controls through the crosswalk.
2. Each linked **control** has an implementation status (per organization for program-scope controls; per applicable record for record-scope controls) and linked evidence.
3. A requirement is:
   - **Covered** when every linked control is implemented and has current evidence.
   - **Partly covered** when some are, or when evidence has expired.
   - **A gap** when none are implemented.
   - **Not mapped** when no control is linked to it, which is shown as its own state and never counted as covered.
   - **Not applicable** when the organization has marked it so, with a justification.

The framework page shows counts in each state, the tree with each requirement's state, and, for any requirement, the controls and evidence behind it. For record-scope controls it shows the share of applicable records that have implemented them.

GovWren does not show a single compliance percentage as a headline, because one number hides the difference between a gap and an unmapped requirement. A summary bar shows the five states side by side.

A **statement of applicability** is an export of the control library with each control's applicability, justification, status, owner, and evidence.

## Updating a pack

Loading a newer version of a pack shows a comparison first: requirements added, removed, and reworded, and the crosswalks affected. Implementation records and evidence stay attached by code. Requirements that disappear are archived, not deleted, so an earlier assessment can still be read as it was. The update is an event in the history, like any other change.

## Standard formats

- **Export.** The inventory of models, datasets, and their dependencies exports as a machine-readable bill of materials (CycloneDX with its machine-learning model fields); model cards export in a common structure. Control and framework catalogs can be exported in a structure compatible with OSCAL.
- **Import.** Model cards and agent descriptions in common published formats can be imported to prefill a model or agent profile, for the person to confirm.

These are conveniences at the edge. GovWren's own model stays independent of any one format.

## A note on reliance

Framework content in GovWren is a working aid for organizing evidence. It is not legal advice, and showing a requirement as covered is not a certification. Pack pages say so, and say which version of the source they reflect and when the pack was last reviewed.
