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
from ..models import Message, Agent, MemoryReference
from ..services.wakeup_service import WakeupService
from ..services.agent_runner import runner_manager
from ..services.economy_service import economy_service
from ..services.memory_service import memory_service
from ..models import MemoryType
from .schemas import MessageOut
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# prevent fire-and-forget tasks from being GC'd
_background_tasks: set[asyncio.Task] = set()

# 连接池：人类支持多标签页，Bot 同一 agent_id 只允许一个
human_connections: dict[int, list[WebSocket]] = {}  # {0: [ws1, ws2, ...]}
bot_connections: dict[int, WebSocket] = {}  # {agent_id: ws}

# 心跳间隔（秒）
HEARTBEAT_INTERVAL = 30

# 唤醒服务单例
wakeup_service = WakeupService()

# M2-4: 每 agent 回复计数器，每 EXTRACT_EVERY 条触发记忆提取
# 注意：仅在 bot 不在线（服务端 fallback 生成回复）时触发，bot 在线时由 bot 自行处理记忆
EXTRACT_EVERY = 5
_agent_reply_counts: dict[int, int] = {}

# M6.2-P1: LLM 记忆摘要
MEMORY_SUMMARY_TIMEOUT = 15  # 秒
MEMORY_SUMMARY_PROMPT = """你是一个记忆提取助手。请从以下对话中提取值得记住的关键信息。

要求：
- 提取关键事实、用户偏好、承诺、重要决定
- 忽略寒暄、问候、无实质内容的闲聊
- 用第三人称陈述句，每条信息独立完整
- 如果对话没有值得记住的内容，返回"无有效记忆"
- 输出不超过100字

对话内容：
{conversation}

请输出摘要："""


def _truncation_fallback(conversation: str) -> str:
    """截断拼接兜底（与原逻辑一致）"""
    return f"对话摘要: {conversation[:200]}"


async def _call_llm_provider(provider, prompt: str) -> str:
    """调用单个 LLM provider，返回文本结果"""
    async with AsyncOpenAI(
        api_key=provider.get_auth_token(),
        base_url=provider.get_base_url(),
    ) as client:
        response = await client.chat.completions.create(
            model=provider.model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,  # 100 字 ≈ 150~200 token
        )
        if not response.choices:
            return ""
        content = response.choices[0].message.content or ""
        return content.strip()


async def _llm_summarize(conversation: str) -> str | None:
    """
    调用 LLM 生成对话摘要，带 fallback 链：
    1. memory-summary-model 主供应商
    2. memory-summary-model 备用供应商
    3. 截断拼接兜底
    返回 None 表示"无有效记忆"，调用方跳过保存。
    """
    from ..core.config import MODEL_REGISTRY

    prompt = MEMORY_SUMMARY_PROMPT.format(conversation=conversation)

    entry = MODEL_REGISTRY.get("memory-summary-model")
    if not entry:
        logger.warning("memory-summary-model not in MODEL_REGISTRY, using truncation fallback")
        return _truncation_fallback(conversation)

    for i, provider in enumerate(entry.providers):
        if not provider.is_available():
            continue
        try:
            summary = await asyncio.wait_for(
                _call_llm_provider(provider, prompt),
                timeout=MEMORY_SUMMARY_TIMEOUT,
            )
            if summary and len(summary.strip()) >= 5:
                cleaned = summary.strip()
                if "无有效记忆" in cleaned:
                    logger.info("LLM determined no useful memory in conversation")
                    return None
                return cleaned[:100]
            else:
                logger.warning(
                    "Memory summary validation failed (provider=%s, attempt=%d, len=%d), trying next",
                    provider.name, i + 1, len(summary.strip()) if summary else 0,
                )
                continue
        except asyncio.TimeoutError:
            logger.warning(
                "Memory summary timeout (provider=%s, attempt=%d, limit=%ds), trying next",
                provider.name, i + 1, MEMORY_SUMMARY_TIMEOUT,
            )
            continue
        except Exception as e:
            logger.warning(
                "Memory summary failed (provider=%s, attempt=%d): %s, trying next",
                provider.name, i + 1, e,
            )
            continue

    logger.warning("All memory summary providers failed, using truncation fallback")
    return _truncation_fallback(conversation)


async def _extract_memory(agent_id: int, recent_messages: list[dict]):
    """每 EXTRACT_EVERY 轮对话自动摘要为短期记忆"""
    count = _agent_reply_counts.get(agent_id, 0) + 1
    _agent_reply_counts[agent_id] = count
    if count % EXTRACT_EVERY != 0:
        return
    if len(recent_messages) < EXTRACT_EVERY:
        return
    try:
        combined = "\n".join(
            f"{m.get('name', '?')}: {m.get('content', '')}"
            for m in recent_messages[-EXTRACT_EVERY:]
        )
        summary = await _llm_summarize(combined)
        if summary is None:
            return  # LLM 判断无需记忆，跳过
        async with async_session() as db:
            await memory_service.save_memory(agent_id, summary, MemoryType.SHORT, db)
        logger.info("Memory extracted for agent %d (reply #%d): %s", agent_id, count, summary[:50])
    except Exception as e:
        logger.warning("Memory extraction failed for agent %d: %s", agent_id, e)


