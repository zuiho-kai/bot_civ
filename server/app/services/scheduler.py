"""
定时任务调度器

- 每日 00:00：信用点发放 + 过期记忆清理
- 每小时：autonomy tick（行为决策 + 聊天，统一循环）
- 使用 asyncio.sleep 实现，无外部依赖
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import update

from ..core.database import async_session
from ..models import Agent
from .memory_service import memory_service
from . import autonomy_service

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
        try:
            from .city_service import daily_attribute_decay
            async with async_session() as db:
                await daily_attribute_decay(db)
            logger.info("Daily attribute decay completed")
        except Exception as e:
            logger.error("Daily attribute decay failed: %s", e)
        try:
            from .city_service import production_tick
            async with async_session() as db:
                await production_tick("长安", db)
            logger.info("Daily production tick completed")
        except Exception as e:
            logger.error("Production tick failed: %s", e)


AUTONOMY_INTERVAL = 3600  # 1 小时


async def autonomy_loop():
    """Agent 自主行为定时循环（含聊天 + 游戏行为）。

    - 启动后等 60s（让系统初始化完成）
    - 每小时触发一次 autonomy_service.tick()
    """
    await asyncio.sleep(60)
    while True:
        try:
            await autonomy_service.tick()
        except Exception as e:
            logger.error("autonomy_loop failed: %s", e, exc_info=True)
        await asyncio.sleep(AUTONOMY_INTERVAL)
