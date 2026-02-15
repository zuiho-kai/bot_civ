# 竞品深度分析：MaiBot (MaiCore)

**日期**：2026-02-15
**仓库**：https://github.com/Mai-with-u/MaiBot
**版本**：0.12.2
**定位**：单 Agent 仿生聊天机器人框架（QQ/Telegram/WebUI 多平台）

---

## 一、产品定位对比

| 维度 | MaiBot | 我们（bot_civ） |
|------|--------|-----------------|
| 核心愿景 | 单个拟人 AI 伴侣 | 多 Agent 社区（聊天群 + 页游） |
| Agent 数量 | 1 个 Bot | 5-20 个独立 Bot |
| 架构模式 | 单体进程，所有逻辑内聚 | Server + 多 OpenClaw Agent 分离 |
| 平台 | QQ / Telegram / WebUI | 自建 Web 社区 |
| 记忆系统 | 三层仿生（海马体 + ReAct 检索 + 梦境整理） | 三层结构化（短期 + 长期 + 公共，LanceDB 向量） |
| 经济系统 | 无（仅 LLM 用量追踪） | 双货币（信用点 + 游戏币） |
| 人格系统 | TOML 配置 + 表情学习 + 黑话学习 | 自然语言人设 + JSON 元数据 |
| 关系系统 | 用户记忆点 + LLM 起昵称 + 好感度 | 暂无（M3+） |
| 开源状态 | 开源，社区活跃 | 私有 |

**核心差异**：MaiBot 做的是"一个很像人的 Bot"，我们做的是"一群各不相同的数字公民组成的社区"。MaiBot 的精力全部投入在单 Agent 的深度（记忆、情绪、表情、黑话），我们的挑战在多 Agent 的广度（调度、经济、互动、成本控制）。

---

## 二、架构深度分析

### 2.1 整体数据流

```
消息进入 → message_receive 预处理
    │
    ▼
HeartFChatting（群聊心流）/ BrainChatting（私聊大脑）
    │
    ▼
ActionPlanner / BrainPlanner（LLM 决策）
    ├── reply → memory_retrieval（ReAct 检索）→ replyer（LLM 生成）→ send
    ├── no_reply → 沉默
    ├── wait / listening → 异步等待（私聊，可被新消息打断）
    └── 插件动作 → action_handler.execute()
    │
    ▼
后台任务（并行）：
    ChatHistorySummarizer → 话题识别 → ChatHistory 存储
    DreamAgent → 记忆整理 / 合并 / 删除
    ExpressionLearner → 表情风格学习
    ReflectTracker → 反思追踪
```

### 2.2 双轨聊天引擎

**HeartFChatting（群聊）**：
- 轮询新消息 → 频率控制概率判断 → 触发思考
- 频率控制自适应：连续不回复时动态提高消息阈值（3 次后 1.5x，5 次后 2x）
- 被 @/提及时强制回复
- 内置 ChatHistorySummarizer 后台定期概括

**BrainChatting（私聊）**：
- ReAct 式持续思考循环（不是"有消息才思考"，而是"持续思考，没事做就等"）
- `asyncio.Event` 实现新消息打断机制
- 无频率控制（私聊每条都需响应）

**对我们的启发**：
- 群聊频率控制的自适应机制值得借鉴 — 我们的定时唤醒是固定间隔，可以考虑加入"连续无人理睬则降低发言欲望"
- 私聊的持续思考循环对我们不适用（我们是群聊为主），但 @必唤的强制回复逻辑类似

### 2.3 Planner（决策引擎）

MaiBot 的 Planner 是核心创新点：

1. 构建上下文：最近聊天记录（带消息 ID：m01, m02...）
2. 动作过滤：按激活类型（ALWAYS / RANDOM / KEYWORD / NEVER）
3. LLM 决策：聊天上下文 + 可用动作列表 + 历史决策日志 → JSON 输出
4. 解析 + 安全校验：防止回复自己、验证动作可用性
5. 支持多动作并行（一次决策选多个动作）

Planner prompt 的精巧设计：
- `reply` 动作携带 `unknown_words`（未知词语）和 `question`（需查询的问题），直接传给记忆检索
- 维护最近 20 条决策日志作为上下文
- `plan_style` 从人格配置读取

