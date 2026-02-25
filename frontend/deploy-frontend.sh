#!/bin/bash
# Build frontend and copy to Nginx docroot so Lighting, Video date/time, etc. show up.
set -e
cd "$(dirname "$0")"
echo "[1/2] Building frontend..."
npm run build
echo "[2/2] Copying dist/* to /var/www/cctv/ (needs sudo)..."
sudo cp -r dist/* /var/www/cctv/
echo "Done. Hard-refresh the app (Ctrl+Shift+R) to see Lighting and split date/time."
