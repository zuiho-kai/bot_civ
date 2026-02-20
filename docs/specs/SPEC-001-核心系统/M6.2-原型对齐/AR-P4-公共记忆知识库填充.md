# AR-P4：公共记忆知识库填充 — 架构评审

> 状态：待评审
> 对应 SR：SR-P4-公共记忆知识库填充
> 对应 IR：IR-M6.2 P4
> 评审日期：2026-02-20

---

## 1. 架构决策记录（ADR）

### ADR-1：新建 seed_data.py 而非复用 memory_service.save_memory()

- **背景**：`save_memory()` 逐条 commit + 失败时 delete 回滚，适合运行时单条写入
- **决策**：新建 `seed_data.py`，采用批量 flush + 单次 commit 模式
- **理由**：种子填充是启动时一次性批量操作，逐条 commit 产生 N 次磁盘 IO 不合理；失败条目用 expunge 移除即可，无需 delete 回滚
- **后果**：seed 逻辑与运行时记忆写入解耦，各自演进互不影响

### ADR-2：幂等判断采用 count > 0 粗粒度策略

- **背景**：可选方案有逐条 content hash 去重、版本号比对、count 判断三种
- **决策**：`SELECT COUNT(*) WHERE memory_type='public'`，count > 0 即跳过全部
- **理由**：种子数据是一次性批量填充，不存在"部分填充后需补齐"的正常业务场景；逐条去重增加复杂度但收益极低
- **后果**：中途 embedding 失败导致部分缺失时，需管理员手动清空后重启触发重填。这是有意的简化，符合原型阶段定位
- **替代方案被否决**：content hash 去重 — 增加 hash 列或每次启动全量比对，过度设计

### ADR-3：embedding 失败采用跳过策略而非阻塞

- **背景**：embedding 依赖外部 API（硅基流动），启动时可能不可用
- **决策**：单条失败 → warning log + expunge + 继续；全部失败 → 0 条写入，下次启动自愈
- **理由**：公共记忆是增强功能，不应阻塞核心服务启动
- **后果**：极端情况下服务运行但无公共记忆，Agent 对话质量略降但功能不受影响

### ADR-4：种子数据外置 JSON 文件

- **决策**：`server/data/public_memories.json`，纯 content 数组
- **理由**：非开发人员可直接编辑 JSON 调整世界观内容，无需改 Python 代码
- **后果**：需处理文件不存在/解析失败的防御逻辑（已在 SR 中定义）

---

## 2. 模块依赖图

```
main.py (lifespan)
  │
  ├── init_db()                    # 建表
  ├── ensure_human_agent()         # Agent id=0
  ├── seed_jobs_and_items()        # 职业/商品种子
  ├── seed_city_buildings()        # 城市建筑种子
  ├── init_vector_store()          # httpx client 初始化
  ├── seed_public_memories() ←── 新增（必须在 init_vector_store 之后）
  │     │
  │     ├── core.database.async_session  # DB 会话
  │     ├── models.Memory / MemoryType   # ORM 模型
  │     ├── vector_store.upsert_memory() # embedding 生成 + 写入
  │     └── data/public_memories.json    # 种子数据源（只读）
  │
  ├── scheduler_loop()
  └── autonomy_loop()
```

依赖方向：`seed_data → vector_store → httpx(外部API)`，`seed_data → models`，`seed_data → database`。无反向依赖，无循环依赖。新模块不被任何运行时模块引用（纯启动时调用）。

---

## 3. 数据流图

```
服务启动
  │
  ▼
seed_public_memories()
  │
  ├─ SELECT COUNT(*) FROM memories WHERE memory_type='public'
  │    ├─ count > 0 → [info log] → return（幂等跳过）
  │    └─ count == 0 → 继续 ▼
  │
  ├─ _load_seed_file()
  │    ├─ 文件不存在 → [warning log] → return []
  │    ├─ JSON 解析失败 → [warning log] → return []
  │    └─ 正常 → return list[dict]
  │
  ├─ 逐条处理 ──────────────────────────────────┐
  │    │                                         │
  │    ├─ content 为空 → skip                    │
  │    ├─ Memory(agent_id=None, type=PUBLIC)      │
  │    ├─ db.add() + db.flush() → 获取 memory.id │
  │    ├─ vector_store.upsert_memory()            │
  │    │    ├─ embed(content) → 硅基流动 API      │
  │    │    │    └─ 返回 float32 blob             │
  │    │    └─ mem.embedding = blob               │
  │    ├─ 成功 → success++                        │
  │    └─ 异常 → [warning log] + expunge → skip  │
  │                                               │
  └─ db.commit()（一次性提交所有成功条目）──────────┘
```

---

## 4. 性能考量

| 维度 | 分析 | 结论 |
|------|------|------|
| 启动延迟 | 10~15 条 × embedding API 调用（每次 ~200ms）≈ 2~3s | 仅首次启动，后续幂等跳过，可接受 |
| DB IO | 批量 flush + 单次 commit，1 次磁盘写入 | 优于逐条 commit 的 N 次写入 |
| 内存占用 | 15 条 JSON + 15 个 float32 向量（每个 ~4KB）| 可忽略 |
| embedding API 并发 | 当前串行调用，无并发压力 | 15 条规模无需并行优化；若未来扩展到 100+ 条可改为 asyncio.gather 批量 |
| 向量检索影响 | search_memories 全量加载 agent 记忆 + 公共记忆，新增 15 条 | 对 <10k 总量的 NumPy 余弦相似度计算无感知影响 |

---

## 5. 安全考量

