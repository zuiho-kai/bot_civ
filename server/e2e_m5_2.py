"""
E2E Test — M5.2 交易市场端到端验证

覆盖场景：
  ST-1: POST /api/market/orders 挂单成功 + 资源冻结验证
  ST-2: POST /api/market/orders 资源不足挂单失败
  ST-3: POST /api/market/orders/{id}/accept 接单成功 + 资源交换验证
  ST-4: POST /api/market/orders/{id}/accept 部分接单 → 订单 partial
  ST-5: POST /api/market/orders/{id}/cancel 撤单 + 冻结归还
  ST-6: 撤单非本人订单 → 403/409
  ST-7: WebSocket 收到 order_created / order_traded / order_cancelled 广播
  ST-8: GET /api/market/trade-logs 成交日志验证

用法: 先启动服务器 (uvicorn main:app --port 8001)，然后 python e2e_m5_2.py
"""
import asyncio
import sys
import os
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
import websockets

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8001")
WS_BASE = BASE.replace("http://", "ws://").replace("https://", "wss://")
CLIENT = httpx.AsyncClient(base_url=BASE, follow_redirects=True, timeout=30)

passed = 0
failed = 0
errors: list[str] = []


def ok(name: str, detail: str = ""):
    global passed
    passed += 1
    print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = ""):
    global failed
    failed += 1
    errors.append(f"{name}: {detail}")
    print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


async def get_all_agents() -> list[dict]:
    r = await CLIENT.get("/api/agents/")
    return r.json()


async def get_agent_resources(agent_id: int) -> dict:
    r = await CLIENT.get(f"/api/agents/{agent_id}/resources")
    return {item["resource_type"]: item["quantity"] for item in r.json()}


async def ensure_flour(agent_id: int, need: int = 20):
    """确保 agent 有足够 flour（通过 gov_farm 循环生产直到满足）"""
    res = await get_agent_resources(agent_id)
    if res.get("flour", 0) >= need:
        return
    print(f"  agent {agent_id} flour 不足，通过 gov_farm 生产补充...")
    # 先恢复体力（生产需要 stamina >= 20）
    await CLIENT.put(f"/api/agents/{agent_id}", json={"stamina": 100})
    r = await CLIENT.get("/api/cities/长安/buildings")
    buildings = r.json()
    gov_farm = next((b for b in buildings if b["building_type"] == "gov_farm"), None)
    if not gov_farm:
        return
    await CLIENT.post(f"/api/cities/长安/buildings/{gov_farm['id']}/workers",
                      json={"agent_id": agent_id})
    for _ in range(20):
        await CLIENT.post("/api/cities/长安/production-tick")
        res = await get_agent_resources(agent_id)
        if res.get("flour", 0) >= need:
            break
    await CLIENT.delete(f"/api/cities/长安/buildings/{gov_farm['id']}/workers/{agent_id}")
    res = await get_agent_resources(agent_id)
    print(f"  生产后 agent {agent_id} flour={res.get('flour', 0)}")


async def ensure_wheat(agent_id: int, need: int = 20):
    """确保 agent 有足够 wheat（通过 farm 循环生产直到满足）"""
    res = await get_agent_resources(agent_id)
    if res.get("wheat", 0) >= need:
        return
    print(f"  agent {agent_id} wheat 不足，通过 farm 生产补充...")
    # 先恢复体力（生产需要 stamina >= 20）
    await CLIENT.put(f"/api/agents/{agent_id}", json={"stamina": 100})
    r = await CLIENT.get("/api/cities/长安/buildings")
    buildings = r.json()
    farm = next((b for b in buildings if b["building_type"] == "farm"), None)
    if not farm:
        return
    await CLIENT.post(f"/api/cities/长安/buildings/{farm['id']}/workers",
                      json={"agent_id": agent_id})
    for _ in range(20):
        await CLIENT.post("/api/cities/长安/production-tick")
        res = await get_agent_resources(agent_id)
        if res.get("wheat", 0) >= need:
            break
    await CLIENT.delete(f"/api/cities/长安/buildings/{farm['id']}/workers/{agent_id}")
    res = await get_agent_resources(agent_id)
    print(f"  生产后 agent {agent_id} wheat={res.get('wheat', 0)}")


