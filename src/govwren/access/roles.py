"""The six roles (PLT-04). ``member`` is held by everyone who can sign in and is never granted."""

from __future__ import annotations

ADMIN = "admin"
GOVERNANCE = "governance"
REVIEWER = "reviewer"
AUDITOR = "auditor"
STEWARD = "steward"
MEMBER = "member"

GRANTABLE = (ADMIN, GOVERNANCE, REVIEWER, AUDITOR, STEWARD)
ROLES = (*GRANTABLE, MEMBER)

DESCRIPTIONS = {
    ADMIN: "Everything, including accounts, sign-in settings, branding, and system configuration",
    GOVERNANCE: "Run the program: triage, route, decide, edit any record, and manage its rules",
    REVIEWER: "Complete review tasks for the review functions they are granted",
    AUDITOR: "Read every record, decision, and the full history; change nothing",
    STEWARD: "See, edit, and attest for the records of a unit and those beneath it",
    MEMBER: "Browse the catalog, submit requests, and manage the records they own",
}
