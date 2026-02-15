# Agent 交互场景成本优化 — 讨论记录

**日期**：2026-02-15
**议题**：Agent-to-Agent 互@、人类@指派等实时交互场景的成本控制
**参与者**：用户、AI 助手
**触发**：用户分享 GPT 关于多 Agent 系统成本优化的讨论，要求对照分析

---

## 背景

定时触发场景已有 batch 优化方案（见 [Batch推理优化](Batch推理优化.md)）。

本次讨论聚焦实时交互场景：
1. Agent A @Agent B — agent 之间互相对话
2. 人类 @Agent — 指派任务或聊天
3. Agent 回复后触发其他 Agent 反应 — 链式唤醒

这些场景实时性要求高，不能走定时 batch，需要单独的成本控制策略。

---

## GPT 建议 vs 我们现有设计对照

### 已经做了的（不需要改）

| GPT 建议 | 我们的实现 | 状态 |
|---|---|---|
| Memory 分层（短期/长期/公共） | M2 TDD 2.2 MemoryService，short/long/public 三层 | ✅ 已设计 |
| Vector search 检索记忆，不用 LLM | M2 TDD 2.1 LanceDB + bge-small-zh 向量搜索 | ✅ 已设计 |
| 短上下文运行（~2000 tokens） | AgentRunner MAX_CONTEXT_ROUNDS=20, MAX_MEMORY_TOKENS=500 | ✅ 已设计 |
| 经济系统限制发言 | 免费 10 次/天 + 信用点扣减 | ✅ 已设计 |
| 小模型做意图识别 | Qwen 7B 免费模型选人 | ✅ 已设计 |
| 不是所有 agent 都活跃 | 三级唤醒 + "可以选择 0 个" | ✅ 已设计 |

### 值得采纳的新思路

#### 1. Agent 状态分层（Tier 系统）

GPT 提出的 Tier 0-3 分层和我们的经济系统可以结合：

| Tier | 状态 | 触发条件 | 模型 | 成本 |
|---|---|---|---|---|
| 0: 休眠 | 不响应任何消息 | 信用点=0 且免费额度用完 | 无 | 0 |
| 1: 被动 | 只响应 @必唤 | 默认状态 | 便宜模型 | 低 |
| 2: 活跃 | 响应 @必唤 + 消息触发 | 有信用点或免费额度 | 配置模型 | 中 |
| 3: 高活跃 | 全部触发 + 定时主动发言 | 信用点充足 | 配置模型 | 高 |

**和现有设计的关系**：不需要新模块，只需要在 WakeupService 的选人逻辑中加入 Tier 判断。EconomyService.check_quota() 已经有余额检查，扩展一下就行。

#### 2. 链式唤醒深度限制

Agent A @Agent B → B 回复 → B 的回复触发 Agent C → C 回复 → ...

这是 maibot 死循环问题的变种。GPT 没直接说这个，但"event-driven + importance scoring"思路可以用：

```
规则：
- 人类消息 → 唤醒深度 = 1（只唤醒被@者或小模型选的 1 个）
- Agent 消息 → 唤醒深度 = 1（只唤醒被@者，不触发消息选人）
- 链式深度上限 = 3（A→B→C→停止，不再继续）
- 每轮链式唤醒之间加 30-60 秒延迟（模拟思考时间）
```

**实现**：在消息元数据中加 `chain_depth` 字段，每次唤醒 +1，达到上限停止。

#### 3. Compiled Context Cache（应用层 KV cache）

GPT 提到的 "compiled_context cache" 思路很好 — 不是缓存 LLM 的 KV cache（我们控制不了），而是缓存 prompt 构建结果：

```python
class AgentRunner:
    _compiled_context: str | None = None
    _context_dirty: bool = True

    def invalidate_context(self):
        """记忆变化、人设变化时调用"""
        self._context_dirty = True

    async def build_prompt(self, chat_history, db):
        if not self._context_dirty and self._compiled_context:
            # 只需要拼接新的 chat_history
            return self._compiled_context + format_history(chat_history)

        # 重新构建完整 context
        identity = self.persona  # 几乎不变
        memories = await memory_service.search(...)  # 可能变
        self._compiled_context = format_identity(identity) + format_memories(memories)
        self._context_dirty = False
        return self._compiled_context + format_history(chat_history)
```

