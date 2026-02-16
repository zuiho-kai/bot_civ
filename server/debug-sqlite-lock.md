# SQLite 数据库锁定问题诊断记录

## 问题现象
- e2e 测试超时，Agent 不回复
- 服务器日志显示：`sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked`
- 错误发生在保存 Agent 回复消息时：`INSERT INTO messages`

## 根本原因分析

### 已确认的问题
1. **Agent 功能正常**：
   - ✅ 唤醒引擎工作
   - ✅ LLM 调用成功（生成了回复）
   - ✅ 向量存储、经济服务、频率控制都正常
   - ❌ 保存回复到数据库时失败

2. **数据库锁定的根源**：
   - `handle_wakeup` 函数在 `async with async_session() as db:` 块内调用 LLM
   - LLM 调用耗时 4-15 秒，期间数据库会话一直打开
   - 同时 WebSocket 主循环或其他请求也在使用数据库
   - SQLite 不支持多个写入者同时操作 → 锁定

3. **代码位置**：
   - `app/api/chat.py` 第 243 行：`async with async_session() as db:`
   - 在这个会话内：查询历史 → 调用 LLM → 保存消息 → commit
   - LLM 调用期间会话未释放，阻塞其他写入

## 已尝试的方案（均失败）

### 方案 1: 增加 timeout 参数 ❌
```python
connect_args={"timeout": 30, "check_same_thread": False}
```
- **结果**: 失败，还是锁定
- **原因**: timeout 只是等待时间，不解决并发写入冲突

### 方案 2: 启用 WAL 模式 ❌
```python
PRAGMA journal_mode=WAL
PRAGMA busy_timeout=30000
```
- **结果**: 失败，还是锁定
- **原因**: WAL 改善了读写并发，但多个写入者仍会冲突

### 方案 3: 增加连接池配置 ❌
```python
pool_pre_ping=True,
pool_size=20,
max_overflow=0,
```
- **结果**: 失败，还是锁定
- **原因**: 连接池复用可能加剧冲突

### 方案 4: 禁用连接池 (NullPool) ❌
```python
poolclass=NullPool
```
- **结果**: 失败，还是锁定
- **原因**: 每次创建新连接也无法解决同时写入的问题

### 方案 5: 修复 emoji 编码错误 ✅
```python
# 将 print() 改为 logger.info()
```
- **结果**: 修复了编码问题，但数据库锁定依然存在

### 方案 6: 分离数据库会话（第一次尝试）❌
- **思路**: 在 `handle_wakeup` 中分三个阶段：读取 → LLM 调用 → 保存
- **结果**: 失败，还是锁定
- **原因**: `send_agent_message` 内部又创建了新的数据库会话，导致嵌套冲突

### 方案 7: 修复 send_agent_message 嵌套会话 ❌
- **修改**: 让 `send_agent_message` 接受 `db` 参数，不再内部创建会话
- **结果**: 失败，还是锁定
- **当前状态**: 23:35 - 还在调试中

## 当前思路（23:40）

**方案 8 发现了真正的并发冲突源**：
- 日志显示两个 `BEGIN (implicit)` 同时发生
- 一个来自 `send_agent_message`（INSERT messages）
- 另一个来自 `_record_usage`（INSERT llm_usage）
- `_record_usage` 在 `agent_runner.py` 中通过 `asyncio.create_task` fire-and-forget 执行
- 它创建自己的数据库会话，完全绕过了 chat.py 的本地锁

**方案 8 修复**：
1. 在 `database.py` 中定义全局 `db_write_lock = asyncio.Lock()`
2. `chat.py` 和 `agent_runner.py` 都导入并使用同一个锁
3. 所有数据库写入操作都通过 `async with db_write_lock:` 序列化

**当前状态**: 服务器已重启，准备测试

## 时间线

- 23:01 - 首次发现数据库锁定
- 23:05 - 尝试方案 1 (timeout) ❌
- 23:10 - 尝试方案 2 (WAL) ❌
- 23:15 - 尝试方案 3 (连接池) ❌
- 23:20 - 尝试方案 4 (NullPool) ❌
- 23:25 - 发现根本原因：LLM 调用期间持有数据库会话
- 23:30 - 尝试方案 6 (分离会话) ❌
- 23:33 - 发现 send_agent_message 嵌套会话问题
- 23:35 - 修复后还是锁定，继续排查
- 23:38 - 方案 8: 全局 asyncio.Lock ❌ (asyncio.Lock 无法序列化 aiosqlite 的后台线程操作)
- 23:40 - 发现真正并发源：_record_usage fire-and-forget 与 send_agent_message 同时写入
- 23:42 - 方案 9: 统一 usage 写入到 handle_wakeup 第三阶段 ❌ (数据库锁定消失，但 emoji 编码错误导致 reply=None)
- 23:45 - 修复 emoji：main.py 设置 UTF-8 输出 + logger 不打印 reply 内容
- 23:48 - 方案 10: BEGIN IMMEDIATE (SQLAlchemy 官方推荐) - 事件监听器注册但未生效
- 23:50 - 发现 __pycache__ 缓存导致旧代码被加载
- 23:52 - 清除缓存后发现 IndentationError（去掉 _db_write_lock 时缩进没调好）
- 23:54 - 修复缩进后重启，BEGIN IMMEDIATE 仍未出现在日志中
- 23:55 - 发现旧进程（22:40 启动）一直在运行，kill 后重启
- 23:59 - ✅ BEGIN IMMEDIATE 生效！数据库锁定问题彻底解决！
- 00:00 - ✅ Agent 回复成功写入，LLM usage 成功记录，无 ROLLBACK

## 最终解决方案

**根本原因**：SQLite 默认使用 `BEGIN DEFERRED`，两个连接同时持有 SHARED 锁后尝试升级为 RESERVED 锁时产生死锁，SQLite 立即返回 "database is locked" 并忽略 busy_timeout。

**修复方法**：使用 SQLAlchemy 事件监听器将所有事务改为 `BEGIN IMMEDIATE`：

```python
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
    conn.exec_driver_sql("BEGIN IMMEDIATE")
```

**为什么之前的方案都失败了**：
1. `asyncio.Lock()` 无法序列化 aiosqlite 的后台线程操作
2. `NullPool` 每次创建新连接，多连接 = 多 writer = 死锁
3. `busy_timeout` 对 DEFERRED→WRITE 升级死锁无效（SQLite 检测到死锁后立即失败）
4. `BEGIN IMMEDIATE` 在事务开始时就获取 RESERVED 锁，其他连接会等待（尊重 busy_timeout）

## 附带修复

1. **GBK 编码错误**：main.py 中设置 `sys.stdout/stderr.reconfigure(encoding="utf-8")`
2. **LLM usage 统一写入**：不再 fire-and-forget，在 handle_wakeup 第三阶段与消息一起写入同一个事务
3. **移除全局 asyncio.Lock**：不再需要，BEGIN IMMEDIATE 从根本上解决了并发问题
