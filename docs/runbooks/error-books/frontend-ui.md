# 错题本 — 前端/UI

### 记录规则

- **条目只写核心规则**（❌/✅/一句话解释），控制在 **5 行以内**
- **DEV-BUG 条目**：场景/根因/修复，各 1 行，控制在 **6 行以内**
- 详细复盘放 `../postmortems/`，这里只放链接

### DEV-8 新增 UI 必须双主题验证 + 颜色禁止硬编码 `🟢`

❌ 新组件只在当前主题下看一眼就过了；颜色写死 `#f0b232` 或误用语义不匹配的变量
✅ 新增可见 UI 后切换所有主题验证对比度；颜色只用语义匹配的 CSS 变量，没有合适的先在 themes.css 新增
> 硬编码颜色 = 必然在某个主题下翻车。案例：DEV-BUG-11。

### DEV-11 用户反馈消息（成功/失败提示）没有自动清除 `🟢`

❌ 操作成功后 `setMessage("成功")`，消息一直挂着直到下次操作
✅ 设置消息后加 `setTimeout(() => setMessage(null), 3000)` 自动清除，cleanup 里 `clearTimeout`

### DEV-12 多问题批量修复串行处理 + 不分类 `🟢`

❌ 拿到 5 个体验问题逐个串行排查，空日志反复读，UX 问题先查后端
✅ 先花 1 分钟分类（纯 CSS / 前端逻辑 / 后端 / 配置），同类并行处理
> 不分类 = 串行耗时翻倍。案例：DEV-BUG-13。

### DEV-14 大量 UI 一口气写完不分步检查 `🟡中频×2`

❌ types + api + 整个交易市场 UI + CSS 一口气写完再构建验证 → P0 + 4 个 P1
✅ 前端改动 >2 个文件时分步写：① types+api → 对照后端签名 ② UI 组件 → 心理渲染布局 ③ CSS → grep 硬编码颜色 ④ 交互 → 检查破坏性操作确认+表单重置

#### DEV-BUG-11 新增 UI 组件颜色硬编码，不跟主题走 `🟢`

- **场景**: 信用点徽章用固定金色 `#f0b232`，@提及 popup 用暗色语义变量
- **根因 & 修复**: 见流程规则 DEV-8
- **修复文件**: 信用点用 `--credits-text` / `--credits-bg`；popup active 改用 `--accent-subtle` / `--accent-primary`

#### DEV-BUG-13 M3 体验问题修复耗时过长 `🟢`

- **场景**: 5 个体验问题，耗时 ~30 分钟，应 ~15 分钟
- **根因**: 未分类并行处理；空日志反复读；UX 问题误判为后端 bug
- **详细**: [postmortem-dev-bug-13.md](../postmortems/postmortem-dev-bug-13.md)

#### DEV-BUG-20 美学审查漏检 hover 上下文 + 动画舒适度 `🟢`

- **场景**: agent-status hover 用暗色 sidebar 变量（`--channel-hover`）在亮色 info-panel 上一坨黑；pulse opacity 0.4 闪烁刺眼
- **根因**: 设计稿标"hover 无变更"跳过审查；验收只验动画技术参数（频率/流畅度）不验主观舒适度
- **修复**: hover 改 `--accent-subtle`；pulse 动画删除，改静态 box-shadow 光晕

### 可访问性规则

✅ 代码生成后必须跑外部审查工具（用 Task 启独立 agent + Playwright MCP 审查 / Lighthouse / axe-core）
✅ 交互元素（button/select/input）强制 `min-height: 44px`（WCAG 2.5.8）
✅ 涉及动态列表/弹出/反馈消息的组件，实现时同步加 ARIA 属性
