#!/bin/sh
# Frontend sanity checks: required files exist and JS parses.
set -eu

cd "$(dirname "$0")/.."

for f in index.html style.css app.js Dockerfile nginx.conf.template entrypoint.sh; do
    if [ ! -f "$f" ]; then
        echo "FAIL: missing $f"
        exit 1
    fi
done

if command -v node >/dev/null 2>&1; then
    node --check app.js
    echo "OK: app.js syntax valid"
else
    echo "SKIP: node not installed, skipping JS syntax check"
fi

echo "OK: all frontend files present"
