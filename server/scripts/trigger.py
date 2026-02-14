#!/usr/bin/env python3
"""
模拟消息触发器 CLI

用法:
  python scripts/trigger.py "你好，大家好"
  python scripts/trigger.py "@小明 介绍一下自己" --sender Human
  python scripts/trigger.py "我来分析一下" --sender Alice
  python scripts/trigger.py --batch  # 运行预设的测试序列
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api"


def trigger(content: str, sender: str = "Human", message_type: str = "chat"):
    data = json.dumps({
        "content": content,
        "sender": sender,
        "message_type": message_type,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/dev/trigger",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            print(f"[OK] msg#{result['message_id']} {result['sender']}: {result['content']}")
            if result["mentions"]:
                print(f"     mentions: {result['mentions']}")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[ERR] {e.code}: {body}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"[ERR] 连接失败: {e.reason}", file=sys.stderr)
        print("     请确认后端已启动 (uvicorn)", file=sys.stderr)
        return None


BATCH_SEQUENCE = [
    ("Human", "大家好，今天来讨论一下项目进展"),
    ("Human", "@小明 你负责的模块进展如何？"),
    ("Human", "有没有遇到什么问题？"),
]


def run_batch(delay: float = 3.0):
    print(f"=== 批量测试模式 ({len(BATCH_SEQUENCE)} 条消息, 间隔 {delay}s) ===\n")
    for i, (sender, content) in enumerate(BATCH_SEQUENCE):
        print(f"--- [{i+1}/{len(BATCH_SEQUENCE)}] ---")
        trigger(content, sender)
        if i < len(BATCH_SEQUENCE) - 1:
            print(f"     等待 {delay}s...\n")
            time.sleep(delay)
    print("\n=== 批量测试完成 ===")


def main():
    parser = argparse.ArgumentParser(description="OpenClaw 模拟消息触发器")
    parser.add_argument("content", nargs="?", help="消息内容")
    parser.add_argument("--sender", default="Human", help="发送者名称 (默认: Human)")
    parser.add_argument("--type", dest="message_type", default="chat", help="消息类型 (默认: chat)")
    parser.add_argument("--batch", action="store_true", help="运行预设测试序列")
    parser.add_argument("--delay", type=float, default=3.0, help="批量模式消息间隔秒数 (默认: 3)")
    args = parser.parse_args()

    if args.batch:
        run_batch(args.delay)
    elif args.content:
        trigger(args.content, args.sender, args.message_type)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