**对我们的启发**：
- 我们的唤醒选人（小模型判断谁想说话）类似 Planner 的 reply/no_reply 决策，但粒度更粗
- MaiBot 的 `unknown_words` → 记忆检索闭环很优雅，我们可以在 prompt 构建时加入类似机制
- 决策日志（最近 20 条）防止重复行为，我们的 chain_depth 限制是更硬性的版本

---

## 三、记忆系统深度分析（重点借鉴）

MaiBot 的记忆系统是其最大亮点，三层仿生设计：

### 3.1 第一层：海马体概括器（ChatHistorySummarizer）

模拟人类海马体的短期→长期记忆转化：

```
后台每 60 秒检查新消息
  → 累积到批次（≥80 条消息 或 距上次 >8 小时且 ≥20 条）
  → LLM 话题识别（将消息编号，识别话题并分配消息）
  → 话题缓存（连续 3 次无更新 或 消息 >5 条时打包存储）
  → 话题相似度匹配（≥90% 合并到历史话题）
  → 持久化到 ChatHistory 表（theme / summary / keywords / key_point）
```

存储结构：
| 字段 | 说明 |
|------|------|
| theme | 话题主题 |
| summary | 话题摘要 |
| keywords | 关键词列表 |
| key_point | 关键观点 |
| participants | 参与者 |

**对我们的启发**：
- 我们的 MemoryService 设计了短期记忆（7 天过期）→ 长期记忆（access_count 升级），但升级条件是"被检索次数"，不如 MaiBot 的"话题识别 + 概括"智能
- 话题识别是个好思路：不是逐条存记忆，而是按话题打包。这对多 Agent 场景更有价值 — 5 个 Agent 聊同一个话题，话题级记忆比消息级记忆更高效
- **建议纳入 M2**：MemoryService 增加话题概括层，定时将聊天记录按话题打包成长期记忆

### 3.2 第二层：ReAct 记忆检索（Memory Retrieval）

这是 MaiBot 代码量最大的模块（57KB），基于 ReAct Agent 的主动记忆检索：

```
Planner 输出 question + unknown_words
  → 先通过 jargon_explainer 检索黑话作为初始信息
  → ReAct Agent 循环（最多 5 轮，30 秒超时）：
      可用工具：
        - search_chat_history（聊天记录搜索）
        - query_words（黑话/缩写查询）
        - 人物信息查询
        - LPMM 知识库
      → found_answer 工具结束查询
  → 结果缓存到 ThinkingBack 表（10 分钟内相同问题复用）
```

**对我们的启发**：
- 我们的记忆检索是简单的向量搜索（LanceDB semantic search），MaiBot 用 ReAct Agent 做多轮推理检索，效果更好但成本更高
- 对我们来说，每次回复多一轮 LLM 调用不现实（5 个 Agent × ReAct 检索 = 成本爆炸）
- **折中方案**：@必唤场景（单个 Agent、实时性要求高）可以用 ReAct 检索；定时唤醒场景（batch、成本敏感）用简单向量搜索
- ThinkingBack 缓存（10 分钟复用）是好设计，我们可以在 MemoryService 加检索结果缓存

### 3.3 第三层：梦境整理（DreamAgent）

MaiBot 最独特的设计 — 模拟人类"做梦"来整理记忆：

```
定时调度（仅在允许时间段内）
  → 随机选一个 chat_id（要求 ≥10 条记录）
  → 随机选一条记忆作为切入点
  → ReAct Agent + function calling 进行记忆维护：
      可用工具：
        - search_chat_history
        - get_chat_history_detail
        - create_chat_history（新建记忆）
        - update_chat_history（更新记忆）
        - delete_chat_history（删除记忆）
        - search_jargon
        - finish_maintenance
  → 合并冗余记录、精简概括、删除噪声/过时信息
  → 生成梦境总结
```

**对我们的启发**：
- 这是我们 TDD 里完全没有的设计。记忆只增不减会导致检索质量下降和存储膨胀
- **强烈建议纳入 M2 或 M3**：Server 侧定时任务，用小模型整理每个 Agent 的记忆（合并重复、删除过时、精简概括）
- 可以复用定时唤醒的 batch 机制：5 个 Agent 的记忆整理按模型分组 batch 调用
- "梦境"这个概念本身也很有趣 — Agent 可以在聊天中提到"我昨晚梦到..."，增加拟人感

---

## 四、人格与关系系统

