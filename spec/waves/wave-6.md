# Wave 6: Adoption (v0.6.0)

**Goal:** an organization that has never seen GovWren installs it, makes it its own, and runs it in production. Waves 1 to 5 built what a governance program does. Wave 6 is about the people who will run the software: it has to hold up at size, look like theirs, start from a program close to their own, speak to their other systems, and be simple to deploy and operate.

**Branch:** `wave-6` · **Target version:** `0.6.0` · **Status:** ☐ planned

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
