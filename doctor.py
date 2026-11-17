#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""环境体检：一条命令弄清"为什么装不上"。

这是陪跑包里最省时间的一步——把客户的机器状态一次性照出来，
省掉"你说的现象我复现不了"那一轮对话。

跑法：
    python server.py --doctor
    python server.py --doctor --json
"""

import json
import os
import socket
import sys
import time
import urllib.parse
import urllib.request

OK, WARN, FAIL = "OK", "WARN", "FAIL"


def _tcp(url, timeout=3.0):
    try:
        p = urllib.parse.urlparse(url)
        host = p.hostname
        port = p.port or (443 if p.scheme == "https" else 80)
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True, "TCP %s:%s 可达" % (host, port)
    except Exception as exc:
        return False, "TCP 不可达: %s" % exc


def _models(provider, timeout=5.0):
    base = (provider.get("base_url") or "").rstrip("/")
    if not base:
        return False, "base_url 未配置", []
    headers = {"Accept": "application/json"}
    key = os.environ.get(provider.get("api_key_env") or "", "")
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        req = urllib.request.Request(base + "/models", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        return True, "返回 %d 个模型" % len(ids), ids
    except Exception as exc:
        return False, "%s" % str(exc)[:90], []


def run(cfg):
    checks = []

    def add(name, level, detail):
        checks.append({"name": name, "level": level, "detail": detail})

    # 1. 运行时
    v = sys.version_info
    add("python", OK if v >= (3, 8) else FAIL, "%d.%d.%d" % (v[0], v[1], v[2]))

    # 2. 配置文件
    if cfg.path and os.path.isfile(cfg.path):
        add("config", OK, cfg.path)
    else:
        add("config", WARN, "未找到配置文件，全部走 mock：%s" % (cfg.path or "(none)"))

    # 3. 账本
    try:
        import sqlite3
        c = sqlite3.connect(cfg.db_path)
        c.execute("SELECT count(*) FROM calls")
        c.close()
        add("usage-db", OK, "%s 可写" % os.path.basename(cfg.db_path))
    except Exception as exc:
        add("usage-db", FAIL, str(exc)[:90])

    # 4. 每个 provider
    for name in sorted(cfg.providers):
        p = cfg.providers[name]
        key_env = p.get("api_key_env") or ""
        needs_key = bool(key_env)
        has_key = bool(os.environ.get(key_env, "")) if key_env else True

        if needs_key and not has_key:
            add("provider:%s" % name, WARN, "缺少环境变量 %s（会降级 mock）" % key_env)
        else:
            add("provider:%s" % name, OK, "key " + ("已配置" if needs_key else "不需要"))

        base = p.get("base_url") or ""
        if base:
            tcp_ok, tcp_detail = _tcp(base)
            # 本机端点（ollama/vLLM）连不上只是"离线兜底不可用"，不是故障：
            # 第一次装的人看到 FAIL 会以为装坏了，实际云端照常能用。
            loopback = any(h in base for h in ("127.0.0.1", "localhost", "0.0.0.0"))
            if tcp_ok:
                level = OK
            else:
                level = WARN if loopback else FAIL
                if loopback:
                    tcp_detail += "（本机模型没启动，不影响云端 provider）"
            add("net:%s" % name, level, tcp_detail)
            if tcp_ok and (has_key or not needs_key):
                m_ok, m_detail, ids = _models(p)
                add("models:%s" % name, OK if m_ok else WARN,
                    (m_detail + (" -> " + ", ".join(ids[:4]) if ids else "")))

    # 5. 客户端配置有没有装（要真解析，别用子串匹配——"tengu_bridge_*" 这种键会误判）
    home = os.path.expanduser("~")

    def has_bridge(path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                data = json.load(fh)
        except Exception:
            return None
        servers = data.get("mcpServers") or {}
        for name, conf in servers.items():
            blob = json.dumps(conf, ensure_ascii=False).lower()
            if "mcp-bridge" in blob or "server.py" in blob or name.lower() in ("bridge", "mcp-bridge"):
                return name
        return ""

    for label, path in (
        ("claude-code", os.path.join(home, ".claude.json")),
        ("claude-code(mcp.json)", os.path.join(home, ".mcp.json")),
        ("cursor", os.path.join(home, ".cursor", "mcp.json")),
    ):
        if os.path.exists(path):
            got = has_bridge(path)
            if got is None:
                add("client:%s" % label, WARN, "文件存在但不是合法 JSON：%s" % path)
            elif got:
                add("client:%s" % label, OK, "已注册 server「%s」" % got)
            else:
                add("client:%s" % label, WARN, "有配置文件但 mcpServers 里没有 bridge 条目")
        else:
            add("client:%s" % label, WARN, "没有找到 %s" % path)

    summary = {
        "ok": sum(1 for c in checks if c["level"] == OK),
        "warn": sum(1 for c in checks if c["level"] == WARN),
        "fail": sum(1 for c in checks if c["level"] == FAIL),
    }
    return {"checks": checks, "summary": summary}


def render(report):
    icon = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}
    lines = ["", "=== mcp-bridge 环境体检 ===", ""]
    for c in report["checks"]:
        lines.append("%s %-22s %s" % (icon[c["level"]], c["name"], c["detail"]))
    s = report["summary"]
    lines.append("")
    lines.append("结果：%d 项正常，%d 项需要留意，%d 项失败" % (s["ok"], s["warn"], s["fail"]))
    if s["fail"] == 0:
        lines.append("没有失败项，可以直接用。")
        if s["warn"]:
            lines.append("WARN 只是还没配的可选项（缺 key、没装客户端、本机模型没启动），不影响云端 provider。")
    else:
        lines.append("按 FAIL 从上往下处理；WARN 里缺 key 那几条可以最后配。")
    lines.append("")
    return "\n".join(lines)
