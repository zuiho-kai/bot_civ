"""M1 Task #1 冒烟测试：Agent CRUD + WebSocket 聊天"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.core.database import engine, Base
from main import app, ensure_human_agent


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_db():
    """每个测试前重建数据库"""
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


# --- Health ---
@pytest.mark.anyio
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --- Human Agent 自动初始化 ---
@pytest.mark.anyio
async def test_human_agent_exists(client):
    r = await client.get("/api/agents/0")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == 0
    assert data["name"] == "Human"


# --- Agent CRUD ---
@pytest.mark.anyio
async def test_create_agent(client):
    r = await client.post("/api/agents/", json={
        "name": "Alice",
        "persona": "乐观开朗的程序员",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Alice"
    assert data["credits"] == 100
    assert data["daily_free_quota"] == 10
    assert data["quota_used_today"] == 0


@pytest.mark.anyio
async def test_create_duplicate_name(client):
    await client.post("/api/agents/", json={"name": "Bob", "persona": "test"})
    r = await client.post("/api/agents/", json={"name": "Bob", "persona": "test2"})
    assert r.status_code == 409


@pytest.mark.anyio
async def test_create_invalid_name(client):
    r = await client.post("/api/agents/", json={"name": "bad name!", "persona": "test"})
    assert r.status_code == 422


@pytest.mark.anyio
async def test_list_agents_excludes_human(client):
    await client.post("/api/agents/", json={"name": "Charlie", "persona": "test"})
    r = await client.get("/api/agents/")
    assert r.status_code == 200
    ids = [a["id"] for a in r.json()]
    assert 0 not in ids


@pytest.mark.anyio
async def test_update_agent(client):
    cr = await client.post("/api/agents/", json={"name": "Dave", "persona": "old"})
    aid = cr.json()["id"]
    r = await client.put(f"/api/agents/{aid}", json={"persona": "new persona"})
    assert r.status_code == 200
    assert r.json()["persona"] == "new persona"


@pytest.mark.anyio
async def test_update_human_forbidden(client):
    r = await client.put("/api/agents/0", json={"persona": "hacked"})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_delete_agent(client):
    cr = await client.post("/api/agents/", json={"name": "Eve", "persona": "temp"})
    aid = cr.json()["id"]
    r = await client.delete(f"/api/agents/{aid}")
    assert r.status_code == 204
    r2 = await client.get(f"/api/agents/{aid}")
    assert r2.status_code == 404


@pytest.mark.anyio
async def test_delete_human_forbidden(client):
    r = await client.delete("/api/agents/0")
    assert r.status_code == 403


# --- Messages ---
@pytest.mark.anyio
async def test_get_messages_empty(client):
    r = await client.get("/api/messages")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
