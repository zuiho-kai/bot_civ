# Postmortem: Gemini CLI 集成耗时过长

> 日期：2026-02-17
> 涉及任务：Gemini CLI 安装 + vault 集成 + UI 设计流程脚本

---

## 卡点时间线

| 轮次 | 问题 | 浪费原因 |
|------|------|---------|
| 1-3 | 误把 vault 里的 key 也删掉 | 误解"把api key删掉"= 删所有存储 |
| 4-8 | Node.js fetch 超时 | 没有先检查是否需要代理（HTTPS_PROXY 已存在） |
| 9-11 | execFileSync ENOENT | 没有先验证 gemini 在脚本环境的 PATH |
| 12-19 | `limit:0` 误判每日用尽 → 绕去 OAuth session resume | 实际是 RPM 速率限制，等 1-2 分钟即恢复 |
| 20-22 | `--resume latest` 接错 session，输出是旧对话的答案 | resume 会复用历史上下文 |
| 23-25 | 最终：换 gemini-2.5-flash + stdin pipe → 通 | — |

## 根因分析

### 根因 1：意图确认失败
**用户说**："把api key删掉，以后不用了"
**我的理解**：删掉所有存储（vault + bashrc）
**正确理解**：不要明文存，改用 vault 管理，以后通过脚本读取
**规则**：用户说"删掉 X"时，先确认是删整个功能还是只删某个存储位置

### 根因 2：没有先做环境探针
正确的调试顺序应该是：
```
1. 确认 CLI 可用（which gemini）
2. 确认网络可达（check HTTPS_PROXY）
3. 确认认证方式（cat ~/.gemini/settings.json）
4. 再写脚本
```
实际顺序：先写脚本 → 遇到各种环境问题再逐个修

### 根因 3：错误信息误判
Gemini 429 错误里 `limit: 0` 的含义：
- ❌ 我的理解：quota 上限本来就是 0（即无额度）
- ✅ 实际含义：当前剩余 quota 为 0（RPM 被打满，等 10-30s 恢复）
- 判断方法：看 `retryDelay` 字段，有秒数 = RPM 限速，没有 = 真正用尽

### 根因 4：模型选择未最优化
gemini-2.5-pro（默认）vs gemini-2.5-flash：
- pro: 5 RPM, 100 RPD → 最容易触限
- flash: 10 RPM, 250 RPD → 更宽松
- flash-lite: 15 RPM, 1000 RPD → 开发测试首选

## 修复结果

最终工作方案：
```bash
# 脚本里用 gemini-2.5-flash，stdin pipe 传 prompt
spawnSync('gemini', ['-m', 'gemini-2.5-flash'], { input: prompt, shell: true })
# API key 从 vault 读取注入
```

## 应提炼的规则

见 DEV-12（error-book-dev-common.md）
