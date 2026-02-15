"""
Agent 自动回复引擎

Phase 1：直接使用 OpenAI/Anthropic SDK 调用 LLM
Phase 2：替换为 OpenClaw SDK（外部接口不变）
"""
import asyncio
import logging
import time
from openai import AsyncOpenAI
from ..core.config import resolve_model
from ..core.database import async_session as db_session_maker
from ..models.tables import LLMUsage

logger = logging.getLogger(__name__)

# prevent fire-and-forget tasks from being GC'd before completion
_background_tasks: set[asyncio.Task] = set()


async def _record_usage(model: str, agent_id: int, usage, latency_ms: int):
    """异步写入 LLM 用量记录，不阻塞主流程"""
    try:
        async with db_session_maker() as session:
            record = LLMUsage(
                model=model,
                agent_id=agent_id,
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens or 0,
                total_tokens=usage.total_tokens or 0,
                latency_ms=latency_ms,
            )
            session.add(record)
            await session.commit()
    except Exception as e:
        logger.error("Failed to record LLM usage: %s", e, exc_info=True)


SYSTEM_PROMPT_TEMPLATE = """你是 {name}，一个聊天群里的成员。

你的人格设定：
{persona}

规则：
- 用自然、口语化的方式说话，符合你的人格
- 回复简短（1-3句话），像真人聊天
- 不要自称AI或机器人
- 可以用 @名字 提及其他群成员"""


class AgentRunner:
    """单个 Agent 的 LLM 调用管理器"""

    MAX_CONTEXT_ROUNDS = 20

    def __init__(self, agent_id: int, name: str, persona: str, model: str):
        self.agent_id = agent_id
        self.name = name
        self.persona = persona
        self.model = model
        self.context: list[dict] = []  # 增量上下文

    async def generate_reply(self, chat_history: list[dict]) -> str | None:
        """
        生成 Agent 回复。
        chat_history: [{"name": "Alice", "content": "xxx"}, ...]
        """
        # 更新增量上下文
        for msg in chat_history:
            self.context.append(msg)
        # FIFO 裁剪
        if len(self.context) > self.MAX_CONTEXT_ROUNDS:
            self.context = self.context[-self.MAX_CONTEXT_ROUNDS:]

        system_msg = SYSTEM_PROMPT_TEMPLATE.format(
            name=self.name, persona=self.persona
        )
        messages = [{"role": "system", "content": system_msg}]
        for entry in self.context:
            if entry.get("name") == self.name:
                messages.append({"role": "assistant", "content": entry["content"]})
            else:
                messages.append({
                    "role": "user",
                    "content": f'{entry.get("name", "someone")}: {entry["content"]}',
                })

        try:
            resolved = resolve_model(self.model)
            if not resolved:
                logger.warning("Model %s not configured or no API key", self.model)
                return None

            base_url, api_key, model_id = resolved
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            start = time.time()
            response = await client.chat.completions.create(
                model=model_id,
                messages=messages,
                max_tokens=800,
            )
            latency_ms = int((time.time() - start) * 1000)
            if response.usage:
                task = asyncio.create_task(_record_usage(
                    model_id, self.agent_id, response.usage, latency_ms
                ))
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)
            reply = response.choices[0].message.content
            # 某些推理模型把回复放在 reasoning 字段
            if not reply:
                msg_data = response.choices[0].message
                reasoning = getattr(msg_data, 'reasoning', None) or getattr(msg_data, 'reasoning_content', None)
                if reasoning:
                    logger.warning("Agent %s: content empty, falling back to reasoning tail", self.name)
                    # 取 reasoning 最后一段作为回复
                    lines = reasoning.strip().splitlines()
                    for line in reversed(lines):
                        if line.strip():
                            reply = line.strip()
                            break
            logger.info("Agent %s generated reply: %s", self.name, reply[:100] if reply else None)
            if reply:
                reply = reply.strip()
                self.context.append({"name": self.name, "content": reply})
            return reply
        except Exception as e:
            logger.error("AgentRunner LLM call failed for %s: %s", self.name, e)
            return None


class AgentRunnerManager:
    """管理所有 Agent 的 Runner 实例"""

    def __init__(self):
        self._runners: dict[int, AgentRunner] = {}

    def get_or_create(
        self, agent_id: int, name: str, persona: str, model: str
    ) -> AgentRunner:
        if agent_id not in self._runners:
            self._runners[agent_id] = AgentRunner(agent_id, name, persona, model)
        return self._runners[agent_id]

    def remove(self, agent_id: int):
        self._runners.pop(agent_id, None)


# 全局单例
runner_manager = AgentRunnerManager()
