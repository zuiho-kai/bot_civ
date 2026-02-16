"""
Agent 自动回复引擎

Phase 1：直接使用 OpenAI/Anthropic SDK 调用 LLM
Phase 2：替换为 OpenClaw SDK（外部接口不变）
"""
import logging
import time
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.config import resolve_model
from ..core.database import async_session as session_maker
from ..models import MemoryType
from .memory_service import memory_service

logger = logging.getLogger(__name__)

MAX_MEMORY_CHARS = 500  # 记忆注入最大字符数


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

    async def generate_reply(
        self, chat_history: list[dict], db: AsyncSession | None = None
    ) -> tuple[str | None, dict | None]:
        """
        生成 Agent 回复。
        chat_history: [{"name": "Alice", "content": "xxx"}, ...]
        db: 传入时启用记忆注入
        """
        # 使用 chat_history 作为上下文（已从 DB 查询最新历史）
        context = list(chat_history)
        if len(context) > self.MAX_CONTEXT_ROUNDS:
            context = context[-self.MAX_CONTEXT_ROUNDS:]

        system_msg = SYSTEM_PROMPT_TEMPLATE.format(
            name=self.name, persona=self.persona
        )

        # M2-3: 记忆注入
        if db is not None:
            try:
                recent_text = " ".join(
                    m.get("content", "") for m in context[-3:]
                )
                memories = await memory_service.search(
                    self.agent_id, recent_text, top_k=5, db=db
                )
                if memories:
                    personal = [m for m in memories if m.memory_type in (MemoryType.SHORT, MemoryType.LONG)]
                    public = [m for m in memories if m.memory_type == MemoryType.PUBLIC]
                    mem_block = ""
                    if personal:
                        mem_block += "\n\n## 你的相关记忆\n"
                        for m in personal[:3]:
                            mem_block += f"- {m.content}\n"
                    if public:
                        mem_block += "\n## 公共知识\n"
                        for m in public[:2]:
                            mem_block += f"- {m.content}\n"
                    if len(mem_block) > MAX_MEMORY_CHARS:
                        mem_block = mem_block[:MAX_MEMORY_CHARS] + "..."
                    system_msg += mem_block
            except Exception as e:
                logger.warning("Memory injection failed for %s: %s", self.name, e)

        messages = [{"role": "system", "content": system_msg}]
        for entry in context:
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
                return None, None

            base_url, api_key, model_id = resolved
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            start = time.time()
            response = await client.chat.completions.create(
                model=model_id,
                messages=messages,
                max_tokens=800,
            )
            latency_ms = int((time.time() - start) * 1000)
            usage_info = None
            if response.usage:
                usage_info = {
                    "model": model_id,
                    "agent_id": self.agent_id,
                    "prompt_tokens": response.usage.prompt_tokens or 0,
                    "completion_tokens": response.usage.completion_tokens or 0,
                    "total_tokens": response.usage.total_tokens or 0,
                    "latency_ms": latency_ms,
                }
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
            logger.info("Agent %s generated reply (len=%d)", self.name, len(reply) if reply else 0)
            if reply:
                reply = reply.strip()
            return reply, usage_info
        except Exception as e:
            logger.error("AgentRunner LLM call failed for %s: %s", self.name, e)
            return None, None


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

    async def batch_generate(
        self,
        agents_info: list[dict],
    ) -> dict[int, tuple[str | None, dict | None]]:
        """
        按模型分组并发调用 LLM。
        agents_info: [{"agent_id", "agent_name", "persona", "model", "history"}, ...]
        返回 {agent_id: (reply, usage_info)}
        每个协程内部创建独立的 AsyncSession，避免并发共享。
        """
        import asyncio

        # 1. 逐个构建 runner + 按模型分组
        prompts_by_model: dict[str, list[tuple[int, AgentRunner, list[dict]]]] = {}
        for info in agents_info:
            runner = self.get_or_create(
                info["agent_id"], info["agent_name"],
                info["persona"], info["model"],
            )
            model_key = info["model"]
            prompts_by_model.setdefault(model_key, []).append(
                (info["agent_id"], runner, info["history"])
            )

        # 2. 按模型分组并发调用（每个协程独立 session）
        results: dict[int, tuple[str | None, dict | None]] = {}

        async def _call_one(agent_id, runner, history):
            try:
                async with session_maker() as db:
                    return agent_id, await runner.generate_reply(history, db=db)
            except Exception as e:
                logger.error("Batch generate failed for agent %d: %s", agent_id, e)
                return agent_id, (None, None)

        tasks = []
        for group in prompts_by_model.values():
            for agent_id, runner, history in group:
                tasks.append(_call_one(agent_id, runner, history))

        gather_results = await asyncio.gather(*tasks)
        for agent_id, result in gather_results:
            results[agent_id] = result

        return results


# 全局单例
runner_manager = AgentRunnerManager()
