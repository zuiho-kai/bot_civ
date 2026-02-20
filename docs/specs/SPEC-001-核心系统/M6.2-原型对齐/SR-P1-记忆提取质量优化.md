# SR-P1：记忆提取质量优化

> 状态：待评审
> 对应 IR：IR-M6.2 P1
> 改动范围：2 文件 3 函数

---

## 1. 功能目标

将 `chat.py:_extract_memory()` 从"硬截断拼接"升级为"LLM 语义摘要"，生成高质量短期记忆条目。同时将 `delayed_send` 中的记忆提取改为 fire-and-forget，消除对消息发送主流程的阻塞。

---

## 2. 改动文件清单

| 文件 | 函数/区域 | 改动类型 | 说明 |
|------|-----------|----------|------|
| `server/app/core/config.py` | `MODEL_REGISTRY` 字典 | 新增条目 | 注册 `memory-summary-model` |
| `server/app/core/config.py` | `list_available_models()` | 修改过滤条件 | 隐藏内部模型 |
| `server/app/api/chat.py` | `_extract_memory()` | 重写 | LLM 摘要 + fallback 链 |
| `server/app/api/chat.py` | `delayed_send()` | 微调 | 记忆提取改为 fire-and-forget |

### 不改动文件

| 文件 | 原因 |
|------|------|
| `server/app/services/memory_service.py` | `save_memory` 接口不变，摘要文本由调用方传入 |
| `server/app/services/agent_runner.py` | 不涉及，LLM 调用在 `chat.py` 内部完成 |
| `server/app/models/tables.py` | 无 schema 变更 |

---

## 3. 接口设计

### 3.1 MODEL_REGISTRY 新增条目

```python
# server/app/core/config.py — MODEL_REGISTRY 字典内新增

"memory-summary-model": ModelEntry(
    display_name="Memory Summary (内部)",
    providers=[
        # 主模型：复用 wakeup-model 同款，openrouter 免费
        ModelProvider(name="openrouter", model_id="google/gemma-3-12b-it"),
        # 备用模型：硅基流动免费模型
        ModelProvider(name="siliconflow", model_id="Qwen/Qwen2.5-7B-Instruct"),
    ],
),
```

设计说明：
- `ModelEntry.get_active_provider()` 已实现"按顺序找第一个有 token 的供应商"，天然支持 fallback 到硅基流动
- 但此处的 provider 优先级是**配置级 fallback**（哪个供应商有 key 就用哪个），与运行时超时/失败 fallback 是两层机制
- 运行时 fallback 链在 `_extract_memory` 内部实现（见 3.3 节）

### 3.2 list_available_models 过滤

```python
# server/app/core/config.py — list_available_models() 函数

# 现有：
if key == "wakeup-model":
    continue

# 改为：
if key in ("wakeup-model", "memory-summary-model"):
    continue
```

### 3.3 _extract_memory 重写

函数签名不变：

```python
async def _extract_memory(agent_id: int, recent_messages: list[dict]):
```

#### 3.3.1 摘要 Prompt 模板

```python
MEMORY_SUMMARY_PROMPT = """你是一个记忆提取助手。请从以下对话中提取值得记住的关键信息。

要求：
- 提取关键事实、用户偏好、承诺、重要决定
- 忽略寒暄、问候、无实质内容的闲聊
- 用第三人称陈述句，每条信息独立完整
- 如果对话没有值得记住的内容，返回"无有效记忆"
- 输出不超过100字

对话内容：
{conversation}

请输出摘要："""
```

#### 3.3.2 完整函数逻辑（伪代码 + 关键代码片段）

