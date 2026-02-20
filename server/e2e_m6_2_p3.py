"""
E2E Test — M6.2 Phase 3 悬赏 Agent 自主接取端到端验证

覆盖场景：
  ST-1: POST /bounties/ 创建悬赏 + GET /bounties/ 列表包含
  ST-2: POST /bounties/{id}/claim 接取悬赏成功
  ST-3: DC-8 同时最多 1 个悬赏 — 已有进行中时接取第二个被拒
  ST-4: CAS 先到先得 — 已被接取的悬赏再次接取返回 409
  ST-5: POST /bounties/{id}/complete 完成悬赏 + credits 增加

用法: python e2e_m6_2_p3.py
"""
import asyncio
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8001")
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


# ─── ST-1: 创建悬赏 + 列表 ───────────────────────────────────────

async def test_create_and_list() -> int | None:
    print("\n=== ST-1: 创建悬赏 + 列表 ===")

    r = await CLIENT.post("/api/bounties/", json={"title": "修复登录Bug", "reward": 50})
    if r.status_code != 201:
        fail("创建悬赏", f"status={r.status_code} body={r.text}")
        return None

    bounty = r.json()
    bounty_id = bounty["id"]
    ok("创建悬赏成功", f"id={bounty_id} title={bounty['title']} reward={bounty['reward']}")

    # 列表包含
    r2 = await CLIENT.get("/api/bounties/")
    items = r2.json()
    found = any(b["id"] == bounty_id for b in items)
    if found:
        ok("列表包含新悬赏")
    else:
        fail("列表不包含新悬赏", f"bounty_id={bounty_id}")

    return bounty_id


# ─── ST-2: 接取悬赏成功 ──────────────────────────────────────────

async def test_claim_bounty(bounty_id: int, agent_id: int) -> bool:
    print("\n=== ST-2: 接取悬赏成功 ===")

    r = await CLIENT.post(f"/api/bounties/{bounty_id}/claim?agent_id={agent_id}")
    if r.status_code != 200:
        fail("接取悬赏", f"status={r.status_code} body={r.text}")
        return False

    data = r.json()
    if data["status"] == "claimed" and data["claimed_by"] == agent_id:
        ok("接取悬赏成功", f"bounty_id={bounty_id} claimed_by={agent_id}")
        return True
    else:
        fail("接取悬赏状态异常", f"data={data}")
        return False


# ─── ST-3: DC-8 同时最多 1 个悬赏 ────────────────────────────────

async def test_dc8_one_active(agent_id: int):
    print("\n=== ST-3: DC-8 同时最多 1 个悬赏 ===")

    # 创建第二个悬赏
    r = await CLIENT.post("/api/bounties/", json={"title": "优化性能", "reward": 80})
    if r.status_code != 201:
        fail("创建第二个悬赏", f"status={r.status_code}")
        return

    bounty2_id = r.json()["id"]

    # 同一 agent 接取第二个 → 应被拒绝
    r2 = await CLIENT.post(f"/api/bounties/{bounty2_id}/claim?agent_id={agent_id}")
    if r2.status_code == 409:
        ok("DC-8 拒绝接取第二个悬赏", f"status=409")
    else:
        fail("DC-8 未拦住", f"status={r2.status_code} body={r2.text}")


# ─── ST-4: CAS 先到先得 ──────────────────────────────────────────

async def test_cas_conflict(agent2_id: int):
    print("\n=== ST-4: CAS 先到先得 ===")

    # 创建一个新悬赏
    r = await CLIENT.post("/api/bounties/", json={"title": "写测试", "reward": 30})
    if r.status_code != 201:
        fail("创建悬赏", f"status={r.status_code}")
        return

    bounty_id = r.json()["id"]

    # agent2 接取
    r2 = await CLIENT.post(f"/api/bounties/{bounty_id}/claim?agent_id={agent2_id}")
    if r2.status_code != 200:
        fail("agent2 接取悬赏", f"status={r2.status_code} body={r2.text}")
        return

    ok("agent2 接取成功", f"bounty_id={bounty_id}")

    # 创建 agent3（或用另一个 agent）再次接取同一悬赏 → 应失败
    # 先确保有第三个 agent
    agents = (await CLIENT.get("/api/agents/")).json()
    bot_agents = [a for a in agents if a["id"] != 0]
    if len(bot_agents) < 3:
        r3 = await CLIENT.post("/api/agents/", json={
            "name": "Charlie", "persona": "好奇的探险家", "model": "stepfun/step-3.5-flash",
        })
        if r3.status_code == 201:
            agent3_id = r3.json()["id"]
        else:
            fail("创建 agent3", f"status={r3.status_code}")
            return
    else:
        agent3_id = [a for a in bot_agents if a["id"] != agent2_id][0]["id"]

    r4 = await CLIENT.post(f"/api/bounties/{bounty_id}/claim?agent_id={agent3_id}")
    if r4.status_code == 409:
        ok("CAS 拒绝重复接取", f"agent3_id={agent3_id} status=409")
    else:
        fail("CAS 未拦住", f"status={r4.status_code} body={r4.text}")


