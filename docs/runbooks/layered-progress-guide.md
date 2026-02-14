# 分层进度管理操作指南

> 核心原则：**减少上下文负担，关注点分离**

---

## 三层结构

| 层级 | 文件 | 记录什么 | 谁关心 |
|------|------|---------|--------|
| 总进展 | `claude-progress.txt` | 大里程碑、重大决策 | 项目经理 |
| 后端细节 | `server/progress.md` | API、数据库、WebSocket等 | 后端开发者 |
| 前端细节 | `web/progress.md` | 组件、UI、路由等 | 前端开发者 |

---

## 什么算大里程碑？

**同步到 `claude-progress.txt`**：
- M1/M2/M3 阶段完成
- 前后端联调完成
- 重大架构决策
- 阻塞性 Bug 修复
- 四方评审结论

**只记在各自 progress.md**：
- 单个 API/组件/测试完成
- 局部重构、依赖升级
- 非阻塞 Bug 修复
- 开发环境配置

---

## 操作流程

### 日常开发

每完成一个功能点 → 更新 `server/progress.md` 或 `web/progress.md`：

```markdown
### 2025-02-14
#### 14:30 - 完成 Agent CRUD API
- 内容: POST/GET/PUT/DELETE 四个接口
- 文件: server/routes/agents.py, server/models/agent.py
- 状态: ✅ 完成
```

### 大里程碑完成后

1. 在各自 progress.md 标记里程碑完成
2. 同步到 `claude-progress.txt`：

```markdown
### 2025-02-14 | M1.1（后端） | Agent CRUD + WebSocket 基础功能完成
- 包含: Agent CRUD API + WebSocket 服务端
- 测试: 单元测试全部通过
- 下一步: 等待前端完成后联调
```

### 设计终端（项目经理）

- 启动时只读 `claude-progress.txt`
- 需要深入了解时才读 `server/progress.md` 或 `web/progress.md`

---

## 常见错误

进度记录相关的错误案例见 [常见错误案例合集](common-mistakes.md) 第1节。
