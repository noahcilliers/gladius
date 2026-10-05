# Path 2 — Importing QLoRA specialists

> Status: design / proposal. Target: let a student add their own locally-held QLoRA
> specialist through one guided configuration flow, with the framework wiring up
> conversion, prompt format, and routing — no code edits, fully offline.

## 1. Where specialists are today

The four demo specialists (`math`, `techwriter`, `creative`, `coding`) are **hardcoded across
five files**. Adding or changing one means editing all of them, by hand, in sync:

| File | What's hardcoded |
|---|---|
| [`setup.sh`](../setup.sh) | `ADAPTERS=(...)` — HF repo per adapter, downloaded + converted to GGUF |
| [`serve.sh`](../serve.sh) | `--lora adapters/math.gguf,...` in a **fixed order**; a comment tracks the id→name mapping (`math=0 techwriter=1 ...`) |
| [`router.py`](../router.py) | `ROUTES = (...)` tuple; routing centroids come from `docs/example_prompts.md` |
| [`engine.py`](../engine.py) | `RAW_PROMPT_ROUTES` / `CHAT_PROMPT_ROUTES` — the per-adapter prompt format (the big footgun; see the SQL adapter saga) |
| [`retro.py`](../retro.py) | `ROUTES` label/colour dict, `CODE_ROUTES`, `STARTERS` |

This is fine for a curated demo and impossible for a student. The whole value of a
"one base model, swap tiny specialists" system is that the **set of specialists is the
user's to choose** — and today it isn't.

Two mechanics already lean the right way and we keep them:

- **Adapters are swapped per-request, not reloaded.** `serve.sh` preloads every adapter with
  `--lora-init-without-apply`; each request sends `scale: 1.0` for the chosen route and `0.0`
  for the rest (`engine.lora_for`). Swapping a specialist is a request parameter, ~<50 ms.
- **`engine.adapter_ids` re-reads the server's `/lora-adapters` every 2 s**, so the id→name
  map is already discovered at runtime rather than assumed — the registry below can change the
  adapter set and the engine follows along.

## 2. Goal

A student imports a QLoRA specialist they hold locally through **one guided configuration
flow** that handles, with no source edits:

1. **source** → a local GGUF adapter,
2. **prompt format** → the format the adapter was trained on,
3. **routing** → example prompts (suggested *or* supplied) averaged into a centroid,
4. **registration** → a single source of truth every component reads.

Everything is local. The adapter is downloaded/converted once to a local `.gguf`, and the
running system only ever references local paths — that's the whole point (offline, on the
laptop you own).

**UI is out of scope here** (moving off Streamlit to a real framework). This doc specifies the
**framework layer**: an adapter **registry** + a set of configuration operations the future
app's menu will drive. The "configure the whole LoRA thing" menu is described as a flow and a
contract, not as widgets.

## 3. Proposed design

### 3.1 One source of truth: the adapter registry

Replace the five scattered hardcodings with a single `adapters/registry.json`. Every
component reads from it instead of its own constants:

```jsonc
{
  "specialists": [
    {
      "name": "chemistry",
      "label": "⚗ CHEMISTRY",          // UI (future app) reads this
      "gguf": "adapters/chemistry.gguf", // LOCAL path only
      "base_model": "Llama-3.2-3B-Instruct",
      "enabled": true,
      "prompt_format": {                 // see §3.4
        "kind": "chat",                  // "chat" | "chat_prefix" | "raw"
        "prefix": null,                  // for chat_prefix, e.g. "Complete the following..."
        "template": null,                // for raw, with {prompt}/{schema} slots
        "stop": []
      },
      "routing": {                       // see §3.5
        "examples": ["Balance this redox reaction ...", "..."],
        "source": "suggested" | "user"
      },
      "rag": null,                        // optional ROUTE_RAG entry; default: no retrieval
      "code_output": false                // was CODE_ROUTES
    }
  ]
}
```

Then:

- `serve.sh` builds its `--lora` list from the enabled entries (order derived, not
  hand-maintained; `engine.adapter_ids` already discovers the ids at runtime).
- `router.py` builds `ROUTES` + centroids from `routing.examples` (so `example_prompts.md`
  becomes just the seed data for the bundled four, not the only source).
- `engine.py` reads `prompt_format` per route instead of `RAW_PROMPT_ROUTES` /
  `CHAT_PROMPT_ROUTES`.
- `retriever.py` reads the optional per-adapter `rag` block instead of hardcoded `ROUTE_RAG`.
- the future UI reads `label` / `code_output`.

### 3.2 The import flow (the "configure this entire LoRA thing" menu)

A framework operation — `add_specialist(...)` — that the future UI (or a thin CLI) drives,
one step at a time:

```
pick source → convert to local GGUF → declare prompt format → smoke test
   → routing examples (suggest or type) → confirm → register → (restart to activate)
```

### 3.3 Step 1–2: Source → local GGUF

Accept, in order of directness (everything ends as a **local** `.gguf`):

1. a **pre-converted `.gguf`** adapter → copy/point into `adapters/`, done.
2. a **local PEFT adapter folder** (the student's own QLoRA training output:
   `adapter_config.json` + `adapter_model.safetensors`) → run
   `convert_lora_to_gguf.py --base-model-id ...` (exactly as `setup.sh` does) → local `.gguf`.
3. **convenience:** an HF repo id → download the two files **once** to a local folder, then
   treat as case 2. After download, runtime never touches the network again.

**Validate before committing:** the adapter's base model / tensor dims must match our base
(`Llama-3.2-3B-Instruct`). A mismatched or full-model "adapter" should fail here with a clear
message — this is exactly how the SQL-adapter search wasted time (wrong base, too large, full
model). Try loading it into llama-server and bail cleanly if it rejects it.

### 3.4 Step 3: Prompt format (the footgun, made explicit)

This project's hardest-won lesson: **an adapter only helps when it gets the exact prompt
format it was trained on.** The SQL adapter went 2/10 → 8/10 purely from matching its raw
`### Context / ### Question / ### SQL` format (`engine.sql_prompt`); the coding adapter needs
its `Complete the following Python function:` prefix (`engine.coding_prompt`).

So the student **declares** the format, with presets mapping to the three kinds already in
`engine.py`:

| `kind` | Maps to today | When |
|---|---|---|
| `chat` | plain chat template | adapter trained with the standard chat template (most instruct LoRAs) |
| `chat_prefix` | `CHAT_PROMPT_ROUTES` | chat template + a fixed instruction prefix (`coding`) |
| `raw` | `RAW_PROMPT_ROUTES` + `/completion` + stop tokens | trained without the chat template, raw text format (old `sql`) |

Provide the presets plus a free-form `template` with `{prompt}` / `{schema}` slots for `raw`.
Then **smoke-test**: run one generation through the chosen format so the student sees the
output style immediately and can fix the format before it's locked in. (Auto-detecting the
format from `adapter_config.json` / tokenizer is unreliable — keep it a declared choice with
good presets.)

### 3.5 Step 4: Routing — suggest-or-edit centroid

The router is a **nearest-centroid classifier**: each route's centroid is the mean embedding
of ~15–20 example prompts (`router.py: centroids`). A new specialist needs its own example
set. The flow (as specified by the project owner):

1. The student gives a **name + one-line description** ("a chemistry tutor for first-year
   university chemistry").
2. The framework **generates ~15–20 candidate example prompts** from that description —
   **using the local base Llama model itself** (no API; it's already loaded and offline).
3. Present them: **"Are these the kinds of questions you'd ask this specialist?"**
   - **Yes** → embed them and **average into the centroid** (exactly as `_unit(v.mean(axis=0))`
     does today), tag `source: "suggested"`.
   - **Edit** → the student removes ones that don't fit and/or **types their own**; the final
     set is what gets averaged, tag `source: "user"`.
   - So: *we suggest, or they add* — both paths end at a centroid built from a confirmed
     example set.
4. **Check the decision boundary.** Adding a route moves the nearest-centroid boundaries.
   Re-run `router.leave_one_out()` and warn if the new specialist sits too close to an
   existing one (low separation / likely mis-routes), so the student can add more
   distinguishing examples before committing.

### 3.6 Step 5: Register + activate

- Write the registry entry (§3.1). The specialist is now visible to every component.
- **Activation needs a server restart** today — llama.cpp loads adapters at startup. The
  future app triggers the restart transparently; for now it's "re-run `./serve.sh`". (A later
  phase can explore hot-loading if llama.cpp support lands, but it's not assumed.)
- Optional `rag` block: a brand-new specialist defaults to **no retrieval** (safest — the demo
  adapters were fine-tuned *without* injected context, and loose context made several worse).
  A student can opt a specialist into retrieval later (see `docs/rag.md`).

## 4. File-level change list

| File | Change |
|---|---|
| new `registry.py` | load/validate `adapters/registry.json`; the `add_specialist()` flow (source→convert→format→routing→register) as callable steps |
| new `adapters/registry.json` | the four demo specialists migrated into it as seed data |
| `serve.sh` | build `--lora` from enabled registry entries instead of a hardcoded list |
| `router.py` | build `ROUTES` + centroids from the registry; keep `example_prompts.md` as seed data; expose a "boundary check" (leave-one-out) for a candidate specialist |
| `engine.py` | drive prompt format from `prompt_format` per route instead of `RAW_/CHAT_PROMPT_ROUTES` |
| `retriever.py` | read the optional per-adapter `rag` block instead of hardcoded `ROUTE_RAG` |
| `setup.sh` | reuse the shared convert step; seed the registry for the demo four |

## 5. Phasing

1. **Registry as source of truth** — migrate the demo four into `registry.json`; make
   `serve.sh` / `router` / `engine` / `retriever` read it. No behaviour change, big decoupling.
2. **`add_specialist()` for a local GGUF** (case 1) + registration + restart-to-activate.
3. **Convert path** (local PEFT folder, then HF-download-once) + base-model validation +
   smoke test.
4. **Suggest-or-edit routing** (base-model example generation → confirm/edit → centroid →
   boundary check).

## 6. Risks / open questions

- **Base-model compatibility.** Only Llama-3.2-3B LoRAs work. Validation (§3.3) must fail
  loudly and early; this was the single biggest time sink in the hackathon.
- **Generated examples quality.** Using the local base model to generate routing examples is
  elegant and offline, but a vague description yields weak examples → mushy routing. The
  confirm/edit step + boundary check (§3.5) are the guardrails.
- **Prompt format is still a human judgement.** Presets cover the known three kinds; an exotic
  training format may need the free-form `raw` template. The smoke test is how the student
  catches a wrong guess.
- **Restart to activate.** Acceptable for now; revisit only if llama.cpp gains reliable
  hot-loading.
- **Shared embedder.** Centroids use the same embedding model as retrieval — dropping Snowflake
  Arctic (see `docs/rag.md` §3.3) must land first or in lockstep, since it changes every
  centroid.