# ─── ST-1: 挂单成功 + 资源冻结 ─────────────────────────────────

async def test_create_order(seller_id: int):
    print("\n=== ST-1: POST /api/market/orders 挂单成功 + 资源冻结 ===")

    res_before = await get_agent_resources(seller_id)
    flour_before = res_before.get("flour", 0)
    if flour_before < 5:
        fail("ST-1", f"seller flour={flour_before} 不足")
        return None

    r = await CLIENT.post("/api/market/orders", json={
        "seller_id": seller_id,
        "sell_type": "flour", "sell_amount": 5.0,
        "buy_type": "wheat", "buy_amount": 3.0,
    })
    if r.status_code != 200:
        fail("ST-1 API", f"status={r.status_code}, body={r.text}")
        return None

    body = r.json()
    if not body.get("ok"):
        fail("ST-1 结果", f"ok=False, reason={body.get('reason')}")
        return None

    order_id = body["order_id"]
    ok("挂单成功", f"order_id={order_id}")

    # 验证资源冻结（quantity 应减少 5）
    res_after = await get_agent_resources(seller_id)
    flour_after = res_after.get("flour", 0)
    if abs(flour_after - (flour_before - 5)) < 0.01:
        ok("资源冻结正确", f"flour: {flour_before} → {flour_after}")
    else:
        fail("ST-1 冻结", f"期望 {flour_before - 5}, 实际 {flour_after}")

    return order_id


# ─── ST-2: 资源不足挂单失败 ─────────────────────────────────────

async def test_create_order_insufficient(seller_id: int):
    print("\n=== ST-2: 资源不足挂单失败 ===")

    r = await CLIENT.post("/api/market/orders", json={
        "seller_id": seller_id,
        "sell_type": "flour", "sell_amount": 999999.0,
        "buy_type": "wheat", "buy_amount": 1.0,
    })
    if r.status_code == 409:
        ok("资源不足正确拒绝 (409)", r.text[:80])
    elif r.status_code == 200 and not r.json().get("ok"):
        ok("资源不足正确拒绝 (200)", r.json().get("reason", ""))
    else:
        fail("ST-2", f"status={r.status_code}, body={r.text[:100]}")


# ─── ST-3: 接单成功 + 资源交换 ─────────────────────────────────

async def test_accept_order_full(seller_id: int, buyer_id: int, order_id: int):
    print("\n=== ST-3: POST /api/market/orders/{id}/accept 全量接单 ===")

    # 确保 buyer 有 wheat（通过 farm 生产）
    await ensure_wheat(buyer_id)

    buyer_res_before = await get_agent_resources(buyer_id)
    wheat_before = buyer_res_before.get("wheat", 0)
    flour_before_buyer = buyer_res_before.get("flour", 0)

    if wheat_before < 3:
        fail("ST-3", f"buyer wheat={wheat_before} 不足，无法接单")
        return

    seller_res_before = await get_agent_resources(seller_id)
    wheat_before_seller = seller_res_before.get("wheat", 0)

    print(f"  接单前: buyer wheat={wheat_before}, flour={flour_before_buyer}")
    print(f"  接单前: seller wheat={wheat_before_seller}")

    r = await CLIENT.post(f"/api/market/orders/{order_id}/accept", json={
        "buyer_id": buyer_id,
        "buy_ratio": 1.0,
    })
    if r.status_code != 200:
        fail("ST-3 API", f"status={r.status_code}, body={r.text}")
        return

    body = r.json()
    if not body.get("ok"):
        fail("ST-3 结果", f"ok=False, reason={body.get('reason')}")
        return

    ok("接单成功", f"trade_sell={body.get('trade_sell')}, trade_buy={body.get('trade_buy')}, status={body.get('order_status')}")

    # 验证资源交换
    buyer_res_after = await get_agent_resources(buyer_id)
    seller_res_after = await get_agent_resources(seller_id)

    # buyer: wheat 减少 3, flour 增加 5
    wheat_after_buyer = buyer_res_after.get("wheat", 0)
    flour_after_buyer = buyer_res_after.get("flour", 0)
    if abs(wheat_after_buyer - (wheat_before - 3)) < 0.01:
        ok("buyer wheat 扣除正确", f"{wheat_before} → {wheat_after_buyer}")
    else:
        fail("ST-3 buyer wheat", f"期望 {wheat_before - 3}, 实际 {wheat_after_buyer}")

    if abs(flour_after_buyer - (flour_before_buyer + 5)) < 0.01:
        ok("buyer flour 增加正确", f"{flour_before_buyer} → {flour_after_buyer}")
    else:
        fail("ST-3 buyer flour", f"期望 {flour_before_buyer + 5}, 实际 {flour_after_buyer}")

    # seller: wheat 增加 3
    wheat_after_seller = seller_res_after.get("wheat", 0)
    if abs(wheat_after_seller - (wheat_before_seller + 3)) < 0.01:
        ok("seller wheat 增加正确", f"{wheat_before_seller} → {wheat_after_seller}")
    else:
        fail("ST-3 seller wheat", f"期望 {wheat_before_seller + 3}, 实际 {wheat_after_seller}")

    # 订单应为 filled
    if body.get("order_status") == "filled":
        ok("订单状态 filled")
    else:
        fail("ST-3 订单状态", f"期望 filled, 实际 {body.get('order_status')}")


