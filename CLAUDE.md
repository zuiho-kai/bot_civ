# OpenClaw 社区项目

> 自动加载：本文件 + `claude-progress.txt`
> 详细文档按需读取：`docs/` 目录

## 核心规则

1. **强制记录**：里程碑完成 → 更新 `claude-progress.txt` 顶部"最近活动"
2. **分层进度**：小改动记 `server/progress.md`，大里程碑记 `claude-progress.txt`（详见 `docs/PROGRESS_FILES.md`）
3. **讨论记录**：功能相关 → `docs/specs/SPEC-XXX/讨论细节/`，项目通用 → `docs/discussions/`
4. **防丢失**：对话是临时的，文件是持久的
5. **代码导航**：不确定功能在哪个文件？查看 `docs/CODE_MAP.md`
6. **不做口头承诺**：任何教训/流程改进/规则变更，发现的当下直接写入对应文件，不要口头说"以后会这样做"（详见 COMMON-12）

## 工作流

- 简单任务 → 直接实施
- 复杂任务 → 读 `docs/personas/human-proxy-pm.md` 对齐意图 → 协作讨论 → 拆解实施
- 完成任务 → ⚠️ **更新进度文件前必须确认**：该 Phase 是否已完成 Code Review 循环（P0/P1 归零）？未完成则先 Review 再更新
- **代码修复流程** → 实现 → 自验证 → Code Review → 修复 → 重新 Review → 循环直到 P0/P1 归零（详见 COMMON-10）
  - **强制门禁**：每个 Phase 实现完毕后，必须先完成 Code Review 循环（P0/P1 归零），才能更新进度文件或进入下一步。不允许跳过。
- **每次修复前必做影响面分析**：grep 引用点 + 追踪下游 + 涟漪推演（详见 DEV-6）
- **每个 Phase 完成后必须跑 ST**：拉起真实服务器 + 调用真实 API + 检查真实数据库，不能只跑 pytest（详见 QA-6）
- **出问题自动落盘流程**（不需要用户提醒）：
  - ⚠️ **逐步执行，不要凭印象跳步**：每完成一步再做下一步，第 2 步必须实际调用 Read 工具读文件，不能跳过
  1. 分析根因 + 溯源各阶段遗漏
  2. **实际调用 Read 读目标错题本顶部的"记录规则"**，确认行数上限（COMMON-14）— 不能跳过此步
  3. 错题本写摘要（≤行数上限），按角色写入对应 `docs/runbooks/error-books/error-book-{role}.md`
  4. 详细复盘放 `docs/runbooks/postmortems/postmortem-dev-bug-N.md`，错题本里放链接
  5. 更新进度文件
- **回溯流程**（用户说"回溯"时触发）：
  1. 回顾刚完成的工作，列出卡点时间线 → 分析根因和浪费轮次 → 提炼可优化点
  2. 落盘到错题本（遵循上述落盘流程，先回读记录规则再写）
  3. 详细回溯表放 postmortem（详见 COMMON-13）
- **dev endpoint 设计规范**：支持 `?debug=1` 返回中间状态；阈值参数可通过 dev API 覆盖；错误路径返回具体原因（详见 COMMON-13、QA-7）

## 双终端分工

- 后端：`server/`（API、数据库、Agent、LLM）
- 前端：`web/`（React UI、WebSocket）
- 接口契约：`docs/api-contract.md`

## 文档速查

- 角色定义：`docs/personas/roles.md`
- 功能规格：`docs/specs/SPEC-001-聊天功能/README.md`
- 讨论索引：`docs/discussions.md`
- PRD：`docs/PRD.md`
- 代码导航：`docs/CODE_MAP.md`（功能→文件映射）
- 进度文件说明：`docs/PROGRESS_FILES.md`（避免混淆）
