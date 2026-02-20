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
from ..models import Agent, Message, Job, CheckIn, VirtualItem, AgentItem, Building, BuildingWorker, AgentResource, AgentStatus
from ..models.tables import Bounty
from .work_service import work_service
from .shop_service import shop_service
from .economy_service import economy_service
from .agent_runner import runner_manager
from .city_service import assign_worker, remove_worker, eat_food, get_agent_resources, construct_building, BUILDING_RECIPES
# 策略系统 dormant（DEV-40: 调度架构不匹配，冻结等待事件驱动重做）
# from .strategy_engine import Strategy, StrategyType, parse_strategies, update_strategies, get_strategies
from .status_helper import set_agent_status

logger = logging.getLogger(__name__)

# 上一轮行为日志（内存缓存，重启丢失可接受）
_last_round_log: list[dict] = []
_round_log_lock = asyncio.Lock()

AUTONOMY_MODEL = "wakeup-model"  # 复用免费小模型做决策

SYSTEM_PROMPT = """你是虚拟城市模拟器。根据世界状态为每个居民决定本轮立即执行的行为。

行为：checkin（打卡）、purchase（购买）、chat（聊天）、rest（休息）、assign_building（应聘建筑）、unassign_building（离职）、eat（吃饭）、transfer_resource（转赠资源）、create_market_order（挂单交易）、accept_market_order（接单交易）、cancel_market_order（撤单）、construct_building（建造建筑）、claim_bounty（接取悬赏）

规则：
1. 已打卡不能重复；余额不足不能购买；行为符合性格
2. rest 是合理选择，不必所有人都行动
3. 饱腹度低时优先 eat；体力低时优先 rest；无工作时考虑 assign_building
4. assign_building 需要 building_id；unassign_building 无需参数
5. transfer_resource：资源充裕且有居民匮乏时可转赠
6. create_market_order：资源富余时挂单交易
7. accept_market_order：合适挂单可接单（buy_ratio 0~1）
8. cancel_market_order：挂单长时间无人接可撤单
9. construct_building：有足够 wood/stone 可建造（farm 需 wood=10 stone=5 工期3天；mill 需 wood=15 stone=10 工期5天）
10. claim_bounty：浏览悬赏任务板，选择感兴趣且有能力完成的悬赏接取。你同时只能接取一个悬赏，接取前考虑自身能力和竞争概率。已有进行中悬赏时不要再接新的

直接输出纯 JSON，不要解释，不要 markdown，不要思考过程。格式：
[<action>...]

action 格式：{"agent_id": 1, "action": "eat", "params": {}, "reason": "饿了"}

params: checkin={}, purchase={"item_id": <int>}, chat={}, rest={}, assign_building={"building_id": <int>}, unassign_building={}, eat={}, transfer_resource={"to_agent_id": <int>, "resource_type": "<str>", "quantity": <number>}, create_market_order={"sell_type": "<str>", "sell_amount": <number>, "buy_type": "<str>", "buy_amount": <number>}, accept_market_order={"order_id": <int>, "buy_ratio": <number>}, cancel_market_order={"order_id": <int>}, construct_building={"building_type": "<farm|mill>", "name": "<str>"}, claim_bounty={"bounty_id": <int>}"""


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
        frozen_str = f"(冻结{ar.frozen_amount})" if ar.frozen_amount > 0 else ""
        agent_res_map.setdefault(ar.agent_id, []).append(f"{ar.resource_type}={ar.quantity}{frozen_str}")

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
        if getattr(b, 'status', 'active') == "constructing":
            started = b.construction_started_at
            if started:
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                elapsed = (now - started).days
                remaining = max(0, b.construction_days - elapsed)
                status_tag = f" [建造中，剩余 {remaining} 天]"
            else:
                status_tag = " [建造中]"
        else:
            status_tag = ""
        building_lines.append(
            f"- ID={b.id} {b.name}({b.building_type}): {w_count}/{b.max_workers}人{status_tag}"
        )

    # 8.1 可建造建筑类型
    recipe_lines = []
    for btype, recipe in BUILDING_RECIPES.items():
        cost_str = ", ".join(f"{k}={v}" for k, v in recipe["cost"].items())
        recipe_lines.append(f"- {btype}: 需要 {cost_str}，工期 {recipe['construction_days']} 天")

    # 9. 上一轮行为
    async with _round_log_lock:
        last_snapshot = list(_last_round_log)
    last_lines = [
        f"- {log['agent_name']}: {log['action']} — {log['reason']}"
        for log in last_snapshot
    ] or ["(首轮)"]

    # 10. 交易市场挂单
    from .market_service import list_orders
    market_orders = await list_orders(db=db)
    market_lines = [
        f"- 挂单#{o['id']}: 卖家ID={o['seller_id']} 卖{o['sell_type']}x{o['remain_sell_amount']} 换{o['buy_type']}x{o['remain_buy_amount']} ({o['status']})"
        for o in market_orders
    ] or ["(无挂单)"]

    # 11. 悬赏任务
    bounty_result = await db.execute(
        select(Bounty).where(Bounty.status.in_(["open", "claimed"]))
    )
    bounties = bounty_result.scalars().all()
    bounty_lines = []
    for b in bounties:
        if b.status == "open":
            bounty_lines.append(
                f"- 悬赏#{b.id}: {b.title} | 奖励={b.reward}信用点 | 状态=开放"
            )
        else:
            bounty_lines.append(
                f"- 悬赏#{b.id}: {b.title} | 奖励={b.reward}信用点 | "
                f"状态=进行中(接取者ID={b.claimed_by})"
            )
    bounty_lines = bounty_lines or ["(无悬赏)"]

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

