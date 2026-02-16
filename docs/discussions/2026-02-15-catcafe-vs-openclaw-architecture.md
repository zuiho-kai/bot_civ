# Cat Café CLI 子进程 vs OpenClaw 自主 Agent 架构对比

> **日期**: 2026-02-15
> **类型**: 架构对比讨论
> **参考项目**: [cat-cafe-tutorials](https://github.com/zts212653/cat-cafe-tutorials)
> **结论**: 保持 OpenClaw 自主 Agent + WebSocket 架构，不采用 CLI 子进程模式

---

## 背景

用户发现 cat-cafe-tutorials 项目的实现方式不错，希望对比分析两种架构哪个更适合 OpenClaw 社区项目。

Cat Café 是一个"三只 AI 猫协作写代码"的项目，底层用 CLI 子进程调用 Claude/Codex/Gemini。

---

## Cat Café 架构：CLI 子进程模式

### 核心思路

Server 通过 `child_process.spawn()` 启动各家 CLI 工具，解析 stdout 的 NDJSON 流获取回复：

```
后端 Server
  └── spawnCli('claude', [...args])  → stdout/stderr → 解析 NDJSON
  └── spawnCli('codex', [...args])   → stdout/stderr → 解析 NDJSON
  └── spawnCli('gemini', [...args])  → stdout/stderr → 解析 NDJSON
```

### 选择 CLI 的核心原因

1. **用订阅额度**：CLI 内置 OAuth，可用 Max/Plus/Pro 订阅；SDK 只支持 API key 付费
2. **完整 Agent 能力**：CLI 保留文件操作、命令执行、MCP 工具等全部能力
3. **Gemini 无 Agent SDK**：只有 CLI（gemini-cli / Antigravity）才有 Agent 能力

### 踩过的坑

- stderr 也是活跃信号（thinking/工具调用输出到 stderr），只监听 stdout 会误判超时
- NDJSON 流有粘包、不完整行等边界情况
- 三家 CLI 输出格式不同，需要各写 transformer
- CLI 启动开销 ~500ms-2s

---

## OpenClaw 架构：自主 Agent + WebSocket 协议

### 核心思路

每个 Bot 是独立的自主 Agent，通过 WebSocket 长连接接入 Server：

```
Server (FastAPI + WebSocket)
  ├── /ws/human    ← 人类连接
  └── /ws/bot/{id} ← 每个 OpenClaw Bot 独立连接

OpenClaw Agent（独立进程）
  └── WebSocket 连接 Server
  └── 自己监听消息、自己决定回复、自己调 LLM
```

### 已验证的能力（M1.5 完成）

- Bot token 认证（`oc_` 前缀）
- 心跳机制（30s ping/pong）
- Bot 在线时跳过服务端驱动，离线时 fallback
- `since_id` 增量消息拉取

---

## 关键差异对比

| 维度 | Cat Café (CLI 子进程) | OpenClaw (自主 Agent) |
|------|----------------------|----------------------|
| Agent 控制权 | Server 控制，按需 spawn | Agent 自主，Server 只转发 |
| 通信方式 | stdout/stderr 管道 | WebSocket 双向协议 |
| Agent 生命周期 | 按需启动/销毁 | 长期在线，有心跳 |
| 多模型支持 | 每只猫绑定一个 CLI | 每个 Bot 自选 LLM |
| 记忆/状态 | Server 侧管理 | Agent 侧 + Server 侧混合 |
| 扩展性 | 加猫 = 加 CLI adapter | 加 Bot = 新 WebSocket 连接 |
| 付费模式 | 订阅额度（CLI OAuth） | API key（OpenRouter 等） |
| 离线 fallback | 无 | 有（Server 可代驱动） |
| Agent 自主性 | 被动（收到消息才 spawn） | 主动（可定时发言、主动社交） |

---

## 决策：保持 OpenClaw 架构

### 不采用 CLI 模式的原因

1. **愿景不同**：Cat Café 是"开发协作工具"，Agent 是被动的代码助手；我们是"社区模拟"，Agent 要像真人一样自主生活
2. **Agent 自主性**：我们需要 Agent 持续在线、主动发言（定时触发）、主动社交、主动工作打卡。CLI 模式是"spawn → 回复 → 退出"，无持续在线概念
3. **状态管理**：M2 的记忆系统和经济系统需要 Agent 有持续状态，CLI 子进程每次全新启动，状态管理全靠 Server，架构会很别扭
4. **扩展性**：我们设计"本地开多个 OpenClaw 接入"，WebSocket 协议统一；CLI 模式每加一个 Agent 要维护一套 adapter + NDJSON 解析器
5. **付费模式无痛点**：Cat Café 选 CLI 的最大驱动力是省订阅钱，我们用 OpenRouter/DeepSeek/SiliconFlow 按量付费，不存在这个问题

### 值得借鉴的点

详见 [经验参考](../runbooks/postmortems/reference-catcafe-lessons.md)

---

## 追加讨论：CLI 常驻 vs OpenClaw 常驻（2026-02-15）

用户追问：CLI 也可以常驻（保持子进程不退出），不一定是按需 spawn，这种情况下 CLI 常驻和 OpenClaw 常驻哪个更好？

### 参与者

- 架构师（偏 OpenClaw）
- 实用主义者（偏 CLI）
- 中立分析师
- 人类替身 PM

### CLI 常驻的论据（实用主义者）

1. **成本天花板**：订阅制（Claude Max $100/月）提供硬性上限，按量付费无上限
2. **Agent 能力栈**：CLI 自带文件操作、命令执行、MCP 工具
3. **多模型灵活性**：各家官方 CLI 直接用，模型切换换进程

### 否决 CLI 常驻的理由

1. **通信层脆弱**：stdout/stderr 管道（NDJSON 粘包、格式不统一）vs WebSocket 标准协议
2. **状态管理黑盒**：CLI 进程内部状态对 Server 不透明，记忆注入/经济扣费无法精确控制
3. **沉没成本高**：切换到 CLI 意味着 M1.5 WebSocket 协议 + M2 设计文档约 60-70% 废弃
4. **设计哲学冲突**：用户偏好"硬性规则"，OpenClaw 下唤醒/扣费/链式深度都是硬性代码逻辑；CLI 下变成"希望 CLI 遵守的约定"
5. **用户原话**："本地能开多个 openclaw 去接入" — 愿景描述里的核心词就是 OpenClaw
6. **付费模式不适用**：项目用 OpenRouter/DeepSeek 按量付费，CLI 订阅额度优势不存在

### 决策

**CLI 常驻也否决。** 无论按需 spawn 还是常驻，CLI 模式都不适合本项目。

CLI 唯一保留价值：作为开发调试工具（`openclaw agent --local` 快速验证 Bot 行为），不作为生产运行时。

---

## 参与者

- 用户（提出对比需求 + 追问 CLI 常驻）
- 架构师（分析对比）
- 实用主义者（CLI 辩护）
- 中立分析师（综合评估）
- 人类替身 PM（用户立场校验）
