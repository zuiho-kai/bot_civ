# 错题本 — 📋 项目经理

> 进度管理、里程碑跟踪相关的典型错误。

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
