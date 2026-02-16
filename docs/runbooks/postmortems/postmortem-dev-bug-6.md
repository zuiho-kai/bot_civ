# DEV-BUG-6 详细复盘：OpenClaw BotCiv Plugin 连接反复断开

> 摘要见 [error-book-dev.md](error-book-dev.md#dev-bug-6)

- **场景**: 编写 OpenClaw botciv channel plugin，让 OpenClaw 作为 bot_civ 的原生 channel 接入
- **现象**: WebSocket 连接成功后立刻断开，3秒重连一次，无限循环
- **原因（三层叠加）**:
  1. **Node 22 原生 WebSocket 与 FastAPI/Starlette 不兼容**: Node 22 内置的 `globalThis.WebSocket` 连接 Starlette WebSocket 后立刻收到 close code 1006（异常关闭）。而 `ws` 库正常工作。原因未知，可能是 Starlette 的 WebSocket 实现对 HTTP/1.1 upgrade 的处理与 Node 原生实现有差异
  2. **`ws` 模块找不到**: plugin 用 `import WebSocket from "ws"` 但 plugin 目录没有 node_modules，OpenClaw 的 `ws` 在 `/usr/lib/node_modules/openclaw/node_modules/ws`，模块解析找不到
  3. **oc_bot.py 抢连接**: 旧的 `oc_bot.py` 脚本也用 agent_id=1 连接，bot_civ 的连接池管理会踢旧连接（code 4001 Replaced），两个客户端互相踢导致无限重连
- **修复**:
  1. 用 `createRequire` + 绝对路径加载 ws: `require("/usr/lib/node_modules/openclaw/node_modules/ws")`
  2. 杀掉 oc_bot.py，确保只有 plugin 一个 bot 连接
  3. 消息格式从 `{type: "send_message", data: {content}}` 改为 `{type: "chat_message", content}` 匹配 bot_civ 协议

## 反思

- **应该先写最小验证脚本**: 在写 plugin 之前，应该先用 Node 脚本验证 WebSocket 连接是否正常，而不是写完整个 plugin 再调试
- **不要假设原生 API 等价于库**: Node 22 的 WebSocket 和 `ws` 库行为不同，特别是跟非标准 WebSocket 服务端交互时
- **多客户端冲突要提前考虑**: bot_civ 的连接池设计是"一个 agent_id 只允许一个 bot 连接"，部署新客户端前应该先停旧的
- **SSH 长命令不稳定**: `pkill` + `openclaw gateway restart` 组合命令经常导致 SSH 断连（exit 255），应该分步执行或用 systemd 管理

## 时间线复盘

| 阶段 | 耗时 | 做了什么 | 问题 |
|------|------|----------|------|
| 1. 初始部署 | 10min | 传文件、重启 gateway、确认 plugin 加载 | 顺利，plugin 被识别 |
| 2. ws 模块缺失 | 15min | 发现 `Cannot find module 'ws'`，尝试 npm install 失败（workspace:* 不兼容），决定改用 Node 22 原生 WebSocket | 方向错误 — 应该直接用绝对路径 require |
| 3. 原生 WS 连接循环 | 30min | 改完原生 WebSocket API，部署，发现不断重连。反复改代码（addEventListener vs .on, event.data vs raw）、传文件、重启 gateway | **最大浪费** — 没有先写最小脚本验证原生 WS 能不能连 Starlette |
| 4. 排查断连原因 | 20min | 看 bot_civ server 日志发现 `connection open → connection closed`，写 Node 测试脚本，发现原生 WS code 1006，ws 库正常 | 这一步做对了，但应该在阶段 2 就做 |
| 5. 改回 ws 库 + 抢连接 | 15min | 用 createRequire 绝对路径加载 ws，发现 oc_bot.py 抢连接（4001 Replaced），杀掉 oc_bot.py | |
| 6. SSH 断连反复重试 | 20min | pkill/kill 命令导致 SSH exit 255，反复等待重连、分步执行 | 应该用 systemd 或 screen/tmux |
| 7. 最终验证 | 10min | 连接稳定，发消息测试通过 | |

## 根因分析

1. **缺少 spike/PoC 环节**: 直接写完整 plugin 再调试，而不是先用 10 行脚本验证 "Node → bot_civ WebSocket" 这个最基本的假设。如果先验证，阶段 2-4 的 45 分钟可以压缩到 5 分钟
2. **远程调试循环太慢**: 每次改代码要：本地编辑 → base64 传输 → SSH 重启 gateway → 看日志。一个循环 3-5 分钟。6 次循环就是 30 分钟。应该直接在远程机器上用 vim/nano 改，或者写一个一键部署脚本
3. **没有提前梳理运行环境**: 不知道 oc_bot.py 还在跑、不知道 gateway 的 systemd 服务名、不知道 Node 22 原生 WS 跟 ws 库的差异。这些都是可以提前调查的
4. **问题叠加导致误判**: 三个独立问题（ws 模块缺失、原生 WS 不兼容、oc_bot.py 抢连接）同时存在，修了一个以为解决了，结果还有下一个。应该先列出所有可能的失败点再逐一排除

## 改进 checklist（下次写 channel plugin 时）

1. [ ] 先在目标机器上写 10 行 Node 脚本验证 WebSocket 连接
2. [ ] 确认目标服务没有其他客户端占用连接
3. [ ] 确认 plugin 的依赖在 OpenClaw 运行时环境中可用
4. [ ] 准备一键部署脚本（scp + restart），避免手动多步操作
5. [ ] gateway 用 systemd 管理，不要手动 kill + nohup
