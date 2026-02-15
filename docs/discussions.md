# 讨论记录归档

> 讨论记录按归属分两类存放：
> - **功能相关** → 跟着 spec 走，存在 `docs/specs/SPEC-XXX/讨论细节/` 目录下
> - **项目级通用** → 存在 `docs/discussions/` 目录下
>
> **生成时机**: 每次协作讨论/重大决策后，必须创建详细文件并在此更新索引。

---

## 快速总结

**SPEC-001 聊天功能：**
- Agent 自动回复采用 OpenClaw SDK + 150 行封装（方案G）
- 唤醒机制三级：@必唤 / 小模型选人 / 定时触发
- 经济系统双货币：信用点（不可购买）+ 游戏币
- Agent 人格：自然语言描述为主，JSON 元数据辅助
- Batch 推理：按模型分组定时唤醒 batch 调用，纳入 M2-12；回复生成也走 Server batch 代调（OpenRouter 按调用次数计费）
- Agent 交互成本：链式深度 ≤3，支持并发调用和 context cache

**项目级通用：**
- 竞品分析：MaiBot（单 Bot 仿生记忆框架），借鉴清单待用户审核
- 后端 FastAPI / 前端 React
- 记忆存储：SQLite + LanceDB 混合架构
- 流程规则：不同维度拆开辩论，记录必须可见
- 文档防丢失：对话是临时的，文件是持久的
- OpenClaw Plugin 放在 bot_civ repo 子目录（方案A）
- 保持 OpenClaw 自主 Agent 架构，不采用 CLI 子进程模式（含常驻 CLI 也否决）

---

## SPEC-001 聊天功能

| 主题 | 类型 | 决策结果 | 文件 |
|------|------|---------|------|
| Agent 自动回复架构 | 协作讨论 | 方案G（OpenClaw SDK + 150行封装） | [查看](specs/SPEC-001-聊天功能/讨论细节/Agent架构方案.md) |
| 唤醒机制最终方案 | 辩论 | 三级唤醒（@必唤/小模型选人/定时触发） | [查看](specs/SPEC-001-聊天功能/讨论细节/唤醒机制.md) |
| 经济系统双货币体系 | 用户决策 | 信用点 + 游戏币双货币 | [查看](specs/SPEC-001-聊天功能/讨论细节/经济系统.md) |
| Agent 人格系统设计 | 辩论 | 自然语言为主 + JSON元数据辅助 | [查看](specs/SPEC-001-聊天功能/讨论细节/Agent人格系统.md) |
| Batch 推理优化 | 架构讨论 | 定时唤醒按模型分组 batch 调用（含回复生成），纳入 M2-12 | [查看](specs/SPEC-001-聊天功能/讨论细节/Batch推理优化.md) |
| Agent 交互成本优化 | 架构讨论 | 链式深度限制、并发调用、context cache | [查看](specs/SPEC-001-聊天功能/讨论细节/Agent交互成本优化.md) |

## 项目级通用

| 日期 | 主题 | 类型 | 决策结果 | 文件 |
|------|------|------|---------|------|
| 2025-02-14 | 前后端框架独立辩论 | 辩论 | 后端 FastAPI / 前端 React | [查看](discussions/2025-02-14-frontend-backend-framework.md) |
| 2025-02-14 | 记忆数据库选型 | 辩论 | SQLite + LanceDB 混合架构 | [查看](discussions/2025-02-14-memory-database.md) |
| 2025-02-14 | 流程规则：禁止打包 + 强制记录 | 规则制定 | 不同维度拆开辩论 + 记录必须可见 | [查看](discussions/2025-02-14-process-rules.md) |
| 2025-02-14 | 文档防丢失机制 | 规则制定 | 对话是临时的，文件是持久的 | [查看](discussions/2025-02-14-doc-persistence.md) |
| 2026-02-14 | OpenClaw Plugin 代码放置方案 | 协作讨论 | 方案A（放在 bot_civ repo 子目录） | [查看](discussions/2026-02-14-openclaw-plugin-architecture.md) |
| 2026-02-15 | Cat Café CLI 子进程 vs OpenClaw 自主 Agent | 架构对比 | 保持 OpenClaw 架构，CLI 常驻也否决 | [查看](discussions/2026-02-15-catcafe-vs-openclaw-architecture.md) |
| 2026-02-15 | 竞品分析：MaiBot (MaiCore) | 竞品研究 | M2 纳入 R3/R5/R7，M3 延后 5 项，详见分析文档 | [查看](runbooks/reference-maibot-analysis.md) |
