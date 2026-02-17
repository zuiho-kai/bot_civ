# 错题本 — 💻 开发者 / 前端专属

## 流程规则

### DEV-8 新增 UI 必须双主题验证 + 颜色禁止硬编码

❌ 新组件只在当前主题下看一眼就过了；颜色写死 `#f0b232` 或误用语义不匹配的变量（如用侧边栏的 `--channel-active` 做弹窗高亮）
✅ 新增可见 UI 后切换所有主题验证对比度；颜色只用语义匹配的 CSS 变量，没有合适的先在 themes.css 新增
> 硬编码颜色 = 必然在某个主题下翻车。案例：DEV-BUG-11。

### DEV-9 useEffect 外部连接必须幂等

❌ useEffect 里直接 `new WebSocket()`，没考虑 StrictMode 双挂载导致重复创建
✅ 外部连接（WebSocket/SSE/EventSource）必须：cleanup 关旧连接 + 创建前检查已有连接 + 消息层去重
> React StrictMode 开发模式双挂载 effect，不做幂等 = 开发时必现重复。案例：DEV-BUG-10。

---

## 前端踩坑记录

#### DEV-BUG-10 React StrictMode 双挂载导致 WebSocket 消息重复

- **场景**: 开发模式下聊天消息每条显示两次
- **根因**: React StrictMode 双挂载 useEffect，创建两个 WebSocket 连接，每条广播收两次
- **修复**: ① useWebSocket hook 加连接守卫 ② DiscordLayout 加 msg.data.id 去重

#### DEV-BUG-11 新增 UI 组件颜色硬编码，不跟主题走

- **场景**: 信用点徽章用固定金色 `#f0b232`，@提及 popup 的 active 状态用 `--channel-active`（暗色语义变量）
- **根因**: 新增组件时只在一个主题下目测，没有切换主题验证
- **修复**: 信用点用 `--credits-text` / `--credits-bg` 主题变量；popup active 改用 `--accent-subtle` / `--accent-primary`

### DEV-10 useEffect 依赖放 render 中新建的数组/对象 → 无限循环

❌ `const filtered = arr.filter(...)` 在 render 里算，然后放进 `useEffect([filtered])` — 每次 render 新引用 → 触发 effect → setState → 再 render
✅ 用 `useMemo` 稳定引用，或用 `.length` 等原始值做依赖
> 数组/对象每次 render 都是新引用。案例：M3 WorkPanel nonHumanAgents 无限循环。

### DEV-11 用户反馈消息（成功/失败提示）没有自动清除

❌ 操作成功后 `setMessage("成功")`，消息一直挂着直到下次操作
✅ 设置消息后加 `setTimeout(() => setMessage(null), 3000)` 自动清除，cleanup 里 `clearTimeout`
> 不清除 = 用户以为还在处理中，或误以为是新消息。

### DEV-12 多问题批量修复串行处理 + 不分类

❌ 拿到 5 个体验问题逐个串行排查，空日志反复读，UX 问题先查后端
✅ 先花 1 分钟分类（纯 CSS / 前端逻辑 / 后端 / 配置），同类并行处理；空文件只读一次；"操作后没反应"先查前端状态流转
> 不分类 = 串行耗时翻倍。案例：DEV-BUG-13。

---

## 前端踩坑记录（续）

#### DEV-BUG-13 M3 体验问题修复耗时过长

- **场景**: 5 个体验问题（表单 UI / dropdown 搜索 / 购买切 tab / 颜色硬编码 / agent 不回复），耗时 ~30 分钟，应 ~15 分钟
- **根因**: 未分类并行处理；空日志反复读；UX 问题误判为后端 bug
- **修复**: 3 文件改动（App.css / WorkPanel.tsx / UserAvatar.tsx）；agent 不回复是配置问题
- **详细**: [postmortem-dev-bug-13.md](../postmortems/postmortem-dev-bug-13.md)
