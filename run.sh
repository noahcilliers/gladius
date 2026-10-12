#!/usr/bin/env bash
# One command for the demo: start llama-server if it isn't running, wait until it's
# ready, warm every adapter so the first live prompt isn't a cold start, then open
# the Gladius UI (retro.py). A server this script started is stopped when the UI exits
# (Ctrl+C); one that was already running (e.g. from ./serve.sh) is left alone.
#   ./run.sh            # UI on http://localhost:8503
set -euo pipefail
cd "$(dirname "$0")"

# Prefer the venv once setup.sh has finished; fall back to the dev machine's conda env.
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -f .venv/.setup-complete ]]; then PYTHON=.venv/bin/python
  elif [[ -x /opt/miniconda3/envs/ml-env/bin/python ]]; then PYTHON=/opt/miniconda3/envs/ml-env/bin/python
  else PYTHON=.venv/bin/python; fi
fi
PY=$PYTHON
UI_PORT=${UI_PORT:-8503}
mkdir -p logs

if [[ ! -x "$PY" || ! -f models/Llama-3.2-3B-Instruct-Q4_K_M.gguf || ! -x vendor/llama.cpp/build/bin/llama-server ]]; then
  echo "Gladius isn't installed yet. Run ./setup.sh first."
  exit 1
fi

# Stop what we started on any exit: Ctrl+C, a closed terminal, or a kill aimed only at
# this script's pid. Without this, killing just the UI orphans llama-server, which keeps
# ~2 GB of RAM until reboot. (serve.sh execs, so $! is llama-server itself.)
server_pid= ui_pid=
cleanup() {
  for pid in $ui_pid $server_pid; do
    kill -0 "$pid" 2>/dev/null || continue
    [[ $pid == "$server_pid" ]] && echo "Stopping llama-server..."
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if ! curl -sf http://127.0.0.1:8080/health >/dev/null; then
  echo "Starting llama-server (log: logs/server.log)..."
  ./serve.sh > logs/server.log 2>&1 &
  server_pid=$!
  until curl -sf http://127.0.0.1:8080/health >/dev/null; do
    kill -0 "$server_pid" 2>/dev/null || { echo "llama-server exited; see logs/server.log"; exit 1; }
    sleep 1
  done
fi

# Always warm: after idling, macOS may have paged the model out (a 15 s first token).
echo "Warming adapters..."
"$PY" -c "
from engine import Engine
e = Engine()
for route in ['base', *e.adapter_ids]:
    _, s = e.generate('Hi', route, max_tokens=4)
    print(f'  {route:<11} first token {s.ttft_ms:5.0f} ms')
print(f'  server memory {e.server_mem_mb():.0f} MB')
"

# In the background plus wait (not exec, not foreground) so a signal to this script runs
# the traps right away instead of after Streamlit exits.
"$PY" -m streamlit run retro.py --server.headless true --server.port "$UI_PORT" \
  --server.fileWatcherType none \
  --client.toolbarMode minimal --theme.base dark --theme.primaryColor "#ff8a1f" \
  --theme.backgroundColor "#090604" --theme.secondaryBackgroundColor "#110b06" \
  --theme.textColor "#f6e6d3" --theme.font monospace &
ui_pid=$!
wait "$ui_pid"
