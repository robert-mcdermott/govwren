# Wave 3: Keeping watch (v0.3.0)

**Goal:** an inventory that stays true without a central team chasing it. Waves 1 and 2 got requests decided and recorded. What was true on the day of a decision drifts: tools change, people leave, approvals run out, things go wrong. Wave 3 gives GovWren a sense of time, so that it asks the right person the right question when it is due, and records what they say.

**Branch:** `wave-3` · **Target version:** `0.3.0` · **Status:** ◐ in progress

## Exit criteria

The wave is done when, on a fresh checkout:

1. Work that is due happens without anyone starting it: an approval nearing its end opens a periodic review with the earlier answers carried forward, an approval that runs out lapses, and reminders and escalations go out, from a scheduler that survives restarts and never runs a job twice (OVR-01, OVR-02, REV-10).
2. Governance runs an attestation campaign: owners confirm their records in a few clicks, stewards attest that their unit's list is complete, and coverage is shown by unit (OVR-03, OVR-04).
3. An owner declares a change. Rules judge whether it is material; a material change opens a review limited to what changed. A record is retired with its dependents told (OVR-05, OVR-09).
4. Findings on a record, such as an incident on a model, are shown on everything that depends on it, marked as inherited (INV-08).
5. An exception is requested, justified, approved with compensating measures and an end date, and expires or is renewed (OVR-06).
6. Anyone reports an incident. It is triaged, linked to the records involved, may suspend an approval, and may open a review. Everything someone must do as a result is one list of actions (OVR-07, OVR-08, OVR-10).
7. The committee meets in a session: an agenda of decision packets, decisions recorded against it, and minutes. A named person accepts the risk where the rules require it. Automatic approvals are sampled and checked (REV-09, REV-11, TIR-10).
8. The demo organization shows all of the above with thirty months of it, the suite passes on both databases, and the accessibility audit passes over every new screen.

## Decisions taken

- **The scheduler lives in the server process**, like the mailer, and takes the mailer over. Each job run is claimed in the database, so several processes never run the same job at once, and `govwren jobs run` does the same from a scheduled task when the server is not up.
- **Time comes from the clock that tests and the demo already set**, so every scheduled behavior is tested by moving the clock and not by waiting.
- **Nothing lapses silently.** Every automatic change of standing is an event with a reason, tells the people it affects, and is visible on the record.

---

## Slice 1: Schedules ☑

**Goal:** GovWren acts when something is due.

- [x] A job scheduler: jobs with a cadence, claimed runs, a run log, `govwren jobs`, and an Admin page
- [x] Periodic reviews opened ahead of an approval's end, with the earlier answers carried forward
- [x] Lapsed standing when an approval runs out, and its return when a periodic review approves
- [x] Reminders before due dates and escalation after them, to the owner and then the unit's steward
- [x] The mailer becomes a job

## Slice 2: Attestation campaigns ☑

**Goal:** the people closest to the work say whether the record is still true.

- [x] Owner confirmation campaigns: confirm, correct, or retire, one record at a time or many at once
- [x] Unit completeness campaigns: a steward adds what is missing and attests
- [x] Coverage by unit, and who has not answered

## Slice 3: Change and retirement ☑

**Goal:** a record changes in the open.

- [x] Change declarations, with rules that say which changes are material
- [x] A change review limited to what changed
- [x] Retirement, with dependents told
- [x] Inherited findings on dependents

## Slice 4: Exceptions ☑

- [x] Request, justification, compensating measures, approval, end date
- [x] Expiry and renewal; the register

## Slice 5: Incidents and actions ☑

- [x] Reporting by anyone; triage; category and severity; linked records
- [x] Suspension, and incident-triggered reviews
- [x] One list of actions with owners and due dates

## Slice 6: Sessions and acceptance ☐

- [ ] Committee sessions: agenda, decisions, minutes
- [ ] Named risk acceptance where the rules require it
- [ ] Sampled checks of automatic approvals

## Slice 7: Release prep ☐

- [ ] Guides, changelog, the demo extended, the accessibility audit
- [ ] Release

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-19 | Wave planned at the end of wave 2 |
| 2026-11-19 | Slice 1. A periodic review opens 60 days before an approval ends and starts with the owner, whose earlier answers are put back as a draft. The standing of the use holds until the review is decided. Confirming applies the rules in force to the answers as they now stand: approved again on the spot, or on to reviewers. A renewal does not set again a standard condition that still stands. |
| 2026-11-19 | Slice 1. Jobs keep a run record only when a run did something or failed, so a job that runs every minute does not fill the table. Reminders are sent once per stage (nearly due, overdue), tracked in their own table. |
| 2026-11-19 | Slice 2. A campaign asks about records (owners answer: confirmed, changed, or no longer in use) or about units (a steward attests the list). "No longer in use" retires the record on the spot; "changed" tells governance, and slice 3 turns it into a change declaration. With no active owner left, a record's question goes to its unit's steward. Each answer is an event on the record it is about. |
| 2026-11-19 | Slice 3. A change is material if the tier rises, a review function is newly required, or an answer the approval rested on differs. The list of such answers is built in and a rule set may replace it under `material_changes`. A change that is not material is recorded by rule and the approval stands with the same end date; a material one opens a change review that shows the answers before and after. A change review never restarts the approval period. Findings are worked out from standing for now; incidents join them in slice 5. |
| 2026-11-19 | Slice 4. An exception belongs to one record, is asked for by whoever is responsible for it, and is decided by governance, never by the person who asked. It runs for a year at most. A renewal is a new request that points to the one it renews, so the register shows how long a departure has really lasted. An exception in force is a finding on its record and is inherited by what relies on it. |
| 2026-11-19 | Slice 5. An incident is seen by governance, auditors, whoever reported it, and whoever is responsible for a record it involves. A report becomes a finding only once triaged. Suspension keeps the standing the use had, so lifting it puts that back; an incident review that approves also ends the suspension, and neither restarts the approval period. An incident cannot be closed while an approval it suspended is still suspended. The action list is actions plus the dated and before-use conditions of decisions, read together; conditions keep their own table and route. |
