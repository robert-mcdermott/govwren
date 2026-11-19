# Security and accessibility review, November 2026

Done in wave 6, before version 0.6.0, against the code on the `wave-6` branch.

This is a record of what was looked at, how, what was found, and what was done about it. It also says plainly what was not done, so that nobody reads more into it than is there.

## Security

### How it was done

A reviewer who had taken no part in writing the code read it with one brief: find concrete weaknesses, confirm each in the code path, and report nothing speculative. The areas were those of a standard application security verification checklist:

- Authentication and password storage
- Session management and cookies
- Request forgery and the origin of requests
- Access control, including reaching a record by a side route
- Injection: SQL, HTML and script, headers, and spreadsheet formulas in exports
- File upload and download
- Requests the server makes: webhooks and the identity provider
- Redirects after sign-in
- Secrets, tokens, and what is logged
- Archives: backup and restore
- Limits on sign-in attempts
- Security headers and the content security policy
- The demo's sign-in

The first three findings were reproduced against a running application. The rest were confirmed by reading.

### What was found, and what was done

| # | Finding | Severity | Since | Fix |
|---|---|---|---|---|
| 1 | Any signed-in person could attach, and so download, a file someone else had uploaded, by sending its number. Numbers run in sequence | High | 0.2.0 | A file may be attached only by whoever sent it, or by someone who can already open evidence that holds it. Who sent each file is now recorded |
| 2 | The address to go to after sign-in accepted a backslash or a control character, which a browser can read as another site | Medium | 0.1.0 | Both checks, in the page and on the server, refuse them, and the page compares the resolved origin |
| 3 | The checkpoint gave the name of a record the asker could not see, and answered for other people's drafts | Medium | this wave | The name is given only to someone who may see the record. Someone else's draft answers 404 |
| 4 | Five wrong passwords for an account locked it for everyone, so a colleague's address was enough to lock them out. Behind a container's proxy, every person shared one address | Medium | 0.1.0 | The limit of five is now for one account from one address. The account alone and the address alone have a limit of thirty. Attempts are counted before the password is checked. Which proxies are believed is a setting |
| 5 | A single sign-on answer was not tied to the browser that began it, so a finished sign-in could be handed to someone else | Low to medium | 0.2.0 | Starting sets a short-lived cookie holding a hash of the state, and the answer is taken only with it |
| 6 | A write token could set a password on an account that had none, turning a token into a way to sign in | Low | this wave | A token cannot change a password |
| 7 | A webhook delivery followed redirects and could be pointed at the server's own network | Low | this wave | Redirects are not followed, and a receiver must resolve to an address on the public internet |
| 8 | A backup file was created readable by other accounts on the machine | Low | this wave | It is created for its owner only |
| 9 | A request body was read whole before its size was checked | Informational | 0.2.0 | A request that declares more than 32 MB is refused before it is read |

Each fix has a test that fails without it.

### Looked at and found sound

Password storage and comparison. Session tokens, their expiry, and their cookies. The forgery token and the origin check. The scopes of API tokens. The policy table, which refuses any route it does not list. The checks each service makes before showing a record, across the dossier, past dates, history, the graph, findings, search, and export. Verification of the identity provider's tokens. Database access, which goes through the ORM throughout. Escaping in the pages the server writes. The web app, which never writes markup from data. The content security policy. Downloads, which are sent as attachments and sandboxed. The cleaning of uploaded SVG. Formula characters in CSV exports. Path containment in restore and in static files. The demo's sign-in.

### Left as it is, on purpose

- **The API description is public.** `/api/openapi.json` needs no sign-in. It describes the routes and holds nothing about an installation.
- **API tokens survive a password change.** A token is revoked by its owner or an administrator. Revoking them when a password changes would surprise the scripts that depend on them.
- **A request with no declared length is not capped by GovWren.** The reverse proxy caps it, and the deployment examples set that cap.

### What this was not

It was a review of the code by one reviewer. It was not a penetration test of a deployed installation, and no outside firm has examined GovWren. An organization with its own security team should have that team look before it relies on GovWren for anything sensitive.

## Accessibility

### How it was done

Three checks, each run over every screen of the demo organization: 109 scenes, as nine different people.

| Check | What it does | Result |
|---|---|---|
| `scripts/a11y-audit.mjs` | Names on controls, labels on fields, headings, landmarks, duplicate ids, target sizes, and the contrast of every piece of text, in three palettes, by day and after dark | No findings |
| `scripts/keyboard-check.mjs`, the keyboard | Tabs through every page from the top: the skip link comes first, every stop is visible and shows where focus is, every control is reached. In a dialog, focus starts inside and stays inside, Escape closes it, and focus returns | No findings, over 8,329 stops |
| `scripts/keyboard-check.mjs`, assistive technology | Reads each page as a screen reader is given it: one main landmark, one main heading, a role and a name on every control, headers on every table | No findings |

The keyboard check is new in this wave. Its first run found two things, both fixed:

| Finding | Fix |
|---|---|
| A record in the dependency graph showed nothing when the keyboard reached it | It now shows a focus ring like any other link |
| A dialog whose last control was a group of choices let focus escape to the page behind | Focus that leaves an open dialog is brought back, whatever its last control is |

### What this was not

No person has yet listened to GovWren with a screen reader. The third check reads what a screen reader is given, which catches missing names and structure, but not whether a page makes sense when heard. That session, with VoiceOver and NVDA on the main journeys, is still to be done by a person and is on the list for the adopter who goes first.
