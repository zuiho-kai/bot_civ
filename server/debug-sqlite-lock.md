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

## 当前思路（23:35）

问题可能不只是 `handle_wakeup`，还有其他地方也在并发写入数据库：

1. **WebSocket 主循环**：接收人类消息时写入数据库
2. **handle_wakeup 异步任务**：保存 Agent 回复时写入数据库
3. **心跳/其他后台任务**：可能也在写入

需要排查所有并发写入点。

## 下一步行动

1. 检查 WebSocket 消息处理是否也持有长时间会话
2. 考虑使用全局锁或消息队列序列化所有数据库写入
3. 如果还不行，考虑切换到 PostgreSQL

## 时间线

- 23:01 - 首次发现数据库锁定
- 23:05 - 尝试方案 1 (timeout)
- 23:10 - 尝试方案 2 (WAL)
- 23:15 - 尝试方案 3 (连接池)
- 23:20 - 尝试方案 4 (NullPool)
- 23:25 - 发现根本原因：LLM 调用期间持有数据库会话
- 23:30 - 尝试方案 6 (分离会话)
- 23:33 - 发现 send_agent_message 嵌套会话问题
- 23:35 - 修复后还是锁定，继续排查
