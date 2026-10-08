"""Mentors catalog endpoints (public read)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.schemas.mentors import MentorItem, MentorListResponse
from backend.services import mentor_service

router = APIRouter(prefix="/mentors", tags=["Mentors"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=MentorListResponse, summary="List the mentor catalog")
async def list_mentors(
    db: DbSession,
    tag: Annotated[str | None, Query(description="Filter by topic tag")] = None,
) -> MentorListResponse:
    """Return active mentors plus the tier -> points pricing table."""
    mentors = await mentor_service.list_mentors(db, tag=tag)
    all_mentors = await mentor_service.list_mentors(db)
    return MentorListResponse(
        mentors=[MentorItem.model_validate(m) for m in mentors],
        total=len(mentors),
        tiers=mentor_service.tier_costs(all_mentors),
    )


@router.get("/{mentor_id}", response_model=MentorItem, summary="Get a single mentor")
async def get_mentor(mentor_id: int, db: DbSession) -> MentorItem:
    """Return one mentor by id."""
    mentor = await mentor_service.get_mentor(db, mentor_id)
    if mentor is None:
        raise HTTPException(status_code=404, detail="Mentor not found")
    return MentorItem.model_validate(mentor)
