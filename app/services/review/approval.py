"""Bind approval to the draft contents, excluding review/audit bookkeeping."""

from app.core.hashing import content_hash
from app.schemas.snapshots import FinalCaseSnapshot


def approval_hash(snapshot: FinalCaseSnapshot) -> str:
    payload = snapshot.model_dump(mode="json")
    payload.pop("human_reviews")
    payload.pop("audit_metadata")
    payload["finalized"] = False
    payload["recommendation"] = {**payload["recommendation"], "status": "draft"}
    return content_hash(payload)


def require_governed_bo(session, case_id):
    """Fail closed for a case whose latest BO is exploratory, including direct finalization."""
    from app.services.bo.handoff import latest_for_case
    from app.services.review.workflow import SignOffRequiredError
    latest = latest_for_case(session, case_id)
    if latest is not None and latest.payload.get('validators_enforced', True) is False:
        raise SignOffRequiredError('Exploratory Business Overview analyses cannot receive final approval. Run Standard Mode first.')
