# Wave 5: Insight (v0.5.0)

**Goal:** answer leadership's questions from the record, with figures that explain themselves. Waves 1 to 4 built the record. Wave 5 reads it back: how long decisions take, how much of the inventory is current, what the portfolio looks like, and what one record's whole story is.

**Branch:** `wave-5` · **Target version:** `0.5.0` · **Status:** ◐ in progress

## Exit criteria

The wave is done when, on a fresh checkout:

1. Turnaround, throughput, coverage, currency, and completeness are each shown with the words that define them, the period they cover, and the cohort they count, and a daily snapshot gives each a trend (RPT-03).
2. The portfolio is shown by unit, tier, domain, vendor, and data class over a chosen period, every figure opens the records it counts, and a steward gets their unit on one page (RPT-04, RPT-10).
3. Any record prints as a complete dossier with a manifest that verifies (RPT-05).
4. A leadership report is frozen as a snapshot that reopens unchanged (RPT-06).
5. Any record, and the inventory, can be seen as it stood on a chosen date (RPT-07).
6. Models export as a bill of materials and as model cards, and a chosen set of approved uses publishes as static pages (RPT-08, RPT-09).
7. The demo organization shows all of the above, the suite passes on both databases, and the accessibility audit passes over every new screen.

## Decisions taken

- **A measure carries its own definition.** The number is never shown without the sentence that says what it counts, the period, and the cohort. A figure nobody can explain is not shown.
- **Trends come from snapshots, not from recomputing the past.** A daily job stores each measure as it stood that day. What a measure said last March is what was stored last March, even if records have since been corrected.

---

## Slice 1: Measures ☑

- [x] Five measures, each with its definition, period, and cohort
- [x] Daily snapshots, and a trend for each measure
- [x] The Measures page

## Slice 2: Portfolio ☑

- [x] Views by unit, tier, domain, vendor, and data class over a chosen period
- [x] The unit report

## Slice 3: Dossier ☑

- [x] A complete, printable package for any record, with a manifest that verifies

## Slice 4: Leadership report ☑

- [x] A periodic report frozen as a snapshot that reopens unchanged

## Slice 5: As of ☐

- [ ] Any record, and the inventory, as it stood on a chosen date

## Slice 6: Open formats and the register ☐

- [ ] Bill-of-materials and model card export
- [ ] The transparency register as static pages

## Slice 7: Release prep ☐

- [ ] Guides, changelog, the demo extended, the accessibility audit
- [ ] Release

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-19 | Wave planned at the end of wave 4 |
| 2026-11-19 | Slice 1. Turnaround and throughput count what was decided in the period; coverage, currency, and completeness describe the inventory at its end. A snapshot is the measure over the ninety days to that day, stored once a day and never recomputed. The demo stores one a week. |
| 2026-11-19 | Slice 2. Standing in the portfolio is always as of today; only the count of decisions follows the period. Each group carries the address of the list that shows its uses. A use that relies on two suppliers is counted under both, and the page says so. The unit report covers a unit with every unit beneath it and is for its stewards and for those who see everything. |
| 2026-11-19 | Slice 3. A dossier is read through the same services as the pages, so it shows its maker what they may see and no more; it needs full sight of the record. The package is a zip made the same way every time: the dossier as data and as a self-contained page, the evidence files, and a manifest sealed with one hash over the file list and the place in the history. Checking a package needs no installation; checking it against the history needs the one it came from. |
| 2026-11-19 | Slice 4. A report is composed once and stored whole with the SHA-256 of its contents; there is no edit and no remake under the same reference. Its contents are left out of the history event, which carries the hash instead. Decisions and incidents are counted over the period; standing is as of the moment it was made. The demo makes one in the first week of each quarter. Found on the way: a date with no time was parsed as midnight UTC and so shown a day early in the Americas; dates are now read as local days, and a test parses every script as a module. |
