# 竞品深度分析：Cat Café（猫猫咖啡馆）

**日期**：2026-02-19
**仓库**：https://github.com/zts212653/cat-cafe-tutorials（教程仓库，代码私有）
**定位**：三 AI 猫协作开发系统（CLI 子进程 + MCP 回传 + A2A 路由）
**技术栈**：TypeScript / Node.js / Redis / Claude CLI + Codex CLI + Gemini CLI
**社区热度**：11 个 issues（含技术讨论），500 人群瞬间满员，有用户跟做教程

---

## 一、产品定位对比

| 维度 | Cat Café | 我们（bot_civ） |
|------|----------|-----------------|
| 核心愿景 | 三只 AI 猫协作写代码 + 游戏化社交 | 多 Agent 社区（聊天群 + 页游城市） |
| Agent 数量 | 3 只（固定：布偶猫/缅因猫/暹罗猫） | 5-20 个（可扩展） |
| Agent 模型 | Claude Opus + Codex + Gemini（异构） | 统一走 OpenRouter（同构） |
| 架构模式 | Server spawn CLI 子进程 + MCP 回传 | Server + 自主 Agent WebSocket 接入 |
| 平台 | 自建 Web（私有，未开源） | 自建 Web 社区 |
| 付费模式 | CLI 订阅额度（Max/Plus/Pro） | API key 按量付费（OpenRouter） |
| 记忆系统 | Hindsight 集成（search-evidence/reflect/retain） | 三层结构化（短期+长期+公共，SQLite+NumPy） |
| 经济系统 | 无 | 双货币（信用点+游戏币） |
| A2A 协作 | @mention 路由 + worklist 串行 + 深度限制 15 | @唤醒 + 链式深度 ≤3 |
| 开源状态 | 教程公开，代码私有 | 私有 |

**核心差异**：Cat Café 做的是"三只异构 AI 猫协作写代码"，核心挑战是跨模型协作（Claude/Codex/Gemini 各有不同的 CLI 接口和能力）。我们做的是"多 Agent 社区模拟"，核心挑战是 Agent 自主性和社区感。Cat Café 的 Agent 是被动的（收到消息才 spawn），我们的 Agent 要像真人一样主动生活。

---

## 二、架构深度分析

### 2.1 CLI 子进程模式

Cat Café 的核心架构决策（ADR-001）：

```
后端 Server (Node.js)
  └── spawnCli('claude', [...args])  → stdout NDJSON → 解析
  └── spawnCli('codex', [...args])   → stdout NDJSON → 解析
  └── spawnCli('gemini', [...args])  → stdout NDJSON → 解析
```

选择 CLI 而非 SDK 的核心原因：
1. CLI 可用订阅额度（Max $100/月），SDK 只能 API key 付费
2. CLI 保留完整 Agent 能力（文件操作、命令执行、MCP 工具）
3. Gemini 当时无 Agent SDK，只有 CLI 有 Agent 能力

**对我们的意义**：我们已在 2026-02-15 讨论中否决了 CLI 模式。我们用 OpenRouter 按量付费，不存在订阅额度痛点；WebSocket 协议比 stdout 管道更稳定；Agent 自主性需要长期在线，CLI 的 spawn-reply-exit 模式不适合。

### 2.2 MCP 回传机制（核心创新）

Cat Café 最精彩的设计。解决"猫怎么在执行过程中主动说话"：

```
Claude:  spawn → --mcp-config 动态挂载 → MCP Server (stdio) → 原生工具调用
Codex:   spawn → 系统提示词注入 HTTP 端点 → AI 自己发 curl → callback 路由
Gemini:  spawn → 系统提示词注入 HTTP 端点 → AI 自己发 curl → callback 路由
```

两条路径，一个终点。后端统一 8 个 callback 路由：
- `post-message` — 发消息
- `thread-context` — 获取对话上下文
- `pending-mentions` — 获取待处理 @提及
- `update-task` — 更新任务状态
- `request-permission` — 请求危险操作授权
- `search-evidence` — 检索项目记忆
- `reflect` — 项目反思
- `retain-memory` — 沉淀长期记忆

认证：invocationId + callbackToken 双 UUID，通过环境变量传递，有 TTL。

**设计哲学**：CLI 输出 = 猫的内心独白（私有），post_message = 猫主动开口（公开）。这个分离让系统可以做游戏（猫猫杀需要隐私）、茶话会等非 coding 场景。

