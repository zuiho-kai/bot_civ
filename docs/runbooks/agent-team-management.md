# Agent Team 管理实践

> **来源**: M2 Phase 1 实战经验 + Anthropic 官方指导
> **日期**: 2026-02-15
> **性质**: 多 Agent 团队的生命周期管理、成本控制、任务分配策略

---

## 一、核心原则

Anthropic 官方建议："Find the simplest solution possible, and only increase complexity when needed."

- 能用单 Agent 解决的不开团队
- 能用 subagent 解决的不开 teammate
- 开了团队要及时关闭，空闲队友持续消耗 token

---

## 二、团队分配策略

### ❌ 按任务分配（Phase 1 教训）

Phase 1 做法：4 个独立任务 → 4 个队友（lancedb-dev, economy-dev, usage-dev, freq-dev）

问题：
- 任务完成后队友立刻无事可做
- 必须关闭团队，下个 Phase 重建
- 新队友没有上下文，需要重新探索代码库
- 团队创建/关闭开销被反复支付

### ✅ 按功能线分配（推荐）

按依赖链分配队友，一个队友负责一条完整的功能线：

```
记忆线队友: M2-1 → M2-2 → M2-3 → M2-4（串行，同一人做）
经济线队友: M2-5 → M2-6 → M2-7 → M2-8（串行，同一人做）
前端线队友: M2-9 → M2-10（等后端 API 就绪）
测试队友:   每个 Phase 结束拉起验收，用完即关
```

优点：
- 上下文天然连续，队友熟悉自己改过的文件
- 不同线的队友不改同一个文件，避免冲突
- 每个队友 3-4 个任务，符合 Anthropic 建议的 5-6 任务/队友
- 线完成后才关闭，减少团队重建次数

### 决策树

```
任务之间有依赖关系？
  ├── 是，且改同一批文件 → 同一个队友串行做
  ├── 是，但改不同文件 → 不同队友，用 blockedBy 管理依赖
  └── 否 → 不同队友并行做

队友做完当前任务后还有后续？
  ├── 是 → 保持存活，分配下一个任务
  └── 否 → shutdown_request 关闭
```

---

## 三、Anthropic 官方团队使用指导

### 适合开团队的场景

- 跨层协作（前端 + 后端 + 测试，各自独立文件）
- 多条并行功能线（记忆线 / 经济线 / 前端线）
- 需要队友间通信协调的任务
- 竞争性调查（多个假设并行验证）

### 不适合开团队的场景

- 纯串行任务（一个做完才能做下一个）
- 多个队友会改同一个文件（导致覆盖）
- 协调开销 > 并行收益
- 任务间依赖过多

### 成本控制要点

| 策略 | 说明 |
|------|------|
| 队友用 Sonnet | 不要用 Opus，性价比差距大 |
| 及时关闭空闲队友 | 活着就消耗 token |
| spawn prompt 要精准 | 写清楚改哪些文件、依赖什么，减少探索时间 |
| 用 DM 不用 broadcast | broadcast 成本 = N × 单条消息 |
| 测试队友用完即关 | 验收是一次性的，不需要常驻 |
| 探索任务用 Haiku subagent | 不需要开 teammate |

---

## 四、团队生命周期管理

### 启动阶段

1. 分析任务依赖图，识别可并行的功能线
2. 每条功能线分配一个队友
3. spawn prompt 包含：功能线全部任务列表、已完成的前置任务产出（文件路径）、代码结构说明
4. 用 TaskCreate 创建所有任务，设好 blockedBy

### 运行阶段

- 队友完成一个任务 → TaskUpdate 标记完成 → 自动检查 TaskList 接下一个
- 线间需要协调 → 用 SendMessage DM，不要 broadcast
- 遇到阻塞 → 通知 lead，lead 决定是否调整

### 收尾阶段

- 功能线全部完成 → shutdown_request 关闭该队友
- 所有线完成 → 拉起测试队友验收
- 验收通过 → 关闭测试队友 → TeamDelete

### 跨 Phase 决策

