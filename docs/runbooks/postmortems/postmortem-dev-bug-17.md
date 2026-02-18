# Postmortem DEV-BUG-17: 前端 API 路径凭记忆写，全量 404

## 场景

M5 前端 api.ts 编写阶段，后端路由已完成，前端凭记忆拼接 API URL。

## 具体错误

| # | 后端实际 | 前端写的 | 错误类型 |
|---|---------|---------|---------|
| 1 | `/cities/{city}/...` | `/city/{city}/...` | 复数形式错 |
| 2 | router prefix="/memories" | `/memory/` | 复数形式错 |
| 3 | `DELETE .../workers/{aid}` | `POST .../remove` + body | HTTP method + 路径都错 |
| 4 | `POST /agents/{id}/eat`（path param） | `POST /city/eat` + body | URL 结构完全不同 |
| 5 | query param `memory_type` | 前端传 `type` | query param 名错 |
| 6 | response `{"by_type": {"short": n}}` | 期望 `{"short_count": n}` | response 字段名错 |

## 根因

DEV-11（字段对齐靠目测）的升级版。DEV-11 只覆盖了"字段名"维度，这次暴露的是"路径 + HTTP method + 参数位置 + response 结构"全面不匹配。

根本原因：后端和前端分阶段写，前端编写时没有打开后端路由文件逐行对照，而是凭记忆拼 URL。

## 前后端 API 对齐 checklist

1. 打开后端路由文件（如 city.py、memory.py），逐条列出：method + path + params + response schema
2. 前端 api.ts 每个函数逐条比对：URL 拼接、HTTP method、参数传递方式（path/query/body）、response 类型
3. 特别注意：复数形式（city vs cities）、连字符（logs vs production-logs）、参数位置（path param vs body）
4. router prefix 要加上 main.py 的 app prefix 才是最终路径
5. 比对完成后跑一遍 mock=false 的冒烟测试确认无 404

## 修复

前端 api.ts 逐条比对后端路由文件，修正所有 URL/method/param/response 不匹配。
