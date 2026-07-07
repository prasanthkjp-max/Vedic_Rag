#!/bin/sh
set -e

# Sync baked-in static files to the bind-mount directory.
# Coolify mounts /app/static as a bind volume, which shadows the image's
# built-in files. This script copies the original files from a backup location
# to the bind-mount before starting the app, ensuring every deploy serves the
# latest static assets.

STATIC_DIR="/app/static"
BACKUP_DIR="/app/.static-original"

if [ -d "$BACKUP_DIR" ]; then
    echo "[entrypoint] Syncing static files from image to bind-mount..."
    cp -a "$BACKUP_DIR/." "$STATIC_DIR/"
    echo "[entrypoint] Static files synced ($(ls "$STATIC_DIR" | wc -l) items)"
else
    echo "[entrypoint] No backup static dir found, using bind-mount as-is"
fi

exec "$@"