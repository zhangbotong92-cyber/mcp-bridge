#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""体检的回归测试：结构要对、不能因为体检本身崩掉、不能出现 FAIL（本机应当能跑）。"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server.py")
CONFIG = os.path.join(HERE, "config.json")


def main():
    proc = subprocess.run([sys.executable, SERVER, "--config", CONFIG, "--doctor", "--json"],
                          capture_output=True, text=True, encoding="utf-8", cwd=HERE, timeout=120)
    if proc.returncode != 0:
        print("doctor 退出码非 0:", proc.returncode)
        print((proc.stderr or "")[-400:])
        return 1

    try:
        data = json.loads(proc.stdout)
    except Exception as exc:
        print("输出不是合法 JSON:", exc)
        print((proc.stdout or "")[:300])
        return 1

    checks = data.get("checks") or []
    summary = data.get("summary") or {}
    must_have = {"python", "config", "usage-db"}
    names = {c["name"] for c in checks}

    results = [
        ("checks 数量 >= 5", len(checks) >= 5, len(checks)),
        ("必备项齐全", must_have.issubset(names), ",".join(sorted(must_have - names)) or "ok"),
        ("summary 结构", all(k in summary for k in ("ok", "warn", "fail")), str(summary)),
        ("没有 FAIL", summary.get("fail", 1) == 0, "fail=%s" % summary.get("fail")),
        ("每项都有 level/detail", all(c.get("level") and c.get("detail") is not None for c in checks), "ok"),
    ]

    print("")
    ok = 0
    for name, passed, detail in results:
        print(("  PASS  " if passed else "  FAIL  ") + name.ljust(22) + str(detail))
        ok += 1 if passed else 0
    print("\n%d/%d passed" % (ok, len(results)))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
