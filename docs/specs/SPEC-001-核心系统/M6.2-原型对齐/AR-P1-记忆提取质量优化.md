# AR-P1：记忆提取质量优化 — 架构评审

> 状态：待评审
> 对应 SR：SR-P1-记忆提取质量优化
> 评审重点：fire-and-forget 并发安全、DB session 生命周期、fallback 链架构

---

## ADR-001：LLM 摘要调用位置 — chat.py 内联 vs 抽取到 service 层

**背景**：`_extract_memory` 需要新增 LLM 调用能力，有两种放置方式。

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. chat.py 内联（采用） | 改动集中在 1 文件；调用频率低（每 5 轮 1 次），不值得抽象 | chat.py 职责略膨胀 |
| B. 抽取到 memory_service | 职责分离更清晰 | 需改 memory_service 接口签名；引入 LLM 依赖到 service 层，耦合扩散 |

**决策**：采用方案 A。`_llm_summarize` 和 `_call_llm_provider` 作为 chat.py 模块级私有函数，下划线前缀明确表达"不对外暴露"。若未来其他模块也需要 LLM 摘要能力，再抽取为公共 util。

## ADR-002：fire-and-forget 模式 vs await 阻塞模式

**背景**：`delayed_send` 中记忆提取当前是 `await` 阻塞的，LLM 调用引入后延迟从 ~0ms 增加到 2~15s。

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. fire-and-forget（采用） | 消息广播零延迟；与 `handle_wakeup` 中已有模式一致 | 异常需在 task 内部自行捕获；调试链路断裂 |
| B. await 阻塞 | 调用链清晰，异常自然传播 | 消息广播被阻塞 2~15s，用户体验不可接受 |

**决策**：采用方案 A。复用已有的 `_background_tasks` 集合防 GC，task 内部 try/except 兜底。

## ADR-003：fallback 链 — provider 遍历 vs resolve_model 单点

**背景**：现有 `resolve_model()` 返回第一个可用 provider，是配置级单点选择。SR 要求运行时超时/失败时自动切换。

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 遍历 entry.providers（采用） | 运行时 fallback，单 provider 故障自动跳过 | 需直接访问 `MODEL_REGISTRY` 而非 `resolve_model` |
| B. 调用两次 resolve_model（不同 key） | 复用现有 API | 需注册两个 model key，配置冗余；fallback 逻辑散落在调用方 |

**决策**：采用方案 A。`_llm_summarize` 直接读取 `MODEL_REGISTRY["memory-summary-model"].providers` 列表，逐个尝试。这是对 `resolve_model` 的合理绕过——`resolve_model` 设计目标是"选一个最优"，而此处需要"逐个尝试直到成功"。

---

## 架构：Fallback 链调用流程

```
delayed_send / handle_wakeup
    │
    └─ asyncio.create_task(_extract_memory)   ← fire-and-forget
           │
           ├─ 频率门控（count % 5 != 0 → return）
           │
           └─ _llm_summarize(combined)
                │
                ├─ Provider[0]: openrouter/gemma-3-12b-it
                │   └─ asyncio.wait_for(timeout=15s)
                │       ├─ 成功 + 校验通过 → return summary[:100]
                │       ├─ "无有效记忆" → return None
                │       └─ 超时/异常/校验失败 → continue
                │
                ├─ Provider[1]: siliconflow/Qwen2.5-7B-Instruct
                │   └─ （同上）
                │
                └─ 全部失败 → _truncation_fallback → "对话摘要: {text[:200]}"
           │
           └─ summary 非 None → async_session() → save_memory()
```

两层 fallback 机制：
1. **配置级**：`ModelEntry.providers` 列表顺序 = 供应商优先级（哪个有 key 用哪个）
2. **运行时**：`_llm_summarize` 遍历所有 provider，超时/失败自动跳到下一个，全败走截断兜底

两层独立运作，互不干扰。配置级决定"哪些 provider 可用"，运行时决定"可用的 provider 中哪个能成功返回"。

---

## 并发安全分析：fire-and-forget 模式

### 异常传播

fire-and-forget task 的异常不会传播到调用方（`delayed_send` / `handle_wakeup`）。这是期望行为——记忆提取失败不应影响消息发送。但需确保异常不会成为"静默黑洞"：

| 异常来源 | 捕获位置 | 处理方式 |
|----------|----------|----------|
| LLM 调用超时/网络错误 | `_llm_summarize` 内 try/except | WARNING 日志 + 尝试下一个 provider |
| 所有 provider 失败 | `_llm_summarize` 末尾 | WARNING 日志 + 截断兜底（不抛异常） |
| `save_memory` DB 写入失败 | `_extract_memory` 内 try/except | WARNING 日志（不抛异常） |
| 未预期异常（bug） | task 内无捕获 → task.exception() | `_background_tasks.discard` 回调触发时 task 已结束，异常被 GC 时 Python 会打印 warning |

**风险点**：未预期异常只会在 GC 时打印 `Task exception was never retrieved`，生产环境可能被忽略。

**缓解**：`_extract_memory` 最外层已有 try/except 兜底（现有代码第 58-59 行），覆盖了所有未预期异常。SR 重写后需保留此兜底。

### 并发记忆写入

场景：Agent A 的第 5 轮和第 10 轮回复间隔很短，两个 `_extract_memory` task 可能并发执行。