# ─── ST-4: 部分接单 → partial ──────────────────────────────────

async def test_accept_order_partial(seller_id: int, buyer_id: int):
    print("\n=== ST-4: 部分接单 → 订单 partial ===")

    # 先创建一个新挂单
    await ensure_flour(seller_id)
    r = await CLIENT.post("/api/market/orders", json={
        "seller_id": seller_id,
        "sell_type": "flour", "sell_amount": 10.0,
        "buy_type": "wheat", "buy_amount": 6.0,
    })
    if r.status_code != 200 or not r.json().get("ok"):
        fail("ST-4 挂单", f"status={r.status_code}, body={r.text[:100]}")
        return
    order_id = r.json()["order_id"]

    # 确保 buyer 有足够 wheat 接单
    await ensure_wheat(buyer_id)

    # 部分接单 50%
    r = await CLIENT.post(f"/api/market/orders/{order_id}/accept", json={
        "buyer_id": buyer_id,
        "buy_ratio": 0.5,
    })
    if r.status_code != 200:
        fail("ST-4 API", f"status={r.status_code}, body={r.text}")
        return

    body = r.json()
    if not body.get("ok"):
        fail("ST-4 结果", f"ok=False, reason={body.get('reason')}")
        return

    if body.get("order_status") == "partial":
        ok("部分接单后订单 partial", f"trade_sell={body.get('trade_sell')}, trade_buy={body.get('trade_buy')}")
    else:
        fail("ST-4 订单状态", f"期望 partial, 实际 {body.get('order_status')}")

    # 验证剩余量
    r = await CLIENT.get("/api/market/orders")
    orders = r.json()
    this_order = next((o for o in orders if o["id"] == order_id), None)
    if this_order:
        if abs(this_order["remain_sell_amount"] - 5.0) < 0.01:
            ok("剩余卖出量正确", f"remain_sell={this_order['remain_sell_amount']}")
        else:
            fail("ST-4 剩余量", f"期望 5.0, 实际 {this_order['remain_sell_amount']}")
    else:
        fail("ST-4 查询", "订单未在列表中找到")

    # 清理：撤掉这个 partial 订单
    await CLIENT.post(f"/api/market/orders/{order_id}/cancel", json={"seller_id": seller_id})
    return order_id


# ─── ST-5: 撤单 + 冻结归还 ────────────────────────────────────

