#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""mcp-bridge 冒烟测试：真起子进程，走 stdio，按 MCP 顺序握手并调工具。

跑法：
    .venv\\Scripts\\python.exe test_stdio.py      （venv 不是必须的，零依赖）
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server.py")
CONFIG = os.path.join(HERE, "config.json")


def main():
    proc = subprocess.Popen(
        [sys.executable, SERVER, "--config", CONFIG],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=HERE,
    )

    def rpc(msg, expect_id=True):
        proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        proc.stdin.flush()
        if not expect_id:
            return None
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout")
        return json.loads(line.decode("utf-8"))

    checks = []

    r = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "smoke", "version": "1"}}})
    info = (r.get("result") or {}).get("serverInfo") or {}
    checks.append(("initialize", bool(info.get("name")), info.get("name")))

    rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_id=False)

    r = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = [(r.get("result") or {}).get("tools") or []]
    names = [t["name"] for t in tools[0]]
    checks.append(("tools/list",
                   names == ["bridge_chat", "bridge_models", "bridge_cost", "bridge_usage"],
                   ",".join(names)))

    r = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "bridge_models", "arguments": {}}})
    payload = json.loads(r["result"]["content"][0]["text"])
    checks.append(("bridge_models", payload.get("count", 0) >= 3, "providers=%s" % payload.get("count")))

    r = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "bridge_chat",
                        "arguments": {"provider": "deepseek", "prompt": "用一句话说明你的省钱逻辑"}}})
    chat = json.loads(r["result"]["content"][0]["text"])
    checks.append(("bridge_chat", bool(chat.get("text")), "mock=%s cost=%s" % (chat.get("mock"), chat.get("cost_cny"))))

    r = rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
             "params": {"name": "bridge_cost",
                        "arguments": {"provider": "deepseek", "model": "deepseek-chat",
                                      "tokens_in": 120000, "tokens_out": 30000}}})
    cost = json.loads(r["result"]["content"][0]["text"])
    checks.append(("bridge_cost", cost.get("cost_cny") == 0.48, "cost=%s" % cost.get("cost_cny")))

    r = rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
             "params": {"name": "bridge_chat", "arguments": {"provider": "nope", "prompt": "x"}}})
    err = (r.get("result") or {}).get("isError") is True
    checks.append(("error path", err, "unknown provider -> isError"))

    # 用量账本：前面已经打过一次 chat，这里必须能看到至少 1 条记录
    r = rpc({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
             "params": {"name": "bridge_usage", "arguments": {"days": 1}}})
    usage = json.loads(r["result"]["content"][0]["text"])
    checks.append(("bridge_usage", usage.get("total_calls", 0) >= 1,
                   "calls=%s cost=%s" % (usage.get("total_calls"), usage.get("total_cost_cny"))))

    rpc({"jsonrpc": "2.0", "id": 7, "method": "shutdown"}, expect_id=False) if False else None

    proc.stdin.close()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    print("")
    ok = 0
    for name, passed, detail in checks:
        print(("  PASS  " if passed else "  FAIL  ") + name.ljust(16) + str(detail))
        ok += 1 if passed else 0
    print("")
    print("%d/%d passed" % (ok, len(checks)))
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
