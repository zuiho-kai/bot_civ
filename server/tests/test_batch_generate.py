"""
M2-12: Batch 推理优化
- AgentRunnerManager.batch_generate() 按模型分组并发
- delayed_send 错开广播
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_runner import AgentRunnerManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RESOLVE_MODEL = "app.services.agent_runner.resolve_model"
MEMORY_SEARCH = "app.services.agent_runner.memory_service.search"


def _mock_llm(reply_text="batch回复"):
    """返回 resolve_model + AsyncOpenAI 的 patch，使 LLM 调用成功。"""
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


HISTORY = [
    {"name": "Alice", "content": "你好"},
    {"name": "Bob", "content": "大家好"},
]


# ===========================================================================
# batch_generate 测试
# ===========================================================================

@pytest.mark.asyncio
async def test_batch_generate_single_agent():
    """单个 agent 的 batch 调用正常返回"""
    mgr = AgentRunnerManager()

    agents_info = [{
        "agent_id": 1,
        "agent_name": "Alice",
        "persona": "友好的",
        "model": "test-model",
        "history": HISTORY,
    }]

    p_resolve, p_openai = _mock_llm("Alice的回复")
    with p_resolve, p_openai, patch(MEMORY_SEARCH, new_callable=AsyncMock, return_value=[]):
        with patch("app.services.agent_runner.session_maker", return_value=AsyncMock()):
            results = await mgr.batch_generate(agents_info)

    assert 1 in results
    reply, usage, _mem_ids = results[1]
    assert reply == "Alice的回复"
    assert usage is not None


@pytest.mark.asyncio
async def test_batch_generate_multiple_agents_same_model():
    """同模型多 agent 并发调用"""
    mgr = AgentRunnerManager()

    agents_info = [
        {"agent_id": 1, "agent_name": "Alice", "persona": "友好", "model": "m1", "history": HISTORY},
        {"agent_id": 2, "agent_name": "Bob", "persona": "幽默", "model": "m1", "history": HISTORY},
    ]

    p_resolve, p_openai = _mock_llm("回复")
    with p_resolve, p_openai, patch(MEMORY_SEARCH, new_callable=AsyncMock, return_value=[]):
        with patch("app.services.agent_runner.session_maker", return_value=AsyncMock()):
            results = await mgr.batch_generate(agents_info)

    assert len(results) == 2
    assert results[1][0] == "回复"
    assert results[2][0] == "回复"


@pytest.mark.asyncio
async def test_batch_generate_multiple_models():
    """不同模型分组并发"""
    mgr = AgentRunnerManager()

    agents_info = [
        {"agent_id": 1, "agent_name": "Alice", "persona": "友好", "model": "m1", "history": HISTORY},
        {"agent_id": 2, "agent_name": "Bob", "persona": "幽默", "model": "m2", "history": HISTORY},
        {"agent_id": 3, "agent_name": "Charlie", "persona": "安静", "model": "m1", "history": HISTORY},
    ]

    p_resolve, p_openai = _mock_llm("回复")
    with p_resolve, p_openai, patch(MEMORY_SEARCH, new_callable=AsyncMock, return_value=[]):
        with patch("app.services.agent_runner.session_maker", return_value=AsyncMock()):
            results = await mgr.batch_generate(agents_info)

    assert len(results) == 3
    for aid in [1, 2, 3]:
        assert results[aid][0] == "回复"


@pytest.mark.asyncio
async def test_batch_generate_partial_failure():
    """部分 agent LLM 调用失败不影响其他 agent"""
    mgr = AgentRunnerManager()

    agents_info = [
        {"agent_id": 1, "agent_name": "Alice", "persona": "友好", "model": "m1", "history": HISTORY},
        {"agent_id": 2, "agent_name": "Bob", "persona": "幽默", "model": "m1", "history": HISTORY},
    ]

    call_count = 0

    async def _side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("LLM boom")
        mock_choice = MagicMock()
        mock_choice.message.content = "成功回复"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage.prompt_tokens = 10
        mock_resp.usage.completion_tokens = 5
        mock_resp.usage.total_tokens = 15
        return mock_resp

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=_side_effect)

    with patch(RESOLVE_MODEL, return_value=("http://fake", "sk-fake", "m1")):
        with patch("app.services.agent_runner.AsyncOpenAI", return_value=mock_client):
            with patch(MEMORY_SEARCH, new_callable=AsyncMock, return_value=[]):
                with patch("app.services.agent_runner.session_maker", return_value=AsyncMock()):
                    results = await mgr.batch_generate(agents_info)

    # 一个失败一个成功（不断言具体哪个 agent 失败，因为 gather 执行顺序不保证）
    assert len(results) == 2
    failed = [aid for aid, (r, _, _m) in results.items() if r is None]
    succeeded = [aid for aid, (r, _, _m) in results.items() if r is not None]
    assert len(failed) == 1
    assert len(succeeded) == 1


@pytest.mark.asyncio
async def test_batch_generate_empty_list():
    """空列表不报错"""
    mgr = AgentRunnerManager()
    results = await mgr.batch_generate([])
    assert results == {}


# ===========================================================================
# delayed_send 测试
# ===========================================================================

SEND_AGENT_MSG = "app.api.chat.send_agent_message"
DEDUCT_QUOTA = "app.api.chat.economy_service.deduct_quota"
EXTRACT_MEMORY = "app.api.chat._extract_memory"
CHAT_ASYNC_SESSION = "app.api.chat.async_session"


def _mock_db_session():
    """创建 mock async session context manager"""
    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_db


@pytest.mark.asyncio
async def test_delayed_send_normal_path():
    """正常路径：消息持久化 + 用量记录 + commit"""
    from app.api.chat import delayed_send

    mock_ctx, mock_db = _mock_db_session()
    info = {
        "agent_id": 1,
        "agent_name": "Alice",
        "history": [{"name": "Bob", "content": "你好"}],
    }
    usage = {
        "model": "test-model",
        "agent_id": 1,
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "latency_ms": 100,
    }

    with patch(CHAT_ASYNC_SESSION, return_value=mock_ctx):
        with patch(SEND_AGENT_MSG, new_callable=AsyncMock) as mock_send:
            with patch(DEDUCT_QUOTA, new_callable=AsyncMock):
                with patch(EXTRACT_MEMORY, new_callable=AsyncMock):
                    await delayed_send(info, "回复内容", usage, delay=0)

    mock_send.assert_awaited_once()
    mock_db.commit.assert_awaited_once()
    mock_db.add.assert_called_once()  # LLMUsage record


@pytest.mark.asyncio
async def test_delayed_send_no_usage_info():
    """usage_info 为 None 时不写 LLMUsage"""
    from app.api.chat import delayed_send

    mock_ctx, mock_db = _mock_db_session()
    info = {
        "agent_id": 1,
        "agent_name": "Alice",
        "history": [],
    }

    with patch(CHAT_ASYNC_SESSION, return_value=mock_ctx):
        with patch(SEND_AGENT_MSG, new_callable=AsyncMock):
            with patch(DEDUCT_QUOTA, new_callable=AsyncMock):
                with patch(EXTRACT_MEMORY, new_callable=AsyncMock):
                    await delayed_send(info, "回复", None, delay=0)

    mock_db.add.assert_not_called()
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delayed_send_does_not_mutate_original_history():
    """delayed_send 不修改原始 history 列表"""
    from app.api.chat import delayed_send

    original_history = [{"name": "Bob", "content": "你好"}]
    info = {
        "agent_id": 1,
        "agent_name": "Alice",
        "history": original_history,
    }

    mock_ctx, mock_db = _mock_db_session()

    with patch(CHAT_ASYNC_SESSION, return_value=mock_ctx):
        with patch(SEND_AGENT_MSG, new_callable=AsyncMock):
            with patch(DEDUCT_QUOTA, new_callable=AsyncMock):
                with patch(EXTRACT_MEMORY, new_callable=AsyncMock):
                    await delayed_send(info, "回复", None, delay=0)

    # 原始 history 不应被修改
    assert len(original_history) == 1