async def test_cancel_order(seller_id: int):
    print("\n=== ST-5: POST /api/market/orders/{id}/cancel 撤单 + 冻结归还 ===")

    await ensure_flour(seller_id)
    res_before = await get_agent_resources(seller_id)
    flour_before = res_before.get("flour", 0)

    # 挂单
    r = await CLIENT.post("/api/market/orders", json={
        "seller_id": seller_id,
        "sell_type": "flour", "sell_amount": 4.0,
        "buy_type": "wheat", "buy_amount": 2.0,
    })
    if r.status_code != 200 or not r.json().get("ok"):
        fail("ST-5 挂单", f"status={r.status_code}")
        return
    order_id = r.json()["order_id"]

    res_after_create = await get_agent_resources(seller_id)
    flour_after_create = res_after_create.get("flour", 0)
    print(f"  挂单后 flour: {flour_before} → {flour_after_create}")

    # 撤单
    r = await CLIENT.post(f"/api/market/orders/{order_id}/cancel", json={
        "seller_id": seller_id,
    })
    if r.status_code != 200:
        fail("ST-5 API", f"status={r.status_code}, body={r.text}")
        return

    body = r.json()
    if not body.get("ok"):
        fail("ST-5 结果", f"ok=False")
        return

    ok("撤单成功")

    # 验证冻结归还
    res_after_cancel = await get_agent_resources(seller_id)
    flour_after_cancel = res_after_cancel.get("flour", 0)
    if abs(flour_after_cancel - flour_before) < 0.01:
        ok("冻结归还正确", f"flour 恢复到 {flour_after_cancel}")
    else:
        fail("ST-5 归还", f"期望 {flour_before}, 实际 {flour_after_cancel}")


# ─── ST-6: 撤单非本人订单 → 拒绝 ──────────────────────────────

async def test_cancel_order_not_owner(seller_id: int, other_id: int):
    print("\n=== ST-6: 撤单非本人订单 → 拒绝 ===")

    await ensure_flour(seller_id)
    r = await CLIENT.post("/api/market/orders", json={
        "seller_id": seller_id,
        "sell_type": "flour", "sell_amount": 2.0,
        "buy_type": "wheat", "buy_amount": 1.0,
    })
    if r.status_code != 200 or not r.json().get("ok"):
        fail("ST-6 挂单", f"status={r.status_code}")
        return
    order_id = r.json()["order_id"]

    # 用 other_id 尝试撤单
    r = await CLIENT.post(f"/api/market/orders/{order_id}/cancel", json={
        "seller_id": other_id,
    })
    if r.status_code in (403, 409):
        ok("非本人撤单被拒绝", f"status={r.status_code}")
    else:
        fail("ST-6", f"期望 403/409, 实际 status={r.status_code}, body={r.text[:80]}")

    # 清理
    await CLIENT.post(f"/api/market/orders/{order_id}/cancel", json={"seller_id": seller_id})


# ─── ST-7: WebSocket 广播验证 ──────────────────────────────────

async def test_ws_market_broadcast(seller_id: int):
    print("\n=== ST-7: WebSocket 收到 order_created / order_cancelled 广播 ===")

    ws_url = f"{WS_BASE}/api/ws/0"
    events_received: list[str] = []

    try:
        async with websockets.connect(ws_url, ping_interval=None) as ws:
            await asyncio.wait_for(ws.recv(), timeout=5)
            print("  WebSocket 已连接")
            await asyncio.sleep(0.3)

            async def collect_events(target_count: int):
                try:
                    while len(events_received) < target_count:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                        data = json.loads(msg)
                        if data.get("type") == "ping":
                            await ws.send(json.dumps({"type": "pong"}))
                            continue
                        if data.get("type") == "system_event":
                            evt = data.get("data", {}).get("event", "")
                            if evt.startswith("order_"):
                                events_received.append(evt)
                                print(f"  收到事件: {evt}")
                except asyncio.TimeoutError:
                    pass

            collector = asyncio.create_task(collect_events(2))
            await asyncio.sleep(0.1)

            await ensure_flour(seller_id)
            r = await CLIENT.post("/api/market/orders", json={
                "seller_id": seller_id,
                "sell_type": "flour", "sell_amount": 1.0,
                "buy_type": "wheat", "buy_amount": 1.0,
            })
            if r.status_code != 200 or not r.json().get("ok"):
                fail("ST-7 挂单", f"status={r.status_code}")
                collector.cancel()
                return
            oid = r.json()["order_id"]

            await asyncio.sleep(0.5)
            await CLIENT.post(f"/api/market/orders/{oid}/cancel", json={"seller_id": seller_id})
            await collector

        if "order_created" in events_received:
            ok("收到 order_created 广播")
        else:
            fail("ST-7", "未收到 order_created")

        if "order_cancelled" in events_received:
            ok("收到 order_cancelled 广播")
        else:
            fail("ST-7", "未收到 order_cancelled")

    except Exception as e:
        fail("ST-7 WebSocket", str(e))


