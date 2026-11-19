"""Every ORM model. Importing this package registers them all on ``Base.metadata``."""

from __future__ import annotations

from govwren.db.models.intake import (
    Form,
    FormResponse,
    FormVersion,
    IntakeDraft,
    ScoringModel,
    TierAssessment,
)
from govwren.db.models.inventory import AISystem, RecordLink, RecordOwner, UseCase, Vendor
from govwren.db.models.people import (
    Account,
    Credential,
    FailedSignIn,
    Membership,
    OrgUnit,
    RoleGrant,
    SessionToken,
)
from govwren.db.models.program import Setting
from govwren.db.models.review import (
    Comment,
    Condition,
    Decision,
    Notification,
    Review,
    ReviewTask,
    RuleSet,
)
from govwren.db.models.system import ChainHead, Counter, Event

__all__ = [
    "AISystem",
    "Account",
    "ChainHead",
    "Comment",
    "Condition",
    "Counter",
    "Credential",
    "Decision",
    "Event",
    "FailedSignIn",
    "Form",
    "FormResponse",
    "FormVersion",
    "IntakeDraft",
    "Membership",
    "Notification",
    "OrgUnit",
    "RecordLink",
    "RecordOwner",
    "Review",
    "ReviewTask",
    "RoleGrant",
    "RuleSet",
    "ScoringModel",
    "SessionToken",
    "Setting",
    "TierAssessment",
    "UseCase",
    "Vendor",
]
