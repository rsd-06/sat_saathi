"""Change and cross-modal analyses an account has run, for its history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from satsaathi_core.models import Analysis

from ..deps import Session, api_error
from ..schemas import AnalysisIn, AnalysisOut
from .auth import CurrentUser, current_user

router = APIRouter(
    prefix="/analyses", tags=["analyses"], dependencies=[Depends(current_user)]
)


@router.post("", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    session: Session, user: CurrentUser, body: AnalysisIn
) -> AnalysisOut:
    row = Analysis(user_id=user.id, method="browser-heuristic", **body.model_dump())
    session.add(row)
    await session.commit()
    return AnalysisOut.model_validate(row, from_attributes=True)


@router.get("", response_model=list[AnalysisOut])
async def list_analyses(
    session: Session, user: CurrentUser, limit: int = 50
) -> list[AnalysisOut]:
    rows = await session.scalars(
        select(Analysis)
        .where(Analysis.user_id == user.id)
        .order_by(Analysis.created_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    return [AnalysisOut.model_validate(r, from_attributes=True) for r in rows]


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    session: Session, user: CurrentUser, analysis_id: uuid.UUID
) -> None:
    row = await session.get(Analysis, analysis_id)
    if row is None or row.user_id != user.id:
        raise api_error(
            status.HTTP_404_NOT_FOUND, "analysis.not_found", id=str(analysis_id)
        )
    await session.delete(row)
    await session.commit()
