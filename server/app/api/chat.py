import re
import json
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from ..core import get_db, async_session
from ..models import Message, Agent
from ..services.wakeup_service import WakeupService
from ..services.agent_runner import runner_manager
from .schemas import MessageOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# 连接池：人类支持多标签页，Bot 同一 agent_id 只允许一个
human_connections: dict[int, list[WebSocket]] = {}  # {0: [ws1, ws2, ...]}
bot_connections: dict[int, WebSocket] = {}  # {agent_id: ws}

# 心跳间隔（秒）
HEARTBEAT_INTERVAL = 30

# 唤醒服务单例
wakeup_service = WakeupService()


def parse_mentions(content: str, agent_names: dict[str, int]) -> list[int]:
    """解析 @提及，返回被提及的 agent_id 列表"""
    pattern = r'@([\w\u4e00-\u9fff]+)'
    matches = re.findall(pattern, content)
    return [agent_names[name] for name in matches if name in agent_names]


async def get_agent_name_map(db: AsyncSession) -> dict[str, int]:
    """获取 {agent_name: agent_id} 映射"""
    result = await db.execute(select(Agent.name, Agent.id))
    return {name: aid for name, aid in result.all()}


def _all_connections() -> list[tuple[int, WebSocket]]:
    """获取所有活跃连接（human + bot）的扁平列表"""
    conns = []
    for aid, ws_list in human_connections.items():
        for ws in ws_list:
            conns.append((aid, ws))
    for aid, ws in bot_connections.items():
        conns.append((aid, ws))
    return conns


async def broadcast(data: dict):
    """广播消息给所有在线连接（human + bot）"""
    text = json.dumps(data, ensure_ascii=False)
    for aid, ws in _all_connections():
        try:
            await ws.send_text(text)
        except Exception:
            # 清理失败的连接
            if aid in human_connections:
                try:
                    human_connections[aid].remove(ws)
                except ValueError:
                    pass
                if not human_connections[aid]:
                    human_connections.pop(aid, None)
            bot_connections.pop(aid, None)


async def broadcast_system_event(event: str, agent_id: int, agent_name: str):
    """广播系统事件（上线/下线）"""
    await broadcast({
        "type": "system_event",
        "data": {
            "event": event,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "timestamp": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }
    })