### 4.1 人格配置（TOML）

MaiBot 用 TOML 配置人格，21 个子配置项，包括：
- `PersonalityConfig`：基础人设
- `ChatConfig`：聊天行为参数
- `ExpressionConfig`：表情风格
- `ChineseTypoConfig`：故意打错字（拟人）
- `ResponseSplitterConfig`：长回复拆分（模拟打字节奏）

**对我们的启发**：
- 故意打错字和回复拆分是低成本高回报的拟人技巧，我们可以在回复后处理层加入
- 我们的人设是自然语言描述，比 TOML 更灵活但更难控制。两种方案各有优劣

### 4.2 关系系统

- `PersonInfo` 表存储用户画像（名字、平台、记忆点、群昵称）
- 记忆点格式：`category:content:weight`（结构化）
- LLM 起昵称：根据 QQ 昵称 + 群名片 + 头像，Bot 给用户起一个"私人昵称"
- Levenshtein 距离去重记忆

**对我们的启发**：
- 我们暂无关系系统（M3+），但 MaiBot 的"记忆点"设计可以参考
- LLM 起昵称是个有趣的拟人细节，成本低（一次调用）效果好

### 4.3 表情学习（ExpressionLearner）

- 按 situation（场景）学习表达风格
- 存储示例内容 + 使用频率
- 支持人工审核（checked / rejected / modified_by）

### 4.4 黑话学习（Jargon/BW Learner）

- Planner 识别 unknown_words → 推理含义 → 存储
- 双推理策略：带上下文推理 + 纯内容推理
- 累积 ≥100 次后停止推理（认为已学会）
- 区分全局黑话和群专属黑话

**对我们的启发**：
- 黑话学习对社区场景很有价值 — 用户群体会发展出自己的"梗"和"黑话"
- 可以作为 M3+ 的功能，让 Agent 逐渐学会社区用语

---

## 五、技术实现细节

### 5.1 数据库

SQLite + Peewee ORM，15 张表：

| 表 | 用途 |
|---|------|
| ChatStreams | 每个会话的状态 |
| Messages | 完整消息存储（含兴趣度、关键词、优先级） |
| ActionRecords | Planner 决策历史 |
| PersonInfo | 用户画像 |
| GroupInfo | 群信息（印象、话题、成员） |
| Expression | 学习到的表达风格 |
| Jargon | 黑话/缩写 |
| ChatHistory | 话题概括后的长期记忆 |
| ThinkingBack | 记忆检索思考过程缓存 |
| Emoji | 表情包注册（含描述和情绪标签） |
| Images / ImageDescriptions | 图片存储和描述缓存 |
| EmojiDescriptionCache | 表情描述缓存 |
| LLMUsage | API 用量追踪（token、成本、延迟） |
| OnlineTime | Bot 在线时间记录 |

**对比我们**：我们用 SQLite + LanceDB 混合，MaiBot 纯 SQLite（无向量搜索，靠 LLM ReAct 做语义检索）。我们的向量搜索成本更低但智能度不如 ReAct。

### 5.2 插件系统

五种组件类型：
- ACTION — Planner 可选的动作
- COMMAND — 正则匹配的直接命令
- TOOL — LLM tool calling
- SCHEDULER — 定时任务
- EVENT_HANDLER — 生命周期钩子

事件生命周期：
```
ON_START → ON_MESSAGE_PRE_PROCESS → ON_MESSAGE → ON_PLAN →
POST_LLM → AFTER_LLM → POST_SEND_PRE_PROCESS → POST_SEND → AFTER_SEND → ON_STOP
```

**对我们的启发**：
- 我们的 OpenClaw channel plugin 是平台适配层，MaiBot 的插件系统是行为扩展层，两者不在同一层面
- MaiBot 的事件钩子设计很完整，如果我们后期需要扩展 Agent 行为（比如"看到图片自动描述"），可以参考

### 5.3 LLM 集成

- 统一 `LLMRequest` 接口
- 按任务分配不同模型（planner / chat / tool / utils / relation_selection）
- 多 provider 支持（OpenAI 兼容接口）
- 每次调用记录 token 数、成本、延迟

**对比我们**：我们用 OpenRouter 统一入口 + 按 Agent 分配模型，MaiBot 按任务分配模型。MaiBot 的方式更精细（规划用便宜模型，回复用贵模型），我们可以借鉴。

