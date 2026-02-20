"""M6.2-P1: 记忆提取质量优化 — 单元测试"""
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# 被测模块路径
CHAT = "app.api.chat"
CONFIG = "app.core.config"


# --- _truncation_fallback ---

def test_truncation_fallback_format():
    """截断兜底格式正确"""
    from app.api.chat import _truncation_fallback
    result = _truncation_fallback("x" * 300)
    assert result.startswith("对话摘要: ")
    assert len(result) <= len("对话摘要: ") + 200


def test_truncation_fallback_short_text():
    """短文本不截断"""
    from app.api.chat import _truncation_fallback
    result = _truncation_fallback("短文本测试")
    assert result == "对话摘要: 短文本测试"


# --- _llm_summarize ---


def _make_mock_provider(name="openrouter", model_id="test-model", available=True):
    """构造 mock ModelProvider"""
    p = MagicMock()
    p.name = name
    p.model_id = model_id
    p.is_available.return_value = available
    p.get_auth_token.return_value = "fake-token"
    p.get_base_url.return_value = "https://fake.api/v1"
    return p


def _make_mock_entry(providers):
    """构造 mock ModelEntry"""
    entry = MagicMock()
    entry.providers = providers
    return entry


def _mock_openai_response(content: str):
    """构造 AsyncOpenAI 返回值"""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_async_client(create_return=None, create_side_effect=None):
    """构造支持 async with 的 mock AsyncOpenAI client"""
    client = AsyncMock()
    if create_side_effect:
        client.chat.completions.create = AsyncMock(side_effect=create_side_effect)
    elif create_return is not None:
        client.chat.completions.create = AsyncMock(return_value=create_return)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_llm_summarize_success():
    """主模型正常返回时，摘要内容由 LLM 生成"""
    from app.api.chat import _llm_summarize

    provider = _make_mock_provider()
    entry = _make_mock_entry([provider])

    mock_client = _make_async_client(
        create_return=_mock_openai_response("张三喜欢吃苹果，李四承诺明天带水果")
    )

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}), \
         patch(f"{CHAT}.AsyncOpenAI", return_value=mock_client):
        result = await _llm_summarize("张三: 我喜欢吃苹果\n李四: 明天我带水果来")

    assert result is not None
    assert not result.startswith("对话摘要:")
    assert len(result) <= 100


@pytest.mark.asyncio
async def test_llm_summarize_respects_100_char_limit():
    """LLM 返回超过 100 字时，硬截断到 100 字"""
    from app.api.chat import _llm_summarize

    long_text = "这是一段很长的摘要内容" * 20  # 远超 100 字
    provider = _make_mock_provider()
    entry = _make_mock_entry([provider])

    mock_client = _make_async_client(
        create_return=_mock_openai_response(long_text)
    )

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}), \
         patch(f"{CHAT}.AsyncOpenAI", return_value=mock_client):
        result = await _llm_summarize("测试对话")

    assert result is not None
    assert len(result) <= 100


@pytest.mark.asyncio
async def test_llm_summarize_no_useful_memory():
    """LLM 返回'无有效记忆'时，返回 None"""
    from app.api.chat import _llm_summarize

    provider = _make_mock_provider()
    entry = _make_mock_entry([provider])

    mock_client = _make_async_client(
        create_return=_mock_openai_response("无有效记忆")
    )

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}), \
         patch(f"{CHAT}.AsyncOpenAI", return_value=mock_client):
        result = await _llm_summarize("你好\n你好啊")

    assert result is None


@pytest.mark.asyncio
async def test_llm_summarize_primary_timeout_fallback_to_secondary():
    """主模型超时时，自动切换到备用模型"""
    from app.api.chat import _llm_summarize

    p1 = _make_mock_provider(name="openrouter")
    p2 = _make_mock_provider(name="siliconflow")
    entry = _make_mock_entry([p1, p2])

    async def slow_create(**kwargs):
        await asyncio.sleep(100)  # 模拟超时

    mock_client_slow = _make_async_client()
    mock_client_slow.chat.completions.create = slow_create

    mock_client_ok = _make_async_client(
        create_return=_mock_openai_response("备用模型的摘要结果内容")
    )

    call_count = 0

    def mock_openai_factory(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_client_slow
        return mock_client_ok

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}), \
         patch(f"{CHAT}.AsyncOpenAI", side_effect=mock_openai_factory), \
         patch(f"{CHAT}.MEMORY_SUMMARY_TIMEOUT", 0.1):  # 缩短超时加速测试
        result = await _llm_summarize("测试对话")

    assert result is not None
    assert not result.startswith("对话摘要:")


@pytest.mark.asyncio
async def test_llm_summarize_all_providers_fail_truncation_fallback():
    """所有 provider 失败时，fallback 到截断拼接"""
    from app.api.chat import _llm_summarize

    p1 = _make_mock_provider(name="openrouter")
    p2 = _make_mock_provider(name="siliconflow")
    entry = _make_mock_entry([p1, p2])

    mock_client = _make_async_client(create_side_effect=Exception("API error"))

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}), \
         patch(f"{CHAT}.AsyncOpenAI", return_value=mock_client):
        result = await _llm_summarize("测试对话内容")

    assert result is not None
    assert result.startswith("对话摘要: ")


