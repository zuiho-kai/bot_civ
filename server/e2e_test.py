"""E2E test: connect as human, send message, wait for agent reply."""
import asyncio
import json
import websockets

async def main():
    uri = "ws://localhost:8000/api/ws/0"  # agent_id=0 = human
    async with websockets.connect(uri) as ws:
        # Wait for online event
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print(f"[recv] {msg}")

        # Send a human message
        payload = {"type": "chat_message", "content": "大家好呀，今天天气真不错！有人想出去玩吗？"}
        await ws.send(json.dumps(payload, ensure_ascii=False))
        print(f"[sent] {payload['content']}")

        # Wait for responses (broadcast of our msg + agent reply)
        for i in range(10):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=60)
                data = json.loads(msg)
                print(f"[recv #{i}] type={data.get('type')}", end="")
                if data.get("type") == "new_message":
                    d = data["data"]
                    print(f"  sender={d['sender_type']} agent={d['agent_name']}: {d['content']}")
                elif data.get("type") == "ping":
                    print("  (heartbeat)")
                else:
                    print(f"  {json.dumps(data, ensure_ascii=False)[:200]}")
            except asyncio.TimeoutError:
                print(f"\n[timeout] No more messages after 30s")
                break

        print("\n--- Done ---")

asyncio.run(main())