async def delayed_send(agent_info: dict, reply: str, usage_info: dict | None, delay: float, used_memory_ids: list[int] | None = None):
    """延迟发送 Agent 回复（batch 模式下错开广播时间）"""
    await asyncio.sleep(delay)
    history = list(agent_info["history"])  # 防御性拷贝
    try:
        async with async_session() as db:
            msg = await send_agent_message(agent_info["agent_id"], agent_info["agent_name"], reply, db)
            await economy_service.deduct_quota(agent_info["agent_id"], db)
            if usage_info:
                from ..models.tables import LLMUsage
                record = LLMUsage(
                    model=usage_info["model"],
                    agent_id=usage_info["agent_id"],
                    prompt_tokens=usage_info["prompt_tokens"],
                    completion_tokens=usage_info["completion_tokens"],
                    total_tokens=usage_info["total_tokens"],
                    latency_ms=usage_info["latency_ms"],
                )
                db.add(record)
            # 写入记忆引用
            if used_memory_ids and msg:
                for mid in used_memory_ids:
                    db.add(MemoryReference(message_id=msg.id, memory_id=mid))
            await db.commit()

        # 记忆提取（fire-and-forget，不阻塞消息发送）
        history.append({"name": agent_info["agent_name"], "content": reply})
        task = asyncio.create_task(
            _extract_memory(agent_info["agent_id"], history)
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        logger.info("Delayed send completed for agent %s (delay=%.1fs)", agent_info["agent_name"], delay)
    except Exception as e:
        logger.error("Delayed send failed for agent %s: %s", agent_info["agent_name"], e, exc_info=True)


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
        except Exception as e:
            logger.warning("broadcast send failed for agent_id=%s: %s", aid, e)
            # 清理失败的连接
            if aid in human_connections:
                try:
                    human_connections[aid].remove(ws)
                except ValueError:
                    pass
                if not human_connections[aid]:
                    human_connections.pop(aid, None)
            elif aid in bot_connections and bot_connections[aid] is ws:
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


async def send_agent_message(agent_id: int, agent_name: str, content: str, db: AsyncSession):
    """Agent 发送消息（持久化 + 广播），调用方负责 commit"""
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
    await db.flush()
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
        # 第一阶段：读取数据（短时间持有数据库会话）
        wake_list = []
        agents_to_reply = []

        async with async_session() as db:
            online_ids = set(human_connections.keys()) | set(bot_connections.keys())
            logger.debug("Wakeup: online_ids=%s", online_ids)
            wake_list = await wakeup_service.process(message, online_ids, db)
            logger.debug("Wakeup: wake_list=%s", wake_list)

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
                    logger.warning("Wakeup: agent %d not found in db", agent_id)
                    continue

                # 经济预检查
                can_speak = await economy_service.check_quota(agent_id, "chat", db)
                if not can_speak.allowed:
                    logger.debug("Wakeup: agent %d quota denied: %s", agent_id, can_speak.reason)
                    continue

                logger.debug("Wakeup: generating reply for agent %d (%s)", agent_id, agent.name)

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

                agents_to_reply.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "persona": agent.persona,
                    "model": agent.model,
                    "history": history,
                })
        # 数据库会话已关闭，释放锁

        # 第二阶段：LLM 调用（记忆注入需要短暂 db 访问）
        for agent_info in agents_to_reply:
            runner = runner_manager.get_or_create(
                agent_info["agent_id"],
                agent_info["agent_name"],
                agent_info["persona"],
                agent_info["model"]
            )
            async with async_session() as mem_db:
                reply, usage_info, used_memory_ids = await runner.generate_reply(
                    agent_info["history"], db=mem_db
                )
            logger.info("Agent %s generated reply", agent_info["agent_name"])

            # 第三阶段：保存结果（创建新的数据库会话，一次性写入所有数据）
            if reply:
                async with async_session() as db:
                    msg = await send_agent_message(agent_info["agent_id"], agent_info["agent_name"], reply, db)
                    await economy_service.deduct_quota(agent_info["agent_id"], db)
                    if usage_info:
                        from ..models.tables import LLMUsage
                        record = LLMUsage(
                            model=usage_info["model"],
                            agent_id=usage_info["agent_id"],
                            prompt_tokens=usage_info["prompt_tokens"],
                            completion_tokens=usage_info["completion_tokens"],
                            total_tokens=usage_info["total_tokens"],
                            latency_ms=usage_info["latency_ms"],
                        )
                        db.add(record)
                    # 写入记忆引用
                    if used_memory_ids and msg:
                        for mid in used_memory_ids:
                            db.add(MemoryReference(message_id=msg.id, memory_id=mid))
                    await db.commit()

                # M2-4: 异步记忆提取（fire-and-forget）
                # 将 Agent 回复追加到 history，确保摘要包含完整对话
                agent_info["history"].append({"name": agent_info["agent_name"], "content": reply})
                task = asyncio.create_task(
                    _extract_memory(agent_info["agent_id"], agent_info["history"])
                )
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)

    except Exception as e:
        logger.error("Wakeup handling failed: %s", e, exc_info=True)


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
            task = asyncio.create_task(handle_wakeup(msg))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        # 清理连接
        if conn_type == "bot":
            if bot_connections.get(agent_id) is websocket:
                bot_connections.pop(agent_id, None)
            runner_manager.remove(agent_id)
            _agent_reply_counts.pop(agent_id, None)
        else:
            if agent_id in human_connections:
                try:
                    human_connections[agent_id].remove(websocket)
                except ValueError:
                    pass
                if not human_connections[agent_id]:
                    human_connections.pop(agent_id, None)
        await broadcast_system_event("agent_offline", agent_id, agent_name)
