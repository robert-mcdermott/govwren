# Wave 8: Standards and agents (v0.8.0)

**Goal:** show an adopter how GovWren answers the standards they are held to, and govern agents as the distinct thing they are. A medical research organization is asked about ISO/IEC 42001 and HIPAA before it is asked about anything else, and an agent raises questions a chat tool does not: what it acts as, what it can reach, and how it is stopped.

**Branch:** `wave-8` · **Target version:** `0.8.0` · **Status:** ◐ in progress

## Exit criteria

The wave is done when, on a fresh checkout:

1. ISO/IEC 42001 and HIPAA load as built-in frameworks beside the NIST AI RMF, and what GovWren can already do (policies, impact assessments, acknowledgments, leadership reports) is counted, because a control stands behind each.
2. An agreement names the AI systems it covers. Each system says whether an agreement covering health information is in place, and the catalog and the checkpoint say so too. A request that would send health data to a supplier's tool with no such agreement cannot be approved.
3. The statement of applicability can be written against a loaded framework: one row for each of its requirements.
4. A guide says plainly what GovWren evidences for each standard and what it does not do.
5. An agent's record says what it acts as, where it runs, and whether it starts other agents. Four controls cover the agent risks that had none, every agent must show it can be stopped, and security reviewers have an agent assessment.
6. An installation that upgrades gains the new controls without losing anything it has set.
7. The suite passes on both databases, and the accessibility audit and keyboard check pass over every new screen.

## Decisions taken

- **A framework pack carries codes and our own words.** ISO/IEC 42001 is copyrighted, so its pack holds clause and control numbers with short labels and summaries written here, and none of the standard's text. HIPAA is public law and is summarized. An organization reads the standard itself for its wording.
- **Mapped means an auditor would accept the evidence.** A requirement is mapped to a control only where that control produces evidence for it, not where a feature is merely related. A requirement nothing answers shows as not mapped, which is the point: the readiness view is the gap list.
- **GovWren evidences; it does not perform.** Technical safeguards live in each AI system. GovWren holds the control that says they must be shown, and the evidence that they were. It still scans nothing.
- **No new kinds of record for a management system.** Management review, internal audit, and training are program controls with evidence attached. Records of their own would make GovWren a different product.
- **A shared tool is an AI system.** An agent's tools and connectors are recorded as AI systems and linked, so that the dependency graph already shows what a compromised tool reaches. There is no sixth kind of record.
- **Questions that only some organizations need go in a starter, not the core.** Which HIPAA pathway a study uses, and whether a tool supports decisions about patient care, are questions in the academic medical center starter, where rules can read them.
- **Packs cite provisions, not news.** What is proposed or pending in regulation changes faster than a release. A pack says what a provision asks; an organization confirms its current status.

---

## Slice 1: Controls and frameworks ☑

- [x] Controls for what the product already does, and for safeguards on health data
- [x] ISO/IEC 42001 and HIPAA as built-in frameworks
- [x] Upgrading adds new built-in controls and risks without touching what is there

## Slice 2: Agreements that cover systems ☑

- [x] An agreement names the AI systems it covers
- [x] Each system's standing for health information, in the catalog and the checkpoint
- [x] Whether a vendor will sign such an agreement
- [x] A rule that stops health data going to a tool with no covering agreement

The rule is on for a new installation and off for one that already holds records
(migration 0031 records the setting), so an upgrade changes no decision until someone
turns it on.

## Slice 3: Applicability and alignment ☐

- [ ] The statement of applicability against a loaded framework
- [ ] A guide to what GovWren evidences for each standard, and what it does not do

## Slice 4: Agents ☐

- [ ] The agent profile: what it acts as, where it runs, whether it starts other agents
- [ ] Controls for least privilege, its own identity, untrusted input, and sandboxed code
- [ ] Every agent shows it can be stopped, whatever its tier
- [ ] An agent assessment for security review
- [ ] An agent security framework pack

## Slice 5: Release prep ☐

- [ ] Guides, changelog, the demo extended, the accessibility audit
- [ ] Release

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-19 | Wave planned after an outside review of how GovWren lines up with the standards its first adopters are held to. Taken from it: controls behind existing features, the two framework packs, agreements at the level of the system, and the agent work. Left out: new record types for management review, audit, and training; a retention setting, since GovWren deletes nothing; and packs of proprietary accreditation content. |
| 2026-11-19 | Slice 1. Twelve controls, in a new group for running the program and in the existing ones. With them ISO/IEC 42001 maps 53 of 64 requirements and HIPAA 24 of 25; what stays unmapped is what GovWren has no evidence for, such as resources and design records for systems an organization builds. The nondiscrimination rule for patient care tools was left out of the HIPAA pack: it is a different rule and belongs with the health starter. The impact assessment is still required by rule only at the top tier, so that an upgrade changes no decision in flight; the new control asks for one from the high tier and shows where it is missing. `ensure` now adds built-in controls and risks an installation lacks and never touches one it holds. |
