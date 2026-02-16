# 去掉 LanceDB 向量数据库方案讨论 — 四方讨论记录

**日期**: 2026-02-16
**类型**: 架构讨论
**参与者**: 🏗️ 架构师、👤 人类替身 PM、🧪 QA Lead、📐 Tech Lead
**触发**: 外部批评引发思考——在 20 Agent / ~1000 条记忆的规模下，是否需要 LanceDB？

---

## 背景

当前记忆系统架构：
- **SQLite**：存结构化数据（Memory 表，含 agent_id / content / memory_type / access_count / expires_at）
- **LanceDB**：存向量（embedding），用于语义搜索
- **sentence-transformers**（BGE-small-zh-v1.5）：本地跑 embedding 模型，512 维向量

双写流程：`save_memory()` 先写 SQLite，再写 LanceDB；搜索时先查 LanceDB 拿排序，再回 SQLite 拿完整记录。

问题：
1. LanceDB + sentence-transformers + PyArrow 带来大量依赖，启动慢 30s+
2. 双数据库一致性风险（代码里已有 orphan 检测日志）
3. 部署门槛高（需要下载 95MB embedding 模型）
4. 当前规模（~1000 条记忆）是否真的需要专门的向量数据库？

### 业界参考

| 产品 | 做法 | 规模 |
|------|------|------|
| Obsidian Smart Connections | embedding 存平面文件，暴力 cosine similarity | 数千笔记 |
| Claude Code | 不用向量搜索，grep + LLM 实时推理 | 任意代码库 |
| ChatGPT Memory | 短文本记忆，暴力相似度 | 数百条/用户 |
| AnythingLLM | LanceDB（嵌入式，零配置） | 通用 RAG |

---

## 候选方案

### 方案 A：SQLite BLOB + NumPy 暴力搜索（替换 LanceDB，保留语义搜索）

```python
# Memory 表新增 embedding BLOB 列
# 存入时：调 embedding API（或本地模型）生成向量，存为 BLOB
# 搜索时：加载该 agent 所有 embedding，NumPy 算 cosine similarity，返回 top-K

import numpy as np

def search(query_vec, all_vecs, top_k=5):
    sims = all_vecs @ query_vec / (np.linalg.norm(all_vecs, axis=1) * np.linalg.norm(query_vec))
    top_idx = np.argsort(sims)[-top_k:][::-1]
    return top_idx, sims[top_idx]
```

- 去掉：LanceDB、PyArrow
- 保留：sentence-transformers（或换成 API 调用）
- 性能：1000 条 × 512 维 ≈ 2MB，暴力搜索 < 5ms

### 方案 B：SQLite FTS5 全文搜索（去掉所有向量相关依赖）

```sql
CREATE VIRTUAL TABLE memories_fts USING fts5(content, agent_id UNINDEXED);
SELECT *, rank FROM memories_fts WHERE memories_fts MATCH '关键词' ORDER BY rank;
```

- 去掉：LanceDB、PyArrow、sentence-transformers
- 零 embedding 成本，零模型下载
- 缺点：不能语义匹配（"开心"搜不到"高兴"）

### 方案 C：LLM 直接挑选（零基础设施）

```python
# 把所有记忆塞进 prompt，让 LLM 挑相关的
memories_text = "\n".join(f"[{m.id}] {m.content}" for m in all_memories)
prompt = f"从以下记忆中选出与'{query}'最相关的5条，返回ID列表：\n{memories_text}"
```

- 去掉：LanceDB、PyArrow、sentence-transformers
- 语义理解最好
- 缺点：每次搜索花 token，长期运行成本最高

### 方案 D：保持现状（LanceDB 不动）

- 不改任何东西
- 理由：能跑，以后规模大了本来就需要向量数据库

---

## 讨论过程

### 第一轮：各方立场

**🏗️ 架构师**

我倾向方案 A。理由：

1. 当前规模完全不需要 LanceDB。1000 条 512 维向量，暴力搜索 < 5ms，LanceDB 的 ANN 索引在 10 万条以下没有性能优势。
2. 去掉 LanceDB 消除了双数据库一致性问题。现在 `memory_service.py:62-65` 已经有 orphan 检测逻辑，说明一致性确实是个隐患。
3. embedding 能力要保留——语义搜索是记忆系统的核心价值。FTS5 只能做关键词匹配，对中文效果尤其差。
4. embedding 模型可以从本地 sentence-transformers 换成 API 调用（OpenAI / 硅基流动等），进一步减轻部署负担。但这个是独立决策，不和去 LanceDB 捆绑。

方案 B 我反对——去掉语义搜索是降级，不是简化。
方案 C 长期成本不可控，只适合记忆极少的早期阶段。
方案 D 能跑但不够好，部署体验是真问题。

**👤 人类替身 PM**

对照用户知识库：

1. 用户偏好"极简实现"和"站在巨人肩膀上"。SQLite BLOB + NumPy 比 LanceDB 更极简。
2. 用户选择 SQLite + LanceDB 混合架构时的理由是"结构化+向量各取所长"。方案 A 仍然保留向量能力，只是存储位置从 LanceDB 挪到 SQLite BLOB，不违背原始意图。
3. 用户重视部署体验（外部批评中"部署门槛高"被列为 P0）。去掉 LanceDB + PyArrow 能显著降低依赖复杂度。
4. 用户风格是"快速验证优先"——先简化跑通，规模大了再上专业方案。

