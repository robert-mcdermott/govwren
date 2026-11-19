"""A request's path from first answer to a tiered, submitted use case."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied, StoreError
from govwren.db.models import (
    FormResponse,
    FormVersion,
    IntakeDraft,
    ScoringModel,
    TierAssessment,
    UseCase,
)
from govwren.events import audit
from govwren.intake import forms, scoring
from govwren.inventory import access, records
from govwren.inventory.registry import USE_CASE
from govwren.program import packs

INTAKE_FORM = "use_case_intake"
OPEN = ("draft", "returned")  # the standings in which the requester may still change answers


def current_form(session: Session) -> FormVersion:
    version = packs.published_form(session, INTAKE_FORM)
    if version is None:
        raise StoreError(
            "There is no intake form. Run `govwren db upgrade` to load the default program."
        )
    return version


def current_scoring(session: Session) -> ScoringModel:
    model = packs.published_scoring(session)
    if model is None:
        raise StoreError(
            "There is no scoring model. Run `govwren db upgrade` to load the default program."
        )
    return model


def program(session: Session) -> dict[str, Any]:
    """The form and scoring model in force, for the web app to draw and to preview with."""
    version, model = current_form(session), current_scoring(session)
    return {
        "form": {"key": INTAKE_FORM, "version": version.version, "schema": version.schema},
        "scoring": {"version": model.version, "definition": model.definition},
    }


def _draft(session: Session, use_case: UseCase) -> IntakeDraft | None:
    return session.get(IntakeDraft, use_case.id)


def _require_open(session: Session, principal: Principal, use_case: UseCase) -> None:
    if not access.can_edit(session, principal, USE_CASE, use_case):
        raise PermissionDenied("You cannot change this request.")
    if use_case.status not in OPEN:
        raise Conflict("This request has been submitted. Declare a change to alter what it says.")


def _sync_basics(
    session: Session, principal: Principal, use_case: UseCase, values: Mapping[str, Any]
) -> None:
    """Keep the record's name and unit in step with the draft, so lists show the right thing."""
    basics = {key: values[key] for key in ("name", "org_unit_id") if key in values}
    changed = {key: value for key, value in basics.items() if getattr(use_case, key) != value}
    if changed:
        records.update(session, principal, USE_CASE, use_case, changed, version=use_case.version)


def start(session: Session, principal: Principal, answers: Mapping[str, Any]) -> UseCase:
    """Begin a request. It needs only enough to be found again: what it is for, and which unit."""
    version = current_form(session)
    cleaned, errors = forms.clean(session, principal, version.schema, answers, complete=False)
    values = forms.mapped(version.schema, cleaned)
    needed = {
        question["key"]: "Answer this to start."
        for section in version.schema["sections"]
        for question in section["questions"]
        if question.get("maps_to") in ("name", "org_unit_id") and question["key"] not in cleaned
    }
    if errors or needed:
        raise Invalid("The request was not started.", {**needed, **errors})
    try:
        use_case = records.create(
            session,
            principal,
            USE_CASE,
            {"name": values["name"], "org_unit_id": values["org_unit_id"]},
        )
    except Invalid as exc:
        raise Invalid(str(exc), _by_question(version.schema, exc.errors)) from exc
    session.add(
        IntakeDraft(
            use_case_id=use_case.id,
            form_version_id=version.id,
            answers=cleaned,
            updated_at=utc_now(),
        )
    )
    session.flush()
    return use_case


def _by_question(schema: Mapping[str, Any], errors: Mapping[str, str]) -> dict[str, str]:
    """Errors keyed by record field, re-keyed by the question that fills the field."""
    question_for = {
        question["maps_to"]: question["key"]
        for section in schema["sections"]
        for question in section["questions"]
        if question.get("maps_to")
    }
    return {question_for.get(field, field): message for field, message in errors.items()}


def save(
    session: Session, principal: Principal, use_case: UseCase, answers: Mapping[str, Any]
) -> dict[str, str]:
    """Save a draft's answers as they are. Returns what is wrong with any of them; the rest
    are kept, and nothing has to be complete yet."""
    _require_open(session, principal, use_case)
    draft = _draft(session, use_case)
    version = session.get(FormVersion, draft.form_version_id) if draft else current_form(session)
    assert version is not None
    cleaned, errors = forms.clean(session, principal, version.schema, answers, complete=False)
    if draft is None:
        session.add(
            IntakeDraft(
                use_case_id=use_case.id,
                form_version_id=version.id,
                answers=cleaned,
                updated_at=utc_now(),
            )
        )
    else:
        draft.answers = cleaned
        draft.updated_at = utc_now()
    try:
        _sync_basics(session, principal, use_case, forms.mapped(version.schema, cleaned))
    except Invalid as exc:
        errors = {**_by_question(version.schema, exc.errors), **errors}
    session.flush()
    return errors


