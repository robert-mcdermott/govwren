# Security

GovWren holds an organization's record of what AI it uses, what was decided about it, and why. That record includes assessments of weaknesses, incident reports, and vendor terms. This document sets out what is protected, from whom, the controls for each threat, and who may do what.

## What is being protected

| Asset | Why it matters |
|---|---|
| **The history** | Its value is that it cannot be quietly changed. A decision record that can be edited is worth nothing to an auditor |
| **Reviews, findings, and incidents** | They describe weaknesses, disagreements, and things that went wrong |
| **Evidence files** | Contracts, security reports, assessments; some confidential by their own terms |
| **Accounts and sessions** | Whoever holds a governance session can approve |
| **Program configuration** | Changing a rule changes what gets approved without review |
| **Availability** | A front door that is down sends people around it |

GovWren is designed **not** to hold the sensitive data that AI is used on. Records describe data; they never contain it. Forms say so where free text is requested, and evidence uploads carry a data class so that anything sensitive is at least labelled and access-limited.

## Who might attack, and how they get in

| Actor | Route |
|---|---|
| Someone outside, without an account | The sign-in page, the single sign-on callback, anything public |
| A signed-in member | Trying to read others' records, approve their own request, or reach admin functions |
| A reviewer or steward | Reaching beyond their function or unit |
| Another website open in a user's browser | Cross-site requests riding the user's session |
| Content a user submitted | Script or markup in a form answer, a comment, a file name, or an uploaded SVG or HTML file |
| Someone with access to the database or disk | Editing history or reading files directly |
| A compromised or careless integration | A leaked API token or webhook secret |

## Controls, by threat

### Sign-in and sessions

- Sign-in is always required; there is no anonymous mode.
- Passwords are hashed with scrypt from the standard library, with parameters stored beside each hash so the cost can be raised later. Rules follow current guidance: a minimum length of 12, no composition rules, no forced rotation.
- Sign-in is throttled per account and per address, with the counters in the database so the limit holds across workers. Unknown accounts take the same time as known ones.
- Sessions are opaque random tokens in an `HttpOnly`, `SameSite=Strict`, `Secure` cookie. Only a hash is stored. Sessions expire after a period idle and after a maximum age, and are revoked on sign-out, password change, and account disablement.
- The last active administrator can never be removed or demoted, locally or through the identity provider.

### Single sign-on

- OpenID Connect authorization-code flow with PKCE, `state`, and `nonce`. Sign-in state is stored server-side, single-use, short-lived, and tied to the browser that began it.
- The ID token's signature, issuer, audience, expiry, and nonce are all verified before a session is created.
- The client secret is read from the environment and never written to the configuration file or the database.
- Roles mapped from the provider are replaced at each sign-in, so removing someone from a group removes their access at their next sign-in. Disabling them at the provider prevents new sessions; a short maximum session age bounds the old one.

### Authorization

- **One policy table.** Every API route names the permission it requires. A route missing from the table is refused, and a test fails if any route lacks an entry.
- **Checked again in the service.** Service functions take the acting principal and check both the permission and the record: scope, ownership, and visibility. The API cannot reach data by skipping a check, because the check is where the data is.
- **A role-by-route matrix test** signs in as each role and exercises every route, asserting the expected outcome.
- **Separation of duties.** Nobody decides a review of a request they submitted or own, whatever their role. Nobody completes a review task on their own request. Nobody approves their own exception. An override of a tier on one's own request is refused.

### Cross-site requests and content

- Every state-changing request needs a per-session CSRF token in a header, and requests whose origin does not match the host are refused.
- The content security policy is `default-src 'self'` with no inline script or style and no third-party origins. Frames are denied.
- The front end inserts data only as text nodes. No user-supplied value is ever parsed as HTML. Comments and descriptions support a small, safe formatting subset rendered by the app's own code.
- The generated theme stylesheet is built only from values that have passed strict validation.

### Files

