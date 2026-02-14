"""
开发用模拟消息触发器

POST /api/dev/trigger — 模拟发送消息并触发唤醒流程
仅用于开发测试，生产环境应禁用。
"""
import asyncio
import logging
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core import get_db
from ..core.database import async_session
from ..models import Agent, Message
from .chat import parse_mentions, get_agent_name_map, broadcast, handle_wakeup

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dev", tags=["dev"])


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
        from fastapi import HTTPException
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

    # 异步唤醒
    asyncio.create_task(handle_wakeup(msg))

    return TriggerResponse(
        ok=True,
        message_id=msg.id,
        sender=agent.name,
        content=req.content,
        mentions=mentions,
    )
