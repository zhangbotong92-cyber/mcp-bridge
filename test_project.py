#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按项目的成本分账验证：这是客户最愿意为它付钱的特性之一。

跑法：python test_project.py
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server.py")
CONFIG = os.path.join(HERE, "config.json")


def main():
    proc = subprocess.Popen([sys.executable, SERVER, "--config", CONFIG],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=HERE)

    def rpc(msg):
        proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        proc.stdin.flush()
        line = proc.stdout.readline()
        return json.loads(line.decode("utf-8")) if line else None

    rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
    proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode("utf-8"))
    proc.stdin.flush()

    # 两个项目各打一次（无 key -> mock，但账照记）
    for i, proj in enumerate(["ACME-官网", "BETA-客服"], start=2):
        rpc({"jsonrpc": "2.0", "id": i, "method": "tools/call",
             "params": {"name": "bridge_chat",
                        "arguments": {"provider": "deepseek", "prompt": "项目 %s 的一次调用" % proj, "project": proj}}})

    r = rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
             "params": {"name": "bridge_usage", "arguments": {"days": 1, "group_by": "project"}}})
    rep = json.loads(r["result"]["content"][0]["text"])

    proc.stdin.close()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    print("group_by:", rep.get("group_by"), " rows:", len(rep.get("rows") or []))
    for row in rep.get("rows") or []:
        print("  %-12s calls=%s tokens=%s" % (row["key"], row["calls"], row["tokens_in"] + row["tokens_out"]))

    keys = {row["key"] for row in rep.get("rows") or []}
    ok = rep.get("group_by") == "project" and {"ACME-官网", "BETA-客服"}.issubset(keys)
    print("")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
