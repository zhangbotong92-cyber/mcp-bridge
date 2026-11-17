#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mcp-bridge — 把任意 OpenAI 兼容的模型端点暴露成 MCP 工具。

设计取向：
  * 零第三方依赖（只用标准库），Python 3.8+ 即可运行；
  * stdio 传输，newline-delimited JSON-RPC 2.0；
  * stdout 只走协议，所有日志走 stderr（这是 MCP stdio 的硬约束）；
  * 没有 API key 时自动降级为 mock，保证任何机器上都能先跑通链路再谈配置。

用法：
    python server.py --config config.json
    python server.py --config config.json --http 127.0.0.1:8787   # 顺带开 HTTP 调试口
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SERVER_NAME = "mcp-bridge"
SERVER_VERSION = "0.3.3"
DEFAULT_PROTOCOL = "2024-11-05"

PRICE_NOTE = "价格为示例值，按 1M tokens 计，单位人民币；上线前请按厂商官网更新。"


def log(msg):
    sys.stderr.write("[mcp-bridge] %s\n" % msg)
    sys.stderr.flush()


# --------------------------------------------------------------------------- 配置
class Config(object):
    def __init__(self, path=None):
        self.providers = {}
        self.path = path
        base = os.path.dirname(os.path.abspath(path)) if path else os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(base, "usage.db")
        if path and os.path.isfile(path):
            # utf-8-sig：很多 Windows 编辑器保存 JSON 会带 BOM，别让客户栽在这一步
            with open(path, "r", encoding="utf-8-sig") as fh:
                raw = json.load(fh)
            self.providers = raw.get("providers", {})
            log("loaded config: %s (%d providers)" % (path, len(self.providers)))
        else:
            log("no config found, running with mock-only providers")

    def get(self, name):
        return self.providers.get(name)


def pick_model(provider, model):
    models = provider.get("models") or []
    if model:
        return model
    return models[0] if models else provider.get("default_model", "unknown")


def resolve_key(provider):
    env_name = provider.get("api_key_env") or ""
    if env_name:
        return os.environ.get(env_name, "")
    return ""


# --------------------------------------------------------------------------- 用量账本
SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    ts TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_cny REAL,
    latency_ms INTEGER,
    ok INTEGER,
    mock INTEGER,
    error TEXT,
    project TEXT
);
CREATE INDEX IF NOT EXISTS idx_calls_ts ON calls(ts);
"""


def usage_init(cfg):
    try:
        conn = sqlite3.connect(cfg.db_path)
        conn.executescript(SCHEMA)
        # 老库升级：0.2 之前没有 project 列
        cols = [r[1] for r in conn.execute("PRAGMA table_info(calls)")]
        if "project" not in cols:
            conn.execute("ALTER TABLE calls ADD COLUMN project TEXT DEFAULT ''")
            log("usage db migrated: added project column")
        conn.commit()
        conn.close()
    except Exception as exc:
        log("usage db unavailable: %s" % exc)


def usage_record(cfg, provider, model, tokens_in, tokens_out, cost, latency_ms, ok, mock, error="", project=""):
    try:
        conn = sqlite3.connect(cfg.db_path, timeout=5)
        conn.execute(
            "INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), provider, model,
             int(tokens_in or 0), int(tokens_out or 0), float(cost or 0.0),
             int(latency_ms or 0), 1 if ok else 0, 1 if mock else 0, error or "", project or ""),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log("usage write failed: %s" % exc)


def usage_report(cfg, days=7, group_by="provider"):
    col = {"provider": "provider", "model": "model",
           "project": "CASE WHEN project IS NULL OR project='' THEN '(未标记)' ELSE project END",
           "day": "substr(ts,1,10)"}.get(group_by, "provider")
    since = (datetime.date.today() - datetime.timedelta(days=int(days))).isoformat()
    conn = sqlite3.connect(cfg.db_path, timeout=5)
    try:
        conn.executescript(SCHEMA)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(calls)")]
        if "project" not in cols:
            conn.execute("ALTER TABLE calls ADD COLUMN project TEXT DEFAULT ''")
            conn.commit()
        rows = conn.execute(
            "SELECT {0} AS k, COUNT(*), SUM(tokens_in), SUM(tokens_out), ROUND(SUM(cost_cny),4), "
            "ROUND(AVG(latency_ms)), SUM(ok), SUM(mock) FROM calls WHERE substr(ts,1,10) >= ? "
            "GROUP BY k ORDER BY 3 DESC".format(col),
            (since,),
        ).fetchall()
    finally:
        conn.close()

    out = []
    for r in rows:
        out.append({
            "key": r[0], "calls": r[1], "tokens_in": r[2] or 0, "tokens_out": r[3] or 0,
            "cost_cny": r[4] or 0.0, "avg_latency_ms": r[5] or 0, "ok": r[6] or 0, "mock": r[7] or 0,
        })
    return {
        "days": int(days),
        "group_by": group_by,
        "since": since,
        "rows": out,
        "total_calls": sum(x["calls"] for x in out),
        "total_tokens": sum(x["tokens_in"] + x["tokens_out"] for x in out),
        "total_cost_cny": round(sum(x["cost_cny"] for x in out), 4),
    }


# --------------------------------------------------------------------------- 成本
def estimate_tokens(text):
    """粗估：中日韩字符≈1 token/字，其他≈1 token/4 字符。只用于成本估算，不用于计费。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return int(cjk + other / 4.0 + 0.5)


