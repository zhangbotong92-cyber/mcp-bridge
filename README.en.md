# mcp-bridge

Expose any **OpenAI-compatible endpoint** (DeepSeek / Qwen / Zhipu GLM / Kimi / local ollama) as **MCP tools**, so Claude Code, Cursor, Cline and Continue can call the model *you* choose.

Zero third-party dependencies. Python 3.8+. Works on Windows without a package manager.

> **Why this exists.** The MCP SDK now pulls **89M downloads/week** — more than the OpenAI SDK (58.8M) and the Anthropic SDK (70.7M) combined traffic-wise. Model access has standardized at the protocol layer. If you are building tooling, bet on the protocol, not the vendor.
>
> The second reason is practical: the good clients are fine, but they pin you to overseas models. Switching to a domestic model means rewriting config, re-managing keys, and losing any visibility into cost. This bridges that gap: one config, per-call cost ledger, offline fallback.

## What you get

| Tool | Purpose |
|---|---|
| `bridge_chat` | One completion. Optional `project` tag for per-client accounting. |
| `bridge_models` | List providers / models / pricing / whether a key is present. |
| `bridge_cost` | Estimate the cost of a call in CNY. |
| `bridge_usage` | Usage and spend over N days, grouped by provider / model / **project** / day. |

Every call is written to a local SQLite file (`usage.db`): timestamp, provider, model, tokens in/out, cost, latency, mock flag, error, project. Token counts prefer the upstream `usage` field and only fall back to estimation.

```
$ python server.py --report 7 --group-by project
last 7 days: 19 calls, 351 tokens, ¥0.0000
key             calls       tok_in      tok_out   cost_cny   avg_ms
(untagged)         17          208          105     0.0000      171
BETA-support        1           11            8     0.0000        0
ACME-website        1           11            8     0.0000        0
```

## Install

```powershell
# Windows, one command: checks Python, writes config, prints the client snippet, runs 7 self-checks
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
```

```bash
# manual
cp config.sample.json config.json
export DEEPSEEK_API_KEY=sk-xxx
python test_stdio.py       # 7 checks over a real stdio session
python probe_local.py      # real call against local ollama (optional)
python demo.py             # writes a transcript of a real MCP session
```

## Wire it into a client

`~/.claude.json`, `.mcp.json`, or `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "bridge": {
      "command": "python",
      "args": ["/abs/path/server.py", "--config", "/abs/path/config.json"],
      "env": { "DEEPSEEK_API_KEY": "sk-xxx" }
    }
  }
}
```

## Design decisions that matter

1. **stdout carries protocol only; all logs go to stderr.** The classic MCP stdio failure: one stray `print()` and the client dies with a parse error.
2. **Forced UTF-8 on stdio.** Windows defaults to cp936; Chinese output becomes invalid bytes and the client raises `UnicodeDecodeError`.
3. **No key → mock, not error.** Users see the tools and the wiring first; configuration friction is where these tools lose people.
4. **Pricing lives in config, not code.** Vendors reprice constantly.
5. **`"discover": true` asks the endpoint for its model list** (with fallback to the configured name) — local model names are never what you guess.
6. **Config is read as `utf-8-sig`.** Plenty of Windows editors save JSON with a BOM; that should not be the customer's problem.

## Verified status

| Item | Status | Evidence |
|---|---|---|
| stdio protocol | pass | `test_stdio.py` 7/7 |
| real upstream call | pass | `probe_local.py` → `链路已通`, 4.2s cold / 70ms warm |
| per-project accounting | pass | `test_project.py` |
| cloud providers | **unverified** | no API key on this machine; only mock and error paths exercised |
| streaming | not implemented | v0.4 target |

## Licence

MIT — see `LICENSE`.
