#!/bin/sh
# Shows the dashboard full-screen on the Pi's monitor. Started at desktop login by zotbins-kiosk.desktop.
# Waits for the dashboard service to answer, and reopens the browser if it closes or crashes.
URL="${1:-http://localhost:9999/bin/main}"

until curl -s -o /dev/null "$URL"; do sleep 2; done

while true; do
    # --incognito: no "restore pages?" prompt after a power cut
    chromium-browser --kiosk --incognito --noerrdialogs --disable-infobars --no-first-run \
        --password-store=basic --ozone-platform=wayland --check-for-update-interval=31536000 "$URL"
    sleep 1  # zotbins-screen-power closes the browser on wake so it reopens full-screen; be quick
done
