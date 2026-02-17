"""
Agent 自主行为引擎 (M4)

每小时一次：构建世界状态快照 → 单次 LLM 决策 → 逐条执行 → 广播事件
"""
import json
import logging
import asyncio
import random
from datetime import datetime, timezone

from openai import AsyncOpenAI
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..core.config import resolve_model
from ..core.database import async_session
from ..models import Agent, Message, Job, CheckIn, VirtualItem, AgentItem
from .work_service import work_service
from .shop_service import shop_service
from .economy_service import economy_service
from .agent_runner import runner_manager

logger = logging.getLogger(__name__)

# 上一轮行为日志（内存缓存，重启丢失可接受）
_last_round_log: list[dict] = []
_round_log_lock = asyncio.Lock()

AUTONOMY_MODEL = "wakeup-model"  # 复用免费小模型做决策

SYSTEM_PROMPT = """你是一个虚拟城市的模拟器。你的任务是根据当前世界状态，为每个居民决定下一步行为。

规则：
1. 每个居民只能选择一个行为：checkin（打卡上班）、purchase（购买商品）、chat（发言聊天）、rest（休息）
2. 行为必须合理：
   - 已打卡的不能重复打卡
   - 余额不足的不能购买
   - 行为应符合居民的性格特征
3. 不是所有人每小时都要行动，rest 是合理选择
4. 聊天内容不需要你生成，只需决定谁要聊天

输出格式：纯 JSON 数组，不要包含 markdown 代码块，每个元素：
{"agent_id": <int>, "action": "<checkin|purchase|chat|rest>", "params": {}, "reason": "<一句话理由>"}

params 说明：
- checkin: {}（岗位由系统自动匹配）
- purchase: {"item_id": <int>}
- chat: {}
- rest: {}"""


async def build_world_snapshot(db: AsyncSession) -> str:
    """构建世界状态快照，返回结构化文本。"""
    now = datetime.now(timezone.utc)
    today_utc = sa_func.date("now")

    # 1. 所有非人类 Agent
    result = await db.execute(select(Agent).where(Agent.id != 0))
    agents = result.scalars().all()
    if not agents:
        return ""

    # 2. 每个 Agent 的今日打卡状态
    checkin_result = await db.execute(
        select(CheckIn.agent_id)
        .where(sa_func.date(CheckIn.checked_at) == today_utc)
    )
    checked_in_agents = {row[0] for row in checkin_result.all()}

    # 3. 每个 Agent 持有的物品
    items_result = await db.execute(
        select(AgentItem.agent_id, VirtualItem.name)
        .join(VirtualItem, AgentItem.item_id == VirtualItem.id)
    )
    agent_items: dict[int, list[str]] = {}
    for aid, item_name in items_result.all():
        agent_items.setdefault(aid, []).append(item_name)

    # 4. 构建居民状态
    agent_lines = []
    for a in agents:
        checked = "已打卡" if a.id in checked_in_agents else "未打卡"
        items = ", ".join(agent_items.get(a.id, [])) or "无"
        persona_brief = a.persona[:60] + ("…" if len(a.persona) > 60 else "")
        agent_lines.append(
            f"- ID={a.id} {a.name}: {persona_brief} | "
            f"余额={a.credits} | 今日{checked} | 物品=[{items}]"
        )

    # 5. 最近 10 条聊天
    msg_result = await db.execute(
        select(Message)
        .options(joinedload(Message.agent))
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    messages = list(reversed(msg_result.scalars().all()))
    msg_lines = [
        f"- {m.agent.name if m.agent else '?'}: {m.content[:80]}"
        for m in messages
    ] or ["(无)"]

    # 6. 岗位列表
    jobs = await work_service.get_jobs(db)
    job_lines = [
        f"- ID={j['id']} {j['title']}: 日薪{j['daily_reward']} | "
        f"今日{j['today_workers']}/{j['max_workers']}人"
        for j in jobs
    ]

    # 7. 商品列表
    shop_items = await shop_service.get_items(db)
    shop_lines = [
        f"- ID={i['id']} {i['name']}: {i['price']}信用点 ({i['item_type']})"
        for i in shop_items
    ]

    # 8. 上一轮行为
    async with _round_log_lock:
        last_snapshot = list(_last_round_log)
    last_lines = [
        f"- {log['agent_name']}: {log['action']} — {log['reason']}"
        for log in last_snapshot
    ] or ["(首轮)"]

    snapshot = f"""当前时间：{now.strftime('%Y-%m-%d %H:%M UTC')}

== 居民状态 ==
{chr(10).join(agent_lines)}

== 最近聊天 ==
{chr(10).join(msg_lines)}

== 上一轮行为 ==
{chr(10).join(last_lines)}

== 可用岗位 ==
{chr(10).join(job_lines)}

== 商店商品 ==
{chr(10).join(shop_lines)}

请为每个居民决定下一步行为。"""

    return snapshot


async def decide(snapshot: str) -> list[dict]:
    """调用 LLM 做出行为决策，返回决策列表。"""
    if not snapshot:
        return []

    resolved = resolve_model(AUTONOMY_MODEL)
    if not resolved:
        logger.warning("Autonomy model not configured")
        return []

    base_url, api_key, model_id = resolved

    raw = ""
    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        response = await client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": snapshot},
            ],
            max_tokens=2000,
        )
        raw = response.choices[0].message.content or ""
        # 某些推理模型把回复放在 reasoning 字段
        if not raw.strip():
            msg_data = response.choices[0].message
            reasoning = getattr(msg_data, 'reasoning', None) or getattr(msg_data, 'reasoning_content', None)
            if reasoning:
                lines = reasoning.strip().splitlines()
                for line in reversed(lines):
                    if line.strip().startswith("["):
                        raw = line.strip()
                        break

        # 清理 markdown 代码块
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        decisions = json.loads(raw)
        if not isinstance(decisions, list):
            logger.warning("Autonomy decide: expected list, got %s", type(decisions))
            return []

        # 基本校验
        valid = []
        for d in decisions:
            if not isinstance(d, dict):
                continue
            if "agent_id" not in d or "action" not in d:
                continue
            if d["action"] not in ("checkin", "purchase", "chat", "rest"):
                d["action"] = "rest"
            valid.append(d)

        logger.info("Autonomy decide: %d valid decisions", len(valid))
        return valid

    except json.JSONDecodeError as e:
        logger.error("Autonomy decide: JSON parse failed: %s, raw=%s", e, raw[:200])
        return []
    except Exception as e:
        logger.error("Autonomy decide: LLM call failed: %s", e)
        return []


