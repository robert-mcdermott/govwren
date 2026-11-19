# Running the program

This guide is for governance leads and administrators. It covers who can do what, how to describe your organization, how to build the catalog, how tiers and routing work, how to change them, and how to read the dashboard and the history.

Two roles share this work. **Administrators** manage people, units, and appearance. **Governance** runs the program: the catalog, triage, and decisions. One person can hold both.

## Roles and scopes

Everyone who can sign in is a member. The other five roles are granted under **Admin → People**.

| Role | Scope | What it allows |
|---|---|---|
| Admin | Whole organization | Manage accounts, roles, units, and appearance. Read and edit every record, including catalog standing |
| Governance | Whole organization | Triage, decide, waive conditions, change tiers, edit any record, set catalog standing, see the dashboard |
| Reviewer | One or more review functions, or every function | Take review tasks for those functions, record findings, write in discussions, change tiers |
| Auditor | Whole organization | Read every record, review, and history, and the dashboard. Change nothing |
| Steward | A unit and every unit beneath it | See and edit that unit's records, and mark their conditions as met |
| Member | Their own records | Browse the catalog, register uses, make requests, manage what they own |

Things worth knowing:

- An administrator who is not also governance cannot triage, review, or decide.
- Nobody triages, reviews, or decides their own request, whatever their role.
- The last active administrator cannot be disabled or lose the role. You cannot disable your own account.
- A person's **Works in** units set which unit their requests default to, and whose records they see in full.

The default review functions and their keys, used when granting the reviewer role from the command line or a CSV file:

| Function | Key | Function | Key |
|---|---|---|---|
| Privacy | `privacy` | Research integrity | `integrity` |
| Information security | `security` | Clinical safety | `clinical_safety` |
| Legal and contracts | `legal` | Data stewardship | `data_stewardship` |
| Research ethics | `ethics` | Architecture | `architecture` |

### Manage people

Under **Admin → People**, open a person to change their name, title, units, and roles, to **Reset password**, or to **Disable** them. A disabled person is signed out and cannot sign in. Their records and everything they did stay in the history.

The same can be done from the command line, which is how you get back in when nobody can sign in:

```bash
uv run govwren users add wei.chen@alderpoint.example --name "Wei Chen" --role reviewer=function:privacy
uv run govwren users roles priya.nair@alderpoint.example --set steward=unit:HALE
uv run govwren users list
```

