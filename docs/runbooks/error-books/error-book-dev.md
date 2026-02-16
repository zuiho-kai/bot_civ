# 错题本 — 💻 开发者

> 按需加载：主文件只放索引，具体内容在子文件中。

### 记录规则

- **DEV-BUG 条目只写摘要**（场景/根因/修复/防范，各 1-2 行），控制在 10 行以内
- **详细复盘**放独立文件 `postmortem-dev-bug-N.md`，错题本里放链接
- **目的**：每次只加载需要的子文件，控制 token 消耗

---

## 子文件索引

| 分类 | 文件 | 覆盖范围 |
|------|------|---------|
| 通用开发 | [error-book-dev-common.md](error-book-dev-common.md) | 协作流程、影响面分析、测试分级 |
| 前端 | [error-book-dev-frontend.md](error-book-dev-frontend.md) | React/CSS/主题、WebSocket hook |
| 后端 | [error-book-dev-backend.md](error-book-dev-backend.md) | SQLite、跨模块语义、Python 环境 |
