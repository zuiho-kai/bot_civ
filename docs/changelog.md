# 变更记录

> 项目文档架构、流程规则等重要变更的历史记录。

---

### 2025-07-09 [文档优化] 开发流程瘦身 + 角色文件拆分 + 记录规则修正
- **背景**: 新终端启动审查发现5个问题：development-workflow.md 592行且引用旧路径、roles.md 模型策略占20%、记录员/开发者行为准则与分层进度规则不一致
- **变更**:
  - `development-workflow.md` 从 592→181 行，模板拆到 `docs/templates/doc-templates.md`，路径更新为 specs/
  - `roles.md` 模型选择策略拆到 `docs/runbooks/model-selection.md`，原位保留速记+链接
  - `roles.md` 记录员行为准则：区分 progress vs changelog 写入目标
  - `roles.md` 开发者行为准则：区分小进展(各自progress.md) vs 大里程碑(claude-progress.txt)
  - CLAUDE.md 索引新增 templates/ 和 model-selection.md
- **原则**: 启动时只需读流程骨架，模板和策略详情按需跳转

### 2025-07-09 [文档优化] requirements + designs 合并为 specs，讨论跟功能走
- **背景**: requirements/ 和 designs/ 功能重叠，REQ-001 后续没维护；讨论文件集中放在 discussions/ 但按使用场景应跟功能走
- **变更**:
  - 删除 `docs/requirements/` 和 `docs/designs/` 目录
  - 新建 `docs/specs/SPEC-001-聊天功能/` 目录（spec.md + eval-review.md + 4个讨论文件）
  - 项目级通用讨论（4个）保留在 `docs/discussions/`
  - `discussions.md` 索引改为按功能/通用分组
  - CLAUDE.md 索引更新
- **原则**: 功能相关讨论跟 spec 走，通用讨论集中放；discussions.md 保留全局索引入口

### 2025-07-09 [文档优化] claude-progress.txt 精简，变更记录拆出
- **背景**: claude-progress.txt 103行，变更记录占30%且持续增长，启动时不需要看
- **变更**:
  - 变更记录拆到本文件（docs/changelog.md）
  - "设计进度" + "前置已完成" 合并为"已完成基础设施"（带文件链接）
  - claude-progress.txt 从 103 行精简到 ~63 行
- **原则**: progress 是仪表盘，只放当前状态和待办；历史变更按需查阅

### 2025-07-09 [文档优化] 错题本按角色拆分
- **背景**: 原 common-mistakes.md 混合了所有角色的错误案例，error-book.md 只有开发踩坑
- **变更**:
  - common-mistakes.md → 通用错误（COMMON-1~6）+ 角色错题本索引
  - 新建 5 个角色错题本：error-book-dev/pm/qa/debate/recorder.md
  - roles.md 每个角色定义下增加错题本链接
  - CLAUDE.md 索引更新，删除旧 error-book.md
- **原则**: 角色专属错误归各自错题本，跨角色通用错误留 common-mistakes.md

### 2026-02-14 [Bug溯源] DEV-BUG-5 @提及唤醒要求 Agent 有 WebSocket 连接
- **背景**: 人类 @Agent 发消息后无回复，唤醒引擎静默跳过。根因是唤醒服务的"在线"概念与方案G的 Agent 存在方式不一致
- **溯源结论**: 跨模块语义不一致——方案G 改变了 Agent 的存在方式，但唤醒服务的候选池来源没有同步更新
- **变更**:
  - error-book-dev.md DEV-BUG-5 补充完整溯源分析和防范措施
  - common-mistakes.md 新增 COMMON-6（跨模块语义假设不一致）
- **行动项**: TDD 审核流程增加检查项——当模块设计前提依赖其他模块行为时，明确列出跨模块依赖假设
