# 错题本 — 📋 项目经理

> 进度管理、里程碑跟踪相关的典型错误。

### 记录规则

- **条目只写核心规则**（❌/✅/一句话解释），控制在 5 行以内
- **实际案例**最多 2-3 行摘要，详细复盘放独立 postmortem 文件并附链接

---

### PM-1 小进展写到总进展

❌
```markdown
# claude-progress.txt
2025-02-14 14:30 | 完成 GET /agents 接口 | 返回 Agent 列表
```

✅
```markdown
# server/progress.md
#### 14:30 - 完成 GET /agents 接口
```
> 单个接口是小进展，只记在局部 progress.md。

### PM-2 大里程碑忘记同步

❌ 只写在 server/progress.md，claude-progress.txt 没有
✅ 两边都写，server/progress.md 标注"已同步到 claude-progress.txt"
> 项目经理只看 claude-progress.txt，漏同步 = 看不到。

### PM-3 讨论细节写在 progress 里

❌
```markdown
# claude-progress.txt
### 数据库选型辩论
A方案: Qdrant，优点是...（20行辩论过程）
```

✅
```markdown
# claude-progress.txt（一行结论）
### 2025-02-14 | 数据库选型 → SQLite + LanceDB（2:1投票）
```
> progress 是仪表盘，不是会议纪要。细节放 discussions。

### PM-4 设计终端加载过多文件

❌ 每次启动读：CLAUDE.md + claude-progress.txt + server/progress.md + web/progress.md + discussions.md
✅ 只读：CLAUDE.md + claude-progress.txt，其他按需加载
> 减少上下文负担，避免信息过载。

### PM-5 需求评审只关注功能需求，遗漏非功能需求

❌ REQ 文档只写"消息存储、Agent 回复、@提及唤醒"等功能需求，没有追问并发安全性、性能约束等非功能需求
✅ 需求评审时主动追问：**并发场景是什么？数据一致性要求？技术选型有什么隐含约束？**，并将非功能需求写入 REQ 文档
> 功能需求决定"做什么"，非功能需求决定"能不能稳定跑"。漏了非功能需求，功能做完也会在生产环境炸。

**需求评审追问清单（涉及数据库/中间件时）**:
1. [ ] 有几个并发写入源？（WebSocket、async task、定时任务）
2. [ ] 数据一致性要求？（强一致 vs 最终一致）
3. [ ] 技术选型的并发限制？（需架构师提供约束清单）
4. [ ] 是否有 fire-and-forget 的写入？（反模式，需要明确标注）

**实际案例**（DEV-BUG-7，详见 COMMON-8）：REQ-001 只关注了功能需求（消息存储、Agent 回复），没有评估 SQLite 在多 async 写入场景下的并发限制，导致后续全链路无人看护。
