# Wave 6: Adoption (v0.6.0)

**Goal:** an organization that has never seen GovWren installs it, makes it its own, and runs it in production. Waves 1 to 5 built what a governance program does. Wave 6 is about the people who will run the software: it has to hold up at size, look like theirs, start from a program close to their own, speak to their other systems, and be simple to deploy and operate.

**Branch:** `wave-6` · **Target version:** `0.6.0` · **Status:** ◐ in progress

## Exit criteria

The wave is done when, on a fresh checkout:

1. With 10,000 records and many people working at once, the common pages answer within a stated time on both databases, several workers run side by side, and an installation can be backed up, restored, and moved between SQLite and PostgreSQL.
2. An organization sets a custom palette, a sign-in message and image, an email header, footer links, and its own words for key terms, and is warned when a choice fails contrast.
3. A new installation starts from a program pack for its kind of organization, with content packs for research and health settings, custom fields on records, and a framework of its own loaded as data.
4. Another system calls the API with a scoped token, receives signed webhooks, and checks a reference at a checkpoint endpoint, against a recorded API contract.
5. GovWren runs from a container image, a compose file, or a hardened systemd unit behind a documented proxy, with an operations view and `doctor --production`.
6. A security verification review and a full accessibility audit with a screen-reader check are done and their findings closed or recorded.
7. An adopter's guide takes a new organization from units and roles to its first campaign.

## Slices

| Slice | Name | Delivers |
|---|---|---|
| 1 | Production | Measured performance at 10,000 records and many people at once; several workers; backup, restore, and moving between databases |
| 2 | Brand kit | A custom palette, sign-in page message and image, email header, footer links, the organization's own terms for key words, contrast checks |
| 3 | Starter packs | Program packs for a research institute, a university, and an academic medical center; research and health content packs; custom fields; custom frameworks |
| 4 | API for others | Scoped tokens, signed webhooks, the checkpoint endpoint, a recorded API contract |
| 5 | Deployment | A container image, a compose file, a hardened systemd unit, proxy examples, the operations view, `doctor --production` |
| 6 | Security and accessibility review | The security verification review; the full accessibility audit and screen-reader check |
| 7 | Adopter's guide | Planning a rollout from units and roles to the first campaign |
| 8 | Release prep | Guides, changelog, release |

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-19 | Wave planned at the end of wave 5. Carried forward from wave 5: the inventory as it stood replays every use-case event on each request, which wants measuring at 10,000 records in slice 1. |
| 2026-11-19 | Slice 1. Measured at 10,200 use cases and 21,000 events with `scripts/perf.py`, which multiplies the demo. Three pages scored every record with two queries each; completeness now reads its facts once, and the control library reads each kind of record once. Every median is under 0.5 s on both databases. A backup is every table as JSON lines plus the files, read in one transaction; a restore reflects the target, loads in dependency order, resets PostgreSQL sequences, and verifies the chain. That one mechanism is also how an installation moves between databases. Several workers were already safe: sessions, job claims, and the chain head all live in the database. |
| 2026-11-19 | Slice 2. The brand kit is more fields on the one branding setting, so it is in the history and in a backup. Links are limited to five and to web and mail addresses. Own words cover six nouns and are applied where the web app names a kind of record or a unit: the menu, page titles, and record headers. Sentences written by the server keep the standard words, and the guide says so. A dark-mode accent may be set by hand and is checked against the dark surface; left empty it is derived as before. |
| 2026-11-19 | Slice 3. The starters are whole program packs written by `scripts/build-packs.py` from the default program, and a test fails if they drift. A content pack carries risks and controls and loads as additions: the libraries' own loaders retire nothing when a pack says it adds. Loading any program pack now keeps a vocabulary value it omits, retired, so one starter can be loaded over another. Custom fields are a setting of definitions and one JSON column on every kind of record; owners may answer them after approval because rules and tiers do not read them. Frameworks of one's own already loaded through the API and now load from the command line too. |
| 2026-11-19 | Slice 4. A token is `gw_` and 32 random bytes; only its SHA-256 is stored, and it acts as its account cut down to checkpoint, read, or write. Token requests skip the origin and CSRF checks, which guard browsers. Webhook messages are made from the history by a job with its own cursor, so nothing in the request path changes; they carry references and standing, never content. When a token was last used and how deliveries are going live in unaudited tables of their own, because the history guard rightly refuses untracked writes to audited rows. The contract test records every route and query parameter and never removes one by itself. The demo switches its webhook job off. |
| 2026-11-19 | Slice 5. The image is built with uv and runs as uid 10001 on a read-only root with every capability dropped; it was built and run that way here, through a restart. Its entrypoint runs `init` every time, which is safe to repeat, and creates the first administrator from the environment once. `doctor --production` adds nine checks; only a non-https address and a demo are failures, the rest are things to decide. `govwren backup` notes itself in the data home so that the check can say how old the last one is. The compose file and the systemd unit were written but not run here. |
| 2026-11-19 | Slice 6. A second reviewer read the code cold and found nine things, one of them serious and in every release since 0.2.0: a file could be attached, and so read, by its number. All nine are fixed, each with a test that fails without the fix, and the changelog says so under Security. A new keyboard check walks every scene by Tab and reads the accessibility tree; it found two real faults on its first run, both fixed. The record, including what was not done (an outside penetration test, a person listening with a screen reader), is in `spec/reviews/`. |
| 2026-11-19 | Slice 7. The adopter's guide is a plan with a timeline, not a manual: what to settle before installing, then stand it up, make the program yours, pilot with two units, open the door, and run the first campaign. It says what to leave for later and what GovWren will not do. Its timings are a reasoned estimate, not experience: no organization has adopted GovWren yet. |
