#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""真实上游调用验证：走 bridge 打本机 ollama，确认非 mock 分支可用。"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import server

cfg = server.Config(os.path.join(HERE, "config.json"))
cfg.providers["local"]["models"] = ["qwen2.5vl:3b"]
cfg.providers["local"]["timeout"] = 180

print("== real upstream call (local ollama, not mock) ==")
out = server.do_chat(cfg, {"provider": "local", "prompt": "只回四个字：链路已通", "max_tokens": 24, "temperature": 0})
print("TEXT    :", repr(out.get("text"))[:300])
print("MODEL   :", out.get("model"), "| MOCK:", out.get("mock", False), "| LATENCY:", out.get("latency_ms"), "ms")
print("USAGE   :", out.get("usage"))
print("COST    :", out.get("cost_cny"))
