# 进度文件职责说明

> 本文档明确各个进度文件的职责和更新时机，避免混淆

## 📁 进度文件体系

### 1. `claude-progress.txt` - 项目级里程碑

**职责**: 记录**重大里程碑**和**项目级别**的进展

**更新时机**:
- ✅ 完成一个完整的 Milestone（如 M1、M2 Phase 1）
- ✅ 完成重要的技术决策（如选定数据库架构）
- ✅ 完成重要的功能集成（如 Bot 接入、定时任务上线）
- ✅ 项目状态变更（如部署上线、测试通过数量大幅增加）

**不应记录**:
- ❌ 单个文件的修改
- ❌ 小 bug 修复
- ❌ 代码重构
- ❌ 文档更新（除非是重大文档重构）

**示例**:
```
### 2026-02-16
- M2 Phase 2 完成（记忆服务+发言扣费+定时任务）
- 62 tests passed
- 文档重构：README/ROADMAP/CONTRIBUTING 增强吸引力
```

---

### 2. `server/progress.md` - 后端开发细节

**职责**: 记录**后端开发**的**日常进展**和**技术细节**

**更新时机**:
- ✅ 实现一个新的 API 端点
- ✅ 修复一个 bug
- ✅ 优化一个服务
- ✅ 添加一个测试
- ✅ 重构一个模块
- ✅ 调整配置或依赖

**不应记录**:
- ❌ 前端相关的改动
- ❌ 文档相关的改动（除非是 API 文档）
- ❌ 项目级别的里程碑（应该记录在 claude-progress.txt）

**示例**:
```
## 2026-02-16
- 实现 memory_service.py 的 search_memories() 方法
- 修复 economy_service.py 中的并发扣费 bug
- 添加 test_memory_service.py 的 10 个测试用例
- 优化 vector_store.py 的向量搜索性能
```

---

### 3. `web/progress.md` - 前端开发细节

**职责**: 记录**前端开发**的**日常进展**和**技术细节**

**更新时机**:
- ✅ 实现一个新的组件
- ✅ 修复一个 UI bug
- ✅ 优化样式或交互
- ✅ 添加一个页面
- ✅ 集成一个 API

**不应记录**:
- ❌ 后端相关的改动
- ❌ 项目级别的里程碑（应该记录在 claude-progress.txt）

**示例**:
```
## 2026-02-16
- 实现 EconomyPanel 组件（显示 credits 和额度）
- 修复 AgentCard 的样式问题
- 优化 MessageList 的滚动性能
- 集成 /api/bounties 接口
```

---

### 4. `docs/specs/SPEC-XXX/04-项目进度.md` - 功能级进度

**职责**: 记录**特定功能规格**的**实施进度**

**更新时机**:
- ✅ 完成该功能规格中的一个任务
- ✅ 该功能的测试通过
- ✅ 该功能的文档完成

**不应记录**:
- ❌ 其他功能的进展
- ❌ 项目级别的里程碑

**示例**:
```
## M2 Phase 1 进度

- [x] M2-1: LanceDB 向量存储
- [x] M2-5: 经济服务
- [ ] M2-3: 记忆注入上下文
```

---

## 🎯 更新决策树

```
完成了一项工作
    │
    ├─ 是否是完整的 Milestone？
    │   └─ 是 → 更新 claude-progress.txt
    │
    ├─ 是否是后端代码改动？
    │   └─ 是 → 更新 server/progress.md
    │
    ├─ 是否是前端代码改动？
    │   └─ 是 → 更新 web/progress.md
    │
    └─ 是否属于某个功能规格？
        └─ 是 → 更新 docs/specs/SPEC-XXX/04-项目进度.md
```

---

## 📝 实际案例

### 案例 1: 实现了记忆服务的搜索功能

**应该更新**:
- ✅ `server/progress.md` - 记录实现细节
- ✅ `docs/specs/SPEC-001/04-项目进度.md` - 勾选 M2-2 任务

