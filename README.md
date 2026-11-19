# GovWren

**AI governance people actually use.**

GovWren is an open system of record for AI governance: one front door for AI requests, review in proportion to risk, a living inventory, and evidence behind every decision. It is built first for research organizations, where many semi-autonomous labs adopt AI tools faster than any committee can track, and it can be adopted and re-branded by any organization.

- **A front door, not a gate.** A catalog of reviewed tools answers "may I use this?" in seconds, and registering a use takes under a minute. Anything new starts with a short form that grows only when the answers call for it.
- **Proportionate.** A transparent risk tier decides who reviews, who decides, and how often a record is revisited. Every tier shows the answers that produced it.
- **Passive by design.** No scanners, agents, or log collectors. GovWren knows what people tell it, and makes telling it the easy path.
- **Built for federated organizations.** Every record belongs to a unit and has named owners. Units attest that their list is complete.
- **An unbroken record.** Every change is written to an append-only, verifiable history.
- **Open and yours.** Apache 2.0. Runs on a laptop with SQLite or on a server with PostgreSQL. Name, logo, colors, forms, and rules are settings.

> **Status:** planning. The specification and roadmap are in [`spec/`](spec/README.md); the first release (wave 1, v0.1.0) is not yet built.

## Read the plan

- [Vision](spec/vision.md): what GovWren is, who it is for, and what it deliberately is not
- [The governance engine](spec/governance-engine.md): how a request is taken in, tiered, reviewed, decided, and kept current
- [Roadmap](spec/roadmap.md): eight waves from v0.1.0 to v1.0.0
- [Wave 1 plan](spec/waves/wave-1.md): the first release, slice by slice
- [Everything else](spec/README.md): requirements, data model, architecture, design system, security, and decisions

## License

Apache License 2.0.
