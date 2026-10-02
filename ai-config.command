#!/bin/bash
# ai-config 统一启动入口（macOS / Linux）。
#
# - 解析脚本所在目录，不依赖当前工作目录。
# - 支持带空格和中文的路径。
# - 只在项目自带的独立环境里安装依赖，不修改系统 PATH、不安装全局包。
# - 检查完运行环境后进入同一个 Python 命令界面。

set -u

# 脚本所在目录就是这个仓库的根目录，与调用时的工作目录无关。
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 2

step() { printf '[ai-config] %s\n' "$1"; }

fail() {
    printf '[ai-config] 错误：%s\n' "$1"
    printf '  原有数据：没有文件被修改。\n'
    printf '  下一步：%s\n' "$2"
    exit 2
}

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "未找到 Python 3.11 或更高版本。" "安装 Python（例如 brew install python），然后重新运行本脚本。"
fi

VENV_PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    step "首次运行：正在创建项目专用环境……"
    if ! "$PYTHON" -m venv "$ROOT/.venv"; then
        fail "创建项目专用环境失败。" "确认当前用户对项目目录有写入权限后重试。"
    fi
    VENV_PYTHON="$ROOT/.venv/bin/python"
    chmod +x "$VENV_PYTHON" 2>/dev/null || true
fi

REQUIREMENTS="$ROOT/requirements.txt"
STAMP="$ROOT/.venv/.requirements.sha256"
NEEDS_INSTALL=1
if [ -f "$REQUIREMENTS" ] && [ -f "$STAMP" ]; then
    if command -v shasum >/dev/null 2>&1; then
        CURRENT="$(shasum -a 256 "$REQUIREMENTS" | awk '{print $1}')"
    else
        CURRENT="$(sha256sum "$REQUIREMENTS" | awk '{print $1}')"
    fi
    RECORDED="$(tr -d '[:space:]' < "$STAMP")"
    [ "$CURRENT" = "$RECORDED" ] && NEEDS_INSTALL=0
fi

if [ "$NEEDS_INSTALL" -eq 1 ]; then
    step "正在安装运行依赖……"
    if ! "$VENV_PYTHON" -m pip install --quiet --disable-pip-version-check -r "$REQUIREMENTS"; then
        fail "安装运行依赖失败。" "检查网络后重试；如使用代理，请先配置好 pip 代理。"
    fi
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$REQUIREMENTS" | awk '{print $1}' > "$STAMP"
    else
        sha256sum "$REQUIREMENTS" | awk '{print $1}' > "$STAMP"
    fi
fi

SYNC_SCRIPT="$ROOT/scripts/sync.py"
if [ "${1:-}" = "machine" ]; then
    SYNC_SCRIPT="$ROOT/scripts/machine.py"
    shift
fi
if [ ! -f "$SYNC_SCRIPT" ]; then
    fail "找不到命令入口，仓库可能不完整。" "重新获取完整的 ai-config 仓库后重试。"
fi

exec "$VENV_PYTHON" "$SYNC_SCRIPT" "$@"