def submit(session: Session, principal: Principal, use_case: UseCase) -> TierAssessment:
    """Submit a request: check the answers are complete, fill the record from them, work out
    the tier, and record all three. After this the answers are part of the history."""
    _require_open(session, principal, use_case)
    draft = _draft(session, use_case)
    if draft is None:
        raise Conflict(
            "There are no answers to submit yet. Open the request and answer its questions."
        )
    version = session.get(FormVersion, draft.form_version_id)
    assert version is not None
    cleaned, errors = forms.clean(session, principal, version.schema, draft.answers, complete=True)
    if errors:
        raise Invalid("Some questions still need an answer.", errors)
    model = current_scoring(session)
    result = scoring.assess(model.definition, cleaned)
    values = forms.mapped(version.schema, cleaned)
    systems = values.pop("systems", None)
    with audit.operation(session, "use_case.submit"):
        try:
            records.update(session, principal, USE_CASE, use_case, values, version=use_case.version)
        except Invalid as exc:
            raise Invalid(
                "Some answers cannot be used.", _by_question(version.schema, exc.errors)
            ) from exc
        if systems is not None:
            records.set_systems(session, principal, use_case, systems)
        response = FormResponse(
            form_version_id=version.id,
            subject_type="use_case",
            subject_id=use_case.id,
            answers=cleaned,
            submitted_by=principal.account_id,
            submitted_at=utc_now(),
        )
        session.add(response)
        session.flush()
        assessment = _record(session, principal, use_case, model, result, response.id)
        use_case.status = "submitted"
        use_case.version += 1
        use_case.updated_at = utc_now()
        session.delete(draft)
        session.flush()
    return assessment


def _record(
    session: Session,
    principal: Principal,
    use_case: UseCase,
    model: ScoringModel,
    result: Mapping[str, Any],
    response_id: int | None,
) -> TierAssessment:
    assessment = TierAssessment(
        subject_type="use_case",
        subject_id=use_case.id,
        scoring_model_id=model.id,
        form_response_id=response_id,
        factors=result["factors"],
        total=result["total"],
        computed_tier=result["computed_tier"],
        floors=result["floors"],
        stops=result["stops"],
        final_tier=result["final_tier"],
        assessed_by=principal.account_id,
        assessed_at=utc_now(),
    )
    session.add(assessment)
    use_case.tier = result["final_tier"]
    use_case.tier_source = "computed"
    session.flush()
    return assessment


def latest_assessment(session: Session, use_case: UseCase) -> TierAssessment | None:
    return session.scalars(
        select(TierAssessment)
        .where(TierAssessment.subject_type == "use_case", TierAssessment.subject_id == use_case.id)
        .order_by(TierAssessment.id.desc())
    ).first()


def latest_response(session: Session, use_case: UseCase) -> FormResponse | None:
    return session.scalars(
        select(FormResponse)
        .where(FormResponse.subject_type == "use_case", FormResponse.subject_id == use_case.id)
        .order_by(FormResponse.id.desc())
    ).first()


