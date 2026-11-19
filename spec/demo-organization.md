# The demo organization

`govwren demo` builds a complete, fictional organization to explore: the **Alderpoint Institute for Medical Research**. It exists so that anyone can see every feature working with realistic content within a minute of installing, so that every screenshot in the documentation shows the real application, and so that the test suite has an end-to-end exercise of the whole system.

Alderpoint is invented. Its people, labs, vendors, products, and incidents do not exist, and nothing in it is taken from a real organization.

## Rules

1. **Built by the real code.** The generator does not insert rows. It calls the same services the app uses, in order, under a simulated clock: accounts are created, requests are submitted, tiers are computed, rules route them, reviewers record findings, decisions are made, campaigns run, incidents are reported. Every record, review, and event in the demo is genuine output, and the history chain verifies.
2. **Deterministic.** The same seed produces the same organization, record for record. A different seed produces different people and details with the same shape.
3. **Relative to today.** History is generated backward from the day the demo is built, so there is always something due this week, something overdue, and a campaign in progress.
4. **Invented and unmistakably so.** Email addresses use `alderpoint.example`. Vendor and product names are made up and checked against the private-terms list. Identifiers for things in other systems (protocols, grants, agreements) use formats that cannot be mistaken for real ones.
5. **Clearly marked.** A demo installation shows a "Demo data" marker on every page, and its sign-in page offers one-click sign-in as each sample person.
6. **Grows with the product.** Each wave extends the generator to cover what the wave adds. The last check of every release is that the demo shows every documented screen with data.

## The institute

Alderpoint is a mid-sized independent medical research institute with a clinical research unit, about 1,400 staff, and a governance program that has been running for thirty months.

| Area | Units |
|---|---|
| **Research divisions** | Cancer Biology · Immunology and Infectious Disease · Neuroscience · Population Health · Computational Biology · Clinical Research |
| **Labs** | About 40, each named for its principal investigator |
| **Core facilities** | Genomics · Imaging · Biostatistics · Proteomics · Research Computing |
| **Administration** | Information Technology · Research Integrity · Privacy Office · Legal · Human Resources · Finance · Communications · Library · Education and Training |

Units nest three and four deep, so scoped roles, roll-ups, and unit attestations all have something to show.

### People

About 240 accounts, including a governance lead and a deputy, a nine-member AI governance committee, reviewers for each of the eight review functions, stewards for every division and most labs, an auditor, an executive risk acceptor, and principal investigators, staff scientists, postdoctoral fellows, students, analysts, and administrators.

Sample accounts for signing in as each role are listed on the demo's sign-in page.

### Scale

Enough to look like an organization that has used GovWren for a while, and small enough to build in under a minute.

| Records | About | Notes |
|---|---|---|
| Org units | 60 | Four levels |
| Accounts | 240 | Every role represented |
| AI systems | 95 | 40 in the catalog as approved or approved with restrictions; several not approved; a dozen agents |
| Models | 65 | Commercial and open-weight language models, fine-tunes with lineage, classical models built in-house |
| Datasets | 85 | Every data class and identifiability level |
| Vendors | 40 | With about 70 agreements, some expiring soon |
| Use cases | 310 | Every stage, standing, tier, and domain |
| Reviews | 380 | Initial, periodic, change, and incident-triggered |
| Conditions | 500 | Open, met, overdue, and waived |
| Incidents | 45 | Every category and severity; a few open |
| Exceptions | 20 | Active, expired, and renewed |
| Campaigns | 6 | One in progress at about three-quarters complete |
| Risks | 140 | With inherent and residual scores |
| Controls | 45 | With implementation at varied states |
| Evidence items | 600 | Some expiring, some expired |
| Policies | 9 | With versions and acknowledgments |
| Events | 25,000+ | Thirty months of history |

The tier mix is realistic: most use is minimal or moderate and went through quickly, with a few dozen high and a handful critical. Turnaround times vary by tier and improve over the thirty months, so trend charts have a story.

## Storylines

Generated volume makes the lists and charts convincing. A set of hand-written storylines makes the detail pages worth reading, and each one demonstrates a capability.

| Storyline | What it shows |
|---|---|
| **A lab registers a chat assistant from the catalog** for drafting and summarizing internal documents | The one-minute path: registration, automatic approval by rule, standard conditions, a yearly attestation |
| **Visit-note summarization in the clinical research unit**, using a vendor system on participant health information | A critical tier with its reasons; privacy, security, legal, clinical safety, and ethics reviews in parallel; a decision with conditions; named risk acceptance; a later incident and a suspension |
| **A service-desk agent that triages and closes tickets** with write access to the ticketing system | An agent profile; an architecture review; limits and a human override recorded as conditions |
| **A variant classifier fine-tuned on controlled-access genomic data** | Model lineage; a dataset under a data use agreement; inherited restrictions shown on every dependent |
| **A request to transcribe participant interviews with a consumer chatbot** | A stop under policy; a declined request with a rationale; a resubmission using an approved tool |
| **A language model the vendor is withdrawing** | The dependency graph; dependents listed and their owners notified; change reviews opened |
| **A grant-writing assistant used across a division** | Research integrity review; standard conditions on disclosure and verification |
| **An imaging lab's segmentation model moving from pilot to routine use** | A change declaration judged material; a change review limited to what changed |
| **The Neuroscience division's completeness attestation** | A steward adds three unregistered uses and attests; coverage rises on the dashboard |
| **A lapsed approval in a lab whose principal investigator has left** | An orphaned record, a lapsed standing, and escalation to the steward |
| **A time-limited exception for a conference deadline** | Justification, compensating measures, approval, and expiry |
| **The committee's most recent session** | An agenda of decision packets, the decisions, and the minutes |

## Using it

```bash
uv run govwren demo                       # builds ./demo
uv run govwren --config demo/govwren.toml serve
```

`govwren demo --seed N` builds a different Alderpoint; `--force` rebuilds in place. The demo directory is ignored by git. The documentation's screenshot capture starts its own demo in a temporary directory, so screenshots are always of a fresh, known state.
