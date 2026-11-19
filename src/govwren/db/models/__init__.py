"""Every ORM model. Importing this package registers them all on ``Base.metadata``."""

from __future__ import annotations

from govwren.db.models.evidence import Evidence, EvidenceLink, StoredFile
from govwren.db.models.intake import (
    Form,
    FormResponse,
    FormVersion,
    IntakeDraft,
    ScoringModel,
    TierAssessment,
)
from govwren.db.models.inventory import (
    Agreement,
    AISystem,
    Dataset,
    ExternalRef,
    Model,
    RecordLink,
    RecordOwner,
    UseCase,
    Vendor,
)
from govwren.db.models.people import (
    Account,
    Credential,
    FailedSignIn,
    Identity,
    Membership,
    OrgUnit,
    ProviderMapping,
    RoleGrant,
    SessionToken,
    SignInRequest,
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
    "Agreement",
    "ChainHead",
    "Comment",
    "Condition",
    "Counter",
    "Credential",
    "Dataset",
    "Decision",
    "Event",
    "Evidence",
    "EvidenceLink",
    "ExternalRef",
    "FailedSignIn",
    "Form",
    "FormResponse",
    "FormVersion",
    "Identity",
    "IntakeDraft",
    "Membership",
    "Model",
    "Notification",
    "OrgUnit",
    "ProviderMapping",
    "RecordLink",
    "RecordOwner",
    "Review",
    "ReviewTask",
    "RoleGrant",
    "RuleSet",
    "ScoringModel",
    "SessionToken",
    "Setting",
    "SignInRequest",
    "StoredFile",
    "TierAssessment",
    "UseCase",
    "Vendor",
]
