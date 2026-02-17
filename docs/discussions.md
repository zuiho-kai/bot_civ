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
- M4 Agent 自主性：世界状态驱动单次 LLM 决策（城市模拟器视角），决策与聊天生成分离防人格污染，每小时 1 次，成本 ~96 次/天

**项目级通用：**
- 竞品分析：MaiBot（单 Bot 仿生记忆框架），借鉴清单待用户审核
- 后端 FastAPI / 前端 React
- 记忆存储：SQLite 单库（原 LanceDB 已决议移除，embedding 存 SQLite BLOB + NumPy 暴力搜索）
- 流程规则：不同维度拆开辩论，记录必须可见
- 文档防丢失：对话是临时的，文件是持久的
- OpenClaw Plugin 放在 bot_civ repo 子目录（方案A）
- 保持 OpenClaw 自主 Agent 架构，不采用 CLI 子进程模式（含常驻 CLI 也否决）
- 文档改进：添加截图/架构图/对比表格，新增代码导航和进度文件说明
- 外部差评评估：40% 事实错误（并发bug/悬赏验证/Batch声称），30% 合理但不紧急，30% 真问题（产品定位对外不清晰+部署门槛高）；技术架构不变，P0 改进 README 定位和部署体验
- 去掉 LanceDB：全票通过 SQLite BLOB + NumPy 暴力 cosine similarity 替换，保留语义搜索能力，去掉 LanceDB/PyArrow 依赖；embedding 模型选择（本地 vs API）另开讨论

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
| M4 Agent 自主性改造 | 五方 Debate | 世界状态驱动单次 LLM 决策（城市模拟器视角），决策与聊天生成分离 | [查看](discussions/agent-autonomy-debate.md) |

## 项目级通用

| 日期 | 主题 | 类型 | 决策结果 | 文件 |
|------|------|------|---------|------|
| 2025-02-14 | 前后端框架独立辩论 | 辩论 | 后端 FastAPI / 前端 React | [查看](discussions/2025-02-14-frontend-backend-framework.md) |
| 2025-02-14 | 记忆数据库选型 | 辩论 | SQLite + LanceDB 混合架构 | [查看](discussions/2025-02-14-memory-database.md) |
| 2025-02-14 | 流程规则：禁止打包 + 强制记录 | 规则制定 | 不同维度拆开辩论 + 记录必须可见 | [查看](discussions/2025-02-14-process-rules.md) |
| 2025-02-14 | 文档防丢失机制 | 规则制定 | 对话是临时的，文件是持久的 | [查看](discussions/2025-02-14-doc-persistence.md) |
| 2026-02-14 | OpenClaw Plugin 代码放置方案 | 协作讨论 | 方案A（放在 bot_civ repo 子目录） | [查看](discussions/2026-02-14-openclaw-plugin-architecture.md) |
| 2026-02-15 | Cat Café CLI 子进程 vs OpenClaw 自主 Agent | 架构对比 | 保持 OpenClaw 架构，CLI 常驻也否决 | [查看](discussions/2026-02-15-catcafe-vs-openclaw-architecture.md) |
| 2026-02-15 | 竞品分析：MaiBot (MaiCore) | 竞品研究 | M2 纳入 R3/R5/R7，M3 延后 5 项，详见分析文档 | [查看](runbooks/postmortems/reference-maibot-analysis.md) |
| 2026-02-15 | 进度索引优化 | 协作讨论 | claude-progress.txt 顶部增加"最近7天活动"章节（手动维护，可选自动化） | [查看](discussions/2026-02-15-progress-index-optimization.md) |
| 2026-02-15 | 文档改进（吸引力+清晰度） | 项目优化 | 添加截图/架构图/对比表格，新增 CODE_MAP.md 和 PROGRESS_FILES.md | [查看](discussions/2026-02-15-documentation-improvement.md) |
| 2026-02-16 | 外部差评回应与改进评估 | 架构评审 | 40% 事实错误，30% 合理但不紧急，30% 真问题（定位+部署）；架构不变，改进对外沟通 | [查看](discussions/2026-02-16-external-criticism-review.md) |
| 2026-02-16 | 去掉 LanceDB 向量数据库 | 架构讨论 | 全票通过方案 A（SQLite BLOB + NumPy 替换 LanceDB），保留语义搜索，去掉重依赖 | [查看](discussions/2026-02-16-remove-lancedb.md) |
| 2026-02-16 | M2.2 前端组件库选型 | 五方讨论 | M2.2 纯 CSS 清理 + stylelint；M3 按需引入 Radix UI；M4 评估 Tailwind；shadcn/ui 否决 | — |
| 2026-02-18 | 开发任务看板方案调研 | 技术调研 | 四种方案已对比，需求不明确，方案未定 | [查看](discussions/2026-02-18-task-board-research.md) |
