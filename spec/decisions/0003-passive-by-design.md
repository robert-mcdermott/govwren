# ADR-0003: Passive by design

- **Status:** Accepted
- **Date:** 2026-11-18

## Context

There are two ways for a governance system to learn what AI an organization uses. It can go looking: inspect network traffic, read logs, scan code and cloud accounts, or sit in the path of requests. Or it can be told: by people, by documents, and by other systems that choose to send it something.

Going looking finds things people did not report. It also needs deep access to the organization's network and data, takes a long security review to deploy, creates a surveillance relationship with the very people whose cooperation governance depends on, and is a different and much larger product.

## Decision

GovWren is passive, and the word has a precise meaning.

**GovWren never:**

- inspects network traffic or reads proxy, firewall, or application logs;
- installs anything on endpoints;
- scans source code, cloud accounts, or software tenants;
- sits in the path of an AI request, or blocks, filters, or modifies one;
- runs tests or monitoring against a model.

**GovWren learns only from:**

- what people enter: requests, registrations, reviews, attestations, incident reports;
- documents people attach;
- what another system deliberately **pushes** to it through the API (wave 7);
- and, only if an administrator turns it on and names the source, a scheduled **read-only pull of metadata** from a registry the organization already runs (wave 7), whose results are suggestions for a person to confirm.

Coverage is reached through process, and the product is designed to make that process work: a front door that is easier than avoiding it, a catalog that answers most questions without a form, unit attestations that produce an attributable statement of completeness, references that other processes can require and check, and reminders tied to renewals. Coverage is measured and shown, never assumed.

## Consequences

- GovWren can be deployed with no access to anything else, which makes it quick to approve and safe to run.
- It is honest about its limits: it shows what has been reported and how recently each unit confirmed its list, and never claims to know what it was not told.
- An organization that also wants active discovery or enforcement runs a separate tool for it and records the results in GovWren.
- Requests to add scanning or enforcement are declined by pointing here. The roadmap lists them under *Never*.

## Alternatives

- **Active discovery as an optional module:** it would dominate the security review of every installation, including those that never enable it, and pull the project toward a different product.
- **Passive with no integrations at all:** simpler, but it rules out other processes checking a reference, which is the strongest passive lever there is.