**对我们的启发**：
- 我们的 Agent 通过 WebSocket 直接发消息，天然具备"主动说话"能力，不需要 MCP 回传这层
- 但"内心独白 vs 公开发言"的分离思路值得借鉴 — Agent 的 LLM 推理过程和最终发言应该分开，前端可以选择性展示
- callback 路由的扩展模式（从 3 个到 8 个，复用同一套基础设施）是好的工程实践

### 2.3 A2A 路由（Agent-to-Agent）

Cat Café 的 A2A 经历了一次 P0 事故后重新设计：

**初始设计（两条路径）**：
- Path A (Worklist)：猫回复结束后检测 @mention → 追加到 worklist 串行执行
- Path B (Callback)：猫执行过程中通过 MCP callback 发消息 → 检测 @mention → 独立发起新调用

**P0 事故（2026-02-14 情人节）**：
- 双重开火：同一个 @mention 被两条路径各触发一次
- 无限递归：Path B 没有深度限制
- 不可取消：callback 触发的 child invocation 未注册到 tracker
- 结果：两只猫无限互调，Stop 按钮失效，被迫强制重启

**修复方案（F27 路径统一）**：
- callback 不再自己执行猫调用，改为追加到父 worklist
- 一条路径 → 自然去重 + 共享深度限制 + 共享 AbortController

**对我们的启发**：
- **教训 1**：同一个语义操作只保留一条路径。我们的唤醒机制（@必唤 / 小模型选人 / 定时触发）是三种触发方式但最终都走同一个 AgentRunner，这是对的
- **教训 2**：所有链式执行必须有深度上限。我们的 chain_depth ≤3 是硬性限制，比 Cat Café 初始设计更保守
- **教训 3**：所有后台执行必须可取消。我们的 WebSocket 模式下，Server 可以直接断开连接或发 cancel 指令
- **教训 4**：局部修复的连锁反应。三次"合理的局部修复"组合产生了 P0 灾难

### 2.4 数据安全事故

Cat Café 经历了两次数据丢失：
1. Redis 307 个 key 变成 15 个（95% 数据消失）
2. 辩论冠军记录因重启丢失

由此建立了三层防线（F23/F25）：
- 防腐门（数据写入前校验）
- 证据闸门（关键操作留证据链）
- Worktree 隔离铁律

**对我们的启发**：我们用 SQLite 单文件数据库，不存在 Redis 重启丢数据的问题。但"防腐门"思路值得借鉴 — Agent 写入记忆/经济数据前应该有校验层。

---

## 三、教程体系分析

Cat Café 的教程仓库是其最大的社区资产：

| 课 | 主题 | 核心价值 |
|----|------|---------|
| 00 | AI Agent 概念演进 | Function Call → MCP → Skills → Agent 的演进脉络 |
| 01 | 从 SDK 到 CLI | 选型决策过程，SDK 付费模式的坑 |
| 02 | CLI 工程化 | stderr 教训、Redis 隔离、幻觉防护 |
| 03 | 元规则 | AI 弱点驱动的协作规范设计 |
| 04 | A2A 路由 | 多 Agent 路由的 P0 事故复盘 |
| 05 | MCP 回传 | 让 Agent 主动说话的机制设计 |
| 06 | 数据安全 | 两次数据丢失 + 三层防线 |
| 07-10 | 待写 | 上下文工程、Session 管理、长期记忆、降级容错 |

**社区反馈（Issues）**：
- 有用户跟做教程并提出实现问题（#8, #9, #11）
- 有用户问为什么不用 AutoGen/AgentOrchestra（#3）
- 有用户催更（#7）
- 500 人群满员

**对我们的启发**：
- Cat Café 通过教程建立了社区影响力，即使代码未开源。我们可以考虑类似策略 — 写开发复盘/技术博客
- 他们的"证据标注"（`[事实]` / `[推断]` / `[外部]`）是好的写作规范

---

## 四、Cat Café 的局限性（我们的优势）

| 维度 | Cat Café 局限 | 我们的优势 |
|------|-------------|-----------|
| Agent 自主性 | 被动（收到消息才 spawn） | 主动（定时唤醒 + 自主行为循环） |
| Agent 数量 | 固定 3 只，加猫需写新 adapter | 可扩展，新 Bot 只需 WebSocket 接入 |
| 经济系统 | 无 | 双货币 + 预算约束 + 商店 |
| 页游集成 | 纯聊天/协作 | 聊天 + 页游城市 + 建造系统 |
| 通信稳定性 | stdout/stderr 管道（NDJSON 粘包） | WebSocket 标准协议 |
| 状态管理 | CLI 子进程无状态，全靠 Server | Agent 可持有本地状态 + Server 同步 |
| 模型灵活性 | 每只猫绑定一个 CLI 工具 | 统一 OpenRouter，模型随时切换 |
| 成本控制 | 订阅制（固定月费） | 按量付费，精确控制 |
| 代码开源 | 私有 | 私有（但我们有完整代码） |