```
Phase N 结束时：
  队友的功能线还有后续任务？
    ├── 是 → 保持存活，直接分配 Phase N+1 的任务
    └── 否 → shutdown_request 关闭

  需要新功能线？
    ├── 是 → spawn 新队友
    └── 否 → 复用现有队友
```

---

## 五、Spawn Prompt 模板

好的 spawn prompt 应该包含：

```
你负责 [功能线名称]，包含以下任务（按顺序执行）：
1. [任务ID] [任务名] — [一句话描述]
2. [任务ID] [任务名] — [一句话描述]
...

已完成的前置：
- [前置任务] 产出在 [文件路径]，关键接口：[接口说明]

项目结构：
- 后端: server/app/（FastAPI + SQLAlchemy async + SQLite）
- 模型: server/app/models/tables.py
- 服务: server/app/services/
- 测试: server/tests/

约束：
- 只改 server/ 下的文件
- 新服务放 server/app/services/
- 遵循现有代码风格（async def, type hints）
- 每个任务完成后 TaskUpdate 标记完成
```

---

## 六、实战对比

| 维度 | Phase 1（按任务分） | 推荐（按功能线分） |
|------|-------------------|-------------------|
| 队友数 | 4 个（每人 1 任务） | 2-3 个（每人 3-4 任务） |
| 上下文连续性 | ❌ 做完就丢 | ✅ 天然连续 |
| 团队重建次数 | 每 Phase 一次 | 功能线结束才重建 |
| 文件冲突风险 | 低（任务独立） | 低（线间独立） |
| 空闲浪费 | 高（等验收时全部空闲） | 低（做完就接下一个） |
| 总 token 消耗 | 较高 | 较低 |

---

## 七、Phase 验收流程（强制）

> **来源**: M2 Phase 1-2 教训 — 跳过 code review 导致 3 个 P0 bug 上线
> **日期**: 2026-02-16

### 教训

Phase 1 和 Phase 2 完成后，只跑了测试就宣布完成，没有做独立 code review。结果 Phase 2 review 时发现：
- P0: 并发竞态 — check_quota 和 deduct_quota 之间无原子保护，双 wakeup 可绕过配额
- P0: 双写不一致 — SQLite commit 后 LanceDB 失败，孤儿行无回滚无日志
- P0: scheduler shutdown 泄漏 — cancel() 后没有 await，DB session 可能未关闭
- P1: search() 丢失向量相似度排序
- P1: cleanup_expired 中途失败导致存储不一致

这些问题测试覆盖不到。测试验证的是"正常路径能跑通"，code review 验证的是"异常路径不会炸"。两者缺一不可。

### 强制验收步骤

每个 Phase 完成后，必须按顺序执行：

```
1. 测试验收
   - 全量 pytest 通过
   - 新增测试覆盖所有新功能

2. 独立 Code Review（不可跳过）
   - 用 subagent 对每个新文件/改动文件做独立 review
   - review 角色：senior code reviewer，不是写代码的人
   - 检查项：bug、竞态、边界情况、双写一致性、错误处理、测试覆盖缺口
   - 输出：P0/P1/P2 分级报告

3. 修复 P0 + P1
   - P0 必须当场修复
   - P1 应当场修复，特殊情况可记录到下一 Phase
   - P2 记录，后续修复

4. 回归测试
   - 修复后再跑一次全量 pytest
   - 确认无回归

5. 更新进度
   - 只有 4 步全部通过，才能在 progress 里标记 ✅
```

### 为什么不能省略 review

| 只跑测试 | 测试 + Review |
|----------|--------------|
| 验证正常路径 | 验证正常 + 异常路径 |
| 发现不了并发问题 | 能发现竞态、双写不一致 |
| 发现不了资源泄漏 | 能发现 session/task 泄漏 |
| 发现不了排序丢失 | 能发现语义正确性问题 |
| 虚假信心 | 真实信心 |

---

## 关联文档

- [开发流程](../workflows/development-workflow.md)
- [模型选择策略](model-selection.md)
- [Cat Café 经验参考](reference-catcafe-lessons.md)