@pytest.mark.asyncio
async def test_llm_summarize_validation_fail_tries_next():
    """主模型返回空字符串时，尝试下一个 provider"""
    from app.api.chat import _llm_summarize

    p1 = _make_mock_provider(name="openrouter")
    p2 = _make_mock_provider(name="siliconflow")
    entry = _make_mock_entry([p1, p2])

    call_count = 0

    def mock_openai_factory(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_async_client(
                create_return=_mock_openai_response("")
            )
        return _make_async_client(
            create_return=_mock_openai_response("有效的摘要内容来自备用模型")
        )

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}), \
         patch(f"{CHAT}.AsyncOpenAI", side_effect=mock_openai_factory):
        result = await _llm_summarize("测试对话")

    assert result is not None
    assert not result.startswith("对话摘要:")


@pytest.mark.asyncio
async def test_llm_summarize_validation_fail_short_text():
    """主模型返回 <5 字时，尝试下一个 provider"""
    from app.api.chat import _llm_summarize

    p1 = _make_mock_provider(name="openrouter")
    p2 = _make_mock_provider(name="siliconflow")
    entry = _make_mock_entry([p1, p2])

    call_count = 0

    def mock_openai_factory(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_async_client(
                create_return=_mock_openai_response("嗯")
            )
        return _make_async_client(
            create_return=_mock_openai_response("有效的摘要内容来自备用模型")
        )

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}), \
         patch(f"{CHAT}.AsyncOpenAI", side_effect=mock_openai_factory):
        result = await _llm_summarize("测试对话")

    assert result is not None
    assert not result.startswith("对话摘要:")


@pytest.mark.asyncio
async def test_llm_summarize_model_not_registered():
    """memory-summary-model 未注册时，直接走截断兜底"""
    from app.api.chat import _llm_summarize

    with patch(f"{CONFIG}.MODEL_REGISTRY", {}):
        result = await _llm_summarize("测试对话内容")

    assert result is not None
    assert result.startswith("对话摘要: ")


@pytest.mark.asyncio
async def test_llm_summarize_all_providers_unavailable():
    """所有 provider is_available() 返回 False 时，走截断兜底"""
    from app.api.chat import _llm_summarize

    p1 = _make_mock_provider(name="openrouter", available=False)
    p2 = _make_mock_provider(name="siliconflow", available=False)
    entry = _make_mock_entry([p1, p2])

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}):
        result = await _llm_summarize("测试对话内容")

    assert result is not None
    assert result.startswith("对话摘要: ")


# --- _extract_memory 集成 ---


@pytest.mark.asyncio
async def test_extract_memory_calls_llm_summarize():
    """_extract_memory 调用 _llm_summarize 而非硬截断"""
    from app.api.chat import _extract_memory, _agent_reply_counts, EXTRACT_EVERY

    _agent_reply_counts[999] = EXTRACT_EVERY - 1  # 下一次调用触发提取
    messages = [{"name": f"agent{i}", "content": f"msg{i}"} for i in range(EXTRACT_EVERY)]

    mock_db = AsyncMock()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(f"{CHAT}._llm_summarize", new_callable=AsyncMock, return_value="测试摘要内容哈哈") as mock_summarize, \
         patch(f"{CHAT}.async_session", return_value=mock_session), \
         patch(f"{CHAT}.memory_service") as mock_mem_svc:
        mock_mem_svc.save_memory = AsyncMock()
        await _extract_memory(999, messages)

    mock_summarize.assert_awaited_once()
    mock_mem_svc.save_memory.assert_awaited_once()
    call_args = mock_mem_svc.save_memory.call_args
    assert call_args[0][1] == "测试摘要内容哈哈"


@pytest.mark.asyncio
async def test_extract_memory_skips_when_none():
    """_llm_summarize 返回 None 时，不调用 save_memory"""
    from app.api.chat import _extract_memory, _agent_reply_counts, EXTRACT_EVERY

    _agent_reply_counts[998] = EXTRACT_EVERY - 1
    messages = [{"name": f"agent{i}", "content": f"msg{i}"} for i in range(EXTRACT_EVERY)]

    with patch(f"{CHAT}._llm_summarize", new_callable=AsyncMock, return_value=None), \
         patch(f"{CHAT}.memory_service") as mock_mem_svc:
        mock_mem_svc.save_memory = AsyncMock()
        await _extract_memory(998, messages)

    mock_mem_svc.save_memory.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_memory_frequency_unchanged():
    """触发频率仍为每 EXTRACT_EVERY 轮一次"""
    from app.api.chat import _extract_memory, _agent_reply_counts, EXTRACT_EVERY

    _agent_reply_counts.pop(997, None)  # 清理
    messages = [{"name": f"agent{i}", "content": f"msg{i}"} for i in range(EXTRACT_EVERY)]

    mock_db = AsyncMock()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(f"{CHAT}._llm_summarize", new_callable=AsyncMock, return_value="摘要内容测试") as mock_summarize, \
         patch(f"{CHAT}.async_session", return_value=mock_session), \
         patch(f"{CHAT}.memory_service") as mock_mem_svc:
        mock_mem_svc.save_memory = AsyncMock()
        for _ in range(EXTRACT_EVERY * 2):
            await _extract_memory(997, messages)

    assert mock_summarize.await_count == 2
