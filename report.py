#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一条命令生成求助报告：把"我要怎么描述问题"变成"跑一下，把文件发过去"。

会自动脱敏（key、token、路径里的用户名），所以可以直接贴到公开 issue 里。

用法：
    python report.py             # 生成 report-YYYYMMDD-HHMM.txt 并打印路径
    python report.py --print     # 直接打印到终端
"""

import datetime
import json
import os
import platform
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
SERVER = os.path.join(HERE, "server.py")

SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***REDACTED***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"), "gh*_***REDACTED***"),
    (re.compile(r"\b[0-9a-f]{32}\b"), "***REDACTED-32HEX***"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{10,}"), r"\1***REDACTED***"),
]


def redact(text):
    for pat, repl in SECRET_PATTERNS:
        text = pat.sub(repl, text)
    # 路径里的用户名：C:\Users\xxx\ 或 /home/xxx/
    text = re.sub(r"([A-Za-z]:\\Users\\)([^\\\s]+)", r"\1***", text)
    text = re.sub(r"(/home/)([^/\s]+)", r"\1***", text)
    return text


def run(cmd, timeout=90):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="ignore", timeout=timeout, cwd=HERE)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as exc:
        return "!! 命令执行失败: %s" % exc


def main():
    lines = []
    lines.append("mcp-bridge 求助报告")
    lines.append("生成时间: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")

    lines.append("## 系统")
    lines.append("OS: %s %s" % (platform.system(), platform.release()))
    lines.append("Python: %s (%s)" % (platform.python_version(), sys.executable))
    lines.append("")

    lines.append("## 配置文件")
    if os.path.exists(CONFIG):
        try:
            raw = open(CONFIG, "r", encoding="utf-8-sig").read()
            data = json.loads(raw)
            providers = list((data.get("providers") or {}).keys())
            lines.append("存在，provider: %s" % ", ".join(providers))
            lines.append("（内容不含 key；key 只在环境变量里）")
        except Exception as exc:
            lines.append("存在但解析失败: %s" % exc)
    else:
        lines.append("不存在：%s" % CONFIG)
    lines.append("")

    lines.append("## 环境体检（--doctor）")
    lines.append(run([sys.executable, SERVER, "--config", CONFIG, "--doctor"]).strip())
    lines.append("")

    lines.append("## 协议自检（test_stdio.py）")
    lines.append(run([sys.executable, os.path.join(HERE, "test_stdio.py")], timeout=120).strip())
    lines.append("")

    lines.append("## 客户端配置里有没有 bridge")
    home = os.path.expanduser("~")
    for label, path in (("claude-code", os.path.join(home, ".claude.json")),
                        ("cursor", os.path.join(home, ".cursor", "mcp.json"))):
        if os.path.exists(path):
            try:
                data = json.load(open(path, "r", encoding="utf-8", errors="ignore"))
                servers = list((data.get("mcpServers") or {}).keys())
                lines.append("%s: 存在，mcpServers = %s" % (label, ", ".join(servers) or "(空)"))
            except Exception as exc:
                lines.append("%s: 存在但解析失败 (%s)" % (label, exc))
        else:
            lines.append("%s: 没有这个文件 (%s)" % (label, path))
    lines.append("")

    lines.append("## 请补充")
    lines.append("1. 客户端里看到的报错原文（截图里的那行字）")
    lines.append("2. 你做了什么操作之后开始出问题的")
    lines.append("")

    text = redact("\n".join(lines))

    if "--print" in sys.argv:
        print(text)
        return 0

    out = os.path.join(HERE, "report-%s.txt" % datetime.datetime.now().strftime("%Y%m%d-%H%M"))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("报告已生成：%s" % out)
    print("把整个文件的内容贴到 1024720334@qq.com 或 https://github.com/zhangbotong92-cyber/mcp-bridge/issues/1")
    print("已自动脱敏：key、token、路径里的用户名。可以直接发。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
