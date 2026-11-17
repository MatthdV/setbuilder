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

is_setbuilder() { curl -s "$URL" 2>/dev/null | grep -q "<title>setbuilder</title>"; }

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
if is_setbuilder; then
  open_app
  exit 0
fi

if curl -s -o /dev/null "$URL" 2>/dev/null && ! is_setbuilder; then
  MSG="Port ${PORT} is used by another service."
  osascript -e "display alert \"setbuilder\" message \"$MSG\"" 2>/dev/null || echo "$MSG" >&2
  exit 1
fi

if [ ! -x "$DIR/.venv/bin/python" ]; then
  echo "setbuilder: Python env missing at $DIR/.venv — run: uv sync" >&2
  read -r "?Press Enter to close."
  exit 1
fi

# Open the window as soon as the server answers, then run the server in front.
( for i in {1..60}; do is_setbuilder && { open_app; break; }; sleep 0.25; done ) &

SETBUILDER_DB="$DB" SETBUILDER_PORT="$PORT" exec "$DIR/.venv/bin/python" -c 'import os, uvicorn; from setbuilder.api import create_app; uvicorn.run(create_app(os.environ["SETBUILDER_DB"]), host="127.0.0.1", port=int(os.environ["SETBUILDER_PORT"]))'
