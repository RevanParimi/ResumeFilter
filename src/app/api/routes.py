"""Ordered API composition; handlers and schemas live in product modules."""
from __future__ import annotations

from fastapi import APIRouter, Depends
# Compatibility aliases retain callable identity for existing route guards.
from app.api.auth import auth_router
from app.api.curation import router as curation_router
from app.api.operator import (
    metrics_router as operator_metrics_router, retention_router as operator_retention_router,
    router as operator_router,
)
from app.api.interviews import (
    candidate_router as interview_candidate_router, org_router as interview_org_router,
)
from app.api.verification import (
    candidate_router as verification_candidate_router, org_router as verification_org_router,
    router as verification_admin_router,
)
from app.api.employer import org_router as employer_router
from app.api.features import router as feature_router
from app.api.portal import candidate_router as portal_candidate_router, router as portal_admin_router
from app.api.ledger import (
    router as ledger_admin_router, org_router as ledger_org_router,
)
from app.api.screening import org_router as screening_router
from app.api.candidates import (
    router as candidate_admin_router,
)
from app.api.reports import (
    evaluation_router, report_router,
)
from app.api.dependencies import (
    PUBLIC_PATHS,
    require_any_principal, require_api_key, require_candidate, require_org,
)

from app.api.public import domain_router, public_router


# These aggregate names and guard aliases remain available to current callers.
# Extend existing APIRoutes to avoid adding inherited dependency contexts.
router = APIRouter(dependencies=[Depends(require_api_key)])
org_router = APIRouter()
candidate_router = APIRouter()

# Preserve the complete admin-plane registration order.
router.routes.extend(evaluation_router.routes)
router.routes.extend(candidate_admin_router.routes)
router.routes.extend(curation_router.routes)
router.routes.extend(ledger_admin_router.routes)
router.routes.extend(verification_admin_router.routes)
router.routes.extend(feature_router.routes)
router.routes.extend(report_router.routes)
router.routes.extend(operator_metrics_router.routes)
router.routes.extend(portal_admin_router.routes)
router.routes.extend(operator_retention_router.routes)
router.routes.extend(domain_router.routes)
router.routes.extend(operator_router.routes)

# Employer and candidate planes retain their original order and own guards.
org_router.routes.extend(screening_router.routes)
org_router.routes.extend(ledger_org_router.routes)
org_router.routes.extend(employer_router.routes)
org_router.routes.extend(verification_org_router.routes)
org_router.routes.extend(interview_org_router.routes)

candidate_router.routes.extend(portal_candidate_router.routes)
candidate_router.routes.extend(verification_candidate_router.routes)
candidate_router.routes.extend(interview_candidate_router.routes)
