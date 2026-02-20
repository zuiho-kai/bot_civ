import enum
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.sql import func
from typing import Optional

from ..core import get_db
from ..models import Bounty, Agent
from .schemas import BountyCreate, BountyOut


class BountyStatus(str, enum.Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    COMPLETED = "completed"


VALID_STATUSES = {s.value for s in BountyStatus}

router = APIRouter(prefix="/bounties", tags=["bounties"])


@router.post("/", response_model=BountyOut, status_code=201)
async def create_bounty(data: BountyCreate, db: AsyncSession = Depends(get_db)):
    bounty = Bounty(title=data.title, description=data.description, reward=data.reward)
    db.add(bounty)
    await db.commit()
    await db.refresh(bounty)
    return bounty


@router.get("/", response_model=list[BountyOut])
async def list_bounties(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    if status and status not in VALID_STATUSES:
        raise HTTPException(422, f"Invalid status '{status}', must be one of: {', '.join(VALID_STATUSES)}")
    stmt = select(Bounty)
    if status:
        stmt = stmt.where(Bounty.status == status)
    stmt = stmt.order_by(Bounty.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{bounty_id}/claim", response_model=BountyOut)
async def claim_bounty_endpoint(
    bounty_id: int,
    agent_id: int = Query(...),  # 注意：当前无鉴权，内部系统调用；引入用户系统后需加 auth middleware
    db: AsyncSession = Depends(get_db),
):
    from ..services.bounty_service import claim_bounty
    result = await claim_bounty(
        agent_id=agent_id, bounty_id=bounty_id, db=db,
    )
    if not result["ok"]:
        reason = result["reason"]
        if "不存在" in reason:
            raise HTTPException(404, reason)
        else:
            raise HTTPException(409, reason)
    await db.commit()
    bounty = await db.get(Bounty, bounty_id)
    return bounty


@router.post("/{bounty_id}/complete", response_model=BountyOut)
async def complete_bounty(bounty_id: int, agent_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    bounty = await db.get(Bounty, bounty_id)
    if not bounty:
        raise HTTPException(404, "Bounty not found")
    if bounty.status != "claimed":
        raise HTTPException(409, "Bounty is not in claimed status")
    if bounty.claimed_by != agent_id:
        raise HTTPException(403, "Only the claiming agent can complete this bounty")

    # Atomic status transition: claimed → completed
    result = await db.execute(
        update(Bounty)
        .where(Bounty.id == bounty_id, Bounty.status == "claimed", Bounty.claimed_by == agent_id)
        .values(status="completed", completed_at=func.now())
    )
    if result.rowcount == 0:
        raise HTTPException(409, "Bounty completion failed (concurrent modification)")

    # Atomic credits award
    await db.execute(
        update(Agent)
        .where(Agent.id == agent_id)
        .values(credits=Agent.credits + bounty.reward)
    )

    await db.commit()
    await db.refresh(bounty)
    return bounty