```python
# 常量
MEMORY_SUMMARY_TIMEOUT = 15  # 秒
MEMORY_SUMMARY_PROMPT = """..."""  # 见上文

async def _extract_memory(agent_id: int, recent_messages: list[dict]):
    """每 EXTRACT_EVERY 轮对话自动摘要为短期记忆"""
    # ---- 频率控制（不变）----
    count = _agent_reply_counts.get(agent_id, 0) + 1
    _agent_reply_counts[agent_id] = count
    if count % EXTRACT_EVERY != 0:
        return
    if len(recent_messages) < EXTRACT_EVERY:
        return

    # ---- 构建对话文本 ----
    combined = "\n".join(
        f"{m.get('name', '?')}: {m.get('content', '')}"
        for m in recent_messages[-EXTRACT_EVERY:]
    )

    # ---- LLM 摘要（fallback 链）----
    summary = await _llm_summarize(combined)

    # ---- 持久化 ----
    try:
        async with async_session() as db:
            await memory_service.save_memory(agent_id, summary, MemoryType.SHORT, db)
        logger.info("Memory extracted for agent %d (reply #%d): %s", agent_id, count, summary[:50])
    except Exception as e:
        logger.warning("Memory save failed for agent %d: %s", agent_id, e)
```

#### 3.3.3 _llm_summarize 函数（新增，chat.py 模块级私有函数）

```python
async def _llm_summarize(conversation: str) -> str:
    """
    调用 LLM 生成对话摘要，带 fallback 链：
    1. memory-summary-model 主供应商（openrouter gemma-3-12b）
    2. memory-summary-model 备用供应商（siliconflow qwen2.5-7b）
    3. 截断拼接兜底
    """
    from ..core.config import MODEL_REGISTRY

    prompt = MEMORY_SUMMARY_PROMPT.format(conversation=conversation)

    entry = MODEL_REGISTRY.get("memory-summary-model")
    if not entry:
        logger.warning("memory-summary-model not in MODEL_REGISTRY, using truncation fallback")
        return _truncation_fallback(conversation)

    # 遍历所有 provider，逐个尝试
    for provider in entry.providers:
        if not provider.is_available():
            continue
        try:
            summary = await asyncio.wait_for(
                _call_llm_provider(provider, prompt),
                timeout=MEMORY_SUMMARY_TIMEOUT,
            )
            # 轻量校验：非空 + 长度 ≥5 字
            if summary and len(summary.strip()) >= 5:
                cleaned = summary.strip()
                # "无有效记忆" 视为无需保存
                if "无有效记忆" in cleaned:
                    logger.info("LLM determined no useful memory in conversation")
                    return None  # 调用方检查 None 跳过保存
                return cleaned[:100]  # 硬上限 100 字
            else:
                logger.warning(
                    "Memory summary validation failed (provider=%s, len=%d), trying next",
                    provider.name, len(summary.strip()) if summary else 0,
                )
                continue
        except asyncio.TimeoutError:
            logger.warning(
                "Memory summary timeout (provider=%s, limit=%ds), trying next",
                provider.name, MEMORY_SUMMARY_TIMEOUT,
            )
            continue
        except Exception as e:
            logger.warning(
                "Memory summary failed (provider=%s): %s, trying next",
                provider.name, e,
            )
            continue

    # 所有 provider 都失败 → 截断拼接兜底
    logger.warning("All memory summary providers failed, using truncation fallback")
    return _truncation_fallback(conversation)


async def _call_llm_provider(provider, prompt: str) -> str:
    """调用单个 LLM provider，返回文本结果"""
    client = AsyncOpenAI(
        api_key=provider.get_auth_token(),
        base_url=provider.get_base_url(),
    )
    response = await client.chat.completions.create(
        model=provider.model_id,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )
    content = response.choices[0].message.content or ""
    return content.strip()


def _truncation_fallback(conversation: str) -> str:
    """截断拼接兜底（与原逻辑一致）"""
    return f"对话摘要: {conversation[:200]}"
```

#### 3.3.4 _extract_memory 中处理 None 返回

`_llm_summarize` 返回 `None` 表示"无有效记忆"，`_extract_memory` 需要跳过保存：

```python
summary = await _llm_summarize(combined)
if summary is None:
    return  # LLM 判断无需记忆，跳过
```

