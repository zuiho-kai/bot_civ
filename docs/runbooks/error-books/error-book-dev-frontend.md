# 错题本 — 💻 开发者 / 前端专属

> **记录规则**：本文件只记录纯前端问题（CSS/组件/ARIA/React hooks）。跨前后端通用教训写 `error-book-dev-common.md`，纯后端问题写 `error-book-dev-backend.md`。每条控制在 **5 行以内**（❌/✅/一句话根因），详细复盘放 `postmortems/postmortem-dev-bug-N.md`，错题本里只放链接。

---

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
- **根因 & 修复**: 见流程规则 DEV-9
- **修复文件**: useWebSocket hook 加连接守卫 + DiscordLayout 加 msg.data.id 去重

#### DEV-BUG-11 新增 UI 组件颜色硬编码，不跟主题走

- **场景**: 信用点徽章用固定金色 `#f0b232`，@提及 popup 用暗色语义变量
- **根因 & 修复**: 见流程规则 DEV-8
- **修复文件**: 信用点用 `--credits-text` / `--credits-bg`；popup active 改用 `--accent-subtle` / `--accent-primary`

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

### DEV-14 大量 UI 一口气写完不分步检查 → Code Review P0/P1 扎堆

❌ types + api + 整个交易市场 UI + CSS 一口气写完再构建验证，写的过程中不对照 checklist → P0（类型与后端不对齐）+ 4 个 P1（布局/状态重置/防误触/硬编码颜色）
✅ 前端改动 >2 个文件时分步写：① types+api 写完 → 对照后端签名逐字段校对 ② UI 组件写完 → 心理渲染 grid/flex 布局 ③ CSS 写完 → grep 硬编码颜色 ④ 交互写完 → 检查破坏性操作确认+表单重置
> 根因：量大时"先全写完再说"跳过了逐步检查。DEV-8（颜色硬编码）、DEV-11（凭记忆写后端字段）同时复犯。

❌ 代码生成后依赖 LLM 自检可访问性和视觉合规性
✅ 代码生成后必须跑外部审查工具（Gemini 视觉审查 / Lighthouse / axe-core）
❌ 触摸目标 padding 随手写 5px/6px，没有 44px 最小尺寸意识
✅ 交互元素（button/select/input）强制 `min-height: 44px`（WCAG 2.5.8）
❌ ARIA 属性（listbox/combobox/aria-live）在功能实现时被忽略
✅ 涉及动态列表/弹出/反馈消息的组件，实现时同步加 ARIA 属性
> 根因：LLM 生成代码时关注功能实现，不会同时跑可访问性 checklist；缺少视觉感知无法判断渲染尺寸。需要外部工具补位。
