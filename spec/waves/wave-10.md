# Wave 10: Stable (v1.0.0)

**Goal:** something an organization can build on. It proves that what exists can be relied on, and writes down what GovWren promises not to break.

This wave waits until GovWren has been shown to prospective adopters and what they ask for has been taken in. A promise made before then would constrain the changes they ask for.

**Branch:** `wave-10` · **Target version:** `1.0.0` · **Status:** ☐ planned, after adopters have seen it

## Exit criteria

The wave is done when, on a fresh checkout:

1. An installation of the release adopters first run upgrades to 1.0 on both databases with every row and file kept and the history verified, checked by script. Releases nobody installed are not carried.
2. A compatibility statement says what will not change without a major version: the API under `/api/v1`, the configuration file, the pack formats, the backup format, and the data home. It says how something is deprecated and for how long.
3. The threat table is walked by a second reviewer, and load and soak tests are run and recorded. (The code review was repeated in wave 9.)
4. The suite passes on both databases, and the accessibility audit and keyboard check pass over every screen.

## Slices

| Slice | Name | Delivers |
|---|---|---|
| 1 | Changes adopters ask for | What the first demonstrations turn up |
| 2 | Upgrades | The release adopters first run upgrades with every row and file kept, on both databases, checked by script |
| 3 | The 1.0 promise | A compatibility statement for the API, configuration file, pack formats, and data home; deprecation rules |
| 4 | Hardened | The threat table walked by a second reviewer; load and soak tests |
| 5 | Release prep | Guides, changelog, release |

## Before 1.0 is declared

These need people, and no script or review of the code can stand in for them. They were recorded as they came up and are gathered here.

| What | Why it matters | Recorded in |
|---|---|---|
| Single sign-on against a real identity provider | Every test so far uses a stand-in provider | `spec/waves/wave-2.md` |
| A person listening with a screen reader | The checks read what a screen reader is given, not whether it makes sense aloud | `spec/reviews/` |
| A penetration test of a deployed installation | The security review was a reading of the code | `spec/reviews/` |
| The compose file and the systemd unit, run on a real server | They were written and read, not run | `spec/waves/wave-6.md` |
| The assistant with a real model | It was proven with a stand-in, so the quality of what it suggests is unknown | `spec/waves/wave-7.md` |
| One organization adopting it | The adopter's guide is a plan, not experience | `docs/adopting.md` |

Version 1.0 is a promise to adopters. It should not be made until at least the first four are done.

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-19 | Wave planned at the end of wave 7, as wave 8. |
| 2026-11-19 | Moved to wave 9 when "Standards and agents" was put before it. A wave that adds nothing should come after the last one that adds something. |
| 2026-11-19 | Moved to wave 10, after adopters have seen GovWren. GovWren runs only on its developer's machines, so proving that every earlier release upgrades would protect nobody: only the path from the release adopters first install will matter. Wave 9 became 0.9.0, a release to show. |