async def execute_decisions(decisions: list[dict], db: AsyncSession) -> dict:
    """逐条执行决策，返回统计。"""
    from ..api.chat import broadcast, send_agent_message

    stats = {"success": 0, "failed": 0, "skipped": 0}
    chat_tasks: list[dict] = []
    round_log: list[dict] = []

    # 预加载 agent 名称映射
    result = await db.execute(select(Agent.id, Agent.name).where(Agent.id != 0))
    agent_names = {aid: name for aid, name in result.all()}

    for dec in decisions:
        aid = dec.get("agent_id")
        action = dec.get("action", "rest")
        params = dec.get("params", {})
        reason = dec.get("reason", "")
        agent_name = agent_names.get(aid, f"Agent#{aid}")

        if aid not in agent_names:
            logger.warning("Autonomy execute: unknown agent_id=%s, skipping", aid)
            stats["skipped"] += 1
            continue

        try:
            if action == "rest":
                stats["skipped"] += 1
                round_log.append({"agent_id": aid, "agent_name": agent_name, "action": "rest", "reason": reason})
                continue

            if action == "checkin":
                # 自动选岗位：用 params 中的 job_id，否则随机选一个有空位的
                job_id = params.get("job_id")
                if not job_id:
                    jobs = await work_service.get_jobs(db)
                    available = [j for j in jobs if j["max_workers"] == 0 or j["today_workers"] < j["max_workers"]]
                    if available:
                        job_id = random.choice(available)["id"]
                if job_id:
                    res = await work_service.check_in(aid, job_id, db)
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(agent_name, aid, "checkin", reason)
                    else:
                        logger.info("Autonomy checkin failed for %s: %s", agent_name, res["reason"])
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1

            elif action == "purchase":
                item_id = params.get("item_id")
                if item_id:
                    res = await shop_service.purchase(aid, item_id, db)
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(agent_name, aid, "purchase", reason)
                    else:
                        logger.info("Autonomy purchase failed for %s: %s", agent_name, res["reason"])
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1

            elif action == "chat":
                # 经济预检查
                can_speak = await economy_service.check_quota(aid, "chat", db)
                if can_speak.allowed:
                    agent = await db.get(Agent, aid)
                    if agent:
                        chat_tasks.append({
                            "agent_id": aid,
                            "agent_name": agent_name,
                            "persona": agent.persona,
                            "model": agent.model,
                        })
                else:
                    logger.info("Autonomy chat quota denied for %s", agent_name)
                    stats["skipped"] += 1

            round_log.append({"agent_id": aid, "agent_name": agent_name, "action": action, "reason": reason})

        except Exception as e:
            logger.error("Autonomy execute failed for agent %s action %s: %s", agent_name, action, e)
            stats["failed"] += 1
            round_log.append({"agent_id": aid, "agent_name": agent_name, "action": action, "reason": f"执行失败: {e}"})

    await db.commit()

    # 聊天统一走 batch_generate
    if chat_tasks:
        await _execute_chats(chat_tasks, db, stats, round_log)

    # 更新上一轮日志
    global _last_round_log
    async with _round_log_lock:
        _last_round_log = round_log

    return stats