### 3.4 delayed_send fire-and-forget 改造

当前代码（`chat.py` 第 88-89 行）：

```python
# 现有：阻塞式
history.append({"name": agent_info["agent_name"], "content": reply})
await _extract_memory(agent_info["agent_id"], history)
```

改为：

```python
# 改后：fire-and-forget
history.append({"name": agent_info["agent_name"], "content": reply})
task = asyncio.create_task(
    _extract_memory(agent_info["agent_id"], history)
)
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```

与 `handle_wakeup` 中第 282-286 行的模式完全一致，复用已有的 `_background_tasks` 集合防止 GC。

---

## 4. Fallback 链流程

```
_extract_memory 触发（每 5 轮）
    │
    ▼
构建对话文本 combined
    │
    ▼
_llm_summarize(combined)
    │
    ├─ Provider 1: openrouter/gemma-3-12b-it
    │   ├─ asyncio.wait_for(timeout=15s)
    │   ├─ 成功 + 校验通过（非空 且 ≥5字）→ 返回 summary[:100]
    │   ├─ 成功 + 含"无有效记忆" → 返回 None（跳过保存）
    │   ├─ 成功 + 校验失败 → 继续下一个 provider
    │   ├─ 超时 → 继续下一个 provider
    │   └─ 异常 → 继续下一个 provider
    │
    ├─ Provider 2: siliconflow/Qwen2.5-7B-Instruct
    │   └─ （同上逻辑）
    │
    └─ 全部失败 → _truncation_fallback(combined)
                   返回 "对话摘要: {combined[:200]}"
    │
    ▼
summary 非 None → save_memory(agent_id, summary, SHORT)
summary 为 None → 跳过，不保存
```

---

## 5. 新增 import

`chat.py` 文件头新增：

```python
from openai import AsyncOpenAI  # 新增：LLM 摘要调用
```

其余 import（`asyncio`、`logging`、`async_session`、`memory_service`、`MemoryType`）已存在，无需新增。

---

## 6. 错误处理策略

| 场景 | 处理方式 | 日志级别 |
|------|----------|----------|
| `memory-summary-model` 未注册 | 直接走截断兜底 | WARNING |
| 所有 provider 无可用 token | 直接走截断兜底 | WARNING |
| 单个 provider 超时（15s） | 跳过，尝试下一个 | WARNING |
| 单个 provider 网络/API 错误 | 跳过，尝试下一个 | WARNING |
| 摘要校验失败（空或 <5 字） | 跳过，尝试下一个 | WARNING |
| LLM 返回"无有效记忆" | 返回 None，跳过保存 | INFO |
| `save_memory` 失败 | 捕获异常，不影响主流程 | WARNING |
| fire-and-forget task 异常 | 被 `_background_tasks` 回调静默处理 | 无（task 内部已有 try/except） |

核心原则：记忆提取是增强功能，任何失败都不能阻塞消息发送主流程，也不能导致未捕获异常。

---

## 7. 关键约束

1. **不抽取公共 LLM 调用函数** — `_call_llm_provider` 和 `_llm_summarize` 都是 `chat.py` 模块级私有函数（下划线前缀），不放入 services 层
2. **不引入新依赖** — `AsyncOpenAI` 已在 `agent_runner.py` 中使用，`asyncio` 已在 `chat.py` 中导入
3. **超时硬编码 15s** — 与 `wakeup_service.py` 的 httpx 超时一致，不做配置化
4. **max_tokens=200** — 摘要 prompt 要求 ≤100 字，200 token 留足余量（中文 1 字 ≈ 1.5~2 token）
5. **`_background_tasks` 复用** — 已有的 GC 防护集合，`handle_wakeup` 和 `delayed_send` 共用

---

## 8. 配置项

