# Wave 9: Ready to show (v0.9.0)

**Goal:** a release to put in front of the governance teams who might adopt GovWren. They need to understand it as the center of their AI governance program, not as a list of features, and it should hold up to a security team's first look.

**Branch:** `wave-9` · **Target version:** `0.9.0` · **Status:** ◐ in progress

## Exit criteria

The wave is done when, on a fresh checkout:

1. An organization can fix its brand exactly in the configuration file, and see it in the app as locked.
2. A governance team can read one handbook, from first decisions to the yearly rhythm, and know how to run its AI governance program in GovWren: what to decide, how to set it up, how to shape the program to its own, what happens to a request, how things are kept current, and how the program is assured and reported. It is on the product site.
3. The code has been reviewed again for security, by reviewers who did not write it, over everything added since 0.6.0, and every confirmed finding is fixed with a test.
4. The suite passes on both databases, and the accessibility audit and keyboard check pass over every screen.

## Slices

| Slice | Name | Delivers | Status |
|---|---|---|---|
| 1 | Branding from the file | A `[branding]` section that sets every color, the logo files, and the typefaces; locked in the app | ☑ |
| 2 | The governance handbook | One guide for governance teams, from first decisions to the yearly rhythm | ☑ |
| 3 | Security review | The code read again over everything since 0.6.0; findings fixed and recorded | ☐ |
| 4 | Release prep | Changelog, site, release | ☐ |

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-19 | Planned in place of "Stable", which moved to wave 10. GovWren has no outside installations yet, so 1.0 waits until adopters have seen it and said what they need changed. |
| 2026-11-19 | Upgrades from every earlier release are not proved. Nobody runs them. The check from the previous release stays in the release routine, since it costs a minute. |
