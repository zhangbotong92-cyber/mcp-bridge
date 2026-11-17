# 装完之后：60 秒确认它真的在工作

装完不等于能用。照这个顺序走一遍，任何一步不对都能立刻定位。

## 第 1 步：自检（10 秒）

```bash
python test_stdio.py
```

期望结尾：`7/7 passed`。

**不对就看**：Python 版本（要 3.8+）、是否在解压出来的目录里执行。

## 第 2 步：环境体检（15 秒）

```bash
python server.py --doctor
```

期望：`0 项失败`。WARN 是正常的——缺 key、没装客户端、本机模型没启动，都只影响对应那一条。

**重点看三行**：

| 行 | 说明 |
|---|---|
| `config` | 不是 OK 说明 config.json 没生成，回到目录里跑一次 `install.ps1` / `install.sh` |
| `provider:<名字>` | WARN「缺少环境变量」= 还没配 key，可以先跳过，用 mock 跑通链路 |
| `net:<名字>` | 云端 provider 显示 FAIL 才是真问题（网络/代理）；`net:local` 是 WARN，只是本机 ollama 没开 |

## 第 3 步：真实调用一次（20 秒）

没配 key 也能验证链路——用 mock：

```bash
python -c "import server;cfg=server.Config('config.json');print(server.do_chat(cfg,{'provider':'deepseek','prompt':'hi','max_tokens':16})['text'][:60])"
```

期望看到以 `[mock:deepseek/...]` 开头的文字。**看到 mock 就说明协议和路由通了。**

有 key 或本机有 ollama 时，走真实模型：

```bash
python probe_local.py     # 需要本机 ollama 在 11434
```

期望：`MOCK: False`，以及模型真实输出。

## 第 4 步：看账（10 秒）

```bash
python server.py --report 1 --group-by project
```

期望：出现刚才那次调用。**这一行出现，说明"每次调用都记账"这件事成立。**

## 第 5 步：接进客户端（5 分钟）

把 `install.ps1` / `install.sh` 打印的那段 JSON 粘进：

- Claude Code：`~/.claude.json`，或项目里的 `.mcp.json`
- Cursor：`~/.cursor/mcp.json`

**改完必须重启客户端**，MCP 配置不做热加载。

重启后在对话里让它调用一次 `bridge_models`，能列出 provider 就是接好了。

---

## 卡在哪一步，就把哪一步的输出发出来

开 issue（[#1](https://github.com/zhangbotong92-cyber/mcp-bridge/issues/1)）或发邮件 `1024720334@qq.com`。
有输出我基本能直接定位；没有也能答，只是会多问两句。
