#!/usr/bin/env bash
# Start llama-server with the 4-bit base model and every LoRA adapter preloaded.
# Each request sets one adapter's scale to 1 and the rest to 0, so swapping never
# reloads anything. Adapter ids follow the order below: math=0 techwriter=1 creative=2 coding=3.
# The SQL adapter (BY-ALF/llama-3.2-3b-sql-lora) was dropped: it lost to the base model on
# every eval (73% vs 93% on single-table questions; see eval_sql_adapter.py).
#
# --load-mode none (no mmap) loads the weights into the server's own memory, so its footprint (what
# Activity Monitor shows, and what engine.py measures) is the real RAM cost.
#
# Memory savers: flash attention plus an 8-bit KV cache halve the
# KV memory, and a smaller physical batch shrinks the compute buffers.
set -euo pipefail
cd "$(dirname "$0")"

BIN=${LLAMA_SERVER:-vendor/llama.cpp/build/bin/llama-server}
exec "$BIN" \
  -m models/Llama-3.2-3B-Instruct-Q4_K_M.gguf \
  --lora adapters/math.gguf,adapters/techwriter.gguf,adapters/creative.gguf,adapters/coding.gguf \
  --lora-init-without-apply \
  --load-mode none \
  -fa on -ctk q8_0 -ctv q8_0 -ub 256 \
  -c 2048 -np 1 --port 8080 "$@"
