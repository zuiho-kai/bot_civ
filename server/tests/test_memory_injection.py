"""
M2-3: 记忆注入 Agent 上下文
M2-4: 对话自动提取记忆
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import MemoryType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_memory(content: str, mtype: MemoryType):
    """创建一个轻量 Memory mock 对象"""
    m = MagicMock()
    m.content = content
    m.memory_type = mtype
    return m


def _make_runner(agent_id=1, name="TestBot", persona="友好的测试机器人", model="test-model"):
    from app.services.agent_runner import AgentRunner
    return AgentRunner(agent_id=agent_id, name=name, persona=persona, model=model)


HISTORY = [
    {"name": "Alice", "content": "你好"},
    {"name": "Bob", "content": "大家好"},
    {"name": "Alice", "content": "今天天气不错"},
]

RESOLVE_MODEL = "app.services.agent_runner.resolve_model"
MEMORY_SEARCH = "app.services.agent_runner.memory_service.search"


def _patch_llm_success(reply_text="测试回复"):
    """返回一个 patch 好的 resolve_model + AsyncOpenAI，使 LLM 调用成功返回。"""
    mock_choice = MagicMock()
    mock_choice.message.content = reply_text
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    mock_response.usage.total_tokens = 15

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    return (
        patch(RESOLVE_MODEL, return_value=("http://fake", "sk-fake", "test-model")),
        patch("app.services.agent_runner.AsyncOpenAI", return_value=mock_client),
    )


# ===========================================================================
# M2-3: 记忆注入 Agent 上下文
# ===========================================================================

@pytest.mark.asyncio
async def test_generate_reply_with_memory_injection():
    """db 传入时，记忆被注入 system prompt"""
    runner = _make_runner()
    db = AsyncMock()

    memories = [
        _make_memory("我喜欢猫", MemoryType.SHORT),
        _make_memory("公共知识条目", MemoryType.PUBLIC),
    ]

    p_resolve, p_openai = _patch_llm_success()
    with p_resolve, p_openai as mock_openai_cls:
        with patch(MEMORY_SEARCH, new_callable=AsyncMock, return_value=memories):
            reply, usage, _mem_ids = await runner.generate_reply(HISTORY, db=db)

    assert reply is not None

    # 验证 system prompt 包含记忆内容
    call_args = mock_openai_cls.return_value.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    system_content = messages[0]["content"]
    assert "我喜欢猫" in system_content
    assert "公共知识条目" in system_content


@pytest.mark.asyncio
async def test_generate_reply_without_db():
    """db=None 时，不做记忆注入，正常生成回复"""
    runner = _make_runner()

    p_resolve, p_openai = _patch_llm_success("无记忆回复")
    with p_resolve, p_openai as mock_openai_cls:
        with patch(MEMORY_SEARCH, new_callable=AsyncMock) as mock_search:
            reply, usage, _mem_ids = await runner.generate_reply(HISTORY, db=None)

    assert reply == "无记忆回复"
    mock_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_injection_failure_does_not_block():
    """memory_service.search 抛异常时，generate_reply 仍正常返回"""
    runner = _make_runner()
    db = AsyncMock()

    p_resolve, p_openai = _patch_llm_success("正常回复")
    with p_resolve, p_openai:
        with patch(MEMORY_SEARCH, new_callable=AsyncMock, side_effect=RuntimeError("search boom")):
            reply, usage, _mem_ids = await runner.generate_reply(HISTORY, db=db)

    assert reply == "正常回复"


@pytest.mark.asyncio
async def test_memory_injection_empty_results():
    """search 返回空列表时，system prompt 不包含记忆块"""
    runner = _make_runner()
    db = AsyncMock()

    p_resolve, p_openai = _patch_llm_success()
    with p_resolve, p_openai as mock_openai_cls:
        with patch(MEMORY_SEARCH, new_callable=AsyncMock, return_value=[]):
            reply, usage, _mem_ids = await runner.generate_reply(HISTORY, db=db)

    assert reply is not None

    call_args = mock_openai_cls.return_value.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    system_content = messages[0]["content"]
    assert "你的相关记忆" not in system_content
    assert "公共知识" not in system_content


# ===========================================================================
# M2-4: 对话自动提取记忆
# ===========================================================================

SAVE_MEMORY = "app.api.chat.memory_service.save_memory"
ASYNC_SESSION = "app.api.chat.async_session"


def _make_messages(n: int):
    """生成 n 条测试消息"""
    return [{"name": f"user{i}", "content": f"消息{i}"} for i in range(n)]


@pytest.fixture(autouse=True)
def _reset_reply_counts():
    """每个测试前后清理全局计数器"""
    from app.api.chat import _agent_reply_counts
    _agent_reply_counts.clear()
    yield
    _agent_reply_counts.clear()


@pytest.mark.asyncio
async def test_extract_memory_triggers_on_fifth_reply():
    """第 5 次调用时触发 save_memory"""
    from app.api.chat import _extract_memory

    mock_db = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    messages = _make_messages(10)

    with patch(SAVE_MEMORY, new_callable=AsyncMock) as mock_save:
        with patch(ASYNC_SESSION, return_value=mock_session_ctx):
            # 前 4 次不触发
            for _ in range(4):
                await _extract_memory(agent_id=1, recent_messages=messages)
            mock_save.assert_not_awaited()

            # 第 5 次触发
            await _extract_memory(agent_id=1, recent_messages=messages)
            mock_save.assert_awaited_once()

    # 验证 save_memory 参数
    call_args = mock_save.call_args
    assert call_args[0][0] == 1  # agent_id
    assert "对话摘要" in call_args[0][1]  # summary content
    assert call_args[0][2] == MemoryType.SHORT


@pytest.mark.asyncio
async def test_extract_memory_skips_before_fifth():
    """前 4 次调用不触发 save_memory"""
    from app.api.chat import _extract_memory

    messages = _make_messages(10)

    with patch(SAVE_MEMORY, new_callable=AsyncMock) as mock_save:
        for _ in range(4):
            await _extract_memory(agent_id=2, recent_messages=messages)

    mock_save.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_memory_includes_agent_reply():
    """验证传入的 history 包含 agent 回复（调用方负责追加）"""
    from app.api.chat import _extract_memory

    mock_db = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    # 模拟 handle_wakeup 中的行为：history 已包含 agent 回复
    messages = _make_messages(4)
    messages.append({"name": "TestBot", "content": "我是机器人的回复"})

    with patch(SAVE_MEMORY, new_callable=AsyncMock) as mock_save:
        with patch(ASYNC_SESSION, return_value=mock_session_ctx):
            # 推进计数器到第 5 次
            for _ in range(4):
                await _extract_memory(agent_id=3, recent_messages=messages)
            await _extract_memory(agent_id=3, recent_messages=messages)

    mock_save.assert_awaited_once()
    summary = mock_save.call_args[0][1]
    assert "TestBot" in summary
    assert "我是机器人的回复" in summary


def test_agent_reply_counts_cleanup_on_disconnect():
    """bot 断开时计数器被清理"""
    from app.api.chat import _agent_reply_counts

    # 模拟计数器已有值
    _agent_reply_counts[42] = 3
    _agent_reply_counts[99] = 7

    # 模拟 websocket_endpoint finally 块中的清理逻辑
    _agent_reply_counts.pop(42, None)

    assert 42 not in _agent_reply_counts
    # 其他 agent 不受影响
    assert _agent_reply_counts[99] == 7