- Uploads have a size limit and an allowlist of types, checked by content, not by name.
- Files are stored by hash outside any served directory and are only ever returned through a route that checks access to something the file is attached to.
- Downloads are always sent as attachments with a restrictive content security policy, so an uploaded HTML or SVG file cannot run in the app's origin.
- Uploaded logos are sanitized and served from a route with its own locked-down policy.

### The history

- Events are append-only in the application, and triggers in the database refuse updates and deletes on the event table. `govwren doctor` reports a missing trigger.
- Each event is hashed together with the previous event's hash. `govwren verify` recomputes the chain and reports the first break. The latest hash can be exported on a schedule and kept elsewhere, so that even rewriting the whole chain is detectable.
- Reading sensitive things is recorded too: evidence downloads, exports, and views of incident records are events.

### Integrations (wave 6 and later)

- API tokens are scoped to a role and optionally to read-only, shown once, stored as hashes, and expire.
- Webhooks are signed, sent only to addresses an administrator registered, and carry references rather than record contents by default.
- The optional tool server for AI assistants acts as a named account with that account's permissions and can only draft; every change waits for a person to confirm.

### Operations

- Secrets come only from the environment.
- No request bodies, form answers, or tokens are written to logs.
- `govwren doctor --production` checks the things that matter before going live: TLS in front, secure cookies in effect, a current schema, a recent backup, mail and single sign-on reachable, and no default or demo accounts present.
- The demo organization is built only by an explicit command into its own data home, marks itself as a demo on every page, and its server refuses to listen on anything but the local machine unless told otherwise.

## Who can see and do what

### Visibility

Research organizations vary in how open they want the inventory to be, so visibility for ordinary members is a setting with three levels:

| Setting | A member sees |
|---|---|
| **Open** | Every approved use case, in full |
| **Summary** (default) | Every approved use case's name, unit, purpose, tier, and systems, so people can find colleagues doing similar work; full detail only for their own units |
| **Unit** | Only the records of their own units |

Whatever the setting, the catalog is visible to everyone, and reviews, findings, internal discussion, incidents, risks, and evidence are visible only to those with a role in them. A record can be marked **restricted**, which limits even its existence to its owners, its unit's stewards, governance, and auditors.

### Permissions

| Capability | Member | Owner of the record | Steward (in scope) | Reviewer (assigned function) | Governance | Auditor | Admin |
|---|---|---|---|---|---|---|---|
| Browse the catalog; register a use; submit a request | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Edit a record | | ✓ | ✓ | | ✓ | | ✓ |
| Read a review's findings and internal discussion | | | | ✓ | ✓ | ✓ | ✓ |
| Complete a review task | | | | ✓ | ✓ | | |
| Override a tier, adjust a route | | | | ✓ (their task's review) | ✓ | | |
| Decide a review | | | | | ✓ (as the rules name) | | |
| Close a condition | | ✓ (propose) | ✓ (propose) | | ✓ | | |
| Respond to an attestation | | ✓ | ✓ (unit) | | ✓ | | |
| Report an incident | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Manage incidents, exceptions, and campaigns | | | | | ✓ | | |
| Manage risks, controls, frameworks, and policies | | | | | ✓ | | |
| Read everything, including the full history; export | | | | | ✓ | ✓ | ✓ |
| Edit forms, scoring, rules, and vocabularies | | | | | ✓ | | ✓ |
| Manage accounts, roles, units, branding, and system settings | | | | | | | ✓ |

Decision authority is narrower than the governance role: the rules name who may decide each tier, and a decision by anyone else is refused. Named risk acceptance can only be given by the person named.

## Review

- **Each wave:** the role-by-route matrix, the web safety tests (no inline script or style, no third-party origins, no HTML parsing of data), and dependency review are part of the definition of done.
- **Wave 6:** a full review against the OWASP Application Security Verification Standard, level 1, with findings and their resolution recorded in this document.
- **Before 1.0:** the review is repeated, and a second person who did not write the code walks the threat table above.

Vulnerabilities are reported privately as described in `SECURITY.md`.
