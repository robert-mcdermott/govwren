"""The one table that says what each API route requires (PLT-04).

Every route under ``/api`` must appear here. A route that does not is refused, and a test
fails the build if one is added without an entry. This is the coarse check; services check
again against the record itself (its unit, its owners, its visibility).
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import HTTPException, Request

from govwren.access.principal import Principal


class Needs(StrEnum):
    PUBLIC = "public"  # no sign-in: health, product name, signing in
    MEMBER = "member"  # anyone signed in
    REVIEW = "review"  # reviewers and governance
    STEWARD = "steward"  # stewards, governance, and administrators
    GOVERN = "govern"  # governance: running the program
    CONFIGURE = "configure"  # governance and administrators: shaping the program
    READ_ALL = "read_all"  # governance, auditors, and administrators
    ADMIN = "admin"  # administrators


POLICIES: dict[tuple[str, str], Needs] = {
    ("GET", "/api/v1/health/live"): Needs.PUBLIC,
    ("GET", "/api/v1/health/ready"): Needs.PUBLIC,
    ("GET", "/api/v1/meta"): Needs.PUBLIC,
    # Signing in and out
    ("GET", "/api/v1/session"): Needs.PUBLIC,  # answers 401 itself, so the app can show sign-in
    ("POST", "/api/v1/session"): Needs.PUBLIC,
    ("DELETE", "/api/v1/session"): Needs.PUBLIC,
    ("POST", "/api/v1/session/demo"): Needs.PUBLIC,  # answers 404 unless this is a demo
    ("POST", "/api/v1/session/password"): Needs.MEMBER,
    # Single sign-on
    ("GET", "/api/v1/sso/start"): Needs.PUBLIC,
    ("GET", "/api/v1/sso/callback"): Needs.PUBLIC,
    ("GET", "/api/v1/sso"): Needs.ADMIN,
    ("PUT", "/api/v1/sso/mappings"): Needs.ADMIN,
    # People
    ("GET", "/api/v1/accounts"): Needs.MEMBER,  # the people picker; members see names only
    ("POST", "/api/v1/accounts"): Needs.ADMIN,
    ("GET", "/api/v1/accounts/{account_id}"): Needs.MEMBER,
    ("PATCH", "/api/v1/accounts/{account_id}"): Needs.MEMBER,  # one's own details, or admin
    ("PUT", "/api/v1/accounts/{account_id}/roles"): Needs.ADMIN,
    ("PUT", "/api/v1/accounts/{account_id}/units"): Needs.ADMIN,
    ("POST", "/api/v1/accounts/{account_id}/password"): Needs.ADMIN,
    ("GET", "/api/v1/roles"): Needs.MEMBER,
    # Units
    ("GET", "/api/v1/units"): Needs.MEMBER,
    ("POST", "/api/v1/units"): Needs.ADMIN,
    ("GET", "/api/v1/units/{unit_id}"): Needs.MEMBER,
    ("PATCH", "/api/v1/units/{unit_id}"): Needs.ADMIN,
    # Branding
    ("GET", "/api/v1/admin/branding"): Needs.ADMIN,
    ("PUT", "/api/v1/admin/branding"): Needs.ADMIN,
    ("POST", "/api/v1/admin/branding/check"): Needs.ADMIN,
    ("POST", "/api/v1/admin/branding/images/{kind}"): Needs.ADMIN,
    ("DELETE", "/api/v1/admin/branding/images/{kind}"): Needs.ADMIN,
    # Inventory: any member may ask; the services decide what each may see and change
    ("GET", "/api/v1/vocabularies"): Needs.MEMBER,
    ("GET", "/api/v1/admin/inventory"): Needs.CONFIGURE,
    ("PUT", "/api/v1/admin/inventory"): Needs.CONFIGURE,
    ("GET", "/api/v1/use-cases"): Needs.MEMBER,
    ("POST", "/api/v1/use-cases"): Needs.MEMBER,
    ("GET", "/api/v1/use-cases/{ref}"): Needs.MEMBER,
    ("PATCH", "/api/v1/use-cases/{ref}"): Needs.MEMBER,
    ("PUT", "/api/v1/use-cases/{ref}/owners"): Needs.MEMBER,
    ("PUT", "/api/v1/use-cases/{ref}/systems"): Needs.MEMBER,
    ("GET", "/api/v1/use-cases/{ref}/history"): Needs.MEMBER,
    ("GET", "/api/v1/systems"): Needs.MEMBER,
    ("POST", "/api/v1/systems"): Needs.MEMBER,
    ("GET", "/api/v1/systems/{ref}"): Needs.MEMBER,
    ("PATCH", "/api/v1/systems/{ref}"): Needs.MEMBER,
    ("PUT", "/api/v1/systems/{ref}/owners"): Needs.MEMBER,
    ("GET", "/api/v1/systems/{ref}/history"): Needs.MEMBER,
    ("GET", "/api/v1/vendors"): Needs.MEMBER,
    ("POST", "/api/v1/vendors"): Needs.MEMBER,
    ("GET", "/api/v1/vendors/{ref}"): Needs.MEMBER,
    ("PATCH", "/api/v1/vendors/{ref}"): Needs.MEMBER,
    ("GET", "/api/v1/vendors/{ref}/history"): Needs.MEMBER,
    ("GET", "/api/v1/record-types"): Needs.MEMBER,
    ("GET", "/api/v1/models"): Needs.MEMBER,
    ("POST", "/api/v1/models"): Needs.MEMBER,
    ("GET", "/api/v1/models/{ref}"): Needs.MEMBER,
    ("PATCH", "/api/v1/models/{ref}"): Needs.MEMBER,
    ("PUT", "/api/v1/models/{ref}/owners"): Needs.MEMBER,
    ("GET", "/api/v1/models/{ref}/history"): Needs.MEMBER,
    ("GET", "/api/v1/datasets"): Needs.MEMBER,
    ("POST", "/api/v1/datasets"): Needs.MEMBER,
    ("GET", "/api/v1/datasets/{ref}"): Needs.MEMBER,
    ("PATCH", "/api/v1/datasets/{ref}"): Needs.MEMBER,
    ("PUT", "/api/v1/datasets/{ref}/owners"): Needs.MEMBER,
    ("GET", "/api/v1/datasets/{ref}/history"): Needs.MEMBER,
    # What a person may link, point to, or agree is decided record by record.
    ("POST", "/api/v1/links"): Needs.MEMBER,
    ("DELETE", "/api/v1/links/{link_id}"): Needs.MEMBER,
    ("GET", "/api/v1/records/{ref}/graph"): Needs.MEMBER,
    ("PUT", "/api/v1/records/{ref}/references"): Needs.MEMBER,
    ("POST", "/api/v1/vendors/{ref}/agreements"): Needs.MEMBER,
    ("PATCH", "/api/v1/agreements/{agreement_id}"): Needs.MEMBER,
    ("DELETE", "/api/v1/agreements/{agreement_id}"): Needs.MEMBER,
    # Intake and tiering
    ("GET", "/api/v1/intake"): Needs.MEMBER,
    ("POST", "/api/v1/intake"): Needs.MEMBER,
    ("GET", "/api/v1/use-cases/{ref}/intake"): Needs.MEMBER,
    ("PUT", "/api/v1/use-cases/{ref}/intake"): Needs.MEMBER,
    ("POST", "/api/v1/use-cases/{ref}/submit"): Needs.MEMBER,
    ("GET", "/api/v1/use-cases/{ref}/tier"): Needs.MEMBER,
    ("POST", "/api/v1/use-cases/{ref}/tier"): Needs.REVIEW,
    # Review and decisions: the services decide who may do what to which review
    ("GET", "/api/v1/me/work"): Needs.MEMBER,
    ("GET", "/api/v1/notifications"): Needs.MEMBER,
    ("POST", "/api/v1/notifications/read"): Needs.MEMBER,
    ("GET", "/api/v1/reviews"): Needs.MEMBER,
    ("GET", "/api/v1/reviews/{ref}"): Needs.MEMBER,
    ("GET", "/api/v1/use-cases/{ref}/review"): Needs.MEMBER,
    ("POST", "/api/v1/reviews/{ref}/triage"): Needs.GOVERN,
    ("POST", "/api/v1/reviews/{ref}/tasks/{task_id}/claim"): Needs.REVIEW,
    ("POST", "/api/v1/reviews/{ref}/tasks/{task_id}/assign"): Needs.GOVERN,
    ("POST", "/api/v1/reviews/{ref}/tasks/{task_id}/complete"): Needs.REVIEW,
    ("POST", "/api/v1/reviews/{ref}/comments"): Needs.MEMBER,
    ("POST", "/api/v1/reviews/{ref}/decision"): Needs.GOVERN,
    ("POST", "/api/v1/reviews/{ref}/withdraw"): Needs.MEMBER,
    ("POST", "/api/v1/conditions/{condition_id}/close"): Needs.MEMBER,
    ("POST", "/api/v1/imports/records/{kind}"): Needs.GOVERN,
    ("GET", "/api/v1/exports/{kind}"): Needs.MEMBER,
    ("GET", "/api/v1/search"): Needs.MEMBER,
    ("GET", "/api/v1/views"): Needs.MEMBER,
    ("POST", "/api/v1/views"): Needs.MEMBER,
    ("DELETE", "/api/v1/views/{view_id}"): Needs.MEMBER,
    ("GET", "/api/v1/duplicates"): Needs.READ_ALL,
    ("POST", "/api/v1/records/{ref}/merge"): Needs.GOVERN,
    # Evidence: who may see or change each item is decided item by item.
    ("POST", "/api/v1/evidence/files"): Needs.MEMBER,
    ("GET", "/api/v1/evidence"): Needs.MEMBER,
    ("POST", "/api/v1/evidence"): Needs.MEMBER,
    ("GET", "/api/v1/evidence/{ref}"): Needs.MEMBER,
    ("PATCH", "/api/v1/evidence/{ref}"): Needs.MEMBER,
    ("GET", "/api/v1/evidence/{ref}/file"): Needs.MEMBER,
    # Catalog and dashboard
    ("GET", "/api/v1/catalog"): Needs.MEMBER,
    ("POST", "/api/v1/catalog/{ref}/register"): Needs.MEMBER,
    ("GET", "/api/v1/catalog/requests"): Needs.MEMBER,
    ("POST", "/api/v1/catalog/requests"): Needs.MEMBER,
    ("GET", "/api/v1/dashboard"): Needs.READ_ALL,
    ("GET", "/api/v1/jobs"): Needs.ADMIN,
    ("POST", "/api/v1/jobs/{key}/run"): Needs.ADMIN,
    ("PUT", "/api/v1/jobs/{key}"): Needs.ADMIN,
    ("GET", "/api/v1/mail"): Needs.ADMIN,
    ("POST", "/api/v1/mail/test"): Needs.ADMIN,
    # Keeping watch
    ("GET", "/api/v1/campaigns"): Needs.MEMBER,  # filtered to what asks something of you
    ("POST", "/api/v1/campaigns"): Needs.GOVERN,
    ("GET", "/api/v1/campaigns/{ref}"): Needs.MEMBER,
    ("POST", "/api/v1/campaigns/{ref}/answers"): Needs.MEMBER,  # each answer is checked
    ("POST", "/api/v1/campaigns/{ref}/close"): Needs.GOVERN,
    ("POST", "/api/v1/use-cases/{ref}/change"): Needs.MEMBER,  # owners; checked in the service
    ("POST", "/api/v1/records/{ref}/retire"): Needs.MEMBER,  # whoever may edit the record
    ("GET", "/api/v1/records/{ref}/findings"): Needs.MEMBER,
    # The program itself
    ("GET", "/api/v1/program"): Needs.CONFIGURE,
    ("POST", "/api/v1/program/check"): Needs.CONFIGURE,
    ("PUT", "/api/v1/program"): Needs.CONFIGURE,
    # Imports
    ("POST", "/api/v1/imports/units"): Needs.ADMIN,
    ("POST", "/api/v1/imports/people"): Needs.ADMIN,
}


def allowed(principal: Principal | None, needs: Needs) -> bool:
    if needs is Needs.PUBLIC:
        return True
    if principal is None:
        return False
    return {
        Needs.MEMBER: True,
        Needs.REVIEW: principal.reviews,
        Needs.STEWARD: principal.stewards or principal.edits_all,
        Needs.GOVERN: principal.governs,
        Needs.CONFIGURE: principal.configures,
        Needs.READ_ALL: principal.reads_all,
        Needs.ADMIN: principal.is_admin,
    }[needs]


def authorize(request: Request) -> None:
    """The app-wide dependency: look the matched route up in the table and check it."""
    route = request.scope.get("route")
    path = getattr(route, "path", "")
    if not path.startswith("/api/"):
        return  # the web app's own files
    needs = POLICIES.get((request.method, path))
    if needs is None:
        raise HTTPException(403, "This route has no access policy.")
    principal: Principal | None = getattr(request.state, "principal", None)
    if allowed(principal, needs):
        return
    if principal is None:
        raise HTTPException(401, "Sign in to continue.")
    raise HTTPException(403, "Your role does not allow this.")


def current(request: Request) -> Principal:
    """The signed-in person, for routes that the table says need one."""
    principal: Principal | None = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(401, "Sign in to continue.")
    return principal
