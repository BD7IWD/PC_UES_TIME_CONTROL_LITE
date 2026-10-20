# 单机版客户端回归测试：清干净 → 启动 → 依次跑测试
# 用法：powershell -ExecutionPolicy Bypass -File tests\run_all.ps1
# 作者：野怼怼；https://www.bd7iwd.com
# 许可：MIT
$ErrorActionPreference = 'Continue'
$R = Split-Path -Parent $PSScriptRoot
$DATA = Join-Path $env:LOCALAPPDATA 'PCTimeControlLite'
$PORT = 8080

function Kill-All {
    # watchdog 会在 3 秒内把主程序拉起来，所以要多轮杀
    for ($i = 0; $i -lt 5; $i++) {
        Get-Process python, pythonw -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like '*Python314*' } | Stop-Process -Force -ErrorAction SilentlyContinue
        Get-Process PCTimeControlLite -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 900
    }
}

Write-Host '=== 1. 停掉所有实例（含 watchdog）===' -ForegroundColor Cyan
Kill-All

Write-Host '=== 2. 等端口释放 ===' -ForegroundColor Cyan
$released = $false
for ($i = 0; $i -lt 30; $i++) {
    $c = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue
    if (-not $c) { $released = $true; break }
    Start-Sleep -Milliseconds 500
}
if (-not $released) { Write-Host "❌ 端口 $PORT 仍被占用，测试中止" -ForegroundColor Red; exit 1 }
Write-Host "  端口 $PORT 已释放" -ForegroundColor Green

Write-Host '=== 3. 清空数据（回到首次使用状态）===' -ForegroundColor Cyan
Remove-Item $DATA -Recurse -Force -ErrorAction SilentlyContinue

Write-Host '=== 4. 启动客户端 ===' -ForegroundColor Cyan
Start-Process -FilePath 'python' -ArgumentList 'main.py' -WorkingDirectory $R -WindowStyle Hidden

# 等它真正起来（日志里出现 已启动 且端口在听）
$up = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $log = Join-Path $DATA 'client.log'
    if (Test-Path $log) {
        $t = Get-Content $log -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($t -match "已启动 http://0\.0\.0\.0:$PORT") {
            $c = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue
            if ($c) { $up = $true; break }
        }
    }
}
if (-not $up) {
    Write-Host "❌ 客户端未能在 $PORT 上启动，日志：" -ForegroundColor Red
    Get-Content (Join-Path $DATA 'client.log') -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 20
    exit 1
}
Write-Host "  已就绪 http://127.0.0.1:$PORT" -ForegroundColor Green

$fail = 0
foreach ($t in @('_test_web_lite.py', '_test_e2e_lite.py')) {
    Write-Host "`n########## $t ##########" -ForegroundColor Cyan
    python (Join-Path $R "tests\$t")
    if ($LASTEXITCODE -ne 0) { $fail++ }
}

Write-Host "`n========== 失败脚本数: $fail / 2 ==========" -ForegroundColor $(if ($fail -eq 0) { 'Green' } else { 'Red' })
exit $fail
