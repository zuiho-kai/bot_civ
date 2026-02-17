"""
定时任务调度器

- 每日 00:00：信用点发放 + 过期记忆清理
- 每小时：定时唤醒 batch 推理
- 使用 asyncio.sleep 实现，无外部依赖
"""
import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from ..core.database import async_session
from ..models import Agent, Message
from .memory_service import memory_service
from .wakeup_service import WakeupService
from .agent_runner import runner_manager
from .economy_service import economy_service
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


HOURLY_WAKEUP_INTERVAL = 3600  # 1 小时


async def hourly_wakeup_loop():
    """每小时定时唤醒：batch 推理 + 错开广播"""
    from ..api.chat import (
        human_connections, bot_connections, delayed_send,
        _background_tasks,
    )

    wakeup_svc = WakeupService()

    while True:
        await asyncio.sleep(HOURLY_WAKEUP_INTERVAL)
        try:
            logger.info("Hourly wakeup: starting batch trigger")

            # 1. 选出应该发言的 Agent
            async with async_session() as db:
                online_ids = set(human_connections.keys()) | set(bot_connections.keys())
                wake_list = await wakeup_svc.scheduled_trigger(online_ids, db)

            if not wake_list:
                logger.info("Hourly wakeup: no agents to wake")
                continue

            logger.info("Hourly wakeup: wake_list=%s", wake_list)

            # 2. 收集 agent 信息 + 经济预检查
            agents_to_reply = []
            async with async_session() as db:
                for agent_id in wake_list:
                    # Bot 在线 → 跳过
                    if agent_id in bot_connections:
                        continue

                    agent = await db.get(Agent, agent_id)
                    if not agent:
                        continue

                    can_speak = await economy_service.check_quota(agent_id, "chat", db)
                    if not can_speak.allowed:
                        logger.debug("Hourly wakeup: agent %d quota denied", agent_id)
                        continue

                    # 构建聊天历史
                    recent = await db.execute(
                        select(Message)
                        .options(joinedload(Message.agent))
                        .order_by(Message.created_at.desc())
                        .limit(10)
                    )
                    history = [
                        {
                            "name": m.agent.name if m.agent else "unknown",
                            "content": m.content,
                        }
                        for m in reversed(recent.scalars().all())
                    ]

                    agents_to_reply.append({
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "persona": agent.persona,
                        "model": agent.model,
                        "history": history,
                    })

            if not agents_to_reply:
                logger.info("Hourly wakeup: no eligible agents after quota check")
                continue

            # 3. Batch 推理（按模型分组并发，每个协程独立 session）
            results = await runner_manager.batch_generate(agents_to_reply)

            # 4. 错开 5-30s 随机延迟广播
            for info in agents_to_reply:
                aid = info["agent_id"]
                reply, usage_info = results.get(aid, (None, None))
                if not reply:
                    continue
                delay = random.uniform(5, 30)
                task = asyncio.create_task(
                    delayed_send(info, reply, usage_info, delay)
                )
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)

            logger.info(
                "Hourly wakeup: dispatched %d replies with random delays",
                sum(1 for aid in results if results[aid][0]),
            )

        except Exception as e:
            logger.error("Hourly wakeup failed: %s", e, exc_info=True)


AUTONOMY_INTERVAL = 3600  # 1 小时


async def autonomy_loop():
    """Agent 自主行为定时循环。

    - 启动后等 60s（让系统初始化完成）
    - 每小时触发一次 autonomy_service.tick()
    - 加 0-120s 随机抖动，避免与 hourly_wakeup_loop 完全同步
    """
    await asyncio.sleep(60)
    while True:
        jitter = random.randint(0, 120)
        await asyncio.sleep(jitter)
        try:
            await autonomy_service.tick()
        except Exception as e:
            logger.error("autonomy_loop failed: %s", e, exc_info=True)
        await asyncio.sleep(AUTONOMY_INTERVAL - jitter)
