#!/usr/bin/env bash
# Start llama-server with the 4-bit base model and every LoRA adapter preloaded.
# Each request sets one adapter's scale to 1 and the rest to 0, so swapping never
# reloads anything. Adapter ids follow the order below: math=0 sql=1 techwriter=2 creative=3.
#
# --load-mode none (no mmap) loads the weights into the server's own memory, so its footprint (what
# Activity Monitor shows, and what engine.py measures) is the real RAM cost.
set -euo pipefail
cd "$(dirname "$0")"

BIN=${LLAMA_SERVER:-vendor/llama.cpp/build/bin/llama-server}
exec "$BIN" \
  -m models/Llama-3.2-3B-Instruct-Q4_K_M.gguf \
  --lora adapters/math.gguf,adapters/sql.gguf,adapters/techwriter.gguf,adapters/creative.gguf \
  --lora-init-without-apply \
  --load-mode none \
  -c 2048 -np 1 --port 8080 "$@"
