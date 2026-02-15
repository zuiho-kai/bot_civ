# Batch 推理优化 — 讨论记录

**日期**：2026-02-15
**议题**：多 Agent 定时唤醒时，是否按模型分组 batch 调用以降低开销
**参与者**：用户、AI 助手
**触发**：GPT 讨论中提到斯坦福小镇 batch 执行模式与我们"数字公民"架构的冲突

---

## 背景

现有设计（03-技术设计.md）中，定时唤醒流程为：

```
每小时定时触发 → WakeupService → 逐个 AgentRunner.generate_reply() → 逐个 LLM 调用
```

问题：5 个 bot 唤醒 = 5 次独立 LLM 调用，开销线性增长。

斯坦福小镇（Generative Agents）的做法是将多个 agent 的推理 batch 合并，共享 KV cache prefix，推理成本降 60-70%。

## 核心矛盾

| | 现有设计（独立调用） | Batch 优化 |
|---|---|---|
| 哲学 | 每个 bot 独立进程、独立调用 | 集中调度、按模型分组 |
| 开销 | N 个 bot = N 次调用 | N 个 bot = M 次调用（M = 模型种类数） |
| 体验 | 回复时间分散 | 回复几乎同时到达 |

## 决策：Batch 不冲突，采纳

**关键洞察**：batch 是推理层优化，"数字公民"是架构层抽象，两层解耦。

类比：人类都用同一个大脑皮层结构（共享推理引擎），但每个人的记忆、性格、经历不同。batch 调用 = 共享推理引擎，人设+记忆 = 个体差异。对外表现完全是独立个体。

## 优化后的定时唤醒流程

```
每小时定时触发
  → 意图识别（Qwen 7B 免费，1次调用）
      → 输入：最近 1 小时聊天摘要 + 全部 agent 列表
      → 输出：wake_list（哪些 agent 应该发言）
  → 对 wake_list 中的 agent：
      → 逐个检索记忆（memory_service.search）
      → 逐个构建 prompt（人设 + 长期记忆 + 短期记忆 + 聊天上下文）
  → 按模型分组 batch 调用：
      dsv3 组:    [Alice(prompt), Bob(prompt)]    → 1 次 batch 请求
      qwen32b 组: [Charlie(prompt)]               → 1 次 batch 请求
  → 结果分发
      → 逐个经济扣费 deduct_quota()
      → 逐个异步记忆提取 _extract_memory()
      → 错开 5-30 秒随机延迟广播（模拟自然对话节奏）
```

## 每小时开销分析

| 步骤 | 模型 | 调用次数 | 成本 |
|---|---|---|---|
| 意图识别 | Qwen 7B (OpenRouter 免费) | 1 次 | 0（每日 1000 次额度） |
| 思考生成 | dsv3 / qwen32b 等 | 按模型种类，每种 1 次 | 取决于模型定价 |

示例：5 个 bot（3 个 dsv3 + 2 个 qwen32b）→ 每小时 1 次意图识别 + 2 次思考调用。

每日 24 小时 = 24 次意图识别（远低于 1000 次免费额度）+ 48 次思考调用。

## 对现有模块的影响

| 模块 | 影响 | 说明 |
|---|---|---|
| AgentRunner | 需改造 | 新增 `batch_generate()` 方法 |
| AgentRunnerManager | 需改造 | 新增按模型分组逻辑 |
| WakeupService | 小改 | 定时触发路径调用 batch 而非逐个 |
| MemoryService | 不变 | 记忆检索仍然逐个，只是检索完后拼进各自 prompt |
| EconomyService | 不变 | 扣费仍然逐个 |
| WebSocket 广播 | 小改 | 加随机延迟错开广播 |
| 前端 | 不变 | 完全透明 |

## 不影响的设计原则

- 每个 bot 的记忆独立 — 检索阶段仍然逐个
- 每个 bot 的经济独立 — 扣费阶段仍然逐个
- 每个 bot 的人设独立 — prompt 构建阶段仍然逐个
- 对用户透明 — 错开广播后看起来和独立调用一样

## 实施建议

纳入 M2 TDD 作为 AgentRunner 改造的一部分，具体任务：
1. `AgentRunnerManager.batch_generate()` — 按模型分组，构建 batch 请求
2. 定时唤醒路径切换到 batch 模式
3. 广播层加随机延迟（5-30 秒）

@必唤和消息触发仍然走逐个调用（实时性要求高），batch 仅用于定时触发场景。

---

## 补充讨论：回复生成 batch vs 逐个（2026-02-15）

**议题**：定时唤醒场景下，回复生成是 Server 侧 batch 代调还是让每个 OpenClaw Agent 自己调 LLM？

**参与者**：成本优化派、自主性派、中立分析师、人类替身 PM

### 三种方案

| 方案 | 描述 | 优势 | 劣势 |
|------|------|------|------|
| A: Server batch 代调 | Server 构建个性化 prompt，按模型分组 batch 发送 | 省调用次数、避免并发限制 | Agent 失去 prompt 构建自主权 |
| B: Agent 逐个自调 | Server 通知"你被唤醒了"，Agent 自己调 LLM | Agent 完全自主 | 调用次数多、并发压力大 |
| C: 混合 | 意图识别 batch + 回复生成逐个并发 | 折中 | 无 batch 成本优势 |

### 关键发现

1. **OpenRouter 按调用次数计费**，不是纯 token 计费 — batch 合并请求有实际成本差异
2. **并发限制**：20 个 Agent 同时 asyncio.gather 可能撞 rate limit，batch 减少并发压力
3. **个性化不受影响**：batch ≠ 合并 prompt，每个 Agent 仍然是独立 prompt → 独立回复，只是传输层合并
4. **人类替身 PM 确认**：用户接受 Server batch 代调，前提是"N 个独立 prompt → N 个独立回复"，符合"对外表现不变，优化在推理层做"

### 决策

**定时唤醒回复生成采用 Server 侧 batch 代调（方案 A）。**

完整流程：
```
定时触发 → 意图识别（免费小模型 batch）→ wake_list
  → 逐个检索记忆
  → 逐个构建个性化 prompt（人设 + 记忆 + 上下文）
  → 按模型分组 batch 调用 API
  → 结果分发：逐个扣费 + 逐个记忆提取 + 错开广播
```

**@必唤和消息触发仍走逐个调用**（实时性要求高）。

### 不可接受的边界

- 一次 LLM 调用模拟多个 Agent 回复 — 已否决（破坏独立个体原则）
- batch 代调时跳过个性化 prompt 构建 — 不可接受
