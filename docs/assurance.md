# Assurance

Deciding requests and keeping the inventory true is most of governance. Assurance is the part that lets you show it: the risks that are known, what is done about each, and what is left.

This guide grows with each release. It covers the risk register. Controls, evidence freshness, policies, and frameworks follow.

Who does what:

| Task | Who |
|---|---|
| Record a risk on a record | Whoever is responsible for the record: its owners, its unit's stewards, or governance |
| Record a risk from a review | A reviewer of that request |
| Record a risk to the organization | Governance |
| Say what is done about a risk, and rescore it | Its owner, whoever is responsible for the record, or governance |
| Accept a risk as it stands, or close one | Governance |

## The risk register

**Risks** lists every risk you may see, highest first. Beside the list, a grid counts open risks by how likely and how bad they are, as they stand now.

![The risk register: a grid of open risks by likelihood and impact, and the list of risks with their level and owner](images/risks-light.webp "The risk register")

Who sees a risk: governance, auditors, and administrators see every risk. Anyone else sees the risks they own, and the risks on records they can see in full.

### How a risk is scored

A risk has two scores from 1 to 5: how likely it is, and how bad it would be. Their product gives the level.

| Likelihood times impact | Level |
|---|---|
| 1 to 4 | Low |
| 5 to 9 | Moderate |
| 10 to 16 | High |
| 17 to 25 | Critical |

A risk is scored twice. The first score is before anything is done about it. The second is as it stands after treatment. The register and the grid use the second once it is given.

### Record a risk

Choose **Record a risk**. To record one on a record, open the record and choose **Risks**, then **Add a risk**.

Draw the wording from the library, or write your own. Choose a category, then how likely it is and how bad it would be before anything is done.

The risk belongs to whoever records it until an owner is named.

### The risk library

GovWren ships about forty risk statements written for research and health settings, in eight categories:

- Data and privacy
- Accuracy and reliability
- Fairness and effects on people
- Human oversight
- Security and misuse
- Suppliers and dependence
- Research integrity
- Operations and accountability

Each statement says what could go wrong and what usually answers it. A risk drawn from the library keeps a note of which statement it came from. You can change its wording freely; the library is a starting point.

### Say what is done about it

Open the risk and choose **Say what is done about it…**. Choose the treatment:

| Treatment | Meaning |
|---|---|
| Reduce it | Something is done that makes it less likely or less bad |
| Pass it to someone else | Another party carries it, such as a supplier under an agreement |
| Stop doing what causes it | The activity that gives rise to it ends |
| Accept it as it stands | Nothing more is done. Only governance may choose this |

Say what is done and by whom, score the risk as it now stands, and set a date to look at it again.

![One risk: what could go wrong, what is done about it, and how it scores before and after](images/risk-light.webp "A risk, with its scores before and after treatment")

On that date the owner is reminded. Setting a new date asks again when it comes.

### A risk from a review

A reviewer who finds something that will outlast the review can record it as a risk, from the review. It is attached to the use case and goes to the use's accountable owner, with the review it came from noted on it.

### Risks are findings

An open risk at the two highest levels is shown at the top of its record. Like an incident or an exception, it is also shown on everything that relies on that record, marked as inherited. See [Findings are inherited](keeping-watch.md#findings-are-inherited).

Treating a risk down to moderate or low removes it from there. It stays in the register.

### Close a risk

When a risk no longer applies, governance closes it with the reason. A closed risk keeps its history and is left out of the grid.
