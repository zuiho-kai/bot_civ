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


async def call_wakeup_model(prompt: str) -> str:
    """调用小模型进行唤醒选人"""
    resolved = resolve_model("wakeup-model")
    if not resolved:
        logger.warning("Wakeup model not configured or no API key, falling back to NONE")
        return "NONE"

    base_url, api_key, model_id = resolved

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 50,
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error("Wakeup model call failed: %s", e)
        return "NONE"


class WakeupService:
    async def process(
        self, message: Message, online_agent_ids: set[int], db: AsyncSession
    ) -> list[int]:
        """
        处理消息，返回需要唤醒的 agent_id 列表。
        不包含发送者自身，不包含 Human Agent (id=0)。
        """
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

        return wake_list

    async def _select_responder(
        self, message: Message, online_agent_ids: set[int], db: AsyncSession
    ) -> int | None:
        """小模型选人：人类消息时选择最合适的回复者"""
        candidates = await self._get_candidates(online_agent_ids, message.agent_id, db)
        if not candidates:
            return None

        recent = await self._get_recent_messages(db, limit=10)
        agent_list = "\n".join(
            f"- {a.name}: {a.persona[:80]}" for a in candidates
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

    async def _maybe_trigger(
        self, message: Message, online_agent_ids: set[int], db: AsyncSession
    ) -> int | None:
        """Agent 消息时，小概率触发另一个 Agent 参与对话"""
        candidates = await self._get_candidates(online_agent_ids, message.agent_id, db)
        if not candidates:
            return None

        recent = await self._get_recent_messages(db, limit=10)
        agent_list = "\n".join(
            f"- {a.name}: {a.persona[:80]}" for a in candidates
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
    ) -> int | None:
        """定时触发：判断是否有 Agent 应该主动发言"""
        # 前置条件：至少有 1 个非 Agent 活跃连接（即人类在线）
        if 0 not in online_agent_ids:
            return None

        candidates = await self._get_candidates(online_agent_ids, exclude_id=0, db=db)
        if not candidates:
            return None

        recent = await self._get_recent_messages(db, limit=10)
        if not recent:
            return None

        agent_list = "\n".join(
            f"- {a.name}: {a.persona[:80]}" for a in candidates
        )
        recent_text = "\n".join(
            f"{m.agent.name if m.agent else 'unknown'}: {m.content[:100]}"
            for m in recent
        )

        prompt = WAKEUP_PROMPT.format(
            agent_list=agent_list,
            recent_messages=recent_text,
            new_message="(定时检查：是否有人想主动发言？)",
        )

        result = await call_wakeup_model(prompt)
        return self._resolve_name(result, candidates)

    async def _get_candidates(
        self, online_agent_ids: set[int], exclude_id: int, db: AsyncSession
    ) -> list[Agent]:
        """获取候选 Agent（在线、非发送者、非 Human）"""
        if not online_agent_ids:
            return []
        candidate_ids = [
            aid for aid in online_agent_ids if aid != exclude_id and aid != 0
        ]
        if not candidate_ids:
            return []
        result = await db.execute(
            select(Agent).where(Agent.id.in_(candidate_ids))
        )
        return list(result.scalars().all())

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
