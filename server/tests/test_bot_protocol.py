"""M1.5 冒烟测试：Bot WebSocket 协议 + 认证 + since_id + 心跳"""
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient
from app.core.database import engine, Base
from main import app, ensure_human_agent


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _reset_db_sync():
    """同步重建数据库"""
    async def _do():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await ensure_human_agent()
    asyncio.run(_do())


def _teardown_db_sync():
    async def _do():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    asyncio.run(_do())


# --- Async fixtures (for async tests) ---
@pytest.fixture
async def async_setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await ensure_human_agent()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(async_setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def bot_agent(client):
    r = await client.post("/api/agents/", json={"name": "TestBot", "persona": "测试机器人"})
    data = r.json()
    return data["id"], data["bot_token"]


# --- Sync fixtures (for WebSocket tests) ---
@pytest.fixture
def sync_setup():
    _reset_db_sync()
    yield
    _teardown_db_sync()


@pytest.fixture
def sync_client(sync_setup):
    return TestClient(app)


@pytest.fixture
def bot_agent_sync(sync_client):
    r = sync_client.post("/api/agents/", json={"name": "SyncBot", "persona": "同步测试"})
    data = r.json()
    return data["id"], data["bot_token"], sync_client


# --- Bot Token 生成 ---
@pytest.mark.anyio
async def test_bot_token_generated_on_create(client):
    r = await client.post("/api/agents/", json={"name": "TokenBot", "persona": "test"})
    data = r.json()
    assert data["bot_token"] is not None
    assert data["bot_token"].startswith("oc_")
    assert len(data["bot_token"]) == 51  # "oc_" + 48 hex chars


@pytest.mark.anyio
async def test_human_agent_no_token(client):
    r = await client.get("/api/agents/0")
    data = r.json()
    assert data["bot_token"] is None


@pytest.mark.anyio
async def test_regenerate_token(client, bot_agent):
    aid, old_token = bot_agent
    r = await client.post(f"/api/agents/{aid}/regenerate-token")
    assert r.status_code == 200
    new_token = r.json()["bot_token"]
    assert new_token != old_token
    assert new_token.startswith("oc_")


@pytest.mark.anyio
async def test_regenerate_token_human_forbidden(client):
    r = await client.post("/api/agents/0/regenerate-token")
    assert r.status_code == 403


# --- Bot WebSocket 认证 ---
def test_bot_ws_no_token_rejected(sync_client):
    """Bot 连接不带 token → accept 后立即 close(4003)"""
    with sync_client.websocket_connect("/api/ws/99") as ws:
        pass  # 连接被关闭是预期行为


def test_bot_ws_invalid_token_rejected(bot_agent_sync):
    """Bot 连接带错误 token → accept 后立即 close(4003)"""
    aid, _, sync_client = bot_agent_sync
    with sync_client.websocket_connect(f"/api/ws/{aid}?token=wrong_token") as ws:
        pass


def test_bot_ws_valid_token_connects(bot_agent_sync):
    """Bot 带正确 token 可以连接并收到上线事件"""
    aid, token, sync_client = bot_agent_sync
    with sync_client.websocket_connect(f"/api/ws/{aid}?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "system_event"
        assert msg["data"]["event"] == "agent_online"
        assert msg["data"]["agent_id"] == aid


def test_human_ws_no_token_needed(sync_client):
    """Human (id=0) 连接不需要 token"""
    with sync_client.websocket_connect("/api/ws/0") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "system_event"
        assert msg["data"]["event"] == "agent_online"
        assert msg["data"]["agent_id"] == 0


# --- Bot 发消息 ---
def test_bot_sends_message(bot_agent_sync):
    """Bot 通过 WebSocket 发消息，消息被广播"""
    aid, token, sync_client = bot_agent_sync
    with sync_client.websocket_connect(f"/api/ws/{aid}?token={token}") as ws:
        ws.receive_json()  # 上线事件
        ws.send_json({"type": "chat_message", "content": "Hello from bot!"})
        msg = ws.receive_json()
        assert msg["type"] == "new_message"
        assert msg["data"]["agent_id"] == aid
        assert msg["data"]["content"] == "Hello from bot!"
        assert msg["data"]["sender_type"] == "agent"


# --- 心跳 pong ---
def test_bot_pong_ignored(bot_agent_sync):
    """Bot 发 pong 不影响正常消息流"""
    aid, token, sync_client = bot_agent_sync
    with sync_client.websocket_connect(f"/api/ws/{aid}?token={token}") as ws:
        ws.receive_json()  # 上线事件
        ws.send_json({"type": "pong"})
        ws.send_json({"type": "chat_message", "content": "after pong"})
        msg = ws.receive_json()
        assert msg["type"] == "new_message"
        assert msg["data"]["content"] == "after pong"


# --- since_id 增量拉取 ---
def test_since_id_incremental_fetch(bot_agent_sync):
    """since_id 参数返回增量消息"""
    aid, token, sync_client = bot_agent_sync

    # 发 3 条消息
    with sync_client.websocket_connect(f"/api/ws/{aid}?token={token}") as ws:
        ws.receive_json()  # 上线
        for i in range(3):
            ws.send_json({"type": "chat_message", "content": f"msg-{i}"})
            ws.receive_json()  # 收广播

    # 拉全部消息（默认按时间升序返回）
    r = sync_client.get("/api/messages?limit=50")
    all_msgs = r.json()
    assert len(all_msgs) >= 3

    # 用 since_id 拉增量（取最小 id）
    first_id = min(m["id"] for m in all_msgs)
    r2 = sync_client.get(f"/api/messages?since_id={first_id}")
    incremental = r2.json()
    assert all(m["id"] > first_id for m in incremental)
    assert len(incremental) == len(all_msgs) - 1
