# OpenClaw 社区项目

> 自动加载：本文件 + `claude-progress.txt`
> 详细文档按需读取：`docs/` 目录

## 核心规则

1. **强制记录**：里程碑完成 → 更新 `claude-progress.txt` 顶部"最近活动"
2. **分层进度**：小改动记 `server/progress.md`，大里程碑记 `claude-progress.txt`（详见 `docs/PROGRESS_FILES.md`）
3. **讨论记录**：功能相关 → `docs/specs/SPEC-XXX/讨论细节/`，项目通用 → `docs/discussions/`
4. **防丢失**：对话是临时的，文件是持久的
5. **代码导航**：不确定功能在哪个文件？查看 `docs/CODE_MAP.md`

## 工作流

- 简单任务 → 直接实施
- 复杂任务 → 读 `docs/personas/human-proxy-pm.md` 对齐意图 → 协作讨论 → 拆解实施
- 完成任务 → 更新进度文件

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
