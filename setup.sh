#!/usr/bin/env bash
# One-time install: Python env, llama-server, base model, LoRA adapters and the
# router's embedding model (~2.5 GB of downloads). Safe to re-run: every step
# skips work that's already done, so a failed or interrupted run just resumes.
#   ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

LLAMA_CPP_COMMIT=bed0a856606ee4a24a164066f73d2379447033f5   # the build we benchmarked
BASE_REPO=bartowski/Llama-3.2-3B-Instruct-GGUF
BASE_FILE=Llama-3.2-3B-Instruct-Q4_K_M.gguf
ADAPTERS=(
  math=SriSanthM/LLAMA-3.2-3B-MathInstruct_LORA_SFT
  techwriter=Shankarblr/Llama-3.2-3B-TechWriter-LoRA
  creative=closestfriend/brie-llama-3b
  coding=yusifnuri/Llama-3.2-3B-Instruct_code_generation
)

step() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mError: %s\033[0m\n' "$*" >&2; exit 1; }

# --- 1. System tools ---------------------------------------------------------
step "Checking system tools"
command -v git >/dev/null || die "git not found. On macOS run: xcode-select --install"
if [[ "$(uname)" == Darwin ]] && ! xcode-select -p >/dev/null 2>&1; then
  die "Xcode Command Line Tools are needed to build llama.cpp. Run: xcode-select --install, then re-run ./setup.sh"
fi
command -v c++ >/dev/null || die "No C++ compiler found (install build-essential / Xcode Command Line Tools)"

# ML wheels lag behind new Python releases, so use 3.10-3.13.
find_python() {
  for py in "${PYTHON:-}" python3.11 python3.12 python3.13 python3.10 python3; do
    [[ -n "$py" ]] && command -v "$py" >/dev/null || continue
    "$py" -c 'import sys; exit(not (3, 10) <= sys.version_info[:2] <= (3, 13))' 2>/dev/null && { echo "$py"; return; }
  done
}
PY_SYS=$(find_python || true)
if [[ -z "$PY_SYS" ]] && command -v brew >/dev/null; then
  step "Installing Python 3.11 with Homebrew"
  brew install python@3.11
  PY_SYS=$(find_python || true)
fi
[[ -n "$PY_SYS" ]] || die "Python 3.10-3.13 not found. Install Python 3.11 (https://www.python.org/downloads/) and re-run."
echo "Using $PY_SYS ($("$PY_SYS" --version))"

# --- 2. Python environment ---------------------------------------------------
step "Creating Python environment in .venv"
[[ -x .venv/bin/python ]] || "$PY_SYS" -m venv .venv
PY=.venv/bin/python
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt
export PATH="$PWD/.venv/bin:$PATH"   # picks up the pip-installed cmake

# --- 3. llama.cpp (llama-server + LoRA converter) ----------------------------
step "Building llama-server"
if [[ ! -d vendor/llama.cpp/.git ]]; then
  mkdir -p vendor
  git init -q vendor/llama.cpp
  git -C vendor/llama.cpp remote add origin https://github.com/ggml-org/llama.cpp
  git -C vendor/llama.cpp fetch -q --depth 1 origin "$LLAMA_CPP_COMMIT"
  git -C vendor/llama.cpp checkout -q FETCH_HEAD
fi
if [[ -x vendor/llama.cpp/build/bin/llama-server ]]; then
  echo "Already built."
else
  cmake -S vendor/llama.cpp -B vendor/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
  cmake --build vendor/llama.cpp/build --target llama-server -j "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
fi

# --- 4. Models ---------------------------------------------------------------
step "Downloading base model ($BASE_FILE, ~2 GB)"
if [[ -f models/$BASE_FILE ]]; then
  echo "Already downloaded."
else
  "$PY" - "$BASE_REPO" "$BASE_FILE" <<'EOF'
import sys
from huggingface_hub import hf_hub_download
hf_hub_download(sys.argv[1], sys.argv[2], local_dir="models")
EOF
fi

step "Downloading and converting LoRA adapters"
for pair in "${ADAPTERS[@]}"; do
  name=${pair%%=*} repo=${pair#*=}
  if [[ -f adapters/$name.gguf ]]; then echo "  $name: done"; continue; fi
  echo "  $name: $repo"
  "$PY" - "$repo" "adapters/$name" <<'EOF'
import sys
from huggingface_hub import hf_hub_download
for f in ("adapter_config.json", "adapter_model.safetensors"):
    hf_hub_download(sys.argv[1], f, local_dir=sys.argv[2])
EOF
  # --base-model-id reads only the config, from an ungated mirror, so no HF login is needed.
  "$PY" vendor/llama.cpp/convert_lora_to_gguf.py "adapters/$name" \
    --base-model-id unsloth/Llama-3.2-3B-Instruct --outtype f16 --outfile "adapters/$name.gguf"
done

step "Caching the router's embedding model"
"$PY" -c "from sentence_transformers import SentenceTransformer; from router import EMBED_MODEL; SentenceTransformer(EMBED_MODEL, device='cpu')"

touch .venv/.setup-complete   # run.sh prefers .venv only once this exists
step "Setup complete. Start Gladius with: ./run.sh"
