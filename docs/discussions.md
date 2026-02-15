# 讨论记录归档

> 讨论记录按归属分两类存放：
> - **功能相关** → 跟着 spec 走，存在 `docs/specs/SPEC-XXX/讨论细节/` 目录下
> - **项目级通用** → 存在 `docs/discussions/` 目录下
>
> **生成时机**: 每次协作讨论/重大决策后，必须创建详细文件并在此更新索引。

---

## SPEC-001 聊天功能

| 主题 | 类型 | 决策结果 | 文件 |
|------|------|---------|------|
| Agent 自动回复架构 | 协作讨论 | 方案G（OpenClaw SDK + 150行封装） | [查看](specs/SPEC-001-聊天功能/讨论细节/Agent架构方案.md) |
| 唤醒机制最终方案 | 辩论 | 三级唤醒（@必唤/小模型选人/定时触发） | [查看](specs/SPEC-001-聊天功能/讨论细节/唤醒机制.md) |
| 经济系统双货币体系 | 用户决策 | 信用点 + 游戏币双货币 | [查看](specs/SPEC-001-聊天功能/讨论细节/经济系统.md) |
| Agent 人格系统设计 | 辩论 | 自然语言为主 + JSON元数据辅助 | [查看](specs/SPEC-001-聊天功能/讨论细节/Agent人格系统.md) |

## 项目级通用

| 日期 | 主题 | 类型 | 决策结果 | 文件 |
|------|------|------|---------|------|
| 2025-02-14 | 前后端框架独立辩论 | 辩论 | 后端 FastAPI / 前端 React | [查看](discussions/2025-02-14-frontend-backend-framework.md) |
| 2025-02-14 | 记忆数据库选型 | 辩论 | SQLite + LanceDB 混合架构 | [查看](discussions/2025-02-14-memory-database.md) |
| 2025-02-14 | 流程规则：禁止打包 + 强制记录 | 规则制定 | 不同维度拆开辩论 + 记录必须可见 | [查看](discussions/2025-02-14-process-rules.md) |
| 2025-02-14 | 文档防丢失机制 | 规则制定 | 对话是临时的，文件是持久的 | [查看](discussions/2025-02-14-doc-persistence.md) |
| 2026-02-14 | OpenClaw Plugin 代码放置方案 | 协作讨论 | 方案A（放在 bot_civ repo 子目录） | [查看](discussions/2026-02-14-openclaw-plugin-architecture.md) |
| 2026-02-15 | Cat Café CLI 子进程 vs OpenClaw 自主 Agent | 架构对比 | 保持 OpenClaw 架构，不采用 CLI 子进程 | [查看](discussions/2026-02-15-catcafe-vs-openclaw-architecture.md) |
