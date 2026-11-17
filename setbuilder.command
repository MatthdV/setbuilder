#!/bin/zsh
# Double-click to launch setbuilder as a desktop-style app window.
# - starts the local server if it isn't already running
# - opens a chromeless window (Chrome --app mode; no address bar, no :8000 shown)
# - closing this Terminal window quits the app (server runs in foreground)
set -e
DIR="${0:A:h}"            # this script's folder = repo root
DB="${DIR}.db"            # sibling cache: .../rekordbox/setbuilder.db
PORT=8000
URL="http://127.0.0.1:${PORT}/"

open_app() {
  if [ -d "/Applications/Google Chrome.app" ]; then
    open -na "Google Chrome" --args --app="$URL" --new-window
  elif [ -d "/Applications/Brave Browser.app" ]; then
    open -na "Brave Browser" --args --app="$URL" --new-window
  else
    open "$URL"            # fallback: default browser (normal tab)
  fi
}

cd "$DIR"

# Already running (e.g. started elsewhere)? Just open the window.
if curl -s "$URL" >/dev/null 2>&1; then
  open_app
  exit 0
fi

# Open the window as soon as the server answers, then run the server in front.
( for i in {1..60}; do curl -s "$URL" >/dev/null 2>&1 && { open_app; break; }; sleep 0.25; done ) &

exec "$DIR/.venv/bin/python" -c "import uvicorn; from setbuilder.api import create_app; uvicorn.run(create_app('$DB'), host='127.0.0.1', port=${PORT})"
