# API

Everything the web app does, it does through GovWren's JSON API. You can use the same API to connect another system. This guide covers the conventions and the main routes. The exact shape of every request and response is in the OpenAPI document.

## The basics

| | |
|---|---|
| Base path | `/api/v1` |
| Format | JSON in, JSON out |
| Sign-in | A session cookie, set by `POST /api/v1/session` |
| Changes | Need the `X-CSRF-Token` header |
| Success | `{"data": …, "meta": …}` |
| Errors | A problem document, `application/problem+json` |
| OpenAPI | [`docs/openapi.json`](openapi.json) in the repository, and `/api/openapi.json` on a running server |

The API is not cached: every API response carries `Cache-Control: no-store`. The server does not serve interactive API documentation pages. Load the OpenAPI document into a viewer of your choice.

This release has no API keys or tokens for other systems. A script signs in as an account, as shown below, and can do exactly what that account's roles allow. Give a script its own account with the least it needs.

## Sign in

Send an email address and password. The answer sets the session cookie, `govwren_session`, and returns who you are, your roles, and a CSRF token.

```bash
curl -s -c cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"email": "you@example.org", "password": "your password"}' \
  http://127.0.0.1:8000/api/v1/session
```

```json
{
  "data": {
    "account": {"id": 1, "name": "Your Name", "email": "you@example.org"},
    "roles": ["governance", "member"],
    "permissions": {"admin": false, "govern": true, "configure": true, "read_all": true,
                    "edit_all": true, "review": true, "steward": false},
    "steward_units": [],
    "member_units": [],
    "has_password": true,
    "csrf_token": "…"
  },
  "meta": {}
}
```