def cost_of(provider, model, tokens_in, tokens_out):
    prices = (provider.get("prices") or {}).get(model) or {}
    pin = float(prices.get("in", 0) or 0)
    pout = float(prices.get("out", 0) or 0)
    return round(tokens_in / 1e6 * pin + tokens_out / 1e6 * pout, 6)


# --------------------------------------------------------------------------- 调用
def call_openai_compatible(provider, model, messages, temperature, max_tokens, timeout):
    base = (provider.get("base_url") or "").rstrip("/")
    if not base:
        raise ValueError("provider base_url missing")
    url = base + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)

    headers = {"Content-Type": "application/json"}
    key = resolve_key(provider)
    if key:
        headers["Authorization"] = "Bearer " + key

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    elapsed = round((time.time() - started) * 1000)

    choice = (body.get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content")) or ""
    usage = body.get("usage") or {}
    return {
        "text": text,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "latency_ms": elapsed,
        "raw_model": body.get("model"),
    }


def mock_call(provider, name, model, messages, reason):
    prompt = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
    tin = estimate_tokens(prompt)
    tout = max(8, tin // 2)
    return {
        "text": "[mock:%s/%s] %s\n用户最后一条输入：%s" % (name, model, reason, prompt[:200]),
        "usage": {"prompt_tokens": tin, "completion_tokens": tout, "total_tokens": tin + tout},
        "latency_ms": 0,
        "raw_model": model,
        "mock": True,
    }


# --------------------------------------------------------------------------- 工具定义
def tool_defs():
    return [
        {
            "name": "bridge_chat",
            "description": "调用配置好的 OpenAI 兼容模型端点完成一次对话。无 key 时返回 mock，便于先联通链路。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "description": "配置里的 provider 名，如 deepseek / moonshot / zhipu / dashscope"},
                    "model": {"type": "string", "description": "可选，留空用该 provider 的默认模型"},
                    "prompt": {"type": "string", "description": "用户输入"},
                    "system": {"type": "string", "description": "可选 system prompt"},
                    "temperature": {"type": "number", "description": "默认 0.7"},
                    "max_tokens": {"type": "number", "description": "可选，输出上限"},
                    "project": {"type": "string", "description": "可选，项目/客户标签，用于分账统计"},
                },
                "required": ["provider", "prompt"],
            },
        },
        {
            "name": "bridge_models",
            "description": "列出当前配置里可用的 provider 与模型，以及各自的计价和 key 环境变量名。",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "bridge_cost",
            "description": "按配置中的价格表估算一次调用的成本（人民币）。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "model": {"type": "string"},
                    "tokens_in": {"type": "number"},
                    "tokens_out": {"type": "number"},
                },
                "required": ["provider", "tokens_in"],
            },
        },
        {
            "name": "bridge_usage",
            "description": "查看最近若干天的模型调用用量与花费（按 provider / model / 天聚合），数据存在本地 SQLite 里。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days": {"type": "number", "description": "统计天数，默认 7"},
                    "group_by": {"type": "string", "enum": ["provider", "model", "project", "day"], "description": "聚合维度，默认 provider"},
                },
            },
        },
    ]


