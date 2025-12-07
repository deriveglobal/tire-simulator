#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate

# 1) Start the server in the background
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
UVICORN_PID=$!

# 2) Give it a second to start
sleep 2

# 3) Open the browser
open "http://127.0.0.1:8000"

# 4) Keep terminal open until server stops
wait $UVICORN_PID