| 风险点 | 缓解措施 |
|--------|----------|
| JSON 注入 | 种子数据为项目内静态文件，非用户输入；content 直接存储不做 SQL 拼接（ORM 参数化） |
| 文件路径穿越 | `_load_seed_file()` 硬编码相对路径 `Path(__file__).parent.parent.parent / "data" / ...`，不接受外部输入 |
| embedding API 密钥泄露 | 密钥通过 `settings.embedding_api_key` 环境变量注入，不写入 JSON 文件 |
| 公共记忆内容污染 | 种子数据由开发者维护（代码仓库管控）；运行时增删通过管理 API（需认证，当前原型阶段无认证但在规划中） |
| 大文件 DoS | JSON 文件为项目内文件，非用户上传；即使被篡改为大文件，逐条处理 + embedding 超时兜底 |

---

## 6. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| embedding API 首次启动不可用 | 中 | 低：0 条公共记忆，Agent 对话可用但无共享知识 | 下次启动自愈（count=0 重试）；管理员可通过 API 手动补充 |
| 部分 embedding 失败后永久缺失 | 低 | 低：缺几条世界观不影响核心功能 | 管理员清空公共记忆后重启，或通过 `POST /api/memories` 手动补充 |
| JSON 文件被误删 | 低 | 低：`_load_seed_file()` 返回空列表，不报错不阻塞 | 文件在 Git 仓库中，可恢复 |
| 种子数据内容质量差 | 中 | 中：Agent 引用低质量公共记忆影响对话体验 | 内容由开发者审核后提交；后续可通过管理 API 增删调整 |
| expunge 后 session 状态异常 | 低 | 高：commit 失败导致全部种子丢失 | SR 中 expunge 逻辑需 UT 覆盖；commit 失败上抛由 lifespan 处理 |

---

## 7. 与现有架构的兼容性分析

| 现有模块 | 兼容性 | 说明 |
|----------|--------|------|
| `main.py` lifespan | 完全兼容 | 新增一行 `await seed_public_memories()` 调用，与 `seed_jobs_and_items()` / `seed_city_buildings()` 模式完全一致 |
| `vector_store.upsert_memory()` | 完全兼容 | 直接调用已有接口，`agent_id=-1` 为公共记忆标识（与 `memory_service.save_memory()` 中的约定一致） |
| `vector_store.search_memories()` | 完全兼容 | 查询条件 `Memory.agent_id.is_(None)` 已包含公共记忆，无需修改 |
| `Memory` 模型 | 完全兼容 | `MemoryType.PUBLIC` 枚举已存在，`agent_id=NULL` 已支持 |
| `memory_service.search()` | 完全兼容 | 底层调用 `vector_store.search_memories()`，公共记忆自动包含在结果中 |
| `agent_runner` | 完全兼容 | 已有公共知识分区展示逻辑，种子数据填充后自动生效 |
| 管理 API | 完全兼容 | `POST /api/memories` 和 `DELETE /api/memories/{id}` 可管理公共记忆，无需修改 |
| DB schema | 完全兼容 | 不新增表/列，使用现有 Memory 表 |

结论：P4 是纯数据填充任务，不修改任何现有接口签名或数据模型，兼容性风险为零。

---

## 8. 重点关注项

### 8.1 幂等设计的边界条件

| 场景 | 行为 | 是否可接受 |
|------|------|------------|
| 首次启动，embedding 全部成功 | 写入 N 条，下次跳过 | 是（正常路径） |
| 首次启动，embedding 全部失败 | 写入 0 条，下次重试 | 是（自愈） |
| 首次启动，部分失败（成功 M 条） | 写入 M 条，下次跳过（不补齐） | 是（有意简化，管理员可手动处理） |
| JSON 新增条目后重启 | 不会填充新条目（count > 0 跳过） | 是（种子数据是一次性的，后续增删走管理 API） |
| 管理员通过 API 删除全部公共记忆后重启 | count=0，重新填充 | 是（这是预期的"重置"操作路径） |
| 管理员通过 API 删除部分后重启 | count > 0，不补齐 | 是（部分删除是有意操作，不应自动恢复） |

**架构建议**：当前粗粒度幂等策略与原型阶段匹配。若未来需要版本化种子数据（如 JSON 文件更新后自动增量同步），可引入 `seed_version` 元数据表，但 M6.2 不需要。

### 8.2 embedding 失败的容错策略

```
失败点          │ 处理                    │ 恢复路径
────────────────┼─────────────────────────┼──────────────────
httpx 超时(30s) │ try/except → skip       │ 下次启动自愈(若全失败)
API 返回非200   │ raise_for_status → skip │ 同上
返回维度不匹配  │ ValueError → skip       │ 需修复 config
client 未初始化 │ RuntimeError → skip     │ 检查 init_vector_store 调用顺序
```

**关键保证**：任何单条失败都不阻塞服务启动，不影响其他条目写入。DB commit 级别的致命错误（磁盘满等）上抛，这是合理的 — 此时整个服务都无法正常运行。

### 8.3 种子数据与运行时数据的隔离

| 维度 | 种子数据 | 运行时数据 |
|------|----------|------------|
| 写入时机 | 启动时（lifespan） | 运行时（API / Agent 对话） |
| 写入路径 | `seed_public_memories()` | `memory_service.save_memory()` |
| 事务模式 | 批量 flush + 单次 commit | 逐条 commit + 失败 delete 回滚 |
| 数据源 | `public_memories.json`（静态文件） | 用户/Agent 输入（动态） |
| DB 标识 | `memory_type='public'`, `agent_id=NULL` | 同（公共）或 `agent_id=N`（私有） |

两者在 DB 层面无结构区分（都是 Memory 行），这是有意设计 — 公共记忆不区分来源，统一参与向量检索。若未来需要区分种子数据与运行时添加的公共记忆（如"重置为初始状态"），可新增 `source` 字段（`seed` / `api` / `agent`），但 M6.2 不需要。
