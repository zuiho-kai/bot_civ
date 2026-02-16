# DEV-BUG-7 详细复盘：SQLite 并发锁定导致测试死循环

> 摘要见 [error-book-dev.md](error-book-dev.md#dev-bug-7)

- **场景**: 运行 M2 Phase 1 完整测试（WebSocket 消息 + Agent 异步回复 + LLM usage 记录）
- **现象**: Agent 回复生成成功，但保存到数据库时报 `database is locked`，消息无法广播，e2e 测试超时
- **原因（根本原因 + 表面原因）**:

  **根本原因**: SQLite 默认使用 `BEGIN DEFERRED` 事务。当两个连接同时持有 SHARED 锁后尝试升级为 RESERVED 锁时，SQLite 检测到死锁并**立即**返回 "database is locked"，**忽略 busy_timeout**。

  **表面原因（并发写入源）**:
  1. WebSocket 主循环保存人类消息（`chat.py` 第 340 行）
  2. `handle_wakeup` 异步任务保存 Agent 回复（`chat.py` 第 194 行）
  3. `_record_usage` fire-and-forget 任务写入 LLM 用量（`agent_runner.py`）
  4. 三者创建独立数据库会话，DEFERRED 事务互相死锁

- **最终修复（方案 10 — BEGIN IMMEDIATE）**:
  ```python
  # app/core/database.py
  from sqlalchemy import event

  engine = create_async_engine(
      f"sqlite+aiosqlite:///{settings.db_path}",
      echo=settings.debug,
  )

  @event.listens_for(engine.sync_engine, "connect")
  def _set_sqlite_pragma(dbapi_connection, connection_record):
      dbapi_connection.isolation_level = None  # 禁用驱动自动事务
      cursor = dbapi_connection.cursor()
      cursor.execute("PRAGMA journal_mode=WAL")
      cursor.execute("PRAGMA busy_timeout=30000")
      cursor.execute("PRAGMA synchronous=NORMAL")
      cursor.close()

  @event.listens_for(engine.sync_engine, "begin")
  def _do_begin(conn):
      conn.exec_driver_sql("BEGIN IMMEDIATE")  # 事务开始时立即获取 RESERVED 锁
  ```

  **附带修复**:
  1. `generate_reply` 返回 `(reply, usage_info)` 元组，不再 fire-and-forget 写 usage
  2. `handle_wakeup` 第三阶段在同一个事务中写入消息 + 扣额度 + 记录 usage
  3. `main.py` 添加 `sys.stdout/stderr.reconfigure(encoding="utf-8")` 解决 Windows GBK 编码错误

## 失败方案清单（为什么前 9 个方案都不行）

| # | 方案 | 为什么失败 |
|---|------|-----------|
| 1 | `connect_args={"timeout": 30}` | aiosqlite 不支持此参数 |
| 2 | WAL 模式 | WAL 允许并发读，但仍然只允许一个 writer |
| 3 | 连接池配置 | 不影响事务类型 |
| 4 | NullPool | 每次新连接，更多并发 writer，更容易死锁 |
| 5 | 分离 DB 会话 | 减少了持锁时间，但 DEFERRED 死锁仍然存在 |
| 6 | send_agent_message 接受 db 参数 | 减少了会话数量，但并发源仍在 |
| 7 | 全局 asyncio.Lock | asyncio.Lock 只序列化协程，aiosqlite 的 SQL 在后台线程执行，锁无法覆盖 |
| 8 | Lock 应用到 _record_usage | 同上，且 Lock 必须包裹整个会话生命周期才有效 |
| 9 | 统一 usage 写入 | 减少了并发源，但 DEFERRED 死锁根因未解决 |

## 关键认知突破

1. **`asyncio.Lock()` 对 aiosqlite 无效**: aiosqlite 在后台线程执行 SQL，asyncio.Lock 只序列化协程调度，无法阻止两个后台线程同时执行 `BEGIN`
2. **`busy_timeout` 对 DEFERRED 死锁无效**: 两个连接都持有 SHARED 锁想升级 → SQLite 判定为死锁 → 立即失败，不等待
3. **`BEGIN IMMEDIATE` 从根本上解决**: 事务开始时就获取 RESERVED 锁，第二个连接会等待（尊重 busy_timeout）而不是死锁

## 排查过程中的额外坑

1. **旧进程未被 kill**: `python main.py` 后台进程从 22:40 一直运行，新代码改了但旧进程还在用旧代码。`ps aux | grep python` 确认进程启动时间很重要
2. **`__pycache__` 缓存**: 清除缓存后才能确保新代码生效
3. **Windows GBK 编码**: Agent 回复包含 emoji（☀🌞），`logger.info` 输出时触发 GBK 编码错误，被 `except Exception` 捕获导致 reply 变成 None。表现为"数据库没报错但消息没保存"
4. **缩进错误**: 去掉 `async with _db_write_lock:` 时内部代码缩进没调整，导致 IndentationError，服务器静默启动失败

## 时间线复盘

| 阶段 | 耗时 | 做了什么 | 问题 |
|------|------|----------|------|
| 1. 初始诊断 | 5min | 发现 database is locked，查看日志 | 正确 |
| 2. 方案 1-4 | 20min | timeout/WAL/连接池/NullPool | 在表面原因上打转，没有理解 DEFERRED 死锁机制 |
| 3. 方案 5-6 | 15min | 分离会话/传递 db 参数 | 方向对了（减少并发），但没解决根因 |
| 4. 方案 7-8 | 15min | asyncio.Lock | **最大误区** — 以为 Lock 能序列化 aiosqlite 写入 |
| 5. 方案 9 | 10min | 统一 usage 写入 | 有效减少并发源，但引入 GBK 编码新问题 |
| 6. 研究根因 | 10min | 搜索 aiosqlite + SQLAlchemy 并发问题 | **转折点** — 发现 BEGIN IMMEDIATE 方案 |
| 7. 方案 10 | 5min | BEGIN IMMEDIATE 事件监听器 | 代码正确 |
| 8. 调试部署 | 20min | 旧进程/缓存/缩进错误/GBK | 非技术问题，但耗时最多 |
| 9. 最终验证 | 5min | 确认 BEGIN IMMEDIATE 生效，无锁定错误 | 成功 |

## 成本反思（200 刀教训）

**问题**: 10 次方案迭代，每次"改代码 → 重启 → e2e 测试 → 看日志 → 分析"循环消耗 15-20 刀 token，总计 200 刀。正确做法 15 分钟 15 刀就能解决。

**根因**: 凭直觉猜方案，没有先研究问题本质。

**三步止血规则（遇到不熟悉的技术问题时）**:

1. **先搜索，不要猜**（5 分钟上限）: 遇到 "database is locked" 这类明确错误信息，第一步是搜索 "aiosqlite SQLAlchemy database is locked"，而不是凭直觉改配置。大多数常见问题都有现成答案。
2. **最小脚本验证，不要跑完整 e2e**（省 80% token）: 写 10 行 Python 脚本复现并发写入问题，验证方案是否有效。不要每次都启动完整服务器 + 跑 e2e 测试。
3. **两次失败后停下来重新思考**（硬性规则）: 如果连续两个方案都失败了，说明对问题的理解有误。停下来重新分析根因，不要继续猜。

**如果遵循这个规则**:
- 方案 1 失败 → 方案 2 失败 → 停下来搜索 → 找到 BEGIN IMMEDIATE → 写最小脚本验证 → 应用到项目 → 完成
- 预计耗时 20 分钟，成本 20 刀，节省 180 刀
