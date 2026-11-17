#!/usr/bin/env sh
# mcp-bridge installer (macOS / Linux / Git Bash on Windows)
# Does four things: check python, create config.json, print the client snippet, run self-checks.
# No network access, no dependencies installed, no system settings touched.

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
cd "$DIR" || exit 1

ok()   { printf '  [ OK ]  %s\n' "$1"; }
warn() { printf '  [WARN]  %s\n' "$1"; }
fail() { printf '  [FAIL]  %s\n' "$1"; }

printf '\n=== mcp-bridge installer ===\n\n'

# 1. python
PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        ver=$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
        if [ -n "$ver" ]; then
            major=${ver%%.*}; minor=${ver#*.}
            if [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; then
                PY="$cand"; ok "Python $ver ($(command -v "$cand"))"; break
            else
                warn "Python $ver is too old, need 3.8+"
            fi
        fi
    fi
done
if [ -z "$PY" ]; then
    fail "no Python 3.8+ found"; exit 1
fi

# 2. files
missing=0
for f in server.py test_stdio.py config.sample.json; do
    if [ -f "$DIR/$f" ]; then ok "$f"; else fail "$f missing"; missing=1; fi
done
[ "$missing" -eq 1 ] && exit 1

# 3. config
if [ -f "$DIR/config.json" ]; then
    ok "config.json exists, left untouched"
else
    cp "$DIR/config.sample.json" "$DIR/config.json"
    ok "config.json created from template"
fi

# 4. client snippet
# In Git Bash / MSYS the path looks like /c/Users/... but clients need C:\Users\...
SERVER_PATH="$DIR/server.py"
CONFIG_PATH="$DIR/config.json"
if command -v cygpath >/dev/null 2>&1; then
    SERVER_PATH=$(cygpath -w "$DIR/server.py")
    CONFIG_PATH=$(cygpath -w "$DIR/config.json")
fi

cat <<EOF

=== paste this into your client config ===
(Claude Code: ~/.claude.json or project .mcp.json ; Cursor: ~/.cursor/mcp.json)

{
  "mcpServers": {
    "bridge": {
      "command": "$PY",
      "args": ["$SERVER_PATH", "--config", "$CONFIG_PATH"],
      "env": { "DEEPSEEK_API_KEY": "sk-your-key" }
    }
  }
}

EOF

# 5. self checks
printf '=== self checks (7) ===\n'
if "$PY" "$DIR/test_stdio.py"; then
    ok "self checks passed"
else
    fail "self checks failed, paste the output above"
    exit 1
fi

# 6. environment doctor
printf '\n=== environment doctor ===\n'
"$PY" "$DIR/server.py" --config "$DIR/config.json" --doctor || true

printf '\nDone. Usage report: %s server.py --report 7\n\n' "$PY"
