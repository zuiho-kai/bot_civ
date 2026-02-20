"""
悬赏业务服务 (M6.2 P3)

从 bounties.py API 层抽取的业务逻辑，供 autonomy_service 和 tool_registry 复用。
事务策略：只 flush 不 commit，由调用方控制事务边界（ADR-2）。
"""
import logging

from sqlalchemy import select, update, exists
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tables import Bounty, Agent

logger = logging.getLogger(__name__)


async def claim_bounty(
    agent_id: int,
    bounty_id: int,
    *,
    db: AsyncSession,
) -> dict:
    """
    接取悬赏。原子校验 + 状态变更，不自行 commit。

    返回值（只使用不可变字段，不依赖 CAS 后的 ORM 缓存）：
        成功：{"ok": True, "bounty_id": int, "title": str, "reward": int}
        失败：{"ok": False, "reason": str}
    """
    # 1. 查询 Bounty
    bounty = await db.get(Bounty, bounty_id)
    if not bounty:
        return {"ok": False, "reason": "悬赏不存在"}

    # 2. 查询 Agent
    agent = await db.get(Agent, agent_id)
    if not agent:
        return {"ok": False, "reason": "居民不存在"}

    # 3. 原子 CAS 更新（先到先得 + DC-8 同时最多 1 个悬赏）
    #    NOT EXISTS 子查询确保即使并发场景下也不会违反 DC-8 约束
    result = await db.execute(
        update(Bounty)
        .where(
            Bounty.id == bounty_id,
            Bounty.status == "open",
            ~exists(
                select(Bounty.id).where(
                    Bounty.claimed_by == agent_id,
                    Bounty.status == "claimed",
                )
            ),
        )
        .values(status="claimed", claimed_by=agent_id)
    )
    if result.rowcount == 0:
        # 区分失败原因：是悬赏已被抢还是 agent 已有进行中悬赏
        active_result = await db.execute(
            select(
                exists(
                    select(Bounty.id).where(
                        Bounty.claimed_by == agent_id,
                        Bounty.status == "claimed",
                    )
                )
            )
        )
        has_active = active_result.scalar()
        if has_active:
            return {"ok": False, "reason": "你已有进行中的悬赏，完成后才能接取新的"}
        return {"ok": False, "reason": "该悬赏已被接取或不再开放"}

    # 4. flush 刷新状态，不 commit（调用方负责）
    await db.flush()

    return {
        "ok": True,
        "bounty_id": bounty_id,
        "title": bounty.title,
        "reward": bounty.reward,
    }
