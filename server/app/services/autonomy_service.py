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
from ..models import Agent, Message, Job, CheckIn, VirtualItem, AgentItem, Building, BuildingWorker, AgentResource
from .work_service import work_service
from .shop_service import shop_service
from .economy_service import economy_service
from .agent_runner import runner_manager
from .city_service import assign_worker, remove_worker, eat_food, get_agent_resources

logger = logging.getLogger(__name__)

# 上一轮行为日志（内存缓存，重启丢失可接受）
_last_round_log: list[dict] = []
_round_log_lock = asyncio.Lock()

AUTONOMY_MODEL = "wakeup-model"  # 复用免费小模型做决策

SYSTEM_PROMPT = """你是虚拟城市模拟器。根据世界状态为每个居民决定行为。

规则：
1. 行为：checkin（打卡）、purchase（购买）、chat（聊天）、rest（休息）、assign_building（应聘建筑）、unassign_building（离职）、eat（吃饭）
2. 已打卡不能重复；余额不足不能购买；行为符合性格
3. rest 是合理选择，不必所有人都行动
4. 饱腹度低时优先 eat；体力低时优先 rest；无工作时考虑 assign_building
5. assign_building 需要 building_id；unassign_building 无需参数（自动查找当前建筑）

直接输出纯 JSON 数组，不要解释，不要 markdown，不要思考过程。示例：
[{"agent_id": 1, "action": "assign_building", "params": {"building_id": 3}, "reason": "去官府田工作赚面粉"}]

params: checkin={}, purchase={"item_id": <int>}, chat={}, rest={}, assign_building={"building_id": <int>}, unassign_building={}, eat={}"""


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

    # 4. 构建居民状态（含三维属性 + 个人资源 + 工作状态）
    # 预加载工作状态
    worker_result = await db.execute(
        select(BuildingWorker.agent_id, Building.id, Building.name, Building.building_type)
        .join(Building, BuildingWorker.building_id == Building.id)
    )
    agent_work: dict[int, dict] = {}
    for aid, bid, bname, btype in worker_result.all():
        agent_work[aid] = {"building_id": bid, "building_name": bname, "building_type": btype}

    # 预加载个人资源
    res_result = await db.execute(select(AgentResource))
    agent_res_map: dict[int, list[str]] = {}
    for ar in res_result.scalars().all():
        agent_res_map.setdefault(ar.agent_id, []).append(f"{ar.resource_type}={ar.quantity}")

    agent_lines = []
    for a in agents:
        checked = "已打卡" if a.id in checked_in_agents else "未打卡"
        items = ", ".join(agent_items.get(a.id, [])) or "无"
        persona_brief = a.persona[:60] + ("…" if len(a.persona) > 60 else "")
        work_info = agent_work.get(a.id)
        work_str = f"[在岗：{work_info['building_name']}]" if work_info else "无业"
        res_str = ", ".join(agent_res_map.get(a.id, [])) or "无"
        stamina_tag = " [体力不足，无法工作]" if a.stamina < 20 else ""
        agent_lines.append(
            f"- ID={a.id} {a.name}: {persona_brief} | "
            f"余额={a.credits} | 饱腹={a.satiety} 心情={a.mood} 体力={a.stamina}{stamina_tag} | "
            f"今日{checked} | {work_str} | 资源=[{res_str}] | 物品=[{items}]"
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

    # 8. 建筑列表
    building_result = await db.execute(select(Building))
    building_lines = []
    for b in building_result.scalars().all():
        w_count_result = await db.execute(
            select(sa_func.count()).select_from(BuildingWorker)
            .where(BuildingWorker.building_id == b.id)
        )
        w_count = w_count_result.scalar() or 0
        building_lines.append(
            f"- ID={b.id} {b.name}({b.building_type}): {w_count}/{b.max_workers}人"
        )

    # 9. 上一轮行为
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

== 城市建筑 ==
{chr(10).join(building_lines)}

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
                {"role": "user", "content": SYSTEM_PROMPT + "\n\n" + snapshot},
            ],
            max_tokens=4000,
        )
        raw = response.choices[0].message.content or ""
        # 某些推理模型把回复放在 reasoning 字段，content 为空
        if not raw.strip():
            msg_data = response.choices[0].message
            reasoning = getattr(msg_data, 'reasoning', None) or getattr(msg_data, 'reasoning_content', None)
            if reasoning:
                # 用正则提取 reasoning 中最后一个 JSON 数组
                import re
                json_matches = re.findall(r'\[[\s\S]*?\]', reasoning)
                for candidate in reversed(json_matches):
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, list) and len(parsed) > 0:
                            raw = candidate
                            logger.info("Autonomy decide: extracted JSON from reasoning field")
                            break
                    except json.JSONDecodeError:
                        continue

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
            if d["action"] not in ("checkin", "purchase", "chat", "rest", "assign_building", "unassign_building", "eat"):
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

            elif action == "assign_building":
                building_id = params.get("building_id")
                if building_id:
                    res = await assign_worker("长安", building_id, aid, db)
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(agent_name, aid, "assign_building", reason)
                    else:
                        logger.info("Autonomy assign_building failed for %s: %s", agent_name, res["reason"])
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1

            elif action == "unassign_building":
                # TDD: 自动查找 agent 当前所在建筑，不需要 LLM 传 building_id
                bw_result = await db.execute(
                    select(BuildingWorker).where(BuildingWorker.agent_id == aid)
                )
                bw = bw_result.scalar()
                if bw:
                    res = await remove_worker("长安", bw.building_id, aid, db)
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(agent_name, aid, "unassign_building", reason)
                    else:
                        logger.info("Autonomy unassign_building failed for %s: %s", agent_name, res["reason"])
                        stats["failed"] += 1
                else:
                    logger.info("Autonomy unassign_building: %s not assigned to any building", agent_name)
                    stats["failed"] += 1

            elif action == "eat":
                res = await eat_food(aid, db)
                if res["ok"]:
                    stats["success"] += 1
                    await _broadcast_action(agent_name, aid, "eat", reason)
                else:
                    logger.info("Autonomy eat failed for %s: %s", agent_name, res["reason"])
                    stats["failed"] += 1

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
        reply, usage_info, _mem_ids = results.get(aid, (None, None, []))
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
