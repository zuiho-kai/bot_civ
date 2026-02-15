# 模型选择策略

> 子 Agent 调度和主 Agent 定位的参考。按需查阅。

---

## 适用场景

### 主 Agent（与用户直接对话）
- **交互式讨论**（需求分析、设计决策、文档重构等）：主 agent 必须有足够能力，模型由用户启动时决定
- **批量执行**（"把 M1 后端任务都做了"）：主 agent 当调度器，用 Sonnet 即可，把实际工作派给合适模型的子 agent

### 子 Agent（被 Task 工具启动）
模型由主 agent 在 `Task(model=...)` 中指定，参考下方策略。

---

## 模型分类

| 模型 | 能力特点 | 成本 | 适用场景 |
|------|---------|------|---------|
| **Haiku** | 快速、格式化处理、基础推理 | 低 | 文件操作、记录、搜索 |
| **Sonnet** | 深度推理、代码生成、论证能力 | 中 | 设计、辩论、评审、简单实施 |
| **Opus** | 最强推理、复杂问题、创造力 | 高 | 架构设计、复杂代码、算法 |

## 按任务类型推荐

| 任务类型 | 推荐模型 | 理由 |
|---------|---------|------|
| 需求评审 | Sonnet | 多方评估，深度思考 |
| 技术设计 | Sonnet / Opus | 架构图、流程图设计 |
| 串讲讨论 | Sonnet | 理解验证、问题澄清 |
| 测试用例 | Sonnet | 边界条件识别 |
| 代码实施（简单） | Sonnet | CRUD、单文件改动、UI 调整 |
| 代码实施（复杂） | **Opus** | 算法、多模块联动、复杂业务逻辑 |
| 协作讨论 | Sonnet | 多角度分析、融合方案（3个并行，成本可控） |
| 文档记录 | **Haiku** | 进度更新、格式化写入 |
| 文件操作 | **Haiku** | Grep、Glob、Read |

### 代码实施复杂度判断

**用 Sonnet**：单文件 CRUD、UI 组件、简单 API、配置修改、测试编写
**用 Opus**：算法实现、多模块协调、WebSocket/并发逻辑、状态机、复杂调试

## 按角色推荐

- **Architect**：Opus（需要全局视野）
- **Tech Lead**：Sonnet（技术判断和可行性分析）
- **Developer**：Sonnet（简单）/ Opus（复杂）
- **QA Lead**：Sonnet（测试场景设计和边界思考）
- **Discussion Expert**：Sonnet（多角度分析，3个并行时成本可控）
- **Recorder**：**Haiku**（格式化记录，快速完成）

## 成本优化原则

1. **格式化任务优先 Haiku**：记录、搜索、简单读写
2. **并行任务避免 Opus**：讨论（3个Agent）用 Sonnet
3. **复杂代码必须 Opus**：算法、多模块联动，Sonnet 容易出错
4. **默认用 Sonnet**：不确定时的安全选择

## 示例

```python
Task(model="haiku", prompt="更新 claude-progress.txt...")          # 格式化写入
Task(model="sonnet", prompt="从性能角度分析方案A...")                   # 讨论，3个并行
Task(model="sonnet", prompt="实现 Agent CRUD API...")              # 简单 CRUD
Task(model="opus", prompt="实现唤醒服务的小模型选人算法...")          # 复杂逻辑
Task(model="opus", prompt="设计分布式记忆系统架构...")               # 复杂架构
```

## 踩坑记录

### 2026-02-14: Sonnet 做多步骤 DevOps 任务耗时过长

**任务**：git push + SSH 远程部署 + 写 Bot 脚本 + 端到端验证（一个 Task 包含 5 个串行步骤）

**耗时**：~23 分钟（79 次 tool call），Opus 预估 5-8 分钟

**原因分析**：
1. **任务粒度过大**：把 git push、远程部署、写脚本、验证全塞进一个 Task，Sonnet 缺乏全局规划能力，遇到问题时反复试错
2. **环境调试链路长**：远程 SSH + pip install + config 修复 + server 启动，每一步都可能出错，Sonnet 的错误恢复能力弱于 Opus
3. **不适合 Sonnet 的场景**：涉及多环境（本地 Windows + 远程 Linux）、多工具（git/gh/ssh/curl）、多步骤依赖的 DevOps 任务，实际复杂度高于"简单实施"

**教训**：
- **DevOps/部署类任务用 Opus**：涉及 SSH、环境配置、多步骤依赖的任务，Sonnet 容易在错误恢复上浪费大量 turn
- **或者拆成多个小 Task**：git push 一个 Task，远程部署一个 Task，写脚本一个 Task，各自独立
- **Sonnet 适合单一环境内的简单实施**：不要让它跨环境、跨工具链做复杂编排

**更新建议**：

| 任务类型 | 推荐模型 | 理由 |
|---------|---------|------|
| DevOps/部署（多步骤） | **Opus** | 跨环境、错误恢复、全局规划 |
| DevOps/部署（单步骤） | Sonnet | 单个 SSH 命令、单个配置修改 |
