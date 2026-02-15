# Multi-Agent Workflow System

> 本文件是主索引，详细内容按需跳转读取。
> 每次启动自动加载本文件 + `claude-progress.txt`。

---

## 📚 文档索引

### 角色定义
详见 [docs/personas/roles.md](docs/personas/roles.md)
- 🏗️ 架构师 / 📋 项目经理 / 💻 开发者 / ⚖️ 讨论专家 / 📝 记录员

### 功能规格 (`docs/specs/`)
- [SPEC-001 聊天功能](docs/specs/SPEC-001-聊天功能/README.md) — 需求/设计/进度/讨论，详见目录索引

### 讨论记录
- **索引**: [docs/discussions.md](docs/discussions.md) — 按功能/通用分组
- **功能相关**: 跟着 spec 走，存在 `docs/specs/SPEC-XXX/讨论细节/` 目录下
- **项目级通用**: `docs/discussions/` — 框架选型、流程规则等

### 操作手册 (`docs/runbooks/`)
- [常见错误案例合集](docs/runbooks/common-mistakes.md) — 按角色分类的错题本索引
- [模型选择策略](docs/runbooks/model-selection.md) — 子 Agent 调度时的模型选择参考
- [分层进度管理指南](docs/runbooks/layered-progress-guide.md)
- [试运行完整流程](docs/runbooks/trial-run-complete-workflow.md)
- [Cat Café 经验参考](docs/runbooks/reference-catcafe-lessons.md) — 外部项目借鉴：元规则、交接五件套、P1/P2/P3 分级

### 工作流程 (`docs/workflows/`)
- [协作讨论流程](docs/workflows/debate-workflow.md)
- [标准开发流程](docs/workflows/development-workflow.md)
- [前后端联调流程](docs/workflows/integration-workflow.md)

### 文档模板 (`docs/templates/`)
- [文档模板库](docs/templates/doc-templates.md) — 需求评审、技术设计、测试用例、测试报告、上线总结模板

### 其他
- [产品需求文档 PRD](docs/PRD.md) — 项目愿景、核心概念、技术决策
- [接口契约](docs/api-contract.md) — 前后端协作边界
- [变更记录](docs/changelog.md) — 文档架构、流程规则等历史变更

---

## ⚡ 核心规则

### 1. 强制记录（最高优先级）
- **任务完成/里程碑** → 更新 `claude-progress.txt`
- **文档架构/流程变更** → 记录到 `docs/changelog.md`
- 格式：`### [日期] [类型] 标题` + 背景/结论/行动项

### 2. 防丢失
- 原始需求、设计思路 → 写入 `docs/PRD.md`
- 技术决策 → 同时记录到 `claude-progress.txt` 和 `docs/PRD.md`
- 原则：**对话是临时的，文件是持久的**

### 3. 分层进度管理
- **小进展**（单个API/组件/测试）→ 只记 `server/progress.md` 或 `web/progress.md`
- **大里程碑**（M1/M2完成、联调、架构决策）→ 同步到 `claude-progress.txt`
- 详细规范见 [分层进度管理指南](docs/runbooks/layered-progress-guide.md)

### 4. 讨论记录
- **功能相关** → 落盘到 `docs/specs/SPEC-XXX/讨论细节/主题.md`
- **项目级通用** → 落盘到 `docs/discussions/YYYY-MM-DD-主题.md`
- 摘要索引 → 同步更新 `docs/discussions.md`（按功能/通用分组）

### 5. 讨论触发条件
详见 [协作讨论流程](docs/workflows/debate-workflow.md)

**必须讨论**：架构选型、设计模式、影响面>3文件的重构、≥2种可行方案的新功能、用户要求
**不需要讨论**：Bug修复、单文件改动、文档更新、用户明确指示

---

## 🔄 快速工作流

### 标准开发流程
```
用户提出需求 → [架构师] 判断复杂度
  ├── 简单 → 直接实施
  └── 复杂 → 协作讨论 → [PM] 拆解任务 → [开发者] 逐个实施
每完成一个任务 → 📝 更新进度文件
```

### 会话恢复流程
```
1. 读取 CLAUDE.md + claude-progress.txt
2. 检查 TaskList
3. 向用户汇报：上次做到哪里，本次从哪里继续
```

---

## 🎯 双终端分工

- **后端终端**: 只改 `server/`（API、数据库、Agent逻辑、LLM集成）
- **前端终端**: 只改 `web/`（React UI、WebSocket客户端、页面交互）
- **接口契约**: `docs/api-contract.md` 是协作边界，改接口需同步更新
- 联调流程见 [integration-workflow.md](docs/workflows/integration-workflow.md)

---

## 🚀 快速参考

- "开始新项目" → 架构师分析 + PM建任务
- "讨论一下" → 启动协作讨论流程
- "目前进度" → 读取 claude-progress.txt + TaskList
- "继续工作" → 读取进度 → 捡起下一个任务
