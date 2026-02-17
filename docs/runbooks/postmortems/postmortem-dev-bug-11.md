# Postmortem DEV-BUG-11：M4 autonomy_service 首轮 Code Review 出 3×P1 + 3×P2

## 时间线

1. TDD-M4 通过 PM 审查，进入 Phase 1 后端编码
2. 一次性写完 `autonomy_service.py`（~420 行）+ `scheduler.py` 修改 + `main.py` 修改
3. 首轮 Code Review 发现 3 个 P1 + 3 个 P2
4. 修复后二轮 Review 通过（P0=0, P1=0）

## 问题清单

| 级别 | 问题 | 根因分类 |
|------|------|----------|
| P1 | `_execute_chats` 串行 sleep 阻塞 tick ~2min | 不复用已有 pattern |
| P1 | 广播事件格式与 TDD 嵌套层级不一致 | TDD 写时没回查代码 |
| P1 | `decide()` 中 `raw` 变量异常路径可能未定义 | 异常路径分析不足 |
| P2 | checkin prompt 写了 `job_id`，TDD 说 `{}` | 擅自偏离 TDD |
| P2 | `persona[:60]` 截断无省略号 | 防御性编程不足 |
| P2 | `_last_round_log` 全局变量无并发保护 | 防御性编程不足 |

## 根因分析

### 共性根因 1：写代码前没有回顾已有 pattern

项目里 `hourly_wakeup_loop` 已经有成熟的"并行 create_task + 延迟发送"模式。写 `_execute_chats` 时没有先 grep `create_task` 或 `delayed_send` 看已有实现，直接写了最朴素的 for 循环串行 sleep。

**为什么会这样**：急于产出，觉得"功能对就行"，没有意识到性能也是正确性的一部分（10 个 agent 串行等 2 分钟会影响调度周期）。

### 共性根因 2：写完没有逐条对照 TDD 自查

写完代码直接提交 Review，没有做"TDD 一致性检查"。导致：
- 广播事件格式嵌套层级与 TDD 不一致（虽然代码是对的，TDD 是错的，但应该在编码时就发现并更新 TDD）
- checkin prompt 擅自加了 `job_id`，偏离 TDD 设计

**为什么会这样**：TDD 写完到编码之间有时间间隔，编码时凭记忆而非逐条对照文档。

### 共性根因 3：异常路径思考不足

`try/except` 写完 happy path 就觉得完了，没有逐个 except 分支检查"此时哪些变量已定义"。`raw` 变量在 try 块第 3 行才赋值，如果第 1-2 行抛异常，except 中引用 `raw` 就会 NameError。

**为什么会这样**：Python 的变量作用域不像 Java 那样在编译期检查，容易遗漏。

## 防范措施

已写入 `error-book-dev-common.md` DEV-14，核心是**编码前自查清单**：

1. grep 同类功能的已有实现，确认项目 pattern
2. 对照 TDD 逐项检查：函数签名、消息格式、prompt 内容、容错边界
3. 每个 try/except 块检查异常路径的变量可达性
4. 不偏离 TDD，需要改设计先更新文档

## 影响

- 浪费 1 轮 Review + 修复周期（约 15 分钟）
- 无生产影响（代码未部署）
- 修复后二轮 Review 通过，无残留问题
