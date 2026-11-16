# mcp-bridge 一键安装（Windows / PowerShell 5.1+）
# 做三件事：检查环境 -> 生成 config.json -> 打印可直接粘贴的客户端配置 -> 跑一遍自检
# 不联网、不装依赖、不改系统设置。

param(
    [string]$Dir = $PSScriptRoot,
    [switch]$SkipTest
)

$ErrorActionPreference = 'Continue'
$ok = $true

function Say($m) { Write-Host $m }
function Good($m) { Write-Host ("  [OK]   " + $m) -ForegroundColor Green }
function Warn($m) { Write-Host ("  [WARN] " + $m) -ForegroundColor Yellow }
function Bad($m)  { Write-Host ("  [FAIL] " + $m) -ForegroundColor Red }

Say ""
Say "=== mcp-bridge 安装检查 ==="
Say ""

# 1. Python
$py = $null
foreach ($cand in @('python', 'py', 'python3')) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            $ver = & $cand -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($ver -and [version]$ver -ge [version]'3.8') { $py = $cand; Good ("Python " + $ver + "  (" + $cmd.Source + ")"); break }
            else { Warn ("Python " + $ver + " 太旧，需要 3.8+") }
        } catch { }
    }
}
if (-not $py) { Bad "没找到可用的 Python 3.8+，请先装 Python 再回来"; exit 1 }

# 2. 文件齐不齐
foreach ($f in @('server.py', 'test_stdio.py', 'config.sample.json')) {
    if (Test-Path (Join-Path $Dir $f)) { Good $f } else { Bad ($f + " 缺失，目录不对"); $ok = $false }
}
if (-not $ok) { exit 1 }

# 3. 配置
$cfg = Join-Path $Dir 'config.json'
if (Test-Path $cfg) {
    Good "config.json 已存在，不覆盖"
} else {
    Copy-Item (Join-Path $Dir 'config.sample.json') $cfg
    Good "已从模板生成 config.json（记得填 key 的环境变量）"
}

# 4. 客户端配置片段
$inside = Join-Path $Dir 'server.py'
Say ""
Say "=== 把下面这段贴进客户端配置（Claude Code: ~/.claude.json 或项目 .mcp.json；Cursor: ~/.cursor/mcp.json）==="
Say ""
Say '{'
Say '  "mcpServers": {'
Say '    "bridge": {'
Say ('      "command": "' + $py + '",')
Say ('      "args": ["' + $inside + '", "--config", "' + $cfg + '"],')
Say '      "env": { "DEEPSEEK_API_KEY": "sk-填你的" }'
Say '    }'
Say '  }'
Say '}'
Say ""

# 5. 自检
if (-not $SkipTest) {
    Say "=== 自检（7 项）==="
    & $py (Join-Path $Dir 'test_stdio.py')
    if ($LASTEXITCODE -eq 0) { Good "自检通过" } else { Bad "自检未通过，把上面的输出发我"; exit 1 }
}

# 6. 本地模型（可选）
$ollama = Test-NetConnection 127.0.0.1 -Port 11434 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($ollama) { Good "检测到本机 ollama（11434），断网时可自动回落" } else { Warn "本机没跑 ollama，断网兜底不可用（不影响云端模型）" }

Say "=== 环境体检 ==="
& $py (Join-Path $Dir 'server.py') --config $cfg --doctor

Say ""
Say "装完了。看账用：python server.py --report 7；有问题先跑：python server.py --doctor"
Say ""