# ─── ST-5: 完成悬赏 + credits 增加 ───────────────────────────────

async def test_complete_bounty(bounty_id: int, agent_id: int):
    print("\n=== ST-5: 完成悬赏 + credits 增加 ===")

    # 先记录 agent 当前 credits
    agent_r = await CLIENT.get(f"/api/agents/")
    agents = agent_r.json()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        fail("找不到 agent", f"agent_id={agent_id}")
        return

    credits_before = agent["credits"]

    # 获取悬赏 reward
    bounties = (await CLIENT.get("/api/bounties/")).json()
    bounty = next((b for b in bounties if b["id"] == bounty_id), None)
    if not bounty:
        fail("找不到悬赏", f"bounty_id={bounty_id}")
        return

    reward = bounty["reward"]

    # 完成悬赏
    r = await CLIENT.post(f"/api/bounties/{bounty_id}/complete?agent_id={agent_id}")
    if r.status_code != 200:
        fail("完成悬赏", f"status={r.status_code} body={r.text}")
        return

    data = r.json()
    if data["status"] != "completed":
        fail("完成后状态异常", f"status={data['status']}")
        return

    ok("悬赏完成", f"bounty_id={bounty_id} status=completed")

    # 验证 credits 增加
    agent_r2 = await CLIENT.get(f"/api/agents/")
    agent2 = next((a for a in agent_r2.json() if a["id"] == agent_id), None)
    credits_after = agent2["credits"]

    if credits_after == credits_before + reward:
        ok("credits 正确增加", f"{credits_before} + {reward} = {credits_after}")
    else:
        fail("credits 不正确", f"before={credits_before} reward={reward} after={credits_after}")


# ─── Main ────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("M6.2 Phase 3 — 悬赏 Agent 自主接取端到端验证")
    print("=" * 60)

    async with __import__("server_utils").managed_server():
        await _run()


async def _run():
    # 确保有至少 2 个 bot agent
    agents = (await CLIENT.get("/api/agents/")).json()
    bot_agents = [a for a in agents if a["id"] != 0]

    if len(bot_agents) < 2:
        print(f"  Bot Agent 不足（{len(bot_agents)}），自动创建...")
        for name, persona in [("Alice", "勤劳的农夫"), ("Bob", "精明的商人")]:
            if not any(a["name"] == name for a in bot_agents):
                r = await CLIENT.post("/api/agents/", json={
                    "name": name, "persona": persona, "model": "stepfun/step-3.5-flash",
                })
                if r.status_code == 201:
                    print(f"  创建 {name} 成功")
        agents = (await CLIENT.get("/api/agents/")).json()
        bot_agents = [a for a in agents if a["id"] != 0]

    if len(bot_agents) < 2:
        print("ERROR: 仍然不足 2 个 Bot Agent")
        return

    agent1_id = bot_agents[0]["id"]
    agent2_id = bot_agents[1]["id"]
    print(f"[OK] 使用 agent1={bot_agents[0]['name']}(id={agent1_id}), agent2={bot_agents[1]['name']}(id={agent2_id})")

    # 执行测试
    bounty_id = await test_create_and_list()                    # ST-1
    if bounty_id:
        claimed = await test_claim_bounty(bounty_id, agent1_id) # ST-2
        if claimed:
            await test_dc8_one_active(agent1_id)                # ST-3
            await test_complete_bounty(bounty_id, agent1_id)    # ST-5
    await test_cas_conflict(agent2_id)                          # ST-4

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
