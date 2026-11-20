# Wave 9: Stable (v1.0.0)

**Goal:** something an organization can build on. Waves 1 to 8 built the product. Wave 9 adds nothing to it. It proves that what exists can be relied on, and writes down what GovWren promises not to break.

**Branch:** `wave-9` · **Target version:** `1.0.0` · **Status:** ☐ planned

## Exit criteria

The wave is done when, on a fresh checkout:

1. A script builds an installation with every earlier release, upgrades each to the current one on both databases, and checks that every row and file is kept and the history verifies.
2. A compatibility statement says what will not change without a major version: the API under `/api/v1`, the configuration file, the pack formats, the backup format, and the data home. It says how something is deprecated and for how long.
3. The security review is repeated over everything added since the first, the threat table is walked by a second reviewer, and load and soak tests are run and recorded.
4. The suite passes on both databases, and the accessibility audit and keyboard check pass over every screen.

## Slices

| Slice | Name | Delivers |
|---|---|---|
| 1 | Upgrades | An installation of every earlier release upgrades with every row and file kept, on both databases, checked by script |
| 2 | The 1.0 promise | A compatibility statement for the API, configuration file, pack formats, and data home; deprecation rules |
| 3 | Hardened | The security review repeated; the threat table walked by a second reviewer; load and soak tests |
| 4 | Release prep | Guides, changelog, release |

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