- **`_agent_reply_counts` 竞态**：Python GIL 保证 dict 的单次读写是原子的，`count = dict.get() + 1` 和 `dict[key] = count` 之间无 await 点，不会被抢占。安全。
- **`save_memory` 并发写入**：两个 task 各自创建独立的 `async_session()`，写入不同的 Memory 行，无主键冲突。安全。
- **同一 agent 重复摘要**：理论上两个 task 可能对重叠的消息窗口做摘要，产生语义相近的记忆条目。影响：向量检索时召回冗余条目，但不影响正确性。可接受。

---

## DB Session 生命周期分析

`_extract_memory` 中的 DB 访问模式：

```python
async with async_session() as db:
    await memory_service.save_memory(agent_id, summary, MemoryType.SHORT, db)
```

关键特性：
1. **短生命周期**：session 仅在 `save_memory` 调用期间存活，LLM 调用（2~15s）期间不持有 session
2. **独立 session**：fire-and-forget task 创建自己的 session，不与调用方（`delayed_send`/`handle_wakeup`）共享
3. **自动 commit/rollback**：`async_session()` 上下文管理器退出时自动处理（`save_memory` 内部 commit）

**对比 `delayed_send` 现有模式**：`delayed_send` 在第 67 行 `async with async_session() as db` 内完成消息持久化 + 经济扣费 + LLM 用量记录 + commit，然后 session 关闭。记忆提取在 session 关闭后执行（fire-and-forget 后更是完全解耦）。无 session 泄漏风险。

**SQLite 并发写入**：项目使用 SQLite（`config.py` 第 13 行），SQLite WAL 模式下并发写入会串行化（database locked 重试）。`save_memory` 是单次 INSERT，持锁时间极短（<1ms），不会成为瓶颈。

---

## MODEL_REGISTRY 扩展点设计

新增 `memory-summary-model` 条目遵循现有 `ModelEntry` / `ModelProvider` 架构，无需改动基础设施：

- **新增内部模型的标准模式**：注册 key → `list_available_models()` 过滤排除 → 代码内部通过 key 直接访问
- **现有先例**：`wakeup-model` 已采用此模式（config.py 第 114 行过滤）
- **扩展方式**：过滤条件从 `key == "wakeup-model"` 改为 `key in ("wakeup-model", "memory-summary-model")`

**未来扩展建议**（不在 P1 范围）：若内部模型继续增加，可在 `ModelEntry` 中新增 `internal: bool = False` 字段，`list_available_models` 按字段过滤，替代硬编码黑名单。当前 2 个内部模型，硬编码可控。

---

## 性能考量：15s 超时对用户体验的影响

### 用户感知链路

```
用户发消息 → 广播 → 唤醒选人 → LLM 生成回复 → 广播回复 → [fire-and-forget] 记忆提取
                                                    ↑                        ↑
                                              用户看到回复            用户无感知
```

记忆提取在回复广播之后异步执行，15s 超时对用户体验零影响。即使最坏情况（两个 provider 各超时 15s = 30s 总耗时），用户也不会感知到任何延迟。

### 服务端资源占用

- **连接数**：每次 LLM 调用创建一个 `AsyncOpenAI` 实例（短连接），调用完成后释放。触发频率 = 每 agent 每 5 轮回复 1 次，20 个 agent 峰值并发 ≤ 4 个 LLM 请求（agent 回复有时间错开），资源占用可忽略。
- **内存**：`_background_tasks` 集合中 task 数量 = 正在执行的记忆提取数。每个 task 持有 ~5 条消息文本（几 KB），无内存压力。
- **超时累积**：最坏路径 = 2 provider × 15s = 30s。task 在 30s 后必定结束（成功或 fallback），不会无限挂起。

---

## 风险评估与缓解

| # | 风险 | 概率 | 影响 | 缓解措施 |
|---|------|------|------|----------|
| R1 | openrouter 免费模型限流/下线 | 中 | 主 provider 不可用 | 备用 provider（siliconflow）自动接管 + 截断兜底保底 |
| R2 | 两个 provider 同时不可用 | 低 | 退化为截断拼接（与改动前行为一致） | 截断兜底确保功能不中断；日志 WARNING 可观测 |
| R3 | LLM 返回低质量/幻觉摘要 | 中 | 记忆条目质量不如预期 | 轻量校验（≥5 字）过滤空/极短回复；100 字硬上限防膨胀；"无有效记忆"识别防垃圾写入 |
| R4 | fire-and-forget task 静默失败 | 低 | 记忆丢失但无告警 | `_extract_memory` 最外层 try/except + WARNING 日志；所有 provider 失败有明确日志 |
| R5 | `_agent_reply_counts` 进程重启后归零 | 确定 | 重启后前 4 轮回复不触发提取 | 可接受——内存计数器是轻量设计，重启后自然恢复；不值得持久化 |
| R6 | AsyncOpenAI 实例未复用导致连接开销 | 低 | 每次调用新建 TCP 连接 | 触发频率极低（每 agent 每 5 轮），连接开销可忽略；SR 附录已说明不缓存的理由 |

---

## 结论

P1 改动范围小（2 文件 3 函数）、架构风险低：
- fire-and-forget 模式有现有先例（`handle_wakeup` 第 282-286 行），并发安全已验证
- DB session 生命周期清晰，LLM 调用期间不持有 session
- fallback 链三层兜底（主 provider → 备用 provider → 截断拼接），最坏情况退化为改动前行为
- 15s 超时对用户体验零影响（异步执行，回复广播在前）

架构评审通过，可进入编码阶段。