async def _execute_chats(
    chat_tasks: list[dict],
    db: AsyncSession,
    stats: dict,
    round_log: list[dict],
):
    """批量生成聊天并发送。"""
    from ..api.chat import send_agent_message, broadcast

    # 构建聊天历史
    msg_result = await db.execute(
        select(Message)
        .options(joinedload(Message.agent))
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    history = [
        {"name": m.agent.name if m.agent else "unknown", "content": m.content}
        for m in reversed(msg_result.scalars().all())
    ]

    agents_info = [
        {**task, "history": history}
        for task in chat_tasks
    ]

    results = await runner_manager.batch_generate(agents_info)

    # 并行错开发送（与 hourly_wakeup_loop 风格一致）
    async def _delayed_chat_send(task, reply, usage_info, delay):
        await asyncio.sleep(delay)
        try:
            async with async_session() as send_db:
                await send_agent_message(task["agent_id"], task["agent_name"], reply, send_db)
                await economy_service.deduct_quota(task["agent_id"], send_db)
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
                    send_db.add(record)
                await send_db.commit()
            await _broadcast_action(task["agent_name"], task["agent_id"], "chat", "主动发言")
            stats["success"] += 1
            # 更新 round_log 中对应条目
            for log in round_log:
                if log["agent_id"] == task["agent_id"] and log["action"] == "chat":
                    log["reason"] = f"发言: {reply[:30]}"
        except Exception as e:
            logger.error("Autonomy chat send failed for %s: %s", task["agent_name"], e)
            stats["failed"] += 1

    send_tasks = []
    for task in chat_tasks:
        aid = task["agent_id"]
        reply, usage_info = results.get(aid, (None, None))
        if not reply:
            stats["failed"] += 1
            continue
        delay = random.uniform(3, 20)
        send_tasks.append(asyncio.create_task(
            _delayed_chat_send(task, reply, usage_info, delay)
        ))

    if send_tasks:
        await asyncio.gather(*send_tasks)


async def _broadcast_action(agent_name: str, agent_id: int, action: str, reason: str):
    """广播 agent_action 系统事件。"""
    from ..api.chat import broadcast

    await broadcast({
        "type": "system_event",
        "data": {
            "event": "agent_action",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "action": action,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds"),
        }
    })


async def tick():
    """一次完整的自主行为循环。"""
    logger.info("Autonomy tick: starting")
    try:
        async with async_session() as db:
            snapshot = await build_world_snapshot(db)

        if not snapshot:
            logger.info("Autonomy tick: no agents, skipping")
            return

        decisions = await decide(snapshot)
        if not decisions:
            logger.info("Autonomy tick: no decisions, skipping")
            return

        logger.info("Autonomy tick: executing %d decisions", len(decisions))
        async with async_session() as db:
            stats = await execute_decisions(decisions, db)

        logger.info("Autonomy tick: done — %s", stats)

    except Exception as e:
        logger.error("Autonomy tick failed: %s", e, exc_info=True)
