#!/bin/sh
# Run as PUID:PGID so edited books keep the library's ownership
set -eu

if [ "$(id -u)" = "0" ]; then
    mkdir -p /data
    chown -R "$PUID:$PGID" /data
    export HOME=/data
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups -- "$@"
fi
exec "$@"