def override_tier(
    session: Session, principal: Principal, use_case: UseCase, tier: int, reason: str
) -> TierAssessment:
    """Change the tier, up or down, with a written reason. The computed tier is kept beside
    the new one. Nobody changes the tier of their own request."""
    if not principal.reviews:
        raise PermissionDenied("Only a reviewer or governance can change a tier.")
    mine = use_case.created_by == principal.account_id or bool(
        access.owner_kinds(session, USE_CASE, use_case.id, principal.account_id)
    )
    if mine:
        raise PermissionDenied("You cannot change the tier of your own request.")
    previous = latest_assessment(session, use_case)
    if previous is None:
        raise Conflict("This use case has no tier yet. It is set when the request is submitted.")
    model = session.get(ScoringModel, previous.scoring_model_id)
    assert model is not None
    levels = scoring.tier_labels(model.definition)
    reason = reason.strip()
    errors = {}
    if tier not in levels:
        errors["tier"] = f"Choose one of: {', '.join(levels.values())}."
    elif tier == use_case.tier:
        errors["tier"] = "That is already its tier."
    if len(reason) < 10:
        errors["reason"] = "Say why, in a sentence, so that the record explains itself."
    if errors:
        raise Invalid("The tier was not changed.", errors)
    with audit.operation(session, "use_case.tier_override"):
        assessment = TierAssessment(
            subject_type="use_case",
            subject_id=use_case.id,
            scoring_model_id=model.id,
            form_response_id=previous.form_response_id,
            factors=previous.factors,
            total=previous.total,
            computed_tier=previous.computed_tier,
            floors=previous.floors,
            stops=previous.stops,
            final_tier=tier,
            override_reason=reason,
            overridden_by=principal.account_id,
            assessed_by=principal.account_id,
            assessed_at=utc_now(),
        )
        session.add(assessment)
        use_case.tier = tier
        use_case.tier_source = "override"
        use_case.version += 1
        use_case.updated_at = utc_now()
        session.flush()
    return assessment


def assessment_view(session: Session, assessment: TierAssessment | None) -> dict[str, Any] | None:
    """A tier with its reasons: each factor's level and what set it, floors, and stops."""
    if assessment is None:
        return None
    model = session.get(ScoringModel, assessment.scoring_model_id)
    assert model is not None
    definition = model.definition
    labels = scoring.tier_labels(definition)
    from govwren.db.models import Account

    overrider = session.get(Account, assessment.overridden_by) if assessment.overridden_by else None
    return {
        "scoring_version": model.version,
        "factors": [
            {
                "key": factor["key"],
                "label": factor["label"],
                "level": assessment.factors.get(factor["key"], {}).get("level", 0),
                "max": len(factor["levels"]) - 1,
                "reason": assessment.factors.get(factor["key"], {}).get("reason")
                or factor["levels"][0],
            }
            for factor in definition["factors"]
        ],
        "total": assessment.total,
        "max_total": sum(len(factor["levels"]) - 1 for factor in definition["factors"]),
        "computed_tier": assessment.computed_tier,
        "final_tier": assessment.final_tier,
        "tiers": [
            {
                "level": t["level"],
                "label": t["label"],
                "min": t["min"],
                "description": t.get("description"),
            }
            for t in definition["tiers"]
        ],
        "tier_label": labels.get(assessment.final_tier),
        "computed_label": labels.get(assessment.computed_tier),
        "floors": assessment.floors,
        "stops": assessment.stops,
        "override": {
            "reason": assessment.override_reason,
            "by": overrider.display_name if overrider else None,
        }
        if assessment.override_reason
        else None,
        "assessed_at": assessment.assessed_at,
    }


def view(session: Session, principal: Principal, use_case: UseCase) -> dict[str, Any]:
    """A request's form and answers: the draft being written, or what was submitted, always
    with the version of the form it was answered on."""
    if access.sight(session, principal, USE_CASE, use_case) != access.FULL:
        raise NotFound(f"There is no use case {use_case.ref}.")
    draft = _draft(session, use_case)
    response = latest_response(session, use_case)
    if draft is not None:
        version, answers, state = (
            session.get(FormVersion, draft.form_version_id),
            draft.answers,
            "draft",
        )
    elif response is not None and use_case.status not in OPEN:
        version, answers, state = (
            session.get(FormVersion, response.form_version_id),
            response.answers,
            "submitted",
        )
    else:
        version = current_form(session)
        linked = [
            system.ref for system in records.systems_of(session, [use_case.id]).get(use_case.id, [])
        ]
        answers = (
            response.answers
            if response is not None
            else forms.prefill(version.schema, use_case, linked)
        )
        state = "draft"
    assert version is not None
    model = current_scoring(session)
    return {
        "ref": use_case.ref,
        "state": state,
        "status": use_case.status,
        "can_edit": state == "draft" and access.can_edit(session, principal, USE_CASE, use_case),
        "form": {"key": INTAKE_FORM, "version": version.version, "schema": version.schema},
        "scoring": {"version": model.version, "definition": model.definition},
        "answers": answers,
        "progress": forms.progress(version.schema, answers),
        "assessment": assessment_view(session, latest_assessment(session, use_case)),
        "submitted_at": response.submitted_at
        if response is not None and state == "submitted"
        else None,
    }
