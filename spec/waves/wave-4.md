# Wave 4: Assurance (v0.4.0)

**Goal:** show that the program's safeguards exist and work, with evidence, and without turning governance into a checklist exercise. Waves 1 to 3 decide requests and keep the inventory true. Wave 4 adds what an assurer asks for: the risks that are known, the controls that answer them, the evidence that the controls work, and the policies behind them.

**Branch:** `wave-4` · **Target version:** `0.4.0` · **Status:** ◐ in progress

## Exit criteria

The wave is done when, on a fresh checkout:

1. A risk is recorded on a record or on the organization, drawn from a library or written fresh, scored before and after treatment, owned, and reviewed on a date. A reviewer's finding becomes a risk in one step (ASR-02, ASR-03).
2. Controls are defined once in a library, apply to the program or to records by rule, and each applicable control has a status, an owner, evidence, and a next check date (ASR-04, ASR-05).
3. Evidence that is expiring or expired is flagged on everything it supports, and a gap becomes an action (ASR-09).
4. A policy has versions, an owner, a review date, and the controls that implement it, and people can be asked to acknowledge it (ASR-10).
5. An impact assessment can be required by rule and is kept with the review. A vendor has a due-diligence questionnaire with its answers and assurances (ASR-11, ASR-12).
6. A framework is loaded as a pack with no code change. Each requirement shows as covered, partly covered, a gap, not mapped, or not applicable, and the statement of applicability can be exported. With no framework loaded, nothing is missing (ASR-06, ASR-07, ASR-08, ASR-13).
7. The demo organization shows all of the above, the suite passes on both databases, and the accessibility audit passes over every new screen.

## Decisions taken

- **The risk library is original text under GovWren's own eight categories.** The specification planned to organize it under a published taxonomy. Writing our own categories keeps the library free of any outside source and of the need to attribute one; a pack can remap it later.
- **A risk is scored on two five-point scales, before and after treatment.** The product of the two gives one of four levels with fixed bands, the same four words the tiers use, so nobody learns a second vocabulary.
- **Risks are findings.** An open risk at the two highest levels shows on its record and on everything that relies on it, like an incident or an exception.

---

## Slice 1: Risks ☑

**Goal:** what could go wrong is written down, scored, owned, and looked at again.

- [x] The risk library, loaded as a pack
- [x] The risk register: risks on a record or on the organization, inherent and residual scores, treatment, owner, review date
- [x] A risk from a review finding
- [x] Open high risks shown as findings, and inherited

## Slice 2: Controls ☑

- [x] The control library, with program and record scope and applicability rules
- [x] Implementation status, owner, and next check date for each applicable control
- [x] Controls linked to the risks they treat

## Slice 3: Evidence freshness ☑

- [x] Evidence linked to controls
- [x] Expiry and renewal prompts; gaps as actions

## Slice 4: Policies ☑

- [x] Versioned policies with owners and review dates, linked to controls
- [x] Acknowledgment campaigns

## Slice 5: Assessments ☑

- [x] Impact assessments required by rule
- [x] Vendor due-diligence questionnaires and assurances

## Slice 6: Frameworks ☑

- [x] The pack loader, the optional built-in framework and its crosswalk
- [x] Readiness views and the statement of applicability

## Slice 7: Release prep ☐

- [ ] Guides, changelog, the demo extended, the accessibility audit
- [ ] Release

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-19 | Wave planned at the end of wave 3 |
| 2026-11-19 | Slice 1. A risk's standing follows from what has been done: open, treated once a treatment and both residual scores are given, or accepted. Only governance accepts a risk as it stands or closes one. A reviewer records a risk through the review they have a part in; it goes to the use's accountable owner. One reminder is sent for each review date. |
| 2026-11-19 | Slice 2. Applicability is a condition in the one condition language, evaluated against the record each time it is asked, so a control starts to apply when a record changes. A row is kept only once someone has said how a control stands. Saying a control does not apply to a record is governance's, with a reason. Marking a control in place sets its next check from the control's cadence. |
| 2026-11-19 | Slice 3. Evidence attaches to a control's standing on a record, like a condition's. Gaps are not stored: the action list works them out each time from controls in place whose check is due or whose evidence has all expired, and from evidence near or past its date. |
| 2026-11-19 | Slice 4. A policy's text lives in its versions; publishing a draft puts it in force and leaves earlier versions as they were. An acknowledgment is of one version and one person, asked once. Acknowledgments have their own table and are not attestation campaigns, which ask about records and units. Everyone signed in reads policies in force; drafts and retired ones are for those who see everything. |
| 2026-11-19 | Slice 5. Assessment templates are read from a pack; the rule that requires an impact assessment is a condition on the template (`required_when`), by default the critical tier, so the routing rule format is unchanged. Approval is refused while a required assessment is missing or still a draft. Nobody reviews an assessment they submitted. A reviewed assessment is fixed; answering again starts a new one. |
| 2026-11-19 | Slice 6. The built-in framework is shipped as its functions and categories in our own one-sentence summaries, with `text_policy` set to `summary`, and not as verbatim subcategories: a pack that claims to quote a standard must be checked line by line against it, and that is left for a later release. The crosswalk travels in the framework's pack and is stored on each requirement. A program control counts as fully in place only with evidence that is still good; a record control counts by the share of records. |
