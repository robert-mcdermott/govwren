# Standards alignment

People adopting GovWren are often asked how it relates to a standard: the NIST AI Risk Management Framework, ISO/IEC 42001, or HIPAA. This guide answers that plainly: what GovWren gives you evidence for, what it leaves to you, and how to produce the documents an assessor asks for.

Nothing here is needed to use GovWren. The [control library](assurance.md#controls) stands on its own, and a framework is a second way of looking at the same controls.

## What GovWren is in a standard's terms

GovWren is a system of record for a governance program. It holds the inventory, the decisions and their reasons, the controls and their evidence, and a history that cannot be quietly changed. In a standard's terms it is where *documented information* lives and where you show that a process was followed.

It is passive. It does not scan networks, read logs, test models, or enforce anything inside another system. So for any requirement there are three honest answers, and this guide uses them throughout:

| Answer | Means |
|---|---|
| GovWren does it | The requirement is about keeping a record, running a review, or deciding with reasons, and GovWren is where that happens |
| GovWren holds the evidence | Someone else does the work, in another system or on paper, and GovWren records that it was done, by whom, and with what proof |
| Outside GovWren | The requirement is about something GovWren has no part in, and no control answers it. It shows as *Not mapped*, never as covered |

No software makes an organization compliant. GovWren does not certify anything, and an assessor or your own counsel decides whether what you hold is enough.

## How alignment works

1. **Controls** are what your program does. Each has a standing, an owner, evidence, and a date it is next checked.
2. A **framework pack** lists a standard's requirements and maps each to the controls that answer it.
3. **Readiness** is worked out, not typed in: a requirement is covered when every control mapped to it is in place with evidence that is still good.
4. The **statement of applicability** is the same picture as a spreadsheet, for a person outside the program.

Three frameworks are built in. Load one from **Frameworks**, or with `POST /api/v1/frameworks`. Loading changes no control and no record.

| Framework | Requirements | Answered by a control | What the pack contains |
|---|---|---|---|
| NIST AI Risk Management Framework 1.0 | 19 | 18 | Codes, with summaries in GovWren's words |
| ISO/IEC 42001:2023 | 64 | 53 | Clause and control numbers, with labels and summaries in GovWren's words. None of the standard's text: you need your own copy |
| HIPAA, as it bears on AI | 25 | 24 | Citations to 45 CFR Part 164, with summaries in GovWren's words |

The summaries are reading aids. The standard or the regulation is the authority, and where a summary and the source differ, the source is right.

## NIST AI Risk Management Framework

The framework is voluntary and organized as four functions. GovWren maps to its categories.

| Function | GovWren does it | GovWren holds the evidence |
|---|---|---|
| Govern | Roles, policies with acknowledgment, the inventory, review rules, decisions with reasons, exceptions that end, retirement | Training of reviewers, leadership review |
| Map | Intake: purpose, people affected, data, autonomy; the tier and why; impact assessments | |
| Measure | The program's own measures; spot checks of automatic approvals | Testing and evaluation of a model, done by its owners, attached as evidence |
| Manage | Conditions, periodic review, incidents, changes declared and reviewed, risks with treatments and owners | Monitoring of a system in use |

One category is not mapped: the one about the make-up and diversity of the workforce that governs AI. That belongs to how you staff the program, and no record in GovWren answers it.

## ISO/IEC 42001

ISO/IEC 42001 describes a management system for AI: clauses 4 to 10, and a set of controls in Annex A. Certification is granted by an accredited body after an audit. GovWren is not certified and cannot certify you. What it can do is hold most of what the audit looks at.

| Part | GovWren does it | GovWren holds the evidence | Outside GovWren |
|---|---|---|---|
| 4 Context, 5 Leadership | Scope, roles, the policy and who has acknowledged it | Leadership's commitment, as approvals and minutes | |
| 6 Planning | The risk register, treatments, impact assessments, objectives as measures | | Planning of changes to the management system itself |
| 7 Support | Policies and records as controlled documents; reviewer training as a control | Competence and awareness | Resources; communication plans |
| 8 Operation | Intake, tiering, review, decision, conditions | | |
| 9 Performance evaluation | Measures, reports to leadership, the dossier | Internal audit and management review | |
| 10 Improvement | Findings, actions, incidents, exceptions | | |
| A.2 to A.5 | Policies, roles, the inventory of systems, models, data, and vendors, impact assessment | | How the AI policy fits with your other policies; impacts on society as a whole |
| A.6 Life cycle | Records of a system from request to retirement | Verification, deployment, and monitoring by the people who build or run it | Design and development process, for organizations that build AI |
| A.7 Data | Datasets with their class, origin, terms, and quality checks | Data preparation | |
| A.8, A.9 | Terms of use shown to users, incident reporting, intended use, human oversight | | Reporting to outside parties |
| A.10 Third parties | Vendors, due diligence, agreements and the systems they cover | | Obligations to your own customers |

Eleven requirements are not mapped, and the table's last column says where they fall. If your organization only *uses* AI and does not build it, several of the life cycle controls may not apply: mark them **Does not apply…** with the reason, and that reason is carried into the statement of applicability.

## HIPAA

GovWren can help a covered entity or business associate show how AI tools are governed. Three points come first.

- **GovWren should hold no health information.** Forms ask people to describe data, not paste it. Keep it that way.
- **The technical safeguards are performed by the systems that hold the data.** Access control, audit logs, integrity, and encryption happen in the AI tool and around it. GovWren holds the evidence that they are in place, as the control *Access, logging, and encryption are shown for tools that hold sensitive data*.
- **This is not legal advice.** Whether an arrangement needs a business associate agreement, and whether data is de-identified, are judgments for your privacy officer and counsel. GovWren records the judgment and who made it.

| Area | GovWren does it | GovWren holds the evidence |
|---|---|---|
| Risk analysis and risk management | The inventory of every AI tool that touches health information, its tier, its risks and treatments | The security risk analysis itself, if it is done elsewhere |
| Assigned responsibility, workforce | Named owners and roles; policies and acknowledgment | Training records |
| Business associates | Agreements, the AI systems each covers, and the [rule](running-the-program.md#health-information-needs-a-covering-agreement) that stops approval without one | The signed agreement |
| Evaluation | Periodic review, declared changes, spot checks | |
| Technical safeguards | | Access control, audit controls, integrity, authentication, transmission security |
| Uses and disclosures, minimum necessary, de-identification | Intake questions, privacy review, conditions on the approval | The de-identification determination |
| Breach notification | Incidents, with what happened and what was decided | The risk assessment and the notices sent |

One requirement is not mapped: contingency planning, which is about backup and recovery of the systems that hold the data.

## Produce the statement of applicability

An assessor usually asks for one document that lists every requirement, says whether it applies, why not if it does not, and what answers it.

1. Open **Frameworks**, then the framework.
2. For each requirement that does not apply to you, choose **Does not apply…** and give the reason.
3. Choose **Statement of applicability**. The spreadsheet has one row for each requirement: its code, its title, whether it applies, the justification, how it stands, and the controls that answer it with where each stands.

The same list comes from `GET /api/v1/statement-of-applicability?framework=iso-iec-42001`, as CSV or, with `format=json`, as JSON. Without `framework`, the list is the [control library](assurance.md#the-statement-of-applicability) instead, which needs no framework loaded.

For the evidence behind the rows, make a [dossier](insight.md) of a record, or open a control to see what is attached and when it was last checked.

## Another standard

A framework is a data file. If you answer to a standard that is not built in, write a pack for it: its requirements by code, and which controls answer each. [Frameworks](assurance.md#frameworks) in the Assurance guide describes the format. Use the publisher's codes and your own words; do not copy text you have no right to distribute.

## What stays your job

- Deciding which standards you answer to, and what is in scope.
- Doing the technical work the records describe.
- Keeping evidence current. GovWren tells you when it has expired; it cannot renew it.
- Reading the standard. A pack is a map of it, not a replacement.
