#!/bin/sh
set -e

BACKEND_URL="${BACKEND_URL:-http://backend:80}"

if [ -n "$BACKEND_URL" ]; then
    sed "s|\${BACKEND_URL}|${BACKEND_URL}|g" \
        /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
fi

exec nginx -g "daemon off;"
