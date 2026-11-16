#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成一段"真跑"的演示记录，用来给客户看，也给录屏当脚本。

不是截图，不是 PPT：每一步都是子进程真起的 MCP 服务真回的包。
输出：demo/transcript-YYYYMMDD.md
"""

import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server.py")
CONFIG = os.path.join(HERE, "config.json")
DEMO = os.path.join(HERE, "demo")
os.makedirs(DEMO, exist_ok=True)


def run_session(steps):
    """跑一段 stdio 会话，返回 [(label, request, response)]。"""
    proc = subprocess.Popen([sys.executable, SERVER, "--config", CONFIG],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=HERE)
    out = []
    for label, msg in steps:
        proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        proc.stdin.flush()
        if msg.get("id") is None:
            out.append((label, msg, None))
            continue
        line = proc.stdout.readline()
        out.append((label, msg, json.loads(line.decode("utf-8")) if line else None))
    proc.stdin.close()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    return out


def brief(resp, limit=900):
    if resp is None:
        return "(no response)"
    text = json.dumps(resp, ensure_ascii=False, indent=2)
    return text if len(text) <= limit else text[:limit] + "\n  ... (truncated)"


def main():
    steps = [
        ("握手", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                             "clientInfo": {"name": "demo", "version": "1"}}}),
        ("初始化通知", {"jsonrpc": "2.0", "method": "notifications/initialized"}),
        ("列出工具", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ("看有哪些模型", {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "bridge_models", "arguments": {}}}),
        ("算一笔钱", {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                      "params": {"name": "bridge_cost",
                                 "arguments": {"provider": "deepseek", "model": "deepseek-chat",
                                               "tokens_in": 120000, "tokens_out": 30000}}}),
        ("真调一次（无 key 时降级 mock）", {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                            "params": {"name": "bridge_chat",
                                                       "arguments": {"provider": "local",
                                                                     "prompt": "只回四个字：链路已通",
                                                                     "max_tokens": 24}}}),
        ("看账", {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                  "params": {"name": "bridge_usage", "arguments": {"days": 1}}}),
    ]

    results = run_session(steps)

    report = subprocess.run([sys.executable, SERVER, "--config", CONFIG, "--report", "7"],
                            capture_output=True, text=True, encoding="utf-8", cwd=HERE)

    md = []
    md.append("# mcp-bridge 演示记录（真实会话）\n")
    md.append("生成时间：%s  \n环境：Windows / Python %s  \n服务：%s\n"
              % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), sys.version.split()[0], SERVER))
    md.append("下面每一段都是子进程真起的 MCP 服务真回的包，没有手写、没有截图。\n")

    for label, req, resp in results:
        md.append("## %s\n" % label)
        md.append("```json")
        md.append("# 客户端 -> 服务端")
        md.append(json.dumps(req, ensure_ascii=False, indent=2))
        if resp is not None:
            md.append("")
            md.append("# 服务端 -> 客户端")
            md.append(brief(resp, limit=600))
        md.append("```\n")
        # 把模型真正返回的那句话单独拎出来，别淹在协议 JSON 里
        if resp is not None:
            try:
                payload = json.loads(resp["result"]["content"][0]["text"])
                if "text" in payload:
                    md.append("**模型实际输出**：`%s`  （mock=%s, 延迟 %sms）\n"
                              % (payload["text"].splitlines()[0][:120], payload.get("mock"), payload.get("latency_ms")))
            except Exception:
                pass

    md.append("## 命令行看账\n")
    md.append("```")
    md.append((report.stdout or "").strip() or "(no output)")
    md.append("```\n")
    md.append("> 真调那一步在有 key 或本机 ollama 在跑时返回真实模型输出；否则明确标注 mock —— 不假装成功。\n")

    path = os.path.join(DEMO, "transcript-%s.md" % datetime.date.today().strftime("%Y%m%d"))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))

    expected = sum(1 for _, _, r in results if True) - sum(1 for label, req, _ in results if req.get("id") is None)
    ok = sum(1 for _, _, r in results if r is not None and "error" not in r)
    print("steps=%d expected_responses=%d ok=%d" % (len(results), expected, ok))
    print("->", path)
    return 0 if ok == expected else 1


if __name__ == "__main__":
    sys.exit(main())
