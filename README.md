# mcp-bridge

![version](https://img.shields.io/badge/version-0.3.4-5eead4)
![python](https://img.shields.io/badge/python-3.8%2B-blue)
![deps](https://img.shields.io/badge/dependencies-0-success)
![license](https://img.shields.io/badge/license-MIT-black)
![ci](https://github.com/zhangbotong92-cyber/mcp-bridge/actions/workflows/ci.yml/badge.svg)

**[下载 v0.3.4](https://github.com/zhangbotong92-cyber/mcp-bridge/releases/download/v0.3.4/mcp-bridge-0.3.4.zip)** · **[配置生成器](https://zhangbotong92-cyber.github.io/mcp-bridge/config.html)**（选两下出 JSON）· **[在线说明页](https://zhangbotong92-cyber.github.io/mcp-bridge/)** · [English](README.en.md)

> **下载了但没跑通？** 跑一条 `python report.py`，它会生成一份自动脱敏的报告（系统信息、体检输出、自检结果）。
> 把内容发到 [issue #1](https://github.com/zhangbotong92-cyber/mcp-bridge/issues/1) 或 1024720334@qq.com，免费回你一条诊断。

把任意 **OpenAI 兼容端点**（DeepSeek / Kimi / 智谱 GLM / 通义千问 / 本地 ollama）接成 **MCP 工具**，让 Claude Code、Cursor、Cline、Continue 这类支持 MCP 的客户端，能直接调用你自己选的模型。

零第三方依赖，Python 3.8+ 直接跑。没配 key 也能先跑通链路（自动降级 mock）。

## 30 秒跑起来

```powershell
# Windows 一条命令：查环境 -> 生成配置 -> 打印客户端配置 -> 7 项自检 -> 环境体检
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
```

```bash
# macOS / Linux / Git Bash 同一套流程
sh install.sh
```

装完先跑一次体检，它会告诉你到底卡在哪：

```bash
python server.py --doctor        # 17 项：python / 配置 / key / 端点 / 模型 / 客户端
python server.py --report 7      # 最近 7 天的调用与花费
```

没配任何 key 也能跑通链路（自动降级 mock），可以先看工具列表再决定填哪家。

装完不确定成没成？→ **[60 秒验证清单](docs/verify.md)**　卡住了？→ **[把输出发我，免费诊断](https://zhangbotong92-cyber.github.io/mcp-bridge/diagnose.html)**

## 数据在哪：不出本机，不上报

这个问题被问得最多，直接写清楚：

- **没有任何遥测。** 代码里没有上报接口，装完不联网也能用。
- **key 放环境变量**，不写进 config.json，也不经过我们的服务器。
- **账本 `usage.db` 是本地 SQLite**，就在你解压出来的目录里，删掉即清空。
- **请求直连你配置的端点**（`api.deepseek.com` / 本机 ollama / 你自建的服务），中间没有我们这一层。

也就是说：**你不需要信任我，只需要看一眼 `server.py`。**
## 它和别的方式有什么不同

| 方式 | 谁持有 key | 断网时 | 花费看得清吗 |
|---|---|---|---|
| API 中转站 | 中转站 | 停服即断 | 只有一张总账单 |
| 客户端内置模型 | 厂商 | 断 | 看得到总额，分不清项目 |
| 自己写适配层 | 你 | 看你怎么写 | 看你怎么写 |
| mcp-bridge | 你（环境变量） | 回落本机模型，回执标注降级 | 每次调用一条记录，可按项目分账 |

共同点只有一句：谁持有 key，谁就承担数据责任。这一列决定了你是"用别人搭好的管子"，还是"自己接一根"。


## 为什么是这个

- `@modelcontextprotocol/sdk` 周下载 **89,463,331**，已经同时超过 `@anthropic-ai/sdk`（70.7M）与 `openai`（58.8M）。接入层已经标准化到协议，做工具的人押协议不押厂商。
- 国内团队的真实痛点：客户端（Claude Code / Cursor）好用，但绑死海外模型；换成国内模型又要到处改接法、算不清成本。
- 所以这里的卖点不是"又一个代理"，是 **一处配置 + 成本可视 + 本地优先**：一个配置文件管住所有厂商，每次调用都回传成本，断网时自动落到本机模型。

## 已验证到什么程度

| 项 | 状态 | 证据 |
|---|---|---|
| stdio 协议链路 | 通过 | `test_stdio.py` 6/6：initialize / tools/list / models / chat / cost / 错误路径 |
| 真实上游调用（非 mock） | 通过 | `probe_local.py` 打本机 ollama `qwen2.5vl:3b`，返回「链路已通」，latency 4234ms（冷）/ 70ms（热） |
| 云端 provider | 未验证 | 没有 API key，只跑通了 mock 分支与错误分支 |
| 流式输出 | 未实现 | v0.2 |

## 跑起来

**Windows 一键（推荐）**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
```

它会检查 Python 版本、生成 `config.json`、打印可直接粘贴的客户端配置、跑完 7 项自检，最后告诉你本机有没有 ollama 兜底。不联网、不装依赖、不改系统设置。

**手动**

```bash
# 1. 复制配置，填你自己的 key（环境变量名写在配置里）
cp config.sample.json config.json
set DEEPSEEK_API_KEY=sk-xxx        # Windows
export DEEPSEEK_API_KEY=sk-xxx     # bash

# 2. 冒烟测试（真起子进程走 stdio，7 项校验）
python test_stdio.py

# 3. 本地模型真跑（需要本机 ollama 在 11434 上跑着）
python probe_local.py

# 4. 生成一段真实会话记录（给客户看 / 录屏当脚本）
python demo.py

# 5. 接到客户端
```

## 接到 Claude Code

`~/.claude.json` 或项目 `.mcp.json`：

```json
{
  "mcpServers": {
    "bridge": {
      "command": "python",
      "args": ["D:/path/to/mcp-bridge/server.py", "--config", "D:/path/to/mcp-bridge/config.json"],
      "env": { "DEEPSEEK_API_KEY": "sk-xxx" }
    }
  }
}
```

## 接到 Cursor

`~/.cursor/mcp.json` 同结构（`mcpServers` → `bridge`）。

## 工具清单

| 工具 | 作用 | 参数 |
|---|---|---|
| `bridge_chat` | 调一次对话 | `provider`、`prompt`，可选 `model` `system` `temperature` `max_tokens` |
| `bridge_models` | 列出已配好的 provider / 模型 / 计价 / key 是否存在 | 无 |
| `bridge_cost` | 按价格表算一次调用的钱（人民币） | `provider`、`tokens_in`，可选 `model` `tokens_out` |
| `bridge_usage` | 最近 N 天用量与花费（按 provider / model / 天聚合） | `days`（默认 7）、`group_by` |

### 用量账本（v0.2 新增）

每次调用自动落一条记录到本地 `usage.db`（SQLite，标准库，不需要装数据库）：时间、provider、model、输入输出 token、成本、延迟、是否 mock、错误原因。
token 优先取上游返回的真实 `usage`，拿不到才退回估算。

命令行直接看账，不用开服务：

```bash
python server.py --report 7                 # 最近 7 天，按 provider 聚合
python server.py --report 30 --group-by day # 按天
python server.py --report 7 --json          # 机器可读，接报表用
```

```
最近 7 天调用：2 次，tokens 合计 33，花费 ¥0.0000
key             calls       tok_in      tok_out   cost_cny   avg_ms
deepseek            1           12            8     0.0000        0
local               1            9            4     0.0000     2850
```

这一块解决的是"团队里没人说得清这个月 token 花在哪"——报价单里能当着客户面跑一遍。

## 结构

```
server.py          # 协议 + 路由 + 成本核算，单文件，零依赖
config.sample.json # provider 模板：deepseek / moonshot / zhipu / dashscope / local
test_stdio.py      # 冒烟测试：initialize -> tools/list -> tools/call -> 错误路径
```

## 免费

MIT，没有付费版，没有功能阉割，也没有"高级支持请打款"。

- 卡住了就开 [issue](https://github.com/zhangbotong92-cyber/mcp-bridge/issues)，或者把 `python server.py --doctor` 的输出发到 `1024720334@qq.com`，我看到会回
- 想加 provider、改协议实现、补测试，直接提 PR，这里的 CI 会跑三系统两个 Python 版本

> 完整一点的排查顺序写在 [article-02](https://zhangbotong92-cyber.github.io/mcp-bridge/article-02.html) 和 [article-03](https://zhangbotong92-cyber.github.io/mcp-bridge/article-03.html)。
## 设计上的几个硬决定

1. **stdout 只走协议，日志全走 stderr。** MCP stdio 的经典翻车点：一行日志写进 stdout，客户端直接解析失败。
2. **强制 UTF-8 重配 stdio。** Windows 默认 cp936，中文输出会变成坏字节，客户端读到 `UnicodeDecodeError` 就断开。
3. **没 key 降级 mock 而不是报错。** 让用户先看见链路通了、工具列出来了，再去配 key——配置摩擦是这类工具最大的流失点。
4. **价格表放配置不放代码。** 厂商调价是常态，改 JSON 不用改代码。
5. **`local` provider 指向 `127.0.0.1:11434/v1`。** 断网时仍可用，这一条是给国内网络环境的默认值。

## 已知边界

- 只做 OpenAI 兼容的 `/chat/completions`；各家私有协议要另写适配器。
- 成本是**估算**（CJK 按 1 字≈1 token），不是计费依据；要精确就对回包里的 `usage`。
- 流式输出尚未实现（v0.2 目标）。
- 无鉴权：这是本地 stdio 服务，不要把 `--http` 调试口暴露到公网。







