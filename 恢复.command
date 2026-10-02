#!/bin/bash
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$ROOT/ai-config.command" machine guide restore "$@"
RESULT=$?
if [ "$RESULT" -ge 2 ]; then
    printf '\n准备没有完成，请按回车关闭窗口。\n'
    read -r _
fi
exit "$RESULT"