---

## 五、Cat Café 的优势（我们的差距）

| 维度 | Cat Café 优势 | 我们的差距 |
|------|-------------|-----------|
| A2A 深度 | 15 轮深度 + P0 事故后的成熟路由 | 链式深度 ≤3，A2A 场景较简单 |
| 异构模型协作 | Claude/Codex/Gemini 三模型各司其职 | 统一模型，缺乏异构协作经验 |
| 事故复盘 | 详细的 P0 事故分析 + 修复方案 | 尚未经历生产级事故 |
| 社区教育 | 7 课完整教程 + 活跃 issues | 无对外教程 |
| 隐私分离 | CLI 内心独白 vs post_message 公开发言 | Agent 所有输出对聊天室可见 |
| 记忆系统 | Hindsight 集成（search/reflect/retain） | 向量搜索为主，缺 LLM 摘要和反思 |
| 授权机制 | request-permission 危险操作授权 | 无（Agent 行为无人类审批门） |

---

## 六、可借鉴清单

### 立即可用（M6.2 或当前迭代）

| 编号 | 借鉴点 | 适配方案 | 工作量 |
|------|--------|---------|--------|
| C1 | 内心独白 vs 公开发言分离 | Agent LLM 推理过程和最终发言分开存储/展示，前端可切换"调试模式" | ~30 行 |
| C2 | 所有链式执行必须可取消 | 检查现有唤醒链是否都注册到可取消机制 | 审查 |

### M7 纳入

| 编号 | 借鉴点 | 适配方案 |
|------|--------|---------|
| C3 | 危险操作授权门 | Agent 执行高成本操作（大额转账、删除记忆）前请求人类批准 |
| C4 | 记忆反思机制 | 定时任务用小模型整理 Agent 记忆（合并重复、删除过时），类似 MaiBot 梦境 + Cat Café reflect |
| C5 | A2A 路由去重 | 如果未来 A2A 深度增加，参考 Cat Café 的 worklist 统一路径设计 |

### 长期参考

| 编号 | 借鉴点 | 说明 |
|------|--------|------|
| C6 | 教程/复盘输出 | 写开发复盘建立社区影响力 |
| C7 | 证据标注规范 | 文档中标注 `[事实]` / `[推断]` / `[外部]` |
| C8 | 异构模型协作 | 如果未来引入不同模型的 Agent，参考 Cat Café 的 adapter 模式 |

### 已有覆盖 / 不采纳

| 编号 | 借鉴点 | 决策 | 理由 |
|------|--------|------|------|
| C9 | CLI 子进程模式 | 不采纳 | 已在 2026-02-15 讨论中否决，详见架构对比文档 |
| C10 | MCP 回传机制 | 已有覆盖 | WebSocket 天然支持双向通信，不需要 HTTP callback 层 |
| C11 | 订阅额度付费 | 不适用 | 我们用 OpenRouter 按量付费 |

---

## 七、关键结论

1. **Cat Café 验证了多 AI Agent 协作的可行性和复杂性**：A2A 路由的 P0 事故是极好的反面教材，证明"两条路径做同一件事"是定时炸弹。我们的单一唤醒路径设计是正确的。

2. **MCP 回传是 CLI 模式的必要补丁，不是我们需要的**：Cat Café 需要 MCP 回传是因为 CLI 子进程天然是被动的。我们的 WebSocket Agent 天然具备主动通信能力。

3. **"内心独白 vs 公开发言"的分离是通用设计**：不管底层架构如何，Agent 的推理过程和最终输出应该分开。这对调试、隐私、游戏化都有价值。

4. **Cat Café 的社区运营值得学习**：教程仓库 + 500 人群 + 活跃 issues，即使代码未开源也建立了影响力。

5. **两个项目互补而非竞争**：Cat Café 专注"开发协作"（深度），我们专注"社区模拟"（广度）。Cat Café 的 Agent 是工具，我们的 Agent 是居民。

---

## 关联文档

- [架构对比讨论](../../discussions/2026-02-15-catcafe-vs-openclaw-architecture.md)
- [Cat Café 经验参考](./reference-catcafe-lessons.md)
- [MaiBot 竞品分析](./reference-maibot-analysis.md)
- [原型差距分析](../../discussions/2026-02-gap-analysis.md)
