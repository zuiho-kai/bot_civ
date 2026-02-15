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

### 方案 1: 增加 timeout 参数
```python
connect_args={"timeout": 30, "check_same_thread": False}
```
- **结果**: 失败，还是锁定
- **原因**: timeout 只是等待时间，不解决并发写入冲突

### 方案 2: 启用 WAL 模式
```python
PRAGMA journal_mode=WAL
PRAGMA busy_timeout=30000
```
- **结果**: 失败，还是锁定
- **原因**: WAL 改善了读写并发，但多个写入者仍会冲突

### 方案 3: 增加连接池配置
```python
pool_pre_ping=True,
pool_size=20,
max_overflow=0,
```
- **结果**: 失败，还是锁定
- **原因**: 连接池复用可能加剧冲突

### 方案 4: 禁用连接池 (NullPool)
```python
poolclass=NullPool
```
- **结果**: 失败，还是锁定
- **原因**: 每次创建新连接也无法解决同时写入的问题

### 方案 5: 修复 emoji 编码错误
```python
# 将 print() 改为 logger.info()
```
- **结果**: 修复了编码问题，但数据库锁定依然存在

## 正确的解决方案（待实施）

### 方案 A: 分离数据库会话（推荐）
**思路**: 在 LLM 调用前关闭数据库会话，调用完成后创建新会话保存结果

```python
async def handle_wakeup(message: Message):
    # 第一个会话：读取数据
    async with async_session() as db:
        # 查询历史、检查配额等
        history = await get_history(db)
        agent = await db.get(Agent, agent_id)
        # 会话结束，释放锁

    # LLM 调用（无数据库会话）
    reply = await runner.generate_reply(history)

    # 第二个会话：保存结果
    async with async_session() as db:
        await send_agent_message(agent.id, agent.name, reply)
        await economy_service.deduct_quota(agent_id, db)
        await db.commit()
```

**优点**:
- LLM 调用期间不持有数据库锁
- 简单直接，不改变架构

**缺点**:
- 需要重构 `handle_wakeup` 函数

### 方案 B: 使用消息队列
**思路**: LLM 调用和数据库写入放到后台任务队列

**优点**: 彻底解耦
**缺点**: 架构复杂度增加

### 方案 C: 切换到 PostgreSQL
**思路**: 换用支持真正并发的数据库

**优点**: 根本解决并发问题
**缺点**: 部署复杂度增加

## 下一步行动

1. **立即实施方案 A**：重构 `handle_wakeup` 分离数据库会话
2. 测试验证
3. 如果还有问题，考虑方案 B 或 C

## 时间线

- 23:01 - 首次发现数据库锁定
- 23:05 - 尝试方案 1 (timeout)
- 23:10 - 尝试方案 2 (WAL)
- 23:15 - 尝试方案 3 (连接池)
- 23:20 - 尝试方案 4 (NullPool)
- 23:25 - 发现根本原因：LLM 调用期间持有数据库会话
- 23:30 - 准备实施方案 A
