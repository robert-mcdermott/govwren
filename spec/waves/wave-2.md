# Wave 2: System of record (v0.2.0)

**Goal:** make the inventory complete enough to rely on and the program editable by the people who run it, and let people sign in with the identity they already have. Wave 1 proved that a request can be taken in, tiered, reviewed, and decided. Wave 2 turns what was decided into a connected record of what the organization actually runs: use cases, systems, models, agents, datasets, and vendors, linked to one another, findable, and exportable.

**Branch:** `wave-2` · **Target version:** `0.2.0` · **Status:** ◐ in progress (slices 1 and 2 of 9 done)

## Exit criteria

The wave is done when, on a fresh checkout:

1. A person signs in through an OpenID Connect provider. Their account is created at first sign-in, and their roles, unit scopes, and review functions follow the groups or application roles the provider sends. Local accounts keep working, and the last administrator cannot be locked out by a mapping (PLT-10, PLT-11).
2. Models, datasets, and agents are records like any other, with owners, history, and detail pages. A model the organization runs or fine-tuned itself records where its weights came from, their checksum and license, where it runs, and its base model, and is shown as at least as sensitive as the data it was trained on (INV-05, INV-06, INV-18).
3. A reviewed model has a catalog standing and a permitted data class, and a use of one registers as quickly as a use of an approved tool (INV-19).
4. Vendor agreements carry kind, dates, and notice periods, and records point to protocols, grants, and tickets in other systems (INV-09, INV-10).
5. Any record shows what it depends on and what depends on it, as a list and as a graph that can be read without a mouse (INV-07).
6. Files are stored once by their content, and evidence items have owners and expiry dates (ASR-01, INT-09).
7. One search finds any record a person may see; lists can be saved as views; each record shows what is missing; likely duplicates are suggested and can be merged (INV-11 to INV-13, INV-15).
8. A spreadsheet of existing records imports through a mapping step with a dry run; every list exports as CSV and JSON (INV-14, RPT-02).
9. Governance edits the intake form, the scoring model, the routing rules, the vocabularies, and the condition templates in the app, sees what a change would have done to past requests before publishing it, and every published version is kept (INT-07, TIR-09, PLT-16, FDR-05, FDR-06).
10. Notices are also sent by email, as they happen or as a digest, according to each person's preference (PLT-13).
11. The demo organization shows all of the above with data, the suite passes on both databases, and the accessibility audit passes over every new screen.

## Decisions taken

- **Single sign-on is tested against a provider that runs inside the test suite**, speaking real OpenID Connect over HTTP with signed tokens. Nothing in the suite or the demo reaches a real identity provider. A guide explains the settings for Microsoft Entra ID.
- **No new runtime dependency for tokens.** Token signatures are verified with the cryptography primitives already available through the standard library where possible; if RSA verification needs a package, it gets a decision record.
- **The graph is drawn by GovWren's own code** as SVG, with the same data available as a list. No charting or graph library is added.
- **Email is plain SMTP** from the standard library. Nothing is sent unless SMTP is configured.

---

## Slice 1: Single sign-on ☑

**Goal:** people sign in with the identity they already have.

- [x] Settings in `govwren.toml`: issuer, client id, the name of the environment variable holding the client secret, scopes, the claim that carries groups or roles
- [x] Discovery, the authorization code flow with PKCE, state and nonce, token verification (signature, issuer, audience, expiry, nonce)
- [x] Accounts created or matched at first sign-in by a stable subject, never by an unverified email address
- [x] Mapping in the app: a group or application role to a role, a unit scope, or a review function; applied at every sign-in; shown on the account as *from the identity provider*
- [x] The last active administrator is never removed by a mapping
- [x] The sign-in page offers single sign-on first when it is configured; local sign-in can be turned off except for a break-glass administrator
- [x] A provider that runs inside the tests; a guide for Microsoft Entra ID

**Acceptance:** a full sign-in round trip passes in the suite on both databases; a tampered, expired, or wrong-audience token is refused; changing a person's groups changes their roles at next sign-in.

