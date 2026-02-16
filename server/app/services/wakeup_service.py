"""
唤醒决策引擎

三种触发方式：
1. @提及 → 必定唤醒
2. 人类消息 → 小模型选人
3. 定时触发 → 小模型判断是否主动发言
"""
import logging
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Agent, Message
from ..core.config import resolve_model

logger = logging.getLogger(__name__)

WAKEUP_PROMPT = """你是一个聊天室管理员。根据以下信息，选择最合适回复的 Agent。

当前在线 Agent：
{agent_list}

最近消息：
{recent_messages}

新消息：
{new_message}

请返回最合适回复的 Agent 名称，如果没有人需要回复则返回 "NONE"。
只返回名称，不要解释。"""

SCHEDULED_WAKEUP_PROMPT = """你是一个聊天室管理员。现在是定时检查时间，根据最近的聊天内容，选出应该主动发言的 Agent。

可选 Agent：
{agent_list}

最近消息：
{recent_messages}

请返回应该主动发言的 Agent 名称，用逗号分隔。如果没有人需要发言则返回 "NONE"。
只返回名称，不要解释。例如：Alice,Bob"""


async def call_wakeup_model(prompt: str) -> str:
    """调用小模型进行唤醒选人"""
    resolved = resolve_model("wakeup-model")
    if not resolved:
        print("[WAKEUP] model not configured, returning NONE", flush=True)
        return "NONE"

    base_url, api_key, model_id = resolved

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800,
                },
            )
            response.raise_for_status()
            data = response.json()
            msg = data["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            # 某些推理模型把答案放在 reasoning 末尾，content 为空
            if not content and msg.get("reasoning"):
                # 取 reasoning 最后一行作为答案
                lines = msg["reasoning"].strip().splitlines()
                content = lines[-1].strip() if lines else ""
            print(f"[WAKEUP] model returned: {content!r}", flush=True)
            return content
    except Exception as e:
        print(f"[WAKEUP] model call failed: {e}", flush=True)
        logger.error("Wakeup model call failed: %s", e, exc_info=True)
        return "NONE"


class WakeupService:
    def __init__(self) -> None:
        self._no_response_count: dict[int, int] = {}  # {agent_id: 连续无回应次数}

    def record_response(self, agent_id: int) -> None:
        """有人回应时重置计数器"""
        self._no_response_count.pop(agent_id, None)

    def record_no_response(self, agent_id: int) -> None:
        """无人回应时计数器+1"""
        self._no_response_count[agent_id] = self._no_response_count.get(agent_id, 0) + 1

    async def process(
        self, message: Message, online_agent_ids: set[int], db: AsyncSession
    ) -> list[int]:
        """
        处理消息，返回需要唤醒的 agent_id 列表。
        不包含发送者自身，不包含 Human Agent (id=0)。
        """
        print(f"[WAKEUP:process] sender_type={message.sender_type!r} agent_id={message.agent_id} content={message.content[:50]!r}", flush=True)
        # 频率控制：人类说话 → 重置所有 agent 计数
        if message.sender_type == "human":
            for aid in list(self._no_response_count):
                self.record_response(aid)

        wake_list: list[int] = []

        # 1. @提及必唤（不要求在线，Agent 由服务端驱动回复）
        mentions = message.mentions or []
        for aid in mentions:
            if aid != message.agent_id and aid != 0:
                wake_list.append(aid)

        # 2. 人类消息 → 小模型选 1 个 Agent
        if message.sender_type == "human":
            selected = await self._select_responder(message, online_agent_ids, db)
            if selected and selected not in wake_list:
                wake_list.append(selected)

        # 3. 普通 Agent 消息（无 @提及）→ 小模型判断
        elif not mentions:
            selected = await self._maybe_trigger(message, online_agent_ids, db)
            if selected:
                wake_list.append(selected)

        # 频率控制：agent 消息触发了新唤醒 → 记录无回应
        if message.sender_type == "agent" and wake_list:
            self.record_no_response(message.agent_id)

        return wake_list

    async def _select_responder(
        self, message: Message, online_agent_ids: set[int], db: AsyncSession
    ) -> int | None:
        """小模型选人：人类消息时选择最合适的回复者"""
        candidates = await self._get_candidates(online_agent_ids, message.agent_id, db)
        print(f"[WAKEUP:select] candidates={[(c.id, c.name) for c in candidates]}", flush=True)
        if not candidates:
            return None

        recent = await self._get_recent_messages(db, limit=10)
        agent_list = "\n".join(
            f"- {a.name}: {a.persona[:80]}"
            + ("（最近发言较多，建议让其他人说话）" if self._no_response_count.get(a.id, 0) >= 3 else "")
            for a in candidates
        )
        recent_text = "\n".join(
            f"{m.agent.name if m.agent else 'unknown'}: {m.content[:100]}"
            for m in recent
        )

        prompt = WAKEUP_PROMPT.format(
            agent_list=agent_list,
            recent_messages=recent_text or "(无)",
            new_message=message.content[:200],
        )

        print(f"[WAKEUP:select] calling wakeup model...", flush=True)
        result = await call_wakeup_model(prompt)
        print(f"[WAKEUP:select] model result={result!r}", flush=True)
        return self._resolve_name(result, candidates)

    async def _maybe_trigger(
        self, message: Message, online_agent_ids: set[int], db: AsyncSession
    ) -> int | None:
        """Agent 消息时，小概率触发另一个 Agent 参与对话"""
        candidates = await self._get_candidates(online_agent_ids, message.agent_id, db)
        if not candidates:
            return None

        recent = await self._get_recent_messages(db, limit=10)
        agent_list = "\n".join(
            f"- {a.name}: {a.persona[:80]}"
            + ("（最近发言较多，建议让其他人说话）" if self._no_response_count.get(a.id, 0) >= 3 else "")
            for a in candidates
        )
        recent_text = "\n".join(
            f"{m.agent.name if m.agent else 'unknown'}: {m.content[:100]}"
            for m in recent
        )

        prompt = WAKEUP_PROMPT.format(
            agent_list=agent_list,
            recent_messages=recent_text or "(无)",
            new_message=message.content[:200],
        )

        result = await call_wakeup_model(prompt)
        return self._resolve_name(result, candidates)

    async def scheduled_trigger(
        self, online_agent_ids: set[int], db: AsyncSession
    ) -> list[int]:
        """定时触发：选出所有应该主动发言的 Agent，返回 agent_id 列表"""
        # 前置条件：至少有 1 个非 Agent 活跃连接（即人类在线）
        if 0 not in online_agent_ids:
            return []

        candidates = await self._get_candidates(online_agent_ids, exclude_id=0, db=db)
        if not candidates:
            return []

        recent = await self._get_recent_messages(db, limit=10)
        if not recent:
            return []

        agent_list = "\n".join(
            f"- {a.name}: {a.persona[:80]}" for a in candidates
        )
        recent_text = "\n".join(
            f"{m.agent.name if m.agent else 'unknown'}: {m.content[:100]}"
            for m in recent
        )

        prompt = SCHEDULED_WAKEUP_PROMPT.format(
            agent_list=agent_list,
            recent_messages=recent_text,
        )

        result = await call_wakeup_model(prompt)
        return self._resolve_names(result, candidates)

    async def _get_candidates(
        self, online_agent_ids: set[int], exclude_id: int, db: AsyncSession
    ) -> list[Agent]:
        """获取候选 Agent（所有非 Human Agent，不限于在线）"""
        result = await db.execute(
            select(Agent).where(Agent.id != 0, Agent.id != exclude_id)
        )
        all_agents = list(result.scalars().all())
        return [
            a for a in all_agents
            if self._no_response_count.get(a.id, 0) < 5
        ]

    async def _get_recent_messages(
        self, db: AsyncSession, limit: int = 10
    ) -> list[Message]:
        """获取最近 N 条消息（带 agent 关系）"""
        from sqlalchemy.orm import joinedload

        result = await db.execute(
            select(Message)
            .options(joinedload(Message.agent))
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    def _resolve_name(self, name: str, candidates: list[Agent]) -> int | None:
        """将模型返回的名称解析为 agent_id"""
        if not name or name.upper() == "NONE":
            return None
        name = name.strip().strip('"').strip("'")
        for agent in candidates:
            if agent.name == name:
                return agent.id
        # 模糊匹配：名称包含
        for agent in candidates:
            if agent.name in name or name in agent.name:
                return agent.id
        return None

    def _resolve_names(self, text: str, candidates: list[Agent]) -> list[int]:
        """将模型返回的逗号分隔名称解析为 agent_id 列表"""
        if not text or text.upper().strip() == "NONE":
            return []
        names = [n.strip().strip('"').strip("'") for n in text.split(",")]
        result = []
        for name in names:
            aid = self._resolve_name(name, candidates)
            if aid is not None and aid not in result:
                result.append(aid)
        return result