def discover_model(provider):
    """本地端点（ollama / vLLM）装了哪个模型不该靠猜：直接问 /models。"""
    base = (provider.get("base_url") or "").rstrip("/")
    if not base:
        return None
    try:
        headers = {"Accept": "application/json"}
        key = resolve_key(provider)
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(base + "/models", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        if ids:
            log("discovered model: %s" % ids[0])
            return ids[0]
    except Exception as exc:
        log("model discovery failed: %s" % exc)
    return None


def do_chat(cfg, args):
    name = args.get("provider")
    provider = cfg.get(name)
    if not provider:
        raise ValueError("unknown provider: %s (available: %s)" % (name, ", ".join(sorted(cfg.providers)) or "none"))

    model = args.get("model")
    if not model and provider.get("discover"):
        cached = provider.get("_discovered")
        if not cached:
            cached = discover_model(provider) or ""
            provider["_discovered"] = cached
        model = cached or None
    if not model:
        model = pick_model(provider, None)
    proj = args.get("project") or ""
    messages = []
    if args.get("system"):
        messages.append({"role": "system", "content": args["system"]})
    messages.append({"role": "user", "content": args.get("prompt", "")})

    temperature = float(args.get("temperature", 0.7))
    max_tokens = args.get("max_tokens")
    timeout = int(provider.get("timeout", 60))

    # 本地端点（ollama / vLLM 之类）根本不需要 key：没有 api_key_env 就直连，
    # 有 api_key_env 但环境变量为空才降级 mock。
    key_env = provider.get("api_key_env") or ""
    needs_key = bool(key_env)
    can_call = (not needs_key) or bool(resolve_key(provider))

    if can_call:
        try:
            out = call_openai_compatible(provider, model, messages, temperature, max_tokens, timeout)
            out["provider"] = name
            out["model"] = model
            # 优先用上游真实 usage，拿不到才退回估算
            used = out.get("usage") or {}
            tin = used.get("prompt_tokens") or estimate_tokens(args.get("prompt", ""))
            tout = used.get("completion_tokens") or estimate_tokens(out["text"])
            out["cost_cny"] = cost_of(provider, model, tin, tout)
            usage_record(cfg, name, model, tin, tout, out["cost_cny"], out.get("latency_ms"), True, False, project=proj)
            return out
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            usage_record(cfg, name, model, estimate_tokens(args.get("prompt", "")), 0, 0, 0, False, False, "HTTP %s" % exc.code, project=proj)
            raise RuntimeError("upstream HTTP %s: %s" % (exc.code, detail))
        except Exception as exc:
            log("upstream failed (%s), falling back to mock: %s" % (name, exc))
            out = mock_call(provider, name, model, messages, "上游调用失败，已降级：%s" % exc)
            out["provider"] = name
            out["model"] = model
            out["cost_cny"] = 0.0
            usage_record(cfg, name, model, out["usage"]["prompt_tokens"], out["usage"]["completion_tokens"],
                         0, 0, False, True, str(exc)[:200], project=proj)
            return out

    out = mock_call(provider, name, model, messages, "未配置 " + (provider.get("api_key_env") or "api_key"))
    out["provider"] = name
    out["model"] = model
    out["cost_cny"] = 0.0
    usage_record(cfg, name, model, out["usage"]["prompt_tokens"], out["usage"]["completion_tokens"],
                 0, 0, False, True, "no api key", project=proj)
    return out


def do_models(cfg):
    rows = []
    for name in sorted(cfg.providers):
        p = cfg.providers[name]
        rows.append({
            "provider": name,
            "base_url": p.get("base_url"),
            "models": p.get("models") or [],
            "key_env": p.get("api_key_env"),
            "key_present": bool(resolve_key(p)),
            "prices": p.get("prices") or {},
        })
    return {"count": len(rows), "providers": rows, "note": PRICE_NOTE}


def do_cost(cfg, args):
    name = args.get("provider")
    provider = cfg.get(name)
    if not provider:
        raise ValueError("unknown provider: %s" % name)
    model = pick_model(provider, args.get("model"))
    tin = float(args.get("tokens_in", 0))
    tout = float(args.get("tokens_out", 0))
    return {
        "provider": name,
        "model": model,
        "tokens_in": tin,
        "tokens_out": tout,
        "cost_cny": cost_of(provider, model, tin, tout),
        "note": PRICE_NOTE,
    }


# --------------------------------------------------------------------------- 协议
def text_result(payload, is_error=False):
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    out = {"content": [{"type": "text", "text": body}]}
    if is_error:
        out["isError"] = True
    return out


def handle(cfg, msg):
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method in ("notifications/initialized", "initialized"):
        return None  # 通知不需要回包

    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": tool_defs()}}

    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"resources": []}}

    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"prompts": []}}

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "bridge_chat":
                return {"jsonrpc": "2.0", "id": mid, "result": text_result(do_chat(cfg, args))}
            if name == "bridge_models":
                return {"jsonrpc": "2.0", "id": mid, "result": text_result(do_models(cfg))}
            if name == "bridge_cost":
                return {"jsonrpc": "2.0", "id": mid, "result": text_result(do_cost(cfg, args))}
            if name == "bridge_usage":
                rep = usage_report(cfg, days=args.get("days", 7), group_by=args.get("group_by", "provider"))
                return {"jsonrpc": "2.0", "id": mid, "result": text_result(rep)}
            raise ValueError("unknown tool: %s" % name)
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": mid, "result": text_result({"error": str(exc)}, is_error=True)}

    if mid is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": mid,
        "error": {"code": -32601, "message": "method not found: %s" % method},
    }


