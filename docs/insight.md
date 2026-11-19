# Insight

GovWren keeps a record of every request, decision, review, and change. This guide covers reading that record back as a whole: how the program is doing, in figures that say what they count.

This guide grows with each release. It covers the measures, the portfolio, and the unit report. The record dossier and the leadership report follow.

Governance, auditors, and administrators see everything in this guide. A steward sees the report for their own unit.

## Measures

**Measures** shows five figures about the program. Each one comes with the sentence that defines it and the cohort it counts, so that nobody has to guess what a number means.

![The Measures page: five figures, each with its definition, what it counts, and its trend](images/measures-light.webp "The program's measures")

| Measure | What it is | What it counts |
|---|---|---|
| Turnaround | The median number of days from a request being submitted to its decision, leaving out the time it spent back with the requester | First reviews decided by a person in the period. Approvals made by a rule and withdrawn requests are left out |
| Throughput | How many requests reached a decision in the period | First reviews decided in the period, whoever or whatever decided them |
| Coverage | The share of uses in the inventory that an owner has confirmed in the twelve months to the end of the period | Use cases that are approved, lapsed, or suspended. A use counts if an owner answered an attestation campaign about it |
| Currency | The share of uses in the inventory whose approval is in force at the end of the period | Use cases that are approved, lapsed, or suspended. A use counts if it is approved and its approval has not passed its end date |
| Completeness | How complete the records of uses in the inventory are, on average | Use cases that are approved, lapsed, or suspended, each scored by the share of expected fields that are filled in |

### Choose the period

The page shows the last ninety days. Choose six months or a year at the top. Turnaround and throughput count what was decided in the period. Coverage, currency, and completeness describe the inventory as it stands at the end of it.

### Read a trend

Under each figure is its trend. Once a day GovWren stores each measure as it stands, over the ninety days to that date. The trend is those stored values, oldest first.

A stored value is not recomputed. What a measure said last March is what was stored last March, even if records have since been corrected. The job that stores them is listed under [Scheduled work](keeping-watch.md#what-govwren-does-by-itself).

### Use a measure well

- A falling turnaround is good only if throughput holds. Read them together.
- Coverage rises when an [attestation campaign](keeping-watch.md#attestation-campaigns) runs, and falls as the twelve months pass.
- Currency falls when approvals [lapse](keeping-watch.md#if-nobody-confirms). The list of lapsed uses is one filter away under **Use cases**.

The same figures are available from the API at `GET /api/v1/measures`, with `from` and `to`.

## The portfolio

**Portfolio** shows the uses in the inventory grouped one way at a time. Choose how at the top:

| Group by | Shows |
|---|---|
| Unit | Each unit that has uses of its own |
| Tier | Minimal, moderate, high, and critical |
| Area | The area of work each use belongs to |
| Data class | The most sensitive class of data each use involves |
| Supplier | The vendors of the tools each use relies on |

![The portfolio grouped by unit: uses in the inventory, their standing, what needs a look, and what was decided in the period](images/portfolio-light.webp "The portfolio, by unit")

For each group the table shows:

- **In use:** how many of its uses are in the inventory, approved, lapsed, or suspended.
- **Standing now:** how those uses stand today, and how many more are in review.
- **Needs a look:** how many are at the high or critical tier, and how many serious risks are open on them.
- **Decided in the period:** how many decisions were made for the group in the period chosen, and how they went.

Each name opens the list of uses it counts, so no figure has to be taken on trust. A supplier's name opens the supplier.

A use that relies on tools from two suppliers is counted under both. Under every other grouping each use is counted once.

Standing is always as of today. Only the last column changes with the period.

## The unit report

A unit report puts one unit on a page: the unit and every unit beneath it.

Stewards open theirs with **My unit**. Governance, auditors, and administrators can open the report for any unit.

![A unit report: counts for the unit, what needs attention, and each use with its tier, standing, and end date](images/unit-report-light.webp "A unit on one page")

It shows:

- How many uses the unit has in the inventory, how many have an approval in force, and how many are in review.
- What needs attention: uses waiting for an owner to confirm, overdue conditions, approvals that end within sixty days, approvals that have lapsed, and open incidents.
- Every use, with its unit, tier, standing, and the date its approval ends.
- Exceptions asked for or in force, and open incidents that involve a use in the unit.

It is the page to open before a meeting with a head of unit, and the page a steward checks before [attesting that their list is complete](keeping-watch.md#attest-that-a-units-list-is-complete).
