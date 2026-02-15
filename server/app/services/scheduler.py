"""
定时任务调度器

- 每日 00:00：信用点发放 + 过期记忆清理
- 使用 asyncio.sleep 实现，无外部依赖
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import update

from ..core.database import async_session
from ..models import Agent
from .memory_service import memory_service

logger = logging.getLogger(__name__)

DAILY_CREDIT_GRANT = 10
HUMAN_ID = 0


async def daily_grant(db_session_maker=None) -> int:
    """每日信用点发放，返回受影响的 Agent 数量"""
    maker = db_session_maker or async_session
    async with maker() as db:
        result = await db.execute(
            update(Agent)
            .where(Agent.id != HUMAN_ID)
            .values(credits=Agent.credits + DAILY_CREDIT_GRANT)
        )
        await db.commit()
        return result.rowcount


async def daily_memory_cleanup(db_session_maker=None) -> int:
    """清理过期短期记忆"""
    maker = db_session_maker or async_session
    async with maker() as db:
        count = await memory_service.cleanup_expired(db)
        return count


def _seconds_until_midnight() -> float:
    """计算到次日 00:00 UTC 的秒数"""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (tomorrow - now).total_seconds()


async def scheduler_loop():
    """主调度循环：等到午夜 → 执行任务 → 循环"""
    while True:
        wait = _seconds_until_midnight()
        logger.info("Scheduler: next run in %.0f seconds", wait)
        await asyncio.sleep(wait)
        try:
            granted = await daily_grant()
            logger.info("Daily grant: %d agents received %d credits", granted, DAILY_CREDIT_GRANT)
        except Exception as e:
            logger.error("Daily grant failed: %s", e)
        try:
            cleaned = await daily_memory_cleanup()
            logger.info("Memory cleanup: %d expired memories removed", cleaned)
        except Exception as e:
            logger.error("Memory cleanup failed: %s", e)