## Slice 2: Models, datasets, and agents ☑

**Goal:** the inventory covers what AI is made of, not only where it is used.

- [x] Model records: kind, provider or origin, version, modality, license, intended use, limitations, evaluation summary (the model card), base model and lineage
- [x] Locally run and in-house fine-tuned models: weights source and checksum, format, license restrictions, where it runs, training datasets, and sensitivity inherited from them
- [x] Models in the catalog with standing and permitted data class; registering a use of one
- [x] Dataset records: classification, identifiability, source, terms, steward
- [x] Agent profiles on systems that act: autonomy, actions, tools, identity, reversibility, human override, limits
- [x] Vendor agreements with kind, dates, notice period; external references on every record
- [x] Intake: questions about the model behind a use, shown when they apply (INT-11)

**Acceptance:** a fine-tune of an open-weight model on a restricted dataset shows as restricted wherever it appears; the demo has commercial, open-weight, and in-house models with lineage.

## Slice 3: Links and the graph ☐

**Goal:** see what depends on what.

- [ ] Typed links between records, with the allowed relations per pair of types
- [ ] *Depends on* and *used by* on every record page
- [ ] A focused graph around a record, drawn as SVG, keyboard reachable, with the list as its equal

**Acceptance:** from a model, every use case that depends on it is one click away, through any number of systems.

## Slice 4: Evidence and files ☐

**Goal:** keep the documents that decisions rest on.

- [ ] Content-addressed file storage in the data home, with type sniffing and size limits
- [ ] Evidence items with a kind, an owner, a date, an expiry, and the records they support
- [ ] Attachments on intake answers, review findings, and conditions

**Acceptance:** the same file uploaded twice is stored once; a file's checksum is in the history.

## Slice 5: Find and tidy ☐

**Goal:** an inventory people can find things in and keep clean.

- [ ] One search across every record type, limited to what the searcher may see
- [ ] Saved views
- [ ] Completeness: what each record is missing, and completeness by type and unit
- [ ] Possible duplicates, and merging that keeps both references resolvable

## Slice 6: Import and export ☐

**Goal:** get existing records in, and anything out.

- [ ] Spreadsheet import with column mapping and a dry run that reports every problem first
- [ ] CSV and JSON export of every list, respecting what the person may see
- [ ] Program packs cover everything governance can edit

## Slice 7: Program editors ☐

**Goal:** governance changes its own program without a developer.

- [ ] Form builder with preview
- [ ] Scoring model and routing rules editors, with a preview of what a change would have done to past requests
- [ ] Vocabularies and condition templates
- [ ] Requests to evaluate a tool that is not in the catalog

## Slice 8: Email ☐

**Goal:** notices reach people where they already are.

- [ ] SMTP delivery, with an outbox that survives restarts
- [ ] Immediate notices and a daily digest; per-person preferences
- [ ] Plain-text and HTML bodies that carry the organization's name

## Slice 9: Release prep ☐

- [ ] Guides updated; the Entra ID guide; changelog; dependency review
- [ ] The demo extended to everything in the wave; the accessibility audit over every new screen
- [ ] Release

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-19 | Wave planned at the end of wave 1 |
| 2026-11-19 | Slice 2: models and datasets are *described* records. Their fields are listed once, and the same list checks what is saved, shapes the API, and tells the web app what to draw, so a record type added in a later wave needs no new form or page. Typed links arrived here and not in slice 3, because lineage and inherited sensitivity need them; slice 3 adds the graph. Membership of the default form changed (pack 1.2.0): existing installations keep their form until governance loads the new pack |
| 2026-11-19 | Slice 1: RSA signatures are verified with integer arithmetic and the standard library's SHA-256, because verification needs only the public key; no cryptography package was added. The session cookie stays `SameSite=Strict`: the callback answers with a page that sends the browser on, since a redirect arriving by way of the provider would be followed without the cookie. Membership of a unit is added by a mapping and never removed, because the membership table does not record where a membership came from |