# ─── ST-8: 成交日志验证 ───────────────────────────────────────

async def test_trade_logs():
    print("\n=== ST-8: GET /api/market/trade-logs 成交日志 ===")

    r = await CLIENT.get("/api/market/trade-logs")
    if r.status_code != 200:
        fail("ST-8 API", f"status={r.status_code}")
        return

    logs = r.json()
    if not isinstance(logs, list):
        fail("ST-8 格式", f"期望 list, 实际 {type(logs)}")
        return

    if len(logs) == 0:
        fail("ST-8", "成交日志为空（前面 ST-3 应该产生了记录）")
        return

    log = logs[0]
    required = ["id", "order_id", "seller_id", "buyer_id",
                 "sell_type", "sell_amount", "buy_type", "buy_amount", "created_at"]
    missing = [k for k in required if k not in log]
    if missing:
        fail("ST-8 字段缺失", str(missing))
    else:
        ok("成交日志字段完整", f"共 {len(logs)} 条, 最新: order_id={log['order_id']}")


# ─── Main ───────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("M5.2 — 交易市场端到端验证")
    print("=" * 60)

    try:
        r = await CLIENT.get("/api/health")
        if r.status_code != 200:
            print("ERROR: 服务器未启动，请先 uvicorn main:app --port 8001")
            return
    except Exception:
        print("ERROR: 无法连接服务器，请先 uvicorn main:app --port 8001")
        return

    print("[OK] 服务器在线")

    agents = await get_all_agents()
    ST_MODEL = "stepfun/step-3.5-flash"

    bot_agents = [a for a in agents if a["id"] != 0]
    if len(bot_agents) < 2:
        print(f"  Bot Agent 不足（{len(bot_agents)}），自动创建...")
        for name, persona in [("Alice", "热心肠的面包师"), ("Bob", "勤劳的农夫")]:
            existing = [a for a in bot_agents if a["name"] == name]
            if not existing:
                r = await CLIENT.post("/api/agents/", json={
                    "name": name, "persona": persona, "model": ST_MODEL,
                })
                if r.status_code == 201:
                    print(f"  创建 {name} 成功")
        agents = await get_all_agents()
        bot_agents = [a for a in agents if a["id"] != 0]

    if len(bot_agents) < 2:
        print("ERROR: 仍然不足 2 个 Bot Agent")
        return

    seller = bot_agents[0]
    buyer = bot_agents[1]
    print(f"[OK] seller={seller['name']}(id={seller['id']}), buyer={buyer['name']}(id={buyer['id']})")

    # 确保资源充足
    await ensure_flour(seller["id"])
    await ensure_flour(buyer["id"])
    await ensure_wheat(buyer["id"])

    # 执行测试
    order_id = await test_create_order(seller["id"])                    # ST-1
    await test_create_order_insufficient(seller["id"])                  # ST-2
    if order_id:
        await test_accept_order_full(seller["id"], buyer["id"], order_id)  # ST-3
    await test_accept_order_partial(seller["id"], buyer["id"])          # ST-4
    await test_cancel_order(seller["id"])                               # ST-5
    await test_cancel_order_not_owner(seller["id"], buyer["id"])        # ST-6
    await test_ws_market_broadcast(seller["id"])                        # ST-7
    await test_trade_logs()                                             # ST-8

    # 汇总
    print("\n" + "=" * 60)
    print(f"结果: {passed} passed, {failed} failed")
    if errors:
        print("失败项:")
        for e in errors:
            print(f"  - {e}")
    print("=" * 60)

    await CLIENT.aclose()


if __name__ == "__main__":
    asyncio.run(main())
