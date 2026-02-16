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