async def send_agent_message(agent_id: int, agent_name: str, content: str):
    """Agent 发送消息（持久化 + 广播）"""
    async with async_session() as db:
        name_map = await get_agent_name_map(db)
        mentions = parse_mentions(content, name_map)
        msg = Message(
            agent_id=agent_id,
            sender_type="agent",
            message_type="chat",
            content=content,
            mentions=mentions,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

    await broadcast({
        "type": "new_message",
        "data": {
            "id": msg.id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "sender_type": "agent",
            "message_type": "chat",
            "content": content,
            "mentions": mentions,
            "created_at": str(msg.created_at),
        }
    })
    return msg


async def handle_wakeup(message: Message):
    """异步唤醒处理：选人 → 如果 Bot 在线则跳过，否则 fallback 生成回复"""
    try:
        async with async_session() as db:
            online_ids = set(human_connections.keys()) | set(bot_connections.keys())
            wake_list = await wakeup_service.process(message, online_ids, db)

            if not wake_list:
                return

            for agent_id in wake_list:
                # Bot 在线 → 跳过，Bot 自己会处理
                if agent_id in bot_connections:
                    logger.info("Agent %d has bot online, skipping server-side reply", agent_id)
                    continue

                # Bot 不在线 → fallback 到服务端驱动
                agent = await db.get(Agent, agent_id)
                if not agent:
                    continue

                # 构建聊天历史给 runner
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

                runner = runner_manager.get_or_create(
                    agent.id, agent.name, agent.persona, agent.model
                )
                reply = await runner.generate_reply(history)
                if reply:
                    await send_agent_message(agent.id, agent.name, reply)

    except Exception as e:
        logger.error("Wakeup handling failed: %s", e)


@router.get("/messages", response_model=list[MessageOut])
async def get_messages(
    limit: int = 50,
    since_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Message).options(joinedload(Message.agent))

    if since_id is not None:
        # 增量拉取：返回 id > since_id 的消息，按 id 升序
        query = query.where(Message.id > since_id).order_by(Message.id.asc())
    else:
        # 默认：最新 N 条，按时间倒序
        query = query.order_by(Message.created_at.desc())

    query = query.limit(limit)
    result = await db.execute(query)
    messages = result.scalars().all()

    # since_id 模式已经是升序；默认模式需要 reverse
    if since_id is None:
        messages = list(reversed(messages))

    return [
        MessageOut(
            id=msg.id,
            agent_id=msg.agent_id,
            agent_name=msg.agent.name if msg.agent else "unknown",
            sender_type=msg.sender_type or "agent",
            message_type=msg.message_type or "chat",
            content=msg.content,
            mentions=msg.mentions or [],
            created_at=str(msg.created_at),
        )
        for msg in messages
    ]


async def _heartbeat(ws: WebSocket):
    """定期发送 ping，检测僵尸连接"""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            await ws.send_json({"type": "ping"})
    except Exception:
        pass  # 连接已断开，心跳自然停止


@router.websocket("/ws/{agent_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    agent_id: int,
    token: str | None = Query(default=None),
):
    # Bot 认证（需要先 accept 再 close，Starlette 不支持 accept 前 close）
    if agent_id != 0:
        if not token:
            await websocket.accept()
            await websocket.close(code=4003, reason="Bot token required")
            return
        async with async_session() as db:
            agent = await db.get(Agent, agent_id)
        if not agent or agent.bot_token != token:
            await websocket.accept()
            await websocket.close(code=4003, reason="Invalid bot token")
            return
        conn_type = "bot"
        agent_name = agent.name
    else:
        # 人类连接，无需 token
        async with async_session() as db:
            agent = await db.get(Agent, agent_id)
        if not agent:
            await websocket.accept()
            await websocket.close(code=4004, reason="Agent not found")
            return
        conn_type = "human"
        agent_name = agent.name

    await websocket.accept()

    # 连接池管理
    if conn_type == "bot":
        # 踢旧连接
        if agent_id in bot_connections:
            old_ws = bot_connections[agent_id]
            try:
                await old_ws.close(code=4001, reason="Replaced by new connection")
            except Exception:
                pass
        bot_connections[agent_id] = websocket
    else:
        # 人类支持多标签页
        if agent_id not in human_connections:
            human_connections[agent_id] = []
        human_connections[agent_id].append(websocket)

    # 启动心跳
    heartbeat_task = asyncio.create_task(_heartbeat(websocket))

    # 广播上线通知
    await broadcast_system_event("agent_online", agent_id, agent_name)

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            # 心跳 pong 响应，忽略
            if payload.get("type") == "pong":
                continue

            # 向后兼容：旧格式 {"content": "..."} 自动识别为 chat_message
            msg_type = payload.get("type", "chat_message")
            content = payload.get("content", "")
            message_type = payload.get("message_type", "chat")

            if msg_type != "chat_message" or not content.strip():
                continue

            # 判断 sender_type
            sender_type = "human" if agent_id == 0 else "agent"
            # 人类消息强制 message_type=work（TDD-001 规定）
            if sender_type == "human":
                message_type = "work"

            # 解析 @提及
            async with async_session() as db:
                name_map = await get_agent_name_map(db)
                mentions = parse_mentions(content, name_map)

                # 持久化消息
                msg = Message(
                    agent_id=agent_id,
                    sender_type=sender_type,
                    message_type=message_type,
                    content=content,
                    mentions=mentions,
                )
                db.add(msg)
                await db.commit()
                await db.refresh(msg)

            # 广播新消息
            await broadcast({
                "type": "new_message",
                "data": {
                    "id": msg.id,
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "sender_type": sender_type,
                    "message_type": message_type,
                    "content": content,
                    "mentions": mentions,
                    "created_at": str(msg.created_at),
                }
            })

            # 异步触发唤醒（不阻塞广播）
            asyncio.create_task(handle_wakeup(msg))

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        # 清理连接
        if conn_type == "bot":
            if bot_connections.get(agent_id) is websocket:
                bot_connections.pop(agent_id, None)
            runner_manager.remove(agent_id)
        else:
            if agent_id in human_connections:
                try:
                    human_connections[agent_id].remove(websocket)
                except ValueError:
                    pass
                if not human_connections[agent_id]:
                    human_connections.pop(agent_id, None)
        await broadcast_system_event("agent_offline", agent_id, agent_name)