**不应该更新**:
- ❌ `claude-progress.txt` - 这不是里程碑级别的改动

---

### 案例 2: M2 Phase 2 完成（记忆+经济+定时任务全部完成）

**应该更新**:
- ✅ `claude-progress.txt` - 记录里程碑完成
- ✅ `server/progress.md` - 记录最后的集成细节
- ✅ `docs/specs/SPEC-001/04-项目进度.md` - 更新 Phase 2 状态

**不应该更新**:
- ❌ `web/progress.md` - 这是后端的里程碑

---

### 案例 3: 修复了一个 WebSocket 断线重连的 bug

**应该更新**:
- ✅ `server/progress.md` - 记录 bug 修复

**不应该更新**:
- ❌ `claude-progress.txt` - 这不是里程碑级别的改动
- ❌ `docs/specs/SPEC-001/04-项目进度.md` - 这不是功能实现

---

### 案例 4: 重构了整个文档结构，增强了项目吸引力

**应该更新**:
- ✅ `claude-progress.txt` - 这是项目级别的重要改动

**不应该更新**:
- ❌ `server/progress.md` - 这不是后端代码改动
- ❌ `web/progress.md` - 这不是前端代码改动

---

## 🤖 AI Agent 使用指南

### 完成任务后的检查清单

```
[ ] 这是否是一个完整的 Milestone？
    → 是：更新 claude-progress.txt 顶部"最近活动"

[ ] 这是否涉及后端代码改动？
    → 是：更新 server/progress.md

[ ] 这是否涉及前端代码改动？
    → 是：更新 web/progress.md

[ ] 这是否属于某个功能规格的任务？
    → 是：更新 docs/specs/SPEC-XXX/04-项目进度.md
```

### 快速判断规则

- **大改动** → `claude-progress.txt`
- **后端日常** → `server/progress.md`
- **前端日常** → `web/progress.md`
- **功能任务** → `docs/specs/SPEC-XXX/04-项目进度.md`

---

## 📊 文件对比表

| 文件 | 粒度 | 更新频率 | 内容类型 | 读者 |
|------|------|----------|----------|------|
| `claude-progress.txt` | 项目级 | 低（里程碑） | 重大进展 | 所有人 |
| `server/progress.md` | 模块级 | 高（每日） | 后端细节 | 后端开发者 |
| `web/progress.md` | 模块级 | 高（每日） | 前端细节 | 前端开发者 |
| `docs/specs/SPEC-XXX/04-项目进度.md` | 功能级 | 中（任务完成） | 功能进度 | 功能负责人 |

---

## ⚠️ 常见错误

### ❌ 错误 1: 在 claude-progress.txt 记录小改动
```
### 2026-02-16
- 修复了 economy_service.py 的一个 typo
- 调整了 AgentCard 的 padding
```
**正确做法**: 这些应该记录在 `server/progress.md` 和 `web/progress.md`

---

### ❌ 错误 2: 在 server/progress.md 记录里程碑
```
## 2026-02-16
- M2 Phase 2 完成！
```
**正确做法**: 里程碑应该记录在 `claude-progress.txt`，server/progress.md 只记录具体的代码改动

---

### ❌ 错误 3: 多个文件记录相同内容
```
claude-progress.txt: "实现了记忆搜索功能"
server/progress.md: "实现了记忆搜索功能"
```
**正确做法**:
- `claude-progress.txt`: 只在完成整个 Phase 时记录
- `server/progress.md`: 记录具体实现细节

---

## 🎯 总结

**一句话原则**:
- **大事记** → `claude-progress.txt`
- **后端日常** → `server/progress.md`
- **前端日常** → `web/progress.md`
- **功能任务** → `docs/specs/SPEC-XXX/04-项目进度.md`

**记住**: 进度文件是为了**快速定位信息**，不是为了重复记录。每个文件有自己的职责，不要混淆。