| 配置项 | 位置 | 默认值 | 说明 |
|--------|------|--------|------|
| `memory-summary-model` | `MODEL_REGISTRY` | openrouter/gemma-3-12b-it + siliconflow/Qwen2.5-7B-Instruct | 摘要模型，双 provider |
| `MEMORY_SUMMARY_TIMEOUT` | `chat.py` 常量 | 15（秒） | 单个 provider 超时 |
| `MEMORY_SUMMARY_PROMPT` | `chat.py` 常量 | 见 3.3.1 节 | 摘要 prompt 模板 |
| `EXTRACT_EVERY` | `chat.py` 常量 | 5（不变） | 触发频率 |

---

## 9. 测试用例

### 9.1 单元测试（UT）

文件：`server/tests/test_memory_summary.py`

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# --- 基础摘要功能 ---

@pytest.mark.asyncio
async def test_llm_summarize_success():
    """主模型正常返回时，摘要内容由 LLM 生成，非截断格式"""
    # mock AsyncOpenAI 返回有效摘要
    # 断言：返回值不以 "对话摘要:" 开头
    # 断言：返回值长度 ≤ 100

@pytest.mark.asyncio
async def test_llm_summarize_respects_100_char_limit():
    """LLM 返回超过 100 字时，硬截断到 100 字"""
    # mock AsyncOpenAI 返回 150 字文本
    # 断言：len(result) <= 100

@pytest.mark.asyncio
async def test_llm_summarize_no_useful_memory():
    """LLM 返回'无有效记忆'时，返回 None"""
    # mock AsyncOpenAI 返回 "无有效记忆"
    # 断言：result is None

# --- Fallback 链 ---

@pytest.mark.asyncio
async def test_llm_summarize_primary_timeout_fallback_to_secondary():
    """主模型超时时，自动切换到备用模型"""
    # mock provider 1 抛出 asyncio.TimeoutError
    # mock provider 2 正常返回
    # 断言：返回值来自 provider 2

@pytest.mark.asyncio
async def test_llm_summarize_all_providers_fail_truncation_fallback():
    """所有 provider 失败时，fallback 到截断拼接"""
    # mock 所有 provider 抛出异常
    # 断言：返回值以 "对话摘要:" 开头
    # 断言：返回值长度 ≤ 204（"对话摘要: " + 200 字符）

@pytest.mark.asyncio
async def test_llm_summarize_validation_fail_tries_next():
    """主模型返回空字符串时，尝试下一个 provider"""
    # mock provider 1 返回 ""
    # mock provider 2 返回有效摘要
    # 断言：返回值来自 provider 2

@pytest.mark.asyncio
async def test_llm_summarize_validation_fail_short_text():
    """主模型返回 <5 字时，尝试下一个 provider"""
    # mock provider 1 返回 "嗯"
    # mock provider 2 返回有效摘要
    # 断言：返回值来自 provider 2

# --- 模型注册 ---

@pytest.mark.asyncio
async def test_llm_summarize_model_not_registered():
    """memory-summary-model 未注册时，直接走截断兜底"""
    # patch MODEL_REGISTRY 为空字典
    # 断言：返回值以 "对话摘要:" 开头

# --- _extract_memory 集成 ---

@pytest.mark.asyncio
async def test_extract_memory_calls_llm_summarize():
    """_extract_memory 调用 _llm_summarize 而非硬截断"""
    # mock _llm_summarize 返回 "测试摘要内容"
    # mock memory_service.save_memory
    # 调用 _extract_memory（设置 count 为 EXTRACT_EVERY 的倍数）
    # 断言：save_memory 被调用，content 参数 = "测试摘要内容"

@pytest.mark.asyncio
async def test_extract_memory_skips_when_none():
    """_llm_summarize 返回 None 时，不调用 save_memory"""
    # mock _llm_summarize 返回 None
    # mock memory_service.save_memory
    # 调用 _extract_memory
    # 断言：save_memory 未被调用

@pytest.mark.asyncio
async def test_extract_memory_frequency_unchanged():
    """触发频率仍为每 EXTRACT_EVERY 轮一次"""
    # mock _llm_summarize
    # 连续调用 _extract_memory 10 次（EXTRACT_EVERY=5）
    # 断言：_llm_summarize 被调用 2 次（第 5 次和第 10 次）