def serve_stdio(cfg):
    log("stdio server ready (%d providers)" % len(cfg.providers))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as exc:
            log("bad json: %s" % exc)
            continue
        try:
            resp = handle(cfg, msg)
        except Exception as exc:  # 兜底，协议层不该崩
            resp = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(exc)}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def serve_http(cfg, addr):
    """极简调试口：POST /rpc 传一条 JSON-RPC，返回一条响应。仅本地调试用。"""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                msg = json.loads(raw.decode("utf-8"))
                resp = handle(cfg, msg)
                body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *a):
            log("http " + (fmt % a))

    host, port = addr.split(":")
    srv = HTTPServer((host, int(port)), H)
    log("http debug endpoint on http://%s/rpc" % addr)
    srv.serve_forever()


def main():
    # MCP stdio 传输要求 UTF-8；Windows 默认 cp936 会把非 ASCII 输出写坏。
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")
        except Exception:
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    ap.add_argument("--http", default=None, help="host:port 开启 HTTP 调试口")
    ap.add_argument("--report", type=int, default=None, metavar="DAYS",
                    help="不开服务，直接打印最近 N 天的用量报表（命令行看账用）")
    ap.add_argument("--group-by", default="provider", choices=["provider", "model", "project", "day"])
    ap.add_argument("--json", action="store_true", help="配合 --report / --doctor 输出 JSON")
    ap.add_argument("--doctor", action="store_true", help="体检本机环境：python/配置/网络/key/客户端")
    args = ap.parse_args()

    cfg = Config(args.config)
    usage_init(cfg)

    if args.doctor:
        import doctor
        rep = doctor.run(cfg)
        if args.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(doctor.render(rep))
        return

    if args.report:
        rep = usage_report(cfg, days=args.report, group_by=args.group_by)
        if args.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return
        print("最近 %d 天调用：%d 次，tokens 合计 %d，花费 ¥%.4f"
              % (rep["days"], rep["total_calls"], rep["total_tokens"], rep["total_cost_cny"]))
        print("%-14s %6s %12s %12s %10s %8s" % ("key", "calls", "tok_in", "tok_out", "cost_cny", "avg_ms"))
        for r in rep["rows"]:
            print("%-14s %6d %12d %12d %10.4f %8d"
                  % (r["key"], r["calls"], r["tokens_in"], r["tokens_out"], r["cost_cny"], r["avg_latency_ms"]))
        return

    if args.http:
        serve_http(cfg, args.http)
    else:
        serve_stdio(cfg)


if __name__ == "__main__":
    main()
