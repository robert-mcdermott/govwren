# ADR-0007: Governance rules and content as data

- **Status:** Accepted
- **Date:** 2026-11-18

## Context

No two organizations govern AI the same way, and no organization governs it the same way two years running. Forms, risk factors, tiers, review routes, cadences, controls, and vocabulary all differ and all change. If any of them lived in code, every adopter would need a developer, and every change would need a release.

At the same time, rules that people can edit must not become a way to run arbitrary code, and a decision made under last year's rules must remain explainable.

## Decision

- **Everything that expresses policy is data:** vocabularies, forms, the scoring model, routing rules, cadences, condition templates, controls and their applicability, and framework mappings.
- **It is edited in the app** by the governance and admin roles, with previews.
- **It is versioned.** A published form version, scoring model, or rule set is immutable. Every response, tier assessment, and review records the version it was made under.
- **One declarative condition language** serves form visibility, scoring contributions, routing rules, and control applicability. It is a small tree of `all`, `any`, `not`, and comparisons over named fields and answers. There are no expression strings, and nothing is ever evaluated as code.
- **The evaluator exists twice**, in Python for authority and in JavaScript for the live form and tier preview, held together by one shared file of test cases that both must pass.
- **Content moves as packs.** A program pack carries an organization's whole configuration; content packs carry control libraries, risk libraries, and optional frameworks ([content-packs.md](../content-packs.md)).
- **GovWren ships a complete default program**, so a new installation works on its first day and editing is optional.
- **Changes are previewed against real records** before publishing: the app lists which existing records would change tier or route.

## Consequences

- An adopter shapes GovWren to its own process without touching code, and can share that shape with another organization as a file.
- Behavior depends on configuration, so support and testing must consider it: the default program has its own tests, and `govwren doctor` validates the active configuration.
- The condition language is deliberately limited. Rules that cannot be expressed in it are a signal to add a field or an effect, not an escape hatch.
- Two evaluators are a duplication to keep in step; the shared cases make drift a test failure.

## Alternatives

- **Rules in code with configuration flags:** simple to build, and every adopter's process becomes a fork.
- **An embedded scripting or expression language:** flexible, and it turns anyone who can edit a rule into someone who can run code on the server.
- **A general workflow engine:** far more than is needed, a heavy dependency, and a second product to learn.
