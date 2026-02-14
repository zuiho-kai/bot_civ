# 错题本 — 📝 记录员

> 讨论记录、文档落盘相关的典型错误。

---

### REC-1 讨论只存在对话中

❌ 辩论完直接告诉用户结论，没有写文件
✅ 辩论完立即创建 `docs/discussions/YYYY-MM-DD-主题.md` + 更新 `docs/discussions.md` 索引
> 对话是临时的，文件是持久的。

### REC-2 讨论文件没有更新索引

❌ 创建了 `docs/discussions/2025-02-14-xxx.md`，但 `docs/discussions.md` 没加条目
✅ 创建详细文件的同时，在 `docs/discussions.md` 索引表添加一行
> 索引是入口，没索引 = 找不到。

### REC-3 多个文件记录同一信息

❌ 文档结构在 CLAUDE.md 写一遍，claude-progress.txt 又写一遍
✅ 只在一个地方维护，其他地方放链接
> 信息只有一个 source of truth，重复 = 不一致风险。

### REC-4 详细内容放在索引文件里

❌ discussions.md 里放完整的辩论过程（几百行）
✅ discussions.md 只放索引表格，详细内容在 `discussions/YYYY-MM-DD-主题.md`
> 索引文件要轻，详细内容按需加载。
