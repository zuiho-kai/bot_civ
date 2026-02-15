"""M2-8 悬赏任务 API 集成测试：通过 HTTP 端点验证完整流程"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.core.database import engine, Base
from main import app, ensure_human_agent


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await ensure_human_agent()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_agent(client, name="Alice") -> dict:
    r = await client.post("/api/agents/", json={"name": name, "persona": "test persona"})
    assert r.status_code == 201
    return r.json()


# --- 创建悬赏 ---

@pytest.mark.anyio
async def test_create_bounty(client):
    r = await client.post("/api/bounties/", json={
        "title": "Fix login bug",
        "description": "Login page crashes on mobile",
        "reward": 50,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Fix login bug"
    assert data["reward"] == 50
    assert data["status"] == "open"
    assert data["claimed_by"] is None


@pytest.mark.anyio
async def test_create_bounty_reward_zero_rejected(client):
    r = await client.post("/api/bounties/", json={
        "title": "Bad", "reward": 0,
    })
    assert r.status_code == 422


@pytest.mark.anyio
async def test_create_bounty_reward_negative_rejected(client):
    r = await client.post("/api/bounties/", json={
        "title": "Bad", "reward": -10,
    })
    assert r.status_code == 422


# --- 列表查询 ---

@pytest.mark.anyio
async def test_list_bounties_all(client):
    await client.post("/api/bounties/", json={"title": "A", "reward": 10})
    await client.post("/api/bounties/", json={"title": "B", "reward": 20})
    r = await client.get("/api/bounties/")
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.anyio
async def test_list_bounties_filter_by_status(client):
    await client.post("/api/bounties/", json={"title": "A", "reward": 10})
    await client.post("/api/bounties/", json={"title": "B", "reward": 20})

    # Claim one
    agent = await _create_agent(client, "Claimer")
    bounties = (await client.get("/api/bounties/")).json()
    bid = bounties[0]["id"]
    await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": agent["id"]})

    # Filter open only
    r = await client.get("/api/bounties/", params={"status": "open"})
    assert r.status_code == 200
    open_bounties = r.json()
    assert len(open_bounties) == 1
    assert all(b["status"] == "open" for b in open_bounties)


# --- 接取悬赏 ---

@pytest.mark.anyio
async def test_claim_bounty(client):
    agent = await _create_agent(client)
    br = await client.post("/api/bounties/", json={"title": "Task", "reward": 30})
    bid = br.json()["id"]

    r = await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": agent["id"]})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "claimed"
    assert data["claimed_by"] == agent["id"]


@pytest.mark.anyio
async def test_claim_already_claimed_bounty_409(client):
    agent1 = await _create_agent(client, "Agent1")
    agent2 = await _create_agent(client, "Agent2")
    br = await client.post("/api/bounties/", json={"title": "Task", "reward": 30})
    bid = br.json()["id"]

    # First claim succeeds
    r1 = await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": agent1["id"]})
    assert r1.status_code == 200

    # Second claim → 409
    r2 = await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": agent2["id"]})
    assert r2.status_code == 409


@pytest.mark.anyio
async def test_claim_nonexistent_bounty_404(client):
    agent = await _create_agent(client)
    r = await client.post("/api/bounties/9999/claim", params={"agent_id": agent["id"]})
    assert r.status_code == 404


@pytest.mark.anyio
async def test_claim_nonexistent_agent_404(client):
    br = await client.post("/api/bounties/", json={"title": "Task", "reward": 30})
    bid = br.json()["id"]
    r = await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": 9999})
    assert r.status_code == 404


# --- 完成悬赏 ---

@pytest.mark.anyio
async def test_complete_bounty_credits_awarded(client):
    agent = await _create_agent(client)
    initial_credits = agent["credits"]

    br = await client.post("/api/bounties/", json={"title": "Task", "reward": 50})
    bid = br.json()["id"]

    # Claim then complete
    await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": agent["id"]})
    r = await client.post(f"/api/bounties/{bid}/complete", params={"agent_id": agent["id"]})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None

    # Verify credits increased
    ar = await client.get(f"/api/agents/{agent['id']}")
    assert ar.json()["credits"] == initial_credits + 50


@pytest.mark.anyio
async def test_complete_by_wrong_agent_403(client):
    agent1 = await _create_agent(client, "Agent1")
    agent2 = await _create_agent(client, "Agent2")

    br = await client.post("/api/bounties/", json={"title": "Task", "reward": 30})
    bid = br.json()["id"]

    await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": agent1["id"]})

    # Agent2 tries to complete agent1's bounty → 403
    r = await client.post(f"/api/bounties/{bid}/complete", params={"agent_id": agent2["id"]})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_complete_open_bounty_409(client):
    agent = await _create_agent(client)
    br = await client.post("/api/bounties/", json={"title": "Task", "reward": 30})
    bid = br.json()["id"]

    # Try to complete without claiming first → 409
    r = await client.post(f"/api/bounties/{bid}/complete", params={"agent_id": agent["id"]})
    assert r.status_code == 409


@pytest.mark.anyio
async def test_complete_already_completed_bounty_409(client):
    agent = await _create_agent(client)
    br = await client.post("/api/bounties/", json={"title": "Task", "reward": 30})
    bid = br.json()["id"]

    await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": agent["id"]})
    await client.post(f"/api/bounties/{bid}/complete", params={"agent_id": agent["id"]})

    # Try to complete again → 409
    r = await client.post(f"/api/bounties/{bid}/complete", params={"agent_id": agent["id"]})
    assert r.status_code == 409


@pytest.mark.anyio
async def test_complete_nonexistent_bounty_404(client):
    agent = await _create_agent(client)
    r = await client.post("/api/bounties/9999/complete", params={"agent_id": agent["id"]})
    assert r.status_code == 404


# --- Review 补充用例 ---

@pytest.mark.anyio
async def test_create_bounty_empty_title_rejected(client):
    r = await client.post("/api/bounties/", json={"title": "   ", "reward": 10})
    assert r.status_code == 422


@pytest.mark.anyio
async def test_create_bounty_title_too_long_rejected(client):
    r = await client.post("/api/bounties/", json={"title": "A" * 129, "reward": 10})
    assert r.status_code == 422


@pytest.mark.anyio
async def test_create_bounty_reward_too_large_rejected(client):
    r = await client.post("/api/bounties/", json={"title": "Big", "reward": 10001})
    assert r.status_code == 422


@pytest.mark.anyio
async def test_list_bounties_invalid_status_422(client):
    r = await client.get("/api/bounties/", params={"status": "bogus"})
    assert r.status_code == 422


@pytest.mark.anyio
async def test_claim_completed_bounty_409(client):
    agent = await _create_agent(client)
    br = await client.post("/api/bounties/", json={"title": "Task", "reward": 30})
    bid = br.json()["id"]

    await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": agent["id"]})
    await client.post(f"/api/bounties/{bid}/complete", params={"agent_id": agent["id"]})

    # Try to claim a completed bounty → 409
    r = await client.post(f"/api/bounties/{bid}/claim", params={"agent_id": agent["id"]})
    assert r.status_code == 409