---

## 六、MaiBot 的局限性（我们的优势）

| 维度 | MaiBot 局限 | 我们的优势 |
|------|------------|-----------|
| 多 Agent | 单 Bot 架构，不支持多 Agent 互动 | 多 Agent 社区，Agent 之间可以对话 |
| 经济系统 | 无，只追踪 LLM 用量 | 双货币经济，Agent 有预算约束 |
| 成本控制 | 单 Bot 成本可控，但 ReAct 检索每次多一轮 LLM | batch 代调 + 免费小模型意图识别 |
| 页游集成 | 纯聊天 | 聊天 + 页游社区 |
| 自建平台 | 依赖第三方平台（QQ/TG） | 自建 Web，完全可控 |
| Agent 自主性 | 被动响应为主（群聊靠频率控制） | 三级唤醒 + 定时主动发言 |

---

## 七、可借鉴清单（用户审核结果）

> 以下为经四方讨论（架构师 + 务实开发者 + 分析师 + 人类替身 PM）后，由用户最终审核确认的决策。审核日期：2026-02-15。

### M2 纳入（~85 行增量）

| 编号 | 借鉴点 | 决策 | 适配方案 | 工作量 |
|------|--------|------|---------|--------|
| R3 | LLM 用量追踪 | M2 建表版 | 新增 LLMUsage 表，在 AgentRunner 调用出口记录 token/成本/延迟 | ~50 行 |
| R5 | 频率控制自适应 | M2 内存版 | WakeupService 选人逻辑加"连续发言无回应"计数器，≥3 次降低权重，重启归零 | ~30 行 |
| R7 | 模型分配配置 | M2 .env 版 | wakeup-model 从硬编码改为环境变量可配 | ~5 行 |

### M3

| 编号 | 借鉴点 | 决策 | 适配方案 |
|------|--------|------|---------|
| R1 | 话题级记忆概括 | M3 | 早期数据量小，M2 简单摘要够用 |
| R4 | 梦境记忆整理 | M3 | Server 定时任务，用小模型整理记忆，复用 batch 机制 |
| R7 | 模型分配配置（完整版） | M3 | DB 配置表 + 前端 UI 下拉切换，按任务类型配置模型 |
| R10 | LLM 起昵称 | M3 | Agent 给用户起私人昵称，支持后续更改外号 / 人工指定 |
| R11 | ReAct 记忆检索 | M3 遗留 | 成本太高，有便宜替代方案，到时再看 |

### M4+

| 编号 | 借鉴点 | 决策 | 理由 |
|------|--------|------|------|
| R8 | 黑话学习 | M4+ | 社区还没跑起来，早期手动在人设里写几个词够了 |
| R9 | 表情学习 | M4+ | 人设 prompt 手写风格覆盖 80%，社区没跑起来没有学习素材 |

### 已有覆盖 / 不采纳

| 编号 | 借鉴点 | 决策 | 理由 |
|------|--------|------|------|
| R2 | 记忆检索结果缓存 | 已有设计覆盖 | Compiled Context Cache 脏标记机制已等价 |
| R6 | 回复后处理 | 不采纳 | 用户决策：不做 |

---

## 八、关键结论

1. **MaiBot 验证了"仿生记忆"的可行性**：话题概括 + 梦境整理 + ReAct 检索三层协作，让单 Bot 的记忆质量远超简单向量搜索。我们应该借鉴话题概括和梦境整理，但 ReAct 检索对多 Agent 成本不可接受。

2. **单 Bot 深度 vs 多 Agent 广度是根本差异**：MaiBot 可以在单 Bot 上投入大量 LLM 调用（ReAct 检索、梦境整理、表情学习），我们需要在 5-20 个 Agent 之间分摊预算，必须更注重成本效率。

3. **模式 1（Server 是大脑）的决策得到验证**：MaiBot 是单体架构，所有逻辑在一个进程内。它不需要解决状态同步问题。我们的多 Agent 架构下，Server 集中管理记忆/经济是正确选择 — 如果每个 Agent 都像 MaiBot 一样自己跑 ReAct 检索和梦境整理，成本和复杂度都不可接受。

4. **MaiBot 没有经济系统是个缺陷**：它只追踪 LLM 用量但不限制。我们的经济系统（信用点预算）是多 Agent 场景的必要约束，这是我们的差异化优势。
