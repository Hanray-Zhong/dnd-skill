#!/bin/sh
set -eu

prototype_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
node "$prototype_root/tools/build-projections.mjs"

prototype_port=${TACTICAL_PROTOTYPE_PORT:-8787}
echo "抛弃式原型：http://127.0.0.1:${prototype_port}/?variant=A&map=small"
echo "按 Ctrl-C 停止本地只读服务器。"
exec python3 -m http.server "$prototype_port" --bind 127.0.0.1 --directory "$prototype_root/public"
