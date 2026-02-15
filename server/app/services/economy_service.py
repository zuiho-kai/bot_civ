from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Agent

HUMAN_ID = 0


@dataclass
class CanSpeakResult:
    allowed: bool
    reason: str


class EconomyService:

    async def _reset_if_needed(self, agent: Agent) -> None:
        if agent.quota_reset_date != date.today():
            agent.quota_used_today = 0
            agent.quota_reset_date = date.today()

    async def check_quota(
        self, agent_id: int, message_type: str, db: AsyncSession
    ) -> CanSpeakResult:
        if agent_id == HUMAN_ID:
            return CanSpeakResult(True, "human")
        if message_type == "work":
            return CanSpeakResult(True, "work is free")

        agent = await db.get(Agent, agent_id)
        if agent is None:
            return CanSpeakResult(False, "agent not found")

        await self._reset_if_needed(agent)

        if agent.quota_used_today < agent.daily_free_quota:
            return CanSpeakResult(True, "free quota available")
        if agent.credits > 0:
            return CanSpeakResult(True, "credits available")
        return CanSpeakResult(False, "no quota or credits left")

    async def deduct_quota(self, agent_id: int, db: AsyncSession) -> None:
        if agent_id == HUMAN_ID:
            return
        agent = await db.get(Agent, agent_id)
        if agent is None:
            return

        await self._reset_if_needed(agent)

        if agent.quota_used_today < agent.daily_free_quota:
            agent.quota_used_today += 1
        else:
            agent.credits = max(agent.credits - 1, 0)

    async def transfer_credits(
        self, from_id: int, to_id: int, amount: int, db: AsyncSession
    ) -> bool:
        if amount <= 0:
            return False
        sender = await db.get(Agent, from_id)
        receiver = await db.get(Agent, to_id)
        if sender is None or receiver is None:
            return False
        if sender.credits < amount:
            return False
        sender.credits -= amount
        receiver.credits += amount
        return True

    async def get_balance(self, agent_id: int, db: AsyncSession) -> dict | None:
        agent = await db.get(Agent, agent_id)
        if agent is None:
            return None
        await self._reset_if_needed(agent)
        return {
            "credits": agent.credits,
            "daily_free_quota": agent.daily_free_quota,
            "quota_used_today": agent.quota_used_today,
            "free_remaining": max(agent.daily_free_quota - agent.quota_used_today, 0),
        }


economy_service = EconomyService()