== 可建造建筑 ==
{chr(10).join(recipe_lines)}

== 交易市场 ==
{chr(10).join(market_lines)}

== 悬赏任务 ==
{chr(10).join(bounty_lines)}

请为每个居民决定下一步行为。"""

    return snapshot


async def decide(snapshot: str) -> list[dict]:
    """调用 LLM 做出行为决策，返回 actions 列表。

    策略系统 dormant（DEV-40），只返回立即行为。
    兼容旧格式 {"actions": [...]} 和纯数组 [...]。
    """
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
                # 用正则提取 reasoning 中所有可能的 JSON 对象或数组
                import re
                # 贪婪匹配，从 { 或 [ 开始到对应的 } 或 ] 结束
                json_matches = []
                for match in re.finditer(r'[\[{]', reasoning):
                    start = match.start()
                    # 尝试从这个位置解析 JSON
                    for end in range(start + 1, len(reasoning) + 1):
                        candidate = reasoning[start:end]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, (list, dict)):
                                json_matches.append(candidate)
                                break
                        except json.JSONDecodeError:
                            continue

                # 从最长的开始尝试（更可能是完整 JSON）
                for candidate in sorted(json_matches, key=len, reverse=True):
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, (list, dict)):
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

        parsed = json.loads(raw)

        # 兼容旧格式：{"actions": [...], "strategies": [...]}（忽略 strategies）
        if isinstance(parsed, dict) and "actions" in parsed:
            actions_raw = parsed.get("actions", [])
            actions = _validate_actions(actions_raw)
            logger.info("Autonomy decide: %d actions (dict format)", len(actions))
            return actions

        # 新格式：[{action...}]
        if isinstance(parsed, list):
            actions = _validate_actions(parsed)
            logger.info("Autonomy decide: %d actions (list format)", len(actions))
            return actions

        logger.warning("Autonomy decide: unexpected format %s", type(parsed))
        return []

    except json.JSONDecodeError as e:
        logger.error("Autonomy decide: JSON parse failed: %s, raw=%s", e, raw[:200])
        return []
    except Exception as e:
        logger.error("Autonomy decide: LLM call failed: %s", e)
        return []


def _validate_actions(raw_list: list) -> list[dict]:
    """校验 action 列表，过滤不合法条目。"""
    valid = []
    for d in raw_list:
        if not isinstance(d, dict):
            continue
        if "agent_id" not in d or "action" not in d:
            continue
        if d["action"] not in ("checkin", "purchase", "chat", "rest", "assign_building", "unassign_building", "eat", "transfer_resource", "create_market_order", "accept_market_order", "cancel_market_order", "construct_building", "claim_bounty"):
            d["action"] = "rest"
        valid.append(d)
    return valid


async def execute_decisions(decisions: list[dict], db: AsyncSession, snapshot: str = "") -> dict:
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

        # F35: 状态 → EXECUTING
        # TODO: set_agent_status 内部 commit 会提前提交 session 中的 pending 变更，
        #       破坏 flush-not-commit 的事务隔离意图。后续重构应改为 flush 或独立 session。
        agent_obj = await db.get(Agent, aid)
        if agent_obj and action != "rest":
            await set_agent_status(agent_obj, AgentStatus.EXECUTING, f"执行 {action}…", db)

        try:
            if action == "rest":
                stats["skipped"] += 1
                round_log.append({"agent_id": aid, "agent_name": agent_name, "action": "rest", "reason": reason})
                # F35: rest 时立即恢复 IDLE（不等最终兜底）
                if agent_obj:
                    await set_agent_status(agent_obj, AgentStatus.IDLE, "", db)
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
                            "reason": reason,
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

            elif action == "transfer_resource":
                to_id = params.get("to_agent_id")
                res_type = params.get("resource_type")
                qty = params.get("quantity")
                if to_id and res_type and qty:
                    from .city_service import transfer_resource
                    res = await transfer_resource(aid, to_id, res_type, qty, db)
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(agent_name, aid, "transfer_resource", reason)
                    else:
                        logger.info("Autonomy transfer_resource failed for %s: %s", agent_name, res["reason"])
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1

            elif action == "create_market_order":
                sell_type = params.get("sell_type")
                sell_amount = params.get("sell_amount")
                buy_type = params.get("buy_type")
                buy_amount = params.get("buy_amount")
                if sell_type and sell_amount and buy_type and buy_amount:
                    from .market_service import create_order
                    res = await create_order(aid, sell_type, sell_amount, buy_type, buy_amount, db=db)
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(agent_name, aid, "create_market_order", reason)
                    else:
                        logger.info("Autonomy create_market_order failed for %s: %s", agent_name, res["reason"])
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1

            elif action == "accept_market_order":
                order_id = params.get("order_id")
                buy_ratio = params.get("buy_ratio", 1.0)
                if order_id:
                    from .market_service import accept_order
                    res = await accept_order(aid, order_id, buy_ratio, db=db)
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(agent_name, aid, "accept_market_order", reason)
                    else:
                        logger.info("Autonomy accept_market_order failed for %s: %s", agent_name, res["reason"])
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1

            elif action == "cancel_market_order":
                order_id = params.get("order_id")
                if order_id:
                    from .market_service import cancel_order
                    res = await cancel_order(aid, order_id, db=db)
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(agent_name, aid, "cancel_market_order", reason)
                    else:
                        logger.info("Autonomy cancel_market_order failed for %s: %s", agent_name, res["reason"])
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1

            elif action == "construct_building":
                building_type = params.get("building_type")
                bname = params.get("name")
                if building_type and bname:
                    res = await construct_building(aid, building_type, bname, "长安", db=db)
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(agent_name, aid, "construct_building", reason)
                    else:
                        logger.info("Autonomy construct_building failed for %s: %s", agent_name, res["reason"])
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1

            elif action == "claim_bounty":
                bounty_id = params.get("bounty_id")
                if bounty_id:
                    from .bounty_service import claim_bounty
                    res = await claim_bounty(
                        agent_id=aid, bounty_id=bounty_id, db=db,
                    )
                    if res["ok"]:
                        stats["success"] += 1
                        await _broadcast_action(
                            agent_name, aid, "claim_bounty", reason,
                        )
                        await _broadcast_bounty_event("bounty_claimed", {
                            "bounty_id": res["bounty_id"],
                            "title": res["title"],
                            "reward": res["reward"],
                            "claimed_by": aid,
                            "claimed_by_name": agent_name,
                        })
                    else:
                        logger.info(
                            "Autonomy claim_bounty failed for %s: %s",
                            agent_name, res["reason"],
                        )
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1

            round_log.append({"agent_id": aid, "agent_name": agent_name, "action": action, "reason": reason})

        except Exception as e:
            logger.error("Autonomy execute failed for agent %s action %s: %s", agent_name, action, e)
            stats["failed"] += 1
            round_log.append({"agent_id": aid, "agent_name": agent_name, "action": action, "reason": f"执行失败: {e}"})

    await db.commit()

    # 聊天统一走 batch_generate
    if chat_tasks:
        await _execute_chats(chat_tasks, db, stats, round_log, snapshot)

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
    snapshot: str = "",
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

    # 构建游戏上下文（去掉聊天和指令部分，避免与 history 重复）
    game_context = ""
    if snapshot:
        lines = []
        skip = False
        for line in snapshot.splitlines():
            if line.startswith("== 最近聊天 =="):
                skip = True
                continue
            if skip and line.startswith("== "):
                skip = False
            if skip or line.startswith("请为每个居民"):
                continue
            lines.append(line)
        game_context = "\n".join(lines).strip()

    agents_info = []
    for task in chat_tasks:
        h = list(history)
        # 注入游戏上下文 + 当轮行为 reason
        ctx_parts = []
        if game_context:
            ctx_parts.append(f"当前游戏状态：\n{game_context}")
        if task.get("reason"):
            ctx_parts.append(f"你刚刚的行为：{task['reason']}")
        if ctx_parts:
            h.append({"name": "系统", "content": "\n".join(ctx_parts)})
        agents_info.append({**task, "history": h})

    results = await runner_manager.batch_generate(agents_info)

    # 并行错开发送
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
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    })


async def _broadcast_bounty_event(event: str, data: dict):
    """广播悬赏相关的 WS 事件，失败不回滚状态变更（AC-8）。"""
    from ..api.chat import broadcast
    try:
        await broadcast({
            "type": "system_event",
            "data": {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(
                    timespec="seconds",
                ),
                **data,
            },
        })
    except Exception as e:
        logger.warning("Bounty broadcast failed (non-fatal): %s", e)


async def execute_strategies(db: AsyncSession) -> dict:
    """策略自动机：遍历所有 Agent 的活跃策略，匹配当前世界状态并执行。

    返回 {"executed": N, "skipped": N, "completed": N}
    """
    from .market_service import list_orders, accept_order
    from .strategy_engine import get_all_strategies, StrategyType

    stats = {"executed": 0, "skipped": 0, "completed": 0}
    all_strategies = get_all_strategies()
    if not all_strategies:
        return stats

    # 预加载 agent 名称和 credits
    result = await db.execute(select(Agent.id, Agent.name, Agent.credits).where(Agent.id != 0))
    agent_names = {}
    agent_resources: dict[int, dict[str, float]] = {}
    for aid, name, agent_credits in result.all():
        agent_names[aid] = name
        agent_resources[aid] = {"credits": float(agent_credits)}

    # 预加载 agent 资源（wheat, flour 等）
    res_result = await db.execute(select(AgentResource))
    for ar in res_result.scalars().all():
        if ar.agent_id not in agent_resources:
            agent_resources[ar.agent_id] = {"credits": 0.0}
        agent_resources[ar.agent_id][ar.resource_type] = ar.quantity

    # 预加载工作状态
    worker_result = await db.execute(
        select(BuildingWorker.agent_id, BuildingWorker.building_id)
    )
    agent_building: dict[int, int] = {aid: bid for aid, bid in worker_result.all()}

    # 预加载市场挂单（opportunistic_buy 用）
    market_orders = await list_orders(db=db)
    open_orders = [o for o in market_orders if o["status"] in ("open", "partial")]

    for aid, strategies in all_strategies.items():
        if aid not in agent_names:
            continue
        agent_name = agent_names[aid]
        my_resources = agent_resources.get(aid, {})

        for s in strategies:
            try:
                if s.strategy == StrategyType.KEEP_WORKING:
                    # 终止条件：资源达标
                    if s.stop_when_resource and s.stop_when_amount is not None:
                        current = my_resources.get(s.stop_when_resource, 0)
                        if current >= s.stop_when_amount:
                            logger.info("Strategy completed: agent %s keep_working, %s reached %.1f",
                                        agent_name, s.stop_when_resource, current)
                            stats["completed"] += 1
                            continue

                    # 执行：如果已在目标建筑，执行 checkin
                    if s.building_id and agent_building.get(aid) == s.building_id:
                        jobs = await work_service.get_jobs(db)
                        available = [j for j in jobs if j["max_workers"] == 0 or j["today_workers"] < j["max_workers"]]
                        if available:
                            res = await work_service.check_in(aid, random.choice(available)["id"], db)
                            if res["ok"]:
                                stats["executed"] += 1
                                await _broadcast_action(agent_name, aid, "checkin", f"策略自动执行: 持续工作")
                            else:
                                stats["skipped"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        stats["skipped"] += 1

                elif s.strategy == StrategyType.OPPORTUNISTIC_BUY:
                    # 终止条件：库存达标
                    if s.stop_when_amount is not None and s.resource:
                        current = my_resources.get(s.resource, 0)
                        if current >= s.stop_when_amount:
                            logger.info("Strategy completed: agent %s opportunistic_buy, %s reached %.1f",
                                        agent_name, s.resource, current)
                            stats["completed"] += 1
                            continue

                    # 执行：扫描市场找低价单
                    bought = False
                    if s.resource and s.price_below is not None:
                        for order in open_orders:
                            if (order["sell_type"] == s.resource
                                    and order["remain_sell_amount"] > 0
                                    and order["remain_buy_amount"] > 0
                                    and order["seller_id"] != aid):
                                unit_price = order["remain_buy_amount"] / order["remain_sell_amount"]
                                if unit_price <= s.price_below:
                                    pay_resource = order["buy_type"]
                                    pay_amount = order["remain_buy_amount"]
                                    my_pay = my_resources.get(pay_resource, 0)
                                    if my_pay >= pay_amount:
                                        res = await accept_order(aid, order["id"], 1.0, db=db)
                                        if res["ok"]:
                                            stats["executed"] += 1
                                            await _broadcast_action(
                                                agent_name, aid, "accept_market_order",
                                                f"策略自动执行: 低价买入 {s.resource}"
                                            )
                                            my_resources[s.resource] = my_resources.get(s.resource, 0) + order["remain_sell_amount"]
                                            my_resources[pay_resource] = my_pay - pay_amount
                                            bought = True
                                            break
                    if not bought:
                        stats["skipped"] += 1

            except Exception as e:
                logger.error("Strategy execution failed: agent %s, strategy %s: %s", agent_name, s.strategy, e)
                stats["skipped"] += 1

    await db.commit()
    return stats


async def tick():
    """一次完整的自主行为循环。

    流程：构建快照 → LLM 决策(actions) → 执行 actions
    策略自动机 dormant（DEV-40: 调度架构不匹配）
    """
    logger.info("Autonomy tick: starting")
    try:
        async with async_session() as db:
            snapshot = await build_world_snapshot(db)

        if not snapshot:
            logger.info("Autonomy tick: no agents, skipping")
            return

        # F35: 所有 agent → THINKING（LLM 决策中）
        async with async_session() as db:
            agents_result = await db.execute(select(Agent).where(Agent.id != 0))
            all_agents = agents_result.scalars().all()
            for agent in all_agents:
                await set_agent_status(agent, AgentStatus.THINKING, "正在分析环境…", db)

        actions = await decide(snapshot)

        # 执行立即行为
        if actions:
            logger.info("Autonomy tick: executing %d actions", len(actions))
            async with async_session() as db:
                stats = await execute_decisions(actions, db, snapshot)
            logger.info("Autonomy tick: actions done — %s", stats)
        else:
            logger.info("Autonomy tick: no actions")

        # 策略自动机 dormant（DEV-40）

        # F35: 所有 agent → IDLE
        async with async_session() as db:
            agents_result = await db.execute(select(Agent).where(Agent.id != 0))
            for agent in agents_result.scalars().all():
                await set_agent_status(agent, AgentStatus.IDLE, "", db)

    except Exception as e:
        logger.error("Autonomy tick failed: %s", e, exc_info=True)
        # F35: 异常时也恢复 IDLE
        try:
            async with async_session() as db:
                agents_result = await db.execute(select(Agent).where(Agent.id != 0))
                for agent in agents_result.scalars().all():
                    await set_agent_status(agent, AgentStatus.IDLE, "", db)
        except Exception:
            pass
