# 角色定义 (Personas)

本目录定义多 Agent 协作系统中的所有角色。每个角色有独立文件，按需加载。

---

## 角色索引

| 角色 | 文件 | 触发词 |
|------|------|--------|
| 🏗️ 架构师 (Architect) | [architect.md](architect.md) | 架构、设计、选型、重构 |
| 📋 项目经理 (PM) | [pm.md](pm.md) | 计划、安排、需求、排期 |
| 💻 开发者 (Developer) | [developer.md](developer.md) | 开发、实现、编码、前端、后端 |
| ⚖️ 讨论专家 (Discussion Expert) | [discussion-expert.md](discussion-expert.md) | 协作讨论时启动 |
| 🧪 测试经理 (QA Lead) | [qa-lead.md](qa-lead.md) | 测试、质量、验证、QA |
| 📐 技术负责人 (Tech Lead) | [tech-lead.md](tech-lead.md) | 技术方案、可行性、技术评审 |
| 📝 记录员 (Recorder) | [recorder.md](recorder.md) | 自动触发（讨论结束/任务完成/会话结束） |

---

## 角色协作原则

### 子 Agent 使用规范
- 使用 `Task` 工具启动子 Agent 处理独立子任务
- 讨论类任务：并行启动 3 个子 Agent（使用 sonnet 模型以节省成本）
- 研究类任务：使用 Explore 类型子 Agent
- 实施类任务：使用 general-purpose 或 Bash 类型子 Agent
- 子 Agent 返回结果后，由主 Agent 综合汇报给用户

### 任务管理规范
- 复杂任务（≥3 步骤）必须使用 TaskCreate 创建任务列表
- 任务之间的依赖用 addBlockedBy/addBlocks 表示
- 开始工作前标记 in_progress，完成后标记 completed
- 按任务 ID 顺序处理（除非有特殊优先级）

### 决策记录规范
- 每个重要决策记录到 `claude-progress.txt`
- 格式：`[日期] [决策类型] 决策内容 | 原因`
- 讨论结果必须记录：选择了什么方案、为什么、放弃了哪些方案

---

## 🤖 模型选择策略

详见 [model-selection.md](../runbooks/model-selection.md) — 子 Agent 调度时的模型选择参考。

**速记**：默认 Sonnet，记录/搜索用 Haiku，复杂代码/架构用 Opus。