See the [command reference](cli.md#govwren-users) for every option.

## Units

Every use case belongs to a unit, and stewards look after a unit and everything beneath it. Units are managed under **Admin → Units**.

- There is one top unit, the organization itself. Every other unit sits within another.
- A unit has a name, a kind (such as division, department, or lab), and an optional code.
- A unit can be renamed or moved. It cannot be moved beneath itself.
- A unit is never deleted. Set its status to **Closed**: it keeps its records and history and can no longer be chosen.

### Import units and people from CSV

Both **Units** and **People** have an **Import** button. Save your spreadsheet as CSV in UTF-8, with a header row.

1. Choose the file, then **Check the file**. Nothing is changed.
2. Read the report: how many rows would be added, changed, or left as they are, and every problem with its row number.
3. Fix the file until there are no problems, then choose **Import**.

Nothing is imported unless every row is good. A file can hold up to 20,000 rows and 5 MB.

**Units.** Matched by code, so importing again updates them.

| Column | Required | Meaning |
|---|---|---|
| `code` | Yes | The unit's short, permanent code |
| `name` | Yes | Its name |
| `kind` | Yes | Such as `organization`, `division`, `department`, `center`, `core`, `lab`, `office` |
| `parent_code` | No | The code of the unit it sits within. Empty for the organization itself |

```text
code,name,kind,parent_code
ALD,Alderpoint Institute,organization,
NEURO,Neuroscience,division,ALD
HALE,Hale Lab,lab,NEURO
```

A parent may come before or after its children. Exactly one unit has no parent.

**People.** Matched by email address. New people are added as invited: they can be named on records at once, and sign in once you set a password for them.

| Column | Required | Meaning |
|---|---|---|
| `email` | Yes | The address they sign in with |
| `name` | Yes | Their name |
| `title` | No | Their job title |
| `unit_codes` | No | The units they work in, separated by semicolons |
| `roles` | No | Roles, separated by semicolons: `admin`, `governance`, `auditor`, `reviewer`, `reviewer=function:KEY`, `steward=unit:CODE` |

```text
email,name,title,unit_codes,roles
priya.nair@alderpoint.example,Priya Nair,Lab Manager,HALE,steward=unit:HALE
wei.chen@alderpoint.example,Wei Chen,Privacy Analyst,ALD,reviewer=function:privacy
```

For someone who already has an account, units and roles are replaced only where the column has a value. An empty cell leaves them as they are.

## Build the catalog

The catalog is what answers "may I use this?". It is drawn from the inventory: an AI system appears in the catalog once governance gives it a standing.

### Add vendors and AI systems

Anyone signed in can add a vendor or an AI system, so people can record what they find. A new system is **Not in the catalog** and a new vendor is **Prospective** until governance says otherwise.

1. Under **Vendors**, choose **Add a vendor**. Add the supplier first, so systems can name it.
2. Under **AI systems**, choose **Add an AI system**. Give its name, kind, vendor, and **Edition**: the exact plan or license tier. A different edition is a different system, because the terms and the data handling differ.
3. Under **How it handles data**, record whether the supplier trains on what is entered, how long inputs are kept, and where data is processed.

### Set a system's standing

Governance and administrators see a **Catalog** section on the system's form.

| Field | Meaning |
|---|---|
| Catalog standing | See the table below |
| May be used with data up to | The most sensitive data class it is permitted for. Required for an approved system |
| Never to be used with | Kinds of data that are excluded even within that class |
| Terms of use | The conditions that apply to everyone who uses it. Shown in the catalog and attached to every registered use |

| Standing | In the catalog | Can a use be registered? |
|---|---|---|
| Not in the catalog | No | No |
| Under evaluation | Yes, marked "Not for use yet" | No |
| Approved | Yes | Yes |
| Approved with restrictions | Yes | Yes |
| Not approved | Yes, so that people get an answer | No |
| Retired | No | No |

A registered use is approved at once only when its data class is within the permitted class, none of its kinds of data is excluded, and the person confirms it only produces output that a person checks. Anything else becomes a request. So the permitted class and the exclusions are the decision you are making once, on behalf of every later use.

A vendor's **Standing** (Prospective, Active, Offboarding, Former) and **Due diligence** (Not started, In progress, Complete) are also set by governance or an administrator.

## Models and datasets

A tool is what people use. A **model** is what the tool is built on, and a **dataset** is what a model was trained on or what a use case works with. Recording them lets you answer "what depends on this?" when a model is withdrawn or a dataset's terms change.

### Record a model

Under **Models**, choose **Add a model**. Say what kind it is and where it comes from:

| Where it comes from | Means | What else to record |
|---|---|---|
| A supplier's service | Reached through an API. The weights stay with the supplier | The vendor, family, and version |
| Open weights | Published weights the organization runs itself | Where the weights were obtained, their checksum and format, the license and what it limits, where it runs |
| Fine-tuned in-house | An existing model adapted with your own data | The same, and how it was tuned |
| Built in-house | Trained from your own data | The same |

Record the checksum for any model you run yourselves: it says exactly which file is in use. Note the format too. A pickle or framework checkpoint can run code when it is loaded, so load one only from a source you trust.

The **Model card** fields (intended use, out-of-scope use, training data, evaluation, known limitations) follow the usual public conventions, so a published card can be copied in.

Anyone can add a model. Only governance sets its **catalog standing**, the data it may be used with, and its terms of use. An approved model appears in the catalog beside the approved tools.

### Record a dataset

Under **Datasets**, choose **Add a dataset**. A dataset record is a description: its data class, the kinds of data in it, who it is about, whether people can be identified, where it came from, and what it may and may not be used for. GovWren never holds the data.

### Link records together

On any record, the **Connected to** card lists what it relies on and what relies on it. Choose **Add** to link it to another record. Each kind of link joins only the kinds of record it makes sense for:

| Link | From | To |
|---|---|---|
| Uses | Use case | AI system, model |
| Processes | Use case, AI system | Dataset |
| Built on | AI system | Model |
| Derived from | Model | Model |
| Trained on, Evaluated on | Model | Dataset |
| Embedded in, Depends on | AI system | AI system |
| Replaces | Any record | A record of the same kind |

You can link from a record you can edit. A link that would make a loop is refused. Once a request has been submitted, what its use case uses is part of what was reviewed, and only governance can change it.

### See what depends on what

Every record has a **Connections** tab. It follows the links outward in both directions: on the left, everything that relies on the record; on the right, everything it relies on. Choose how many steps to follow. The same records are listed under the picture, each with how it is connected and how many steps away it is, so nothing is shown only as a drawing.

Use it when something changes. When a supplier withdraws a model, open the model's Connections tab to see every AI system built on it and every use case that uses those systems. A model with a withdrawal date shows a notice that leads there.

Records you may not see are counted and not shown, and nothing beyond them is followed.

### A model is as sensitive as its training data

A model can reproduce what it was trained on. When you link a model to a dataset with **Trained on**, the model's sensitivity is raised to the dataset's data class if it was lower. The same follows through **Derived from**: a model fine-tuned from another is at least as sensitive as everything in its line. The model's page says which datasets set the level, and nobody can set it lower.

### Describe an agent

An AI system whose kind is **Agent** has a card, **What it can do by itself**: how much it does without a person, what it can change and where, the tools it is connected to, the account it acts as, whether its actions can be undone, how a person stops it, what it remembers, and its limits. An agent with none of this recorded shows a warning.

### Keep vendor agreements

A vendor's page lists its **Agreements**: the kind, a title, your reference, the dates it runs between, the notice it needs, whether it renews by itself, and who looks after it. Each shows where it stands today:

| Shown as | Means |
|---|---|
| Current | In force, with time to spare |
| Ends soon | Ends within 90 days |
| In its notice period | The last day to give notice has passed or is today |
| Ended | Past its end date and does not renew by itself |

### Point to other systems

Every record has an **In other systems** card for the protocol, grant, agreement, purchase, ticket, or repository it belongs to: a kind, the number or name used there, and optionally a label and an address. GovWren stores the pointer and nothing else.

## The data classes

GovWren ships with four data classes, ordered from least to most sensitive. The order matters: catalog permissions compare against it.

| Class | Definition |
|---|---|
| Public | Poses little or no risk if disclosed, and may be shared with anyone |
| Internal | Meant for use inside the organization, by its own people, for its own work. Not to be shared outside without oversight |
| Protected | Could harm people or the organization if seen by the wrong person, inside or out. Access is limited to those who need it for their work |
| Restricted | Governed by specific legal, regulatory, or contractual obligations. Loss or disclosure may require notifying people, partners, or authorities |

Each class carries examples, grouped as Personal, Research, Health, Financial, and Administrative, which people can open wherever they choose a class. The labels, definitions, and examples are yours to change in a [program pack](#change-the-program-with-a-pack).

## How a request gets its tier

The default scoring model has six factors. Each scores 0 to 3, and takes the highest level any answer gives it.

| Factor | 0 | 3 |
|---|---|---|
| Impact on people | No effect on anyone outside the team | Could affect health, safety, legal rights, or livelihood |
| Decision role | Background or exploratory | Decides or acts without a person reviewing each case |
| Autonomy | Produces output only | Acts with effects that are hard to undo |
| Data sensitivity | Public data | Restricted data |
| Data exposure | Stays on the organization's own equipment | A supplier with no covering agreement, or one that may train on what is entered |
| Reach | One person or one team | The whole organization, or the public |

The total, from 0 to 18, gives the tier:

| Tier | Points | Review required | Who decides | Target | Approval runs |
|---|---|---|---|---|---|
| Minimal | 0–4 | None | Approved by rule | At once | 36 months |
| Moderate | 5–8 | None | Governance | 5 working days | 24 months |
| High | 9–12 | Privacy, security | The governance committee | 15 working days | 12 months |
| Critical | 13 and above | Privacy, security, legal | The committee, with an executive accepting the risk | 30 working days | 6 months |

**Floors** set a minimum tier whatever the points. By default, a request is at least High when:

- a mistake could seriously affect a person;
- Restricted data would go to a supplier with no covering agreement;
- it can take actions that are hard to undo;
- it decides about people without a person reviewing each case.

**Stops** mark a prohibited use. A stopped request can be submitted, but it is never approved by rule and cannot be approved in review. The defaults are:

- Restricted data entered into a system whose supplier may train on it;
- generative AI used to carry out confidential peer review;
- fully automated decisions about people, such as admission, hiring, or discipline.

Every tier shows its working: each factor's level, the answer behind it, and any floor or stop.

## Routing rules

Routing rules turn a tiered request into a review. Each rule has a condition, on the tier or on answers, and effects. Rules are read in order and their effects add up.

Besides the four tier rules above, the default rules add reviews for particular answers. Two of them concern models people run or train themselves: any such model needs an information security review and must be recorded in the inventory before use, and a model trained on Protected or Restricted data also needs a data stewardship review.

| When | Adds |
|---|---|
| Human-subjects research data is involved | Research ethics review |
| Health information is involved | Privacy review |
| Data goes to a supplier with no covering agreement | Legal review |
| Patients are affected | Clinical safety review |
| It acts by itself, within limits or irreversibly | Security and architecture reviews |
| Output is used in publications or grant applications | Research integrity review, and conditions on disclosure and checking references |
| Only public or internal data is involved | A condition not to enter Restricted data |

Every approved use also gets four standard conditions: check outputs, stay within the data described, declare changes, and report anything that goes wrong.

A request is approved by rule only when a rule says so, no rule requires a review, and nothing about it is a stop. So a Minimal request that involves health information still goes to privacy review.

## Change the program with a pack

The request form, the scoring model, the routing rules, the standard conditions, and every vocabulary are data. In this release you change them by exporting them as one file, a program pack, editing it, and loading it back. Editors inside the app come later; see the [roadmap](../spec/roadmap.md).

```bash
uv run govwren program export --out program.json     # write the program as it stands
uv run govwren program import --check program.json   # check an edited file; change nothing
uv run govwren program import program.json           # load it
```

A pack is JSON with these parts:

| Part | Holds |
|---|---|
| `pack` | A header: key, kind (`program`), title |
| `vocabularies` | Data classes, kinds of data, domains, stages, review functions, unit kinds, and the rest |
| `forms` | The request form: sections, questions, and when each is shown |
| `scoring_model` | Factors, contributions, tiers, floors, and stops |
| `review` | Standard conditions (`condition_templates`) and routing `rules` |

How loading works:

- The whole file is checked first. If anything is wrong, every problem is listed and nothing is loaded.
- Whatever differs from the published program becomes a new version. Whatever is the same is left alone.
- Earlier versions are kept. A past request still shows the questions it was asked and the rules it was tiered under.
- A vocabulary value can be relabelled, or retired by adding `"retired": true`. It cannot be removed, because records may use it.
- Loading a pack is recorded in the history.

Keep the pack under version control and review changes to it like any other policy. The format is described in [spec/content-packs.md](../spec/content-packs.md).

## Choose who sees approved use cases

One setting decides how much of an approved use case the rest of the organization sees.

| Value | Effect |
|---|---|
| `open` | Everyone sees every approved use case in full |
| `summary` | Everyone sees a summary; a use case's own unit sees it in full. This is the default |
| `unit` | People see only the use cases of their own units |

Drafts and records marked **Restricted** stay private whatever the setting. Owners, stewards of the unit, governance, auditors, and administrators always see a record in full. In this release the setting is changed through the API, by governance or an administrator: see [`PUT /api/v1/admin/inventory`](api.md#inventory).

## Read the dashboard

The **Dashboard** is for governance, auditors, and administrators.

| Figure | What it counts |
|---|---|
| Approved uses of AI | Use cases that are Approved or Approved with conditions |
| Requests in progress | Use cases that are submitted, in review, or back with their requester |
| Systems in the catalog | AI systems that are Approved or Approved with restrictions |
| Vendors | Every vendor recorded |
| Needs attention | Reviews past their target date; conditions past their due date; approvals not yet in effect because a before-use condition is open; approvals ending within 60 days. Only counts above zero are listed |
| Approved uses by tier, unit, area, stage | Approved use cases, grouped. Units are rolled up to the level below the organization, and the ten largest are shown |
| Every use case by status | Every use case except drafts |
| Open reviews | Where they are (waiting for triage, with reviewers, with the requester, ready for a decision) and how many days since each was opened |
| Decisions in the last 90 days | Reviews closed in that time, split into decided by rule and decided by people. A request that was only returned is not counted |
| Median days | For requests decided by people in the last 90 days: the middle value of the time from submission to decision, not counting time the request was back with its requester |

The tiles and the bars are links to the records they count. The last three counts under Needs attention are not links in this release.

## Trust the history

Every change to a record is written to an append-only history in the same transaction as the change: who, when, and each value before and after. Each record's **History** tab shows it in plain words. Changes made at the command line are recorded as such.

Events are chained by hash, and the database itself refuses updates and deletes on the history. To check the chain:

```bash
uv run govwren verify
```

It reports how many events hold, or the first event that has been altered, removed, or cut from the end, and exits with 1 if the history is broken. `uv run govwren doctor` runs the same check along with the rest.

## Set the appearance

Under **Admin → Appearance**:

| Setting | Notes |
|---|---|
| Product name | Shown in the sidebar and the browser tab |
| Organization | Shown on the sign-in page and on Home |
| Default palette | Wren, Slate, or Garnet. What everyone sees unless they choose another for themselves |
| Accent color | Optional. Your brand color as hex. It is adjusted automatically for dark mode, and refused if text on it could not be read |
| Logos and tab icon | A logo for light backgrounds, one for dark, and a browser tab icon. PNG, JPEG, WebP, or SVG, up to 2 MB |

The preview shows your choices by day and after dark before you save. Changes apply for everyone as soon as you save. An uploaded SVG is reduced to its drawing and served so that it cannot run anything.
