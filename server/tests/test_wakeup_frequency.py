import pytest

from app.services.wakeup_service import WakeupService
from app.models import Agent, Message


@pytest.fixture
def svc():
    return WakeupService()


# --- record_response / record_no_response ---

def test_record_response_resets_count(svc):
    svc._no_response_count[1] = 3
    svc.record_response(1)
    assert svc._no_response_count[1] == 0


def test_record_no_response_increments(svc):
    assert svc._no_response_count.get(1, 0) == 0
    svc.record_no_response(1)
    assert svc._no_response_count[1] == 1
    svc.record_no_response(1)
    assert svc._no_response_count[1] == 2


def test_record_no_response_from_zero(svc):
    svc.record_no_response(5)
    assert svc._no_response_count[5] == 1


# --- _get_candidates filtering ---

@pytest.mark.asyncio
async def test_get_candidates_filters_high_count(svc, db):
    # Create agents in DB
    for i in [1, 2, 3]:
        agent = Agent(id=i, name=f"agent_{i}", persona="test")
        db.add(agent)
    await db.commit()

    # Agent 1 has count=5 (should be filtered out)
    svc._no_response_count[1] = 5
    svc._no_response_count[2] = 2
    # Agent 3 has no count (defaults to 0)

    candidates = await svc._get_candidates(
        online_agent_ids={1, 2, 3}, exclude_id=0, db=db
    )
    candidate_ids = {a.id for a in candidates}
    assert 1 not in candidate_ids  # filtered: count >= 5
    assert 2 in candidate_ids
    assert 3 in candidate_ids


@pytest.mark.asyncio
async def test_get_candidates_excludes_sender_and_human(svc, db):
    for i in [1, 2]:
        agent = Agent(id=i, name=f"agent_{i}", persona="test")
        db.add(agent)
    await db.commit()

    candidates = await svc._get_candidates(
        online_agent_ids={0, 1, 2}, exclude_id=1, db=db
    )
    candidate_ids = {a.id for a in candidates}
    assert 0 not in candidate_ids  # human excluded
    assert 1 not in candidate_ids  # sender excluded
    assert 2 in candidate_ids


# --- process: human message resets all counts ---

@pytest.mark.asyncio
async def test_human_message_resets_all_counts(svc, db):
    # Setup agents
    for i in [1, 2]:
        agent = Agent(id=i, name=f"agent_{i}", persona="test")
        db.add(agent)
    await db.commit()

    svc._no_response_count[1] = 4
    svc._no_response_count[2] = 3

    # Create a human message
    msg = Message(agent_id=0, sender_type="human", content="hello", message_type="chat")
    db.add(msg)
    await db.commit()

    # process() will try to call the wakeup model, which will fail gracefully
    # The important thing is that counts get reset
    await svc.process(msg, online_agent_ids={1, 2}, db=db)

    assert svc._no_response_count[1] == 0
    assert svc._no_response_count[2] == 0
