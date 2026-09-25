"""The queue of answers a specialist has to look at before release."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from satsaathi_core.models import Job, JobStatus, ReviewItem, ReviewStatus

from ..deps import Session, api_error
from ..schemas import ReviewDecisionIn, ReviewOut
from .auth import CurrentUser, current_user

# Everything here is somebody's own work, so all of it needs an account.
router = APIRouter(prefix="/review", tags=["review"], dependencies=[Depends(current_user)])

_DECISION_STATUS = {
    "approve": ReviewStatus.approved,
    "edit": ReviewStatus.edited,
    "reject": ReviewStatus.rejected,
}


@router.get("", response_model=list[ReviewOut])
async def list_review(
    session: Session, user: CurrentUser, pending_only: bool = True
) -> list[ReviewOut]:
    stmt = (
        select(ReviewItem, Job).join(Job, ReviewItem.job_id == Job.id).where(Job.user_id == user.id)
    )
    if pending_only:
        stmt = stmt.where(ReviewItem.status == ReviewStatus.pending)

    rows = (await session.execute(stmt.order_by(ReviewItem.created_at.desc()))).all()
    return [
        ReviewOut(
            id=item.id,
            job_id=item.job_id,
            reason=item.reason,
            status=item.status.value,
            reviewer_note=item.reviewer_note,
            edited_answer=item.edited_answer,
            confidence=job.confidence,
            query_text=job.query_text,
            created_at=item.created_at,
            resolved_at=item.resolved_at,
        )
        for item, job in rows
    ]


@router.post("/{job_id}", response_model=ReviewOut)
async def decide(
    session: Session, user: CurrentUser, job_id: uuid.UUID, body: ReviewDecisionIn
) -> ReviewOut:
    """Release, amend or reject a held answer.

    Editing replaces the answer the officer sees but never rewrites the trace:
    what the pipeline actually did stays on the record, with the reviewer's
    version recorded alongside it.
    """
    result = await session.scalars(
        select(ReviewItem)
        .join(Job, ReviewItem.job_id == Job.id)
        .where(ReviewItem.job_id == job_id, Job.user_id == user.id)
    )
    item = result.first()
    if item is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "review.not_found", job_id=str(job_id))
    if item.status != ReviewStatus.pending:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "review.already_resolved",
            resolved_as=item.status.value,
        )

    job = await session.get(Job, job_id)
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "job.not_found", id=str(job_id))

    edited = body.edited_answer
    if body.decision == "edit" and not edited:
        raise api_error(status.HTTP_400_BAD_REQUEST, "review.error.editNeedsAnswer")

    item.status = _DECISION_STATUS[body.decision]
    item.reviewer_note = body.note
    item.edited_answer = edited
    item.resolved_at = datetime.now(UTC)

    if body.decision == "approve":
        job.status = JobStatus.succeeded
    elif body.decision == "edit":
        job.status = JobStatus.succeeded
        job.answer = {**(job.answer or {}), **(edited or {}), "edited": True}
    else:
        job.status = JobStatus.failed
        job.error = {"key": "review.rejected", "params": {}}

    await session.flush()

    return ReviewOut(
        id=item.id,
        job_id=item.job_id,
        reason=item.reason,
        status=item.status.value,
        reviewer_note=item.reviewer_note,
        edited_answer=item.edited_answer,
        confidence=job.confidence,
        query_text=job.query_text,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )
