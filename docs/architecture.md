# Path 3 — Architecture: from scripts to an installable app

> Status: design / proposal. Target: restructure Gladius into a modular core with
> pluggable capabilities (routing, RAG, tools such as file manipulation), behind one API,
> so it can ship as a double-click desktop app for students who never open a terminal.
> Builds on [`specialists.md`](specialists.md) (adapter registry) and [`rag.md`](rag.md)
> (real RAG); does not replace them.

## 1. Where the code is today

A flat set of scripts around one external process:

```
llama-server  (C++, separate process, :8080)   started by serve.sh: base model + every LoRA preloaded
    ▲ HTTP
engine.py      llama-server client; LoRA switch per request; adapter prompt formats (sql, coding)
router.py      Snowflake Arctic embedder + nearest-centroid classifier + semantic cache
rag/           RAG over the workspace (GLADIUS_WORKSPACE); borrows router.model to embed; per-route RAG rules + prompt augmentation
retro.py       Streamlit UI — and also the orchestrator (route → notes override → retrieve → augment → stream → log)
bench.py, eval_sql_adapter.py, charts.py   evals and benchmarks
setup.sh / serve.sh / run.sh               install (compiles llama.cpp), start server, launch UI
```

### Structural problems

| # | Problem | Evidence |
|---|---|---|
| A1 | **The pipeline lives in the UI.** You can't drop Streamlit, add an API, or add a pipeline step without editing UI code. | `retro.py` main block: `router.route` → `retriever.notes_route` → `retrieve` → `augment` → `engine.stream` → session save + `turns.jsonl` |
| A2 | **Specialist knowledge is spread across 5 files.** | `setup.sh` `ADAPTERS`, `serve.sh` `--lora`, `router.ROUTES`, `engine.RAW_/CHAT_PROMPT_ROUTES`, `retriever.ROUTE_RAG` + techwriter/sql branches in `augment`, `retro.ROUTES`/`CODE_ROUTES`/`STARTERS` — see [`specialists.md`](specialists.md) §1 |
| A3 | **Hidden coupling between capabilities.** | `Retriever.__init__` calls `router.model.encode` directly |
| A4 | **Install requires a developer machine.** | `setup.sh` needs git, Xcode CLT / a C++ compiler, Python 3.10–3.13, and pulls torch + transformers to convert adapters |
| A5 | **Demo paths and constants baked in.** | `CORPUS_DIR = data/student`, `models/…gguf` in `serve.sh`/`bench.py`, `LAPTOP_RAM_MB`, port 8080 |

## 2. Why not microservices

The appeal is right — switch capabilities on and off independently and add new ones
without touching the rest. But one process + HTTP API per feature is the wrong tool on an
8 GB laptop:

- **RAM.** Each Python service costs ~50–150 MB before doing any work. Routing and RAG share
  one embedding model; splitting them means loading it twice or adding a third service.
- **The LoRA switch isn't a service.** It's a field on each llama-server request
  (`"lora": [{"id", "scale"}]`, `engine.lora_for`). llama-server is already the one genuine
  service boundary, and the right one: heavy, native, model-owning.
- **Operations.** Startup order, health checks, port allocation and crash recovery across N
  local processes is real work for a single-user offline app, and every one of them is a
  way for a non-technical user's install to break.

**Decision: a modular monolith with a capability (plugin) interface.** Same separation of
concerns, in-process calls. Any capability can later move out of process behind the same
interface if it needs to. The one place an out-of-process boundary pays off now is
**tools**, via **MCP** — a standard protocol, sandboxing, and third-party tools for free.

## 3. Target architecture

```
┌───────────────────────── Desktop shell (§5) ─────────────────────────┐
│  UI  (web tech)                                                      │
└──────────────┬───────────────────────────────────────────────────────┘
               │ HTTP + SSE  (the only contract the UI knows)
┌──────────────▼───────────────────── Gladius backend ─────────────────┐
│  api/        /chat (streaming) /sessions /specialists /capabilities  │
│  core/       pipeline: Turn → [routing] → [rag] → [tools] → inference│
│  capabilities/  routing · rag · tools   (each enable/disable-able)   │
│  specialists/   registry.json  (single source of truth, A2)          │
│  embeddings/    one shared embedder, injected (A3)                   │
│  inference/     llama-server client + prompt formats                 │
└──────┬──────────────────────────────┬───────────────────┬────────────┘
       │ HTTP                         │ HTTP              │ stdio / HTTP
┌──────▼───────────┐       ┌──────────▼────────┐   ┌──────▼──────────┐
│ llama-server     │       │ llama-server      │   │ MCP tool servers│
│ chat: base+LoRAs │       │ --embedding model │   │ (files, …)      │
└──────────────────┘       └───────────────────┘   └─────────────────┘
```

The embedding server comes from the owner's earlier decision to drop sentence-transformers
for llama.cpp's embedding endpoint. One llama-server serves one model, so that's a second,
small instance. It's also what removes torch from the runtime (§5.2).

### 3.1 Package layout

```
gladius/
  core/
    pipeline.py      # builds the stage list from config and runs it over a Turn; no UI imports
    types.py         # Turn / Context: prompt, route, retrieved context, tool calls, stats
    config.py        # enabled capabilities, data dir, thresholds, ports
    sessions.py      # session store + turn log (moved out of retro.py)
  specialists/
    registry.json    # name, gguf path, prompt format, routing examples, RAG policy, UI label/colour
    registry.py
  inference/
    engine.py        # today's engine.py minus the hardcoded route tables
    formats.py       # chat / chat+prefix / raw+stop — chosen per registry entry
  embeddings/
    embedder.py      # client for the embedding llama-server; shared by routing + rag
  capabilities/
    base.py          # Capability interface (below)
    routing/         # router.py
    rag/             # retriever.py; per-route policy moves into the registry
    tools/           # local tools + MCP client
  api/
    server.py        # FastAPI app
  runtime/
    processes.py     # start/stop/health-check llama-server instances (replaces serve.sh/run.sh logic)
ui/                  # the real UI (§5); retro.py kept only until it's replaced
bench/               # bench.py, eval_sql_adapter.py, charts.py, data/*_eval.json
scripts/             # dev-only: setup.sh, serve.sh
```

### 3.2 Capability interface

```python
class Capability(Protocol):
    name: str
    def enabled(self, cfg: Config) -> bool: ...
    def process(self, ctx: Context) -> Context: ...      # routing sets ctx.route; rag adds ctx.context; …
    def tools(self) -> list[ToolSpec]: return []         # optional: functions the model may call
```

The pipeline is just `[c for c in capabilities if c.enabled(cfg)]` followed by inference.
Each capability reads what it needs from `Context` and the registry, never from another
capability. Today's cross-capability logic becomes explicit:

- `retriever.notes_route` (RAG overriding the router) → a step in the rag capability that
  may rewrite `ctx.route`, recorded in `ctx` so the UI can show it.
- Per-route RAG rules and the techwriter/sql branches in `augment` → fields on the
  specialist's registry entry (`rag: {collections, top_k, min_score, template}`).

Adding "file manipulation" = a new folder under `capabilities/tools/` (or an MCP server) + a
config flag. No edits to the UI, the pipeline, or other capabilities.

### 3.3 Tools note

Tool use needs a model that can call tools reliably. Llama-3.2-3B-Instruct supports the
Llama 3.2 tool-call format, but at 3B it's unreliable, and a LoRA may degrade it further.
Plan for: tools run on the `base` route only at first, with a constrained JSON grammar
(llama-server supports grammars/JSON schema), and **every file write or delete is confirmed
in the UI**. This needs its own eval set before it ships.

## 4. Can this be a real app for non-technical users?

**Yes.** Nothing in Gladius requires a terminal. It needs one today only because the
install path is a developer's (A4). The work is packaging and lifecycle, not new ML.

What a non-technical student needs, and what stands in the way today:

| Need | Today | Fix |
|---|---|---|
| Double-click install | `./setup.sh` | Signed installer (`.dmg` / `.msi`) |
| No compiler | Builds llama.cpp from source | Ship llama.cpp's prebuilt release binaries (Metal on macOS), pinned to the benchmarked commit |
| No Python install | `.venv` + pip | Freeze the backend into one binary (PyInstaller) — feasible once torch is gone (§5.2) |
| No HF account / CLI | `huggingface_hub` downloads + local LoRA→GGUF conversion | Ship **pre-converted** adapter GGUFs (converted at our build time); first-run download with progress + resume + checksums |
| App opens and closes like an app | `run.sh` starts servers, Ctrl-C to stop | Shell spawns llama-server(s) + backend as child processes, picks free ports, kills them on quit |
| Their files in a normal place | `models/`, `adapters/`, `results/` in the repo | `~/Library/Application Support/Gladius` (macOS), `%APPDATA%\Gladius` (Windows) |
| Not blocked by the OS | n/a | macOS signing + notarization (Apple Developer Program, $99/yr), otherwise Gatekeeper blocks the app; Windows signing, otherwise SmartScreen warns |
| Updates | `git pull` | Shell's built-in updater |

## 5. Desktop shell

### 5.1 Options

| Option | Shell RAM | Installer size (excl. models) | Notes |
|---|---|---|---|
| **Tauri** (Rust shell, OS webview) | ~30–80 MB | ~10 MB + backend | **Recommended.** Built-in sidecar processes, updater, signing. UI is plain web tech (React/Svelte), talking to `api/` |
| Electron | ~150–300 MB | ~100 MB+ | Most mature, but bundles Chromium. That RAM is real on an 8 GB machine with a 3 GB budget (`plan.md` §2) |
| Native Python UI (PySide6/Qt) | ~80–150 MB | ~100 MB | One language, but a dated look and harder to build polished chat UX |
| Local web app (backend serves UI, opens browser tab) | ~0 | backend only | Not a "real app", but the cheapest stepping stone, and the same `api/` + UI code moves into Tauri unchanged |

### 5.2 The backend: keep Python (for now)

Once embeddings move to llama.cpp, the runtime Python deps shrink to roughly
`fastapi`, `uvicorn`, `numpy`, `requests`, `psutil` (+ an MCP client). **No torch, no
sentence-transformers, no Streamlit.** That freezes into a ~30–60 MB PyInstaller binary
that Tauri runs as a sidecar. Torch/transformers stay **dev-only**, for converting adapters
at build time.

A later option: port the backend into the Tauri Rust process. The remaining logic (cosine
similarity, chunking, prompt templates, orchestration) is small, which would cut a process
and ~50 MB. Not worth it until the Python design settles.

### 5.3 Process lifecycle (runtime/processes.py + shell)

1. Shell starts → launches backend sidecar on a free port.
2. Backend reads `registry.json` → starts chat llama-server (base + enabled adapters) and
   embedding llama-server on free ports → waits for `/health` → warms adapters (today's
   `run.sh` warm-up loop, which hides macOS paging the model out).
3. UI shows a "starting specialists…" state until the backend reports ready. Errors (model
   missing, port in use, server crashed) surface as UI states, never terminal output.
4. Quit → backend stops its children. A watchdog kills orphans if the backend dies.

### 5.4 Knock-on effects on the other design docs

- **[`specialists.md`](specialists.md):** importing a local safetensors adapter needs
  llama.cpp's converter, which needs torch, too heavy to ship. For the app: a **specialist
  catalog** of pre-converted, smoke-tested GGUF adapters is the default path. Importing
  your own `.gguf` is supported; safetensors conversion stays a dev/advanced path. The
  base-model validation from the known footguns (wrong base, wrong dims, full models) runs
  on import either way.
- **[`rag.md`](rag.md):** "point it at my notes folder" becomes a native folder picker plus
  a background indexer with progress. The persistent index lives in the app data dir.
- **Settings/config UI** (left out of both docs): becomes a real screen in the app (enable
  capabilities, manage specialists, choose notes folders).

## 6. Phased plan

| Phase | Goal | Done when |
|---|---|---|
| 0. Modular core ✅ | Pull the pipeline out of `retro.py` into `core/`, no behaviour change (A1) | `retro.py` only draws; it drives `core.Pipeline` stage by stage (`route` → `retrieve` → `stream`) and saves through `core.SessionStore` |
| 1. Registry + shared embedder | `registry.json` replaces the 5 hardcoded lists (A2); embedder injected (A3); embeddings via llama.cpp | Add/remove a specialist by editing only the registry; routing LOO accuracy re-measured on the new embedder |
| 2. API | FastAPI `api/` with streaming `/chat`; `runtime/processes.py` owns llama-server lifecycle | A UI with no Python imports can hold a full chat |
| 3. Real UI, local web app | New web UI served by the backend; Streamlit dropped | Feature parity with `retro.py` (trace, sources, stats, sessions) |
| 4. Desktop app (macOS) | Tauri shell + frozen backend + prebuilt llama.cpp + first-run downloader | A fresh Mac with no dev tools installs from a `.dmg` and chats |
| 5. Distribution | Signing, notarization, auto-update; then Windows (CPU/Vulkan llama.cpp builds) | Gatekeeper/SmartScreen-clean installs; update ships without reinstall |
| 6. Tools | `capabilities/tools/` + MCP client; file tools with confirmation | Tool-call eval passes; no unconfirmed file writes |

**Phase 0 notes.** `core/` sits at the repo root for now, next to `engine.py`, `router.py` and
`retriever.py`. It moves under a `gladius/` package along with them in Phase 1. Checked by running the
old and new `retro.py` under Streamlit's `AppTest` on the same prompts, with the real router and
retriever and a fake embedder and llama-server. Saved turns, rendered answers and session
new/delete/clear all came out identical. One intended change: "adapter swapped" is now tracked
per `Pipeline` (llama-server state) rather than per browser tab.

Phases 0–2 are worth doing regardless of the app decision. Phase 4 can start in parallel
with 3, since the UI is shared.

## 7. Open questions

1. **Platforms.** macOS Apple Silicon only at first? Intel Macs and Windows mean more
   llama.cpp builds and slower CPU-only inference, possibly outside the latency targets.
2. **Model delivery.** First-run download (~2.3 GB, small installer) or bundle models in the
   installer (~2.5 GB `.dmg`, works fully offline from the start)? Hosting the downloads
   (HF repo vs own CDN) is part of this.
3. **Apple Developer account.** Needed for notarization; who owns it?
4. **UI framework** inside the shell (React vs Svelte vs plain): mostly team preference.
5. **Tools scope.** Which file operations, inside which folders? (Sandbox to user-chosen
   folders by default.)
6. **Licensing.** Llama 3.2 community license and each adapter's license must allow
   redistribution in a catalog. Check before Phase 4.