# --- _truncation_fallback ---

def test_truncation_fallback_format():
    """截断兜底格式正确"""
    # 输入 300 字文本
    # 断言：返回 "对话摘要: {前200字}"

def test_truncation_fallback_short_text():
    """短文本不截断"""
    # 输入 50 字文本
    # 断言：返回 "对话摘要: {完整文本}"
```

### 9.2 系统测试（ST）

文件：`server/tests/test_st_memory_summary.py`

```python
import pytest
import asyncio

# --- AC-1：LLM 生成记忆 ---

@pytest.mark.asyncio
async def test_st_memory_content_is_llm_generated():
    """AC-1：正常情况下记忆内容由 LLM 生成，不等于截断格式"""
    # 启动完整服务（或 mock 外部 API）
    # 发送 5 轮对话触发记忆提取
    # 查询 Memory 表最新记录
    # 断言：content 不匹配 "对话摘要: ..." 格式
    # 断言：len(content) <= 100

# --- AC-2：Fallback 链 ---

@pytest.mark.asyncio
async def test_st_fallback_chain_no_error_no_block():
    """AC-2：主模型超时时自动切换，全失败时 fallback 到截断，不报错不阻塞"""
    # mock 主模型超时
    # 验证备用模型被调用
    # mock 全部失败
    # 验证截断兜底生效
    # 验证消息广播未被阻塞（检查广播时间戳）

# --- AC-4：MODEL_REGISTRY 可配置 ---

def test_st_model_registry_has_memory_summary():
    """AC-4：MODEL_REGISTRY 中存在 memory-summary-model 条目"""
    from server.app.core.config import MODEL_REGISTRY
    assert "memory-summary-model" in MODEL_REGISTRY
    entry = MODEL_REGISTRY["memory-summary-model"]
    assert len(entry.providers) >= 2  # 至少主 + 备

def test_st_memory_summary_model_hidden_from_frontend():
    """AC-4 补充：memory-summary-model 不暴露给前端"""
    from server.app.core.config import list_available_models
    models = list_available_models()
    assert all(m["id"] != "memory-summary-model" for m in models)

# --- AC-5：fire-and-forget ---

@pytest.mark.asyncio
async def test_st_delayed_send_not_blocked_by_memory():
    """AC-5：delayed_send 中记忆提取为 fire-and-forget，不阻塞消息广播"""
    # mock _extract_memory 为 sleep(10)（模拟慢摘要）
    # 调用 delayed_send
    # 断言：delayed_send 在 <2s 内返回（不等待 10s 的记忆提取）
```

---

## 10. 参考文件

| 文件 | 参考内容 |
|------|----------|
| `server/app/services/wakeup_service.py` | `call_wakeup_model()` — httpx 调用 LLM 的模式参考（超时 15s） |
| `server/app/services/agent_runner.py` | `AsyncOpenAI` 用法参考（第 109 行） |
| `server/app/core/config.py` | `ModelProvider` / `ModelEntry` / `resolve_model` 机制 |
| `server/app/services/memory_service.py` | `save_memory(agent_id, content, memory_type, db)` 接口 |
| `docs/specs/SPEC-001-核心系统/M6.2-原型对齐/IR-M6.2-原型对齐补丁包.md` | IR 原文，P1 部分 |

---

## 附录：开发终端实施备忘

> 以下为开发终端（Opus/Sonnet）实施时需要自行决定的细节，SR 不做约束：

- `_call_llm_provider` 中 `AsyncOpenAI` 实例是否缓存（建议不缓存，调用频率低，每 5 轮才触发一次）
- 日志中是否打印完整 conversation 文本（建议只打印前 50 字符，避免日志膨胀）
- `_llm_summarize` 中遍历 provider 时是否需要记录尝试次数（建议记录，方便排查）