**收益**：记忆检索（向量搜索 + SQLite 查询）不需要每次都做，只在记忆变化时重建。对于被频繁 @ 的 agent，省掉重复的 memory search 开销。

#### 4. 实时场景也可以"微 batch"

Agent A 发了一条消息，同时 @了 B 和 C。现在是逐个调用 B 和 C 的 LLM。

可以优化：如果 B 和 C 用同一个模型，合并成一次并发请求（不是 batch API，是 asyncio.gather 并发）：

```python
# 现在
for agent_id in wake_list:
    reply = await runner.generate_reply(...)

# 优化后
tasks = [runner_manager.runners[aid].generate_reply(...) for aid in wake_list]
replies = await asyncio.gather(*tasks)
```

**注意**：这不是定时 batch 那种"打包成一个请求"，而是并发发送多个独立请求。对 OpenRouter/Anthropic API 来说，并发请求可能命中服务端 batch 优化。

### 不采纳的建议

| GPT 建议 | 不采纳原因 |
|---|---|
| Deterministic routine（8点上班12点吃饭） | 我们是混合驱动（时间+消息），时间驱动是"定时检查是否有话想说"，不是日程表模拟生活 |
| Daily planning（每天早上生成计划） | 同上，我们的 Agent 不需要日程表，定时触发已覆盖"主动发言"需求 |
| 90% 时间不调用 LLM | 我们已经通过经济系统 + 三级唤醒实现了类似效果，不需要额外的随机跳过 |
| 一次 LLM call 模拟多个 agent | 破坏"独立个体"原则，每个 agent 的人设和记忆不同，合并模拟会降低质量 |
| local vLLM 做 bulk simulation | 当前阶段用 API，vLLM 自部署是后期优化项 |

---

## 决策总结

### 纳入 M2 的改动

| 改动 | 影响模块 | 任务 |
|---|---|---|
| 链式唤醒深度限制 (max=3) | chat.py, Message 表加 chain_depth | M2-6 扩展 |
| 链式唤醒延迟 (30-60s) | chat.py handle_wakeup | M2-6 扩展 |
| 实时场景并发调用 (asyncio.gather) | agent_runner.py | M2-12 扩展 |

### 纳入 M2 但优先级低的改动

| 改动 | 影响模块 | 说明 |
|---|---|---|
| Agent Tier 状态分层 | wakeup_service.py | 可以先用经济系统的 check_quota 近似实现 |
| Compiled context cache | agent_runner.py | 优化项，不影响功能正确性 |

### 后期优化项（M3+）

| 改动 | 说明 |
|---|---|
| vLLM 自部署 | 用户是 vLLM KVC 专家，后期可以混合部署 |
| API prefix cache 利用 | 人设+系统 prompt 作为 prefix，利用 Anthropic/OpenRouter 的 cache |

---

## 与现有唤醒机制的关系

现有三级唤醒 + 本次补充：

```
触发类型          唤醒方式              成本控制
─────────────────────────────────────────────────
@必唤             直接唤醒被@者         经济预检查 + chain_depth 限制
消息触发          小模型选 0-1 个       免费模型 + 只选 1 个
定时触发(每小时)  意图识别 + batch      按模型分组 batch 调用
Agent 回复        链式唤醒(仅@必唤)     chain_depth ≤ 3 + 延迟 30-60s
```

关键补充：Agent 的回复消息，保留消息选人能力（三级唤醒原始设计不变），防循环通过三重防线实现：
1. chain_depth ≤ 3（硬性规则）
2. 经济系统（硬性限制）
3. 强化选人 Prompt（明确"发言机会珍贵，大部分情况返回 NONE"）

这不是调参方案 — chain_depth 是业务规则，经济系统是产品设计，Prompt 强化是指令明确化。