- The cookie is `HttpOnly` and `SameSite=Strict`, and `Secure` when the request arrived over HTTPS.
- A session ends after 12 hours without activity and after 7 days in any case, unless [configured](configuration.md#server) otherwise.
- A wrong email address or password answers 401. After five failures in fifteen minutes, sign-in answers 429 for a while.
- `GET /api/v1/session` returns the same document for the current session, or 401 if nobody is signed in. Use it to fetch the CSRF token again.
- `DELETE /api/v1/session` signs out. It needs no CSRF token.

## Send the CSRF token with every change

Every request that is not a `GET`, `HEAD`, or `OPTIONS` must carry the session's CSRF token in the `X-CSRF-Token` header. Without it the answer is 403. Signing in and signing out are the exceptions.

```bash
curl -s -b cookies.txt \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-Token: THE_TOKEN' \
  -d '{"name": "Brightfen Labs"}' \
  http://127.0.0.1:8000/api/v1/vendors
```

GovWren also refuses changes that come from another site in a browser: a request whose `Origin` header does not match the host it was sent to, or that the browser marks as cross-site, answers 403. A command-line client sends no `Origin` header and is not affected.

## Responses

Every successful answer is an envelope with two keys:

```json
{"data": {"ref": "VND-0041", "name": "Brightfen Labs", "status": "prospective", "version": 1},
 "meta": {}}
```

`data` is the thing you asked for: an object or a list. `meta` holds facts about the answer, such as paging. It is an empty object when there is nothing to say. The example is shortened; a real record has more fields.

A route that creates a record answers 201. Records are named by their permanent reference, such as `UC-0142`, `SYS-0007`, `VND-0041`, or `RV-0087`, not by a numeric id. People and units are named by numeric id.

## Errors

Every error is a problem document with the media type `application/problem+json`.

```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "The request is missing its CSRF token. Reload the page.",
  "instance": "/api/v1/vendors"
}
```

When particular fields are at fault, an `errors` list says which:

```json
{
  "type": "about:blank",
  "status": 422,
  "detail": "The decision was not recorded.",
  "instance": "/api/v1/reviews/RV-0087/decision",
  "errors": [
    {"location": ["rationale"], "message": "Give the reason for the decision. It is shown to the requester."}
  ]
}
```

(The `title` is left out of this example.) `detail` and `message` are written to be shown to a person.

| Status | Meaning |
|---|---|
| 400 | The request could not be carried out |
| 401 | Nobody is signed in, or the sign-in failed |
| 403 | Your role does not allow this; or the CSRF token is missing; or the request came from another site |
| 404 | There is no such record, or you may not see it |
| 409 | A conflict: someone else changed the record, or the action no longer applies, such as deciding a review that is already decided |
| 422 | The request is not valid. See `errors` |
| 429 | Too many failed sign-ins |
| 500 | An unexpected error |
| 503 | The database is unavailable |

A record you are not allowed to see answers 404, the same as one that does not exist.

## Lists: filter, sort, and page

The three inventory lists, `/use-cases`, `/systems`, and `/vendors`, share one set of conventions.

| Parameter | Meaning |
|---|---|
| `q` | Words to look for in the name, reference, and summary |
| `sort` | A field to sort by. Put `-` in front for descending. The default is `-updated_at` |
| `limit` | How many to return, from 1 to 200. The default is 50 |
| `cursor` | Where to continue from. Use the value a previous answer gave you |

| List | Filters | Sort fields |
|---|---|---|
| `/use-cases` | `unit`, `status`, `tier`, `domain`, `stage`, `data_class`, `owner`, `mine` | `updated_at`, `name`, `ref`, `tier`, `status`, `stage` |
| `/systems` | `unit`, `status`, `kind`, `catalog_status`, `vendor`, `owner`, `mine` | `updated_at`, `name`, `ref`, `catalog_status`, `kind` |
| `/vendors` | `status` | `updated_at`, `name`, `ref`, `status` |

- `unit` and `owner` take numeric ids. `unit` includes every unit beneath the one named.
- `vendor` takes a vendor's reference. `tier` takes a level from 1 to 4.
- `mine=true` keeps the records you own.
- On `/use-cases`, `status=live` means approved, with or without conditions.
- Other values are the keys of the vocabularies, from `GET /api/v1/vocabularies`.

The answer's `meta` describes the page:

```json
{"data": [ … ],
 "meta": {"total": 300, "offset": 0, "limit": 50, "next_cursor": "eyJvZmZzZXQiOjUwfQ", "prev_cursor": null}}
```

Pass `next_cursor` back as `cursor` to get the next page. It is `null` on the last page. Treat a cursor as opaque.

A list shows only what you may see. Someone who sees only a summary of a use case gets fewer fields for it, and a `sight` of `summary`.

Other lists are short and are returned whole: `/catalog` (takes `q`), `/accounts` (takes `q` and `status`), `/units`, and `/reviews` (takes `scope=open` or `scope=all`).

## Change a record safely

To change a use case, AI system, or vendor, send a `PATCH` with only the fields that change and the `version` you were looking at.

```bash
curl -s -b cookies.txt -X PATCH \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-Token: THE_TOKEN' \
  -d '{"version": 1, "website": "https://brightfen.example"}' \
  http://127.0.0.1:8000/api/v1/vendors/VND-0041
```

If someone else has saved the record since, the answer is 409 and nothing is changed. Fetch the record again, and repeat your change with the new `version`. Every change is written to the history against the account that made it.

## Routes

"Who" is the least a caller needs. Many routes check again against the record itself: its unit, its owners, and its visibility. The server checks every route against one policy table, and a route with no entry in it is refused.

### System and session

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/health/live` | Anyone | Is the server process running? |
| GET | `/health/ready` | Anyone | Can the server do its work? 503 if not |
| GET | `/meta` | Anyone | The product's name, version, and branding |
| GET | `/session` | Anyone | Who is signed in, or 401 |
| POST | `/session` | Anyone | Sign in |
| DELETE | `/session` | Anyone | Sign out |
| POST | `/session/demo` | Anyone | Sign in as a sample person. Answers 404 unless this is a demo |
| POST | `/session/password` | Signed in | Change your own password |

### People and units

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/accounts` | Signed in | Find people. Members get a short card for each: name, address, title, and status |
| POST | `/accounts` | Admin | Add a person |
| GET | `/accounts/{account_id}` | Signed in | One person |
| PATCH | `/accounts/{account_id}` | Signed in | Change your own details; an admin may change anyone's |
| PUT | `/accounts/{account_id}/roles` | Admin | Set a person's roles |
| PUT | `/accounts/{account_id}/units` | Admin | Set the units a person works in |
| POST | `/accounts/{account_id}/password` | Admin | Give a person a new password |
| GET | `/roles` | Signed in | The roles and what each allows |
| GET | `/units` | Signed in | The units, as a list and as a tree |
| POST | `/units` | Admin | Add a unit |
| GET | `/units/{unit_id}` | Signed in | One unit, with the units above it |
| PATCH | `/units/{unit_id}` | Admin | Rename, move, or close a unit |
| POST | `/imports/units` | Admin | Import units from CSV |
| POST | `/imports/people` | Admin | Import people from CSV |

The import routes take the CSV file itself as the request body, not JSON. They run dry by default: add `?dry_run=false` to apply. The answer reports rows created, updated, and unchanged, and every problem by row.

### Inventory

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/vocabularies` | Signed in | The lists of values records choose from |
| GET | `/use-cases`, `/systems`, `/vendors` | Signed in | Find records |
| POST | `/use-cases`, `/systems`, `/vendors` | Signed in | Add a record. A use case starts as a draft |
| GET | `/use-cases/{ref}`, `/systems/{ref}`, `/vendors/{ref}` | Signed in | One record |
| PATCH | `/use-cases/{ref}`, `/systems/{ref}`, `/vendors/{ref}` | Signed in | Change a record. Catalog and vendor standing need governance or an admin |
| PUT | `/use-cases/{ref}/owners`, `/systems/{ref}/owners` | Signed in | Set a record's owners |
| PUT | `/use-cases/{ref}/systems` | Signed in | Set the AI systems a use case uses |
| GET | `/use-cases/{ref}/history`, `/systems/{ref}/history`, `/vendors/{ref}/history` | Signed in | Everything that has happened to a record |
| GET | `/admin/inventory` | Governance or admin | How much of the inventory everyone can see |
| PUT | `/admin/inventory` | Governance or admin | Change it. Send `{"visibility": "open"}`, `"summary"`, or `"unit"` |

### Catalog and requests

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/catalog` | Signed in | The AI systems the organization has evaluated |
| POST | `/catalog/{ref}/register` | Signed in | Register a use. Approved at once if it fits; otherwise a request is begun |
| GET | `/intake` | Signed in | The request form, scoring model, and routing rules in force |
| POST | `/intake` | Signed in | Begin a request. Needs what it is for and which unit |
| GET | `/use-cases/{ref}/intake` | Signed in | A request's form and answers |
| PUT | `/use-cases/{ref}/intake` | Signed in | Save a draft's answers. Nothing needs to be complete |
| POST | `/use-cases/{ref}/submit` | Signed in | Submit a request, and work out its tier |
| GET | `/use-cases/{ref}/tier` | Signed in | Why a use case has the tier it has |
| POST | `/use-cases/{ref}/tier` | Reviewer or governance | Change a tier, with a reason |

`POST /catalog/{ref}/register` answers `{"registered": true, "ref": …}` when the use was approved, and `{"registered": false, "reason": …, "ref": …}` when a request was begun instead.

### Reviews, decisions, and conditions

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/me/work` | Signed in | What is waiting on you |
| GET | `/notifications` | Signed in | Your notices |
| POST | `/notifications/read` | Signed in | Mark notices as read |
| GET | `/reviews` | Signed in | Reviews you have a part in |
| GET | `/reviews/{ref}` | Signed in | One review: the decision packet |
| GET | `/use-cases/{ref}/review` | Signed in | The latest review of a use case |
| POST | `/reviews/{ref}/triage` | Governance | Confirm or adjust the reviews required, and start them |
| POST | `/reviews/{ref}/tasks/{task_id}/claim` | Reviewer or governance | Take a review task |
| POST | `/reviews/{ref}/tasks/{task_id}/assign` | Governance | Give a review task to someone |
| POST | `/reviews/{ref}/tasks/{task_id}/complete` | Reviewer or governance | Record a finding: `no_concerns`, `conditions`, or `objection` |
| POST | `/reviews/{ref}/comments` | Signed in | Add to the discussion. `visibility` is `internal` or `requester` |
| POST | `/reviews/{ref}/decision` | Governance | Decide: `approved`, `declined`, or `returned`, with a `rationale` |
| POST | `/reviews/{ref}/withdraw` | Signed in | Take a request back. For the requester or governance |
| POST | `/conditions/{condition_id}/close` | Signed in | Mark a condition `met`, or waive it, with a `note` |

What a review returns depends on who asks. The requester never receives findings, reviewers' notes, or internal comments.

### Dashboard and branding

| Method | Path | Who | What it does |
|---|---|---|---|
| GET | `/dashboard` | Governance, auditor, or admin | Where the program stands |
| GET | `/admin/branding` | Admin | The branding, for editing |
| PUT | `/admin/branding` | Admin | Change the product name, palette, and accent |
| POST | `/admin/branding/check` | Admin | How an accent color would read, before saving it |
| POST | `/admin/branding/images/{kind}` | Admin | Upload a logo or tab icon. The image is the request body |
| DELETE | `/admin/branding/images/{kind}` | Admin | Remove a logo or tab icon |

`kind` is `logo-light`, `logo-dark`, or `favicon`.

## A worked example

This signs in, reads the catalog, and lists approved Critical-tier use cases. It uses `jq` to read the JSON.

```bash
BASE=http://127.0.0.1:8000/api/v1

# Sign in, keep the cookie, and take the CSRF token from the answer.
TOKEN=$(curl -s -c cookies.txt -H 'Content-Type: application/json' \
  -d '{"email": "you@example.org", "password": "your password"}' \
  "$BASE/session" | jq -r '.data.csrf_token')

# Read: which tools are approved, and for what data?
curl -s -b cookies.txt "$BASE/catalog" \
  | jq '.data[] | select(.usable) | {ref, name, edition, permitted_data_class}'

# Read a list with filters, sorting, and paging.
curl -s -b cookies.txt "$BASE/use-cases?status=live&tier=4&sort=name&limit=20" \
  | jq '{total: .meta.total, names: [.data[].name]}'

# Change: add a vendor. Changes need the token.
curl -s -b cookies.txt -H 'Content-Type: application/json' -H "X-CSRF-Token: $TOKEN" \
  -d '{"name": "Brightfen Labs", "website": "https://brightfen.example"}' \
  "$BASE/vendors" | jq '.data.ref'

# Sign out.
curl -s -b cookies.txt -X DELETE "$BASE/session"
```

To try this against the [demo organization](getting-started.md#explore-the-demo-organization), use port 8010 and sign in without a password, from the machine the demo runs on:

```bash
curl -s -c cookies.txt -H 'Content-Type: application/json' \
  -d '{"email": "SAMPLE_PERSON_EMAIL"}' \
  http://127.0.0.1:8010/api/v1/session/demo
```

The sample people and their addresses are listed under `demo.accounts` in `GET /api/v1/meta`.

## Stability

Before version 1.0, a release may change the API. Breaking changes are listed in the [changelog](../CHANGELOG.md).
