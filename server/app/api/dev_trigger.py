"""
开发用模拟消息触发器

POST /api/dev/trigger — 模拟发送消息并触发唤醒流程
POST /api/dev/trigger-batch-wakeup — 手动触发一次 hourly batch 唤醒
仅用于开发测试，生产环境应禁用。
"""
import asyncio
import logging
import random
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sql_update
from sqlalchemy.orm import joinedload
from ..core import get_db
from ..core.database import async_session
from ..models import Agent, Message
from .chat import (
    parse_mentions, get_agent_name_map, broadcast, handle_wakeup,
    human_connections, bot_connections, delayed_send, _background_tasks,
    wakeup_service,
)
from ..services.agent_runner import runner_manager
from ..services.economy_service import economy_service
from ..services import autonomy_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dev", tags=["dev"])


class TransferRequest(BaseModel):
    from_id: int
    to_id: int
    amount: int


class TriggerRequest(BaseModel):
    content: str
    sender: str = "Human"  # Agent 名称，默认 Human
    message_type: str = "chat"


class TriggerResponse(BaseModel):
    ok: bool
    message_id: int
    sender: str
    content: str
    mentions: list[int]


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_message(req: TriggerRequest, db: AsyncSession = Depends(get_db)):
    """模拟发送一条消息，走完整的持久化 + 广播 + 唤醒流程"""
    # 查找 sender agent
    result = await db.execute(select(Agent).where(Agent.name == req.sender))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{req.sender}' not found")

    sender_type = "human" if agent.id == 0 else "agent"

    # 解析 @提及
    name_map = await get_agent_name_map(db)
    mentions = parse_mentions(req.content, name_map)

    # 持久化
    msg = Message(
        agent_id=agent.id,
        sender_type=sender_type,
        message_type=req.message_type,
        content=req.content,
        mentions=mentions,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    # 广播
    await broadcast({
        "type": "new_message",
        "data": {
            "id": msg.id,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "sender_type": sender_type,
            "message_type": req.message_type,
            "content": req.content,
            "mentions": mentions,
            "created_at": str(msg.created_at),
        }
    })

    # 异步唤醒（加入 background_tasks 防止 GC 回收）
    task = asyncio.create_task(handle_wakeup(msg))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return TriggerResponse(
        ok=True,
        message_id=msg.id,
        sender=agent.name,
        content=req.content,
        mentions=mentions,
    )


@router.post("/trigger-batch-wakeup")
async def trigger_batch_wakeup():
    """手动触发一次 hourly batch 唤醒流程（跳过 1 小时等待）"""
    # 使用共享实例，保留频率控制计数器状态
    wakeup_svc = wakeup_service

    # 1. 选出应该发言的 Agent
    async with async_session() as db:
        online_ids = set(human_connections.keys()) | set(bot_connections.keys()) | {0}  # dev: 伪造 Human 在线
        wake_list = await wakeup_svc.scheduled_trigger(online_ids, db)

    if not wake_list:
        return {"ok": True, "wake_list": [], "dispatched": 0, "reason": "no agents to wake"}

    # 2. 收集 agent 信息 + 经济预检查
    agents_to_reply = []
    skipped = []
    async with async_session() as db:
        for agent_id in wake_list:
            if agent_id in bot_connections:
                skipped.append({"agent_id": agent_id, "reason": "bot_online"})
                continue

            agent = await db.get(Agent, agent_id)
            if not agent:
                skipped.append({"agent_id": agent_id, "reason": "not_found"})
                continue

            can_speak = await economy_service.check_quota(agent_id, "chat", db)
            if not can_speak.allowed:
                skipped.append({"agent_id": agent_id, "reason": "quota_denied"})
                continue

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
        return {
            "ok": True, "wake_list": wake_list,
            "dispatched": 0, "skipped": skipped,
            "reason": "no eligible agents after quota check",
        }

    # 3. Batch 推理
    results = await runner_manager.batch_generate(agents_to_reply)

    # 4. 错开 2-8s 随机延迟广播（dev 模式用更短延迟）
    dispatched = 0
    for info in agents_to_reply:
        aid = info["agent_id"]
        reply, usage_info = results.get(aid, (None, None))
        if not reply:
            continue
        delay = random.uniform(2, 8)
        task = asyncio.create_task(delayed_send(info, reply, usage_info, delay))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        dispatched += 1

    return {
        "ok": True,
        "wake_list": wake_list,
        "agents_to_reply": [i["agent_name"] for i in agents_to_reply],
        "dispatched": dispatched,
        "skipped": skipped,
    }


@router.post("/transfer")
async def dev_transfer(req: TransferRequest, db: AsyncSession = Depends(get_db)):
    """开发用：Agent 间转账"""
    ok = await economy_service.transfer_credits(req.from_id, req.to_id, req.amount, db)
    if not ok:
        raise HTTPException(400, "Transfer failed (insufficient credits or agent not found)")
    await db.commit()
    return {"ok": True, "from_id": req.from_id, "to_id": req.to_id, "amount": req.amount}


@router.post("/set-credits")
async def dev_set_credits(agent_id: int, credits: int, quota_used: int | None = None, db: AsyncSession = Depends(get_db)):
    """开发用：直接设置 Agent 信用点（用于测试经济边界条件）"""
    values = {"credits": credits}
    if quota_used is not None:
        values["quota_used_today"] = quota_used
    result = await db.execute(
        sql_update(Agent).where(Agent.id == agent_id).values(**values)
    )
    if result.rowcount == 0:
        raise HTTPException(404, "Agent not found")
    await db.commit()
    return {"ok": True, "agent_id": agent_id, "credits": credits}


@router.post("/trigger-autonomy")
async def trigger_autonomy():
    """手动触发一次 autonomy tick（跳过定时器等待）"""
    await autonomy_service.tick()
    return {"ok": True}