我支持方案 A，但有一个提醒：embedding 模型怎么处理需要单独讨论。本地 sentence-transformers 是当前最大的部署负担（95MB 模型 + PyTorch 依赖）。

**📐 Tech Lead**

从实现角度分析方案 A 的改动范围：

影响文件：
- `vector_store.py`（111 行）→ 重写为 `embedding_store.py`，用 SQLite BLOB + NumPy
- `memory_service.py` → 改调用接口（save/search/delete 三个方法）
- `main.py` → 去掉 `init_vector_store()`
- `config.py` → 去掉 `lancedb_path`
- `requirements.txt` → 去掉 lancedb、sentence-transformers（如果换 API）、pyarrow
- Memory 模型 → 新增 `embedding` BLOB 列
- 测试 → mock 接口变了，需要更新

工作量估算：半天到一天。改动集中在 `vector_store.py` 的替换，其他文件是接口适配。

风险点：
- 数据迁移：现有 LanceDB 里的向量数据需要迁移到 SQLite。但当前数据量极小，可以直接重新 embed。
- embedding 模型选择：如果继续用本地模型，部署负担没减多少。建议同步考虑换 API。

**🧪 QA Lead**

从测试角度：

1. 现有 6 个记忆测试全部 mock 了 `vector_store`，说明 vector_store 是干净的可替换模块。换实现不影响测试逻辑，只需要更新 mock 路径。
2. 方案 A 消除了双数据库一致性问题，反而减少了需要测试的边界场景（orphan 检测、双写失败回滚等）。
3. 建议：迁移后跑一次端到端的记忆存取测试（不 mock），验证 SQLite BLOB 读写正确性。

我支持方案 A。

### 第二轮：争议点讨论

**争议 1：embedding 模型怎么处理？**

🏗️ 架构师：这是独立决策，建议拆开讨论。但给个初步方向——
- 选项 1：继续本地 sentence-transformers（保留离线能力，但部署重）
- 选项 2：换 embedding API（硅基流动免费、OpenAI 便宜，部署轻但依赖网络）
- 选项 3：先用 API，配置项支持切回本地（渐进式）

👤 人类替身 PM：用户偏好"免费/低成本方案"。硅基流动有免费 embedding API，符合用户风格。但离线能力也重要——用户说过"先放本地"。建议选项 3。

📐 Tech Lead：同意拆开。今天只决定去不去 LanceDB，embedding 模型另开讨论。

**争议 2：未来规模扩大怎么办？**

🏗️ 架构师：如果未来到 10 万条记忆，SQLite BLOB 暴力搜索会变慢（~500ms）。到时候有两条路：
1. 加 sqlite-vec 扩展（SQLite 原生向量搜索，C 扩展，SQL 语法）
2. 回到专业向量数据库（pgvector 或 LanceDB）

但这是"未来的问题"。用户风格是"不要过早优化，20 个 Agent 规模下不是瓶颈"。

🧪 QA Lead：只要接口抽象干净（search/upsert/delete），底层换实现不影响上层。现在的 `vector_store.py` 已经是这个结构，保持就好。

**争议 3：方案 B（FTS5）要不要作为降级方案保留？**

📐 Tech Lead：可以作为 fallback——如果 embedding 模型不可用（API 挂了、本地没装），退化到 FTS5 关键词搜索。但这增加了复杂度，建议不做，除非用户要求。

🏗️ 架构师：同意不做。YAGNI。

---

## 投票结果

| 参与者 | 投票 | 理由 |
|--------|------|------|
| 🏗️ 架构师 | 方案 A | 保留语义搜索，去掉不必要的依赖，规模匹配 |
| 👤 人类替身 PM | 方案 A | 符合用户极简偏好，不违背原始设计意图 |
| 📐 Tech Lead | 方案 A | 改动可控（半天），风险低 |
| 🧪 QA Lead | 方案 A | 测试影响小，反而减少边界场景 |

**全票通过：方案 A（SQLite BLOB + NumPy 替换 LanceDB）**

---

## 决策总结

1. **去掉 LanceDB**，embedding 存入 SQLite Memory 表的新 BLOB 列
2. **搜索改为 NumPy 暴力 cosine similarity**，当前规模 < 5ms
3. **embedding 模型选择另开讨论**（本地 vs API，不和本次决策捆绑）
4. **保持接口抽象**（search/upsert/delete），未来可换底层实现
5. **不做 FTS5 降级方案**，YAGNI

### 待用户确认

- embedding 模型是继续用本地 sentence-transformers，还是换 API？（影响部署体验，建议单独讨论）

### 实施计划

| 步骤 | 内容 |
|------|------|
| 1 | Memory 模型新增 `embedding` BLOB 列（Alembic 迁移） |
| 2 | 重写 `vector_store.py` → 基于 SQLite BLOB + NumPy 的实现 |
| 3 | 适配 `memory_service.py` 调用接口 |
| 4 | `main.py` 去掉 `init_vector_store()`，`config.py` 去掉 `lancedb_path` |
| 5 | `requirements.txt` 去掉 lancedb、pyarrow |
| 6 | 更新测试 mock，新增端到端记忆存取测试 |
| 7 | 删除 `data/lancedb/` 目录 |
