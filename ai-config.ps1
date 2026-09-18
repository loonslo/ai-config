#Requires -Version 5.1
<#
    ai-config 统一启动入口（Windows）。

    - 解析脚本所在目录，不依赖当前工作目录。
    - 支持带空格和中文的路径。
    - 只在项目自带的独立环境里安装依赖，不修改系统 PATH、不安装全局包、不绕过执行策略。
    - 检查完运行环境后进入同一个 Python 命令界面。
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = 'Stop'

# 脚本所在目录就是这个仓库的根目录，与调用时的工作目录无关。
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

function Write-Step([string]$Message) { Write-Host "[ai-config] $Message" }

function Find-Python {
    foreach ($candidate in @('python', 'python3', 'py')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

# 依赖优先装在项目自带的独立环境里；重复启动不会重复安装。
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$venvReady = Test-Path -LiteralPath $VenvPython

# 已有项目环境时不需要系统 Python 出现在 PATH 上，直接用它。
if (-not $venvReady) {
    $python = Find-Python
    if (-not $python) {
        Write-Host '[ai-config] 错误：未找到 Python，且项目专用环境尚未创建。' -ForegroundColor Red
        Write-Host '  原有数据：没有文件被修改。'
        Write-Host '  下一步：安装 Python 3.11 或更高版本（安装时勾选 Add python.exe to PATH），然后重新运行本脚本。'
        exit 2
    }

    $versionCheck = & $python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        $actual = (& $python -c "import platform; print(platform.python_version())").Trim()
        Write-Host "[ai-config] 错误：当前 Python 版本为 $actual，需要 3.11 或更高。" -ForegroundColor Red
        Write-Host '  原有数据：没有文件被修改。'
        Write-Host '  下一步：安装 Python 3.11 或更高版本后重新运行。'
        exit 2
    }

    Write-Step '首次运行：正在创建项目专用环境……'
    & $python -m venv (Join-Path $Root '.venv')
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[ai-config] 错误：创建项目专用环境失败。' -ForegroundColor Red
        Write-Host '  原有数据：系统 Python 未被修改。'
        Write-Host '  下一步：确认当前用户对项目目录有写入权限后重试。'
        exit 2
    }
    $VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Host '[ai-config] 错误：项目专用环境创建后仍不可用。' -ForegroundColor Red
        Write-Host '  原有数据：没有文件被修改。'
        Write-Host '  下一步：删除项目下的 .venv 目录后重新运行本脚本。'
        exit 2
    }
}

$requirements = Join-Path $Root 'requirements.txt'
$stamp = Join-Path $Root '.venv\.requirements.sha256'
$needsInstall = $true
if ((Test-Path -LiteralPath $VenvPython) -and (Test-Path -LiteralPath $requirements) -and (Test-Path -LiteralPath $stamp)) {
    $current = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
    $recorded = (Get-Content -LiteralPath $stamp -Raw).Trim()
    if ($current -eq $recorded) { $needsInstall = $false }
}
if ($needsInstall) {
    Write-Step '正在安装运行依赖……'
    & $VenvPython -m pip install --quiet --disable-pip-version-check -r $requirements
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[ai-config] 错误：安装运行依赖失败。' -ForegroundColor Red
        Write-Host '  原有数据：系统 Python 和已安装包未被卸载。'
        Write-Host '  下一步：检查网络后重试；如使用代理，请先配置好 pip 代理。'
        exit 2
    }
    (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash | Set-Content -LiteralPath $stamp -NoNewline
}

$syncScript = Join-Path $Root 'scripts\sync.py'
if (-not (Test-Path -LiteralPath $syncScript)) {
    Write-Host '[ai-config] 错误：找不到 scripts\sync.py，仓库可能不完整。' -ForegroundColor Red
    Write-Host '  原有数据：没有文件被修改。'
    Write-Host '  下一步：重新获取完整的 ai-config 仓库后重试。'
    exit 2
}

& $VenvPython $syncScript @Arguments
exit $LASTEXITCODE
