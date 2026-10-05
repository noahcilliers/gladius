# Path 1 — Real, working RAG over a student's own notes

> Status: design / proposal. Target: turn the demo retriever into something a real
> student can point at their own folder of notes and have it just work, fully offline.

## 1. Where RAG is today

All retrieval lives in [`retriever.py`](../retriever.py). At startup it:

- walks `data/student/**.md`, splits each file on `##` headings, and treats **one
  `##` section = one chunk** (`load_chunks`). `README.md` and the `#` title are skipped.
- embeds every chunk with the **router's** Snowflake Arctic Embed model (reused, so no
  second model in memory) into an in-memory NumPy matrix (`Retriever.__init__`).
- gates retrieval **per route** via the hardcoded `ROUTE_RAG` table: each route declares
  which folder-collections it may see (`courses`, `syllabi`, `notes`, `schemas`,
  `profile`), a `top_k`, and sometimes a strict `min_score`.
- keeps a chunk only if it clears `RAG_THRESHOLD = 0.57` **or** beats the prompt's median
  chunk score by `RAG_MIN_GAP = 0.14` (`search`).
- layers several demo-specific heuristics on top: a `profile.md` block, a 10-day calendar
  deadline window (`upcoming`), `_PERSONAL_RE` / `_LOGISTICS_RE` regexes, and
  `notes_route()` which reroutes a specialist prompt back to `base` when it's really a
  question about the student's own courses.

It works well — on **one fictional student and one 21-prompt eval set**
(`data/rag_eval.json`): 90% hit rate, 82% recall, 0/4 false injections.

### Why it isn't "real" yet

| # | Problem | Evidence in code |
|---|---|---|
| 1 | **Corpus is a fixed fictional student.** There's no way to point it at *your* notes. | `CORPUS_DIR = data/student`, folder-name collections baked into `ROUTE_RAG` |
| 2 | **Thresholds are overfit to one corpus + one embedder.** `0.57` / `0.14` were hand-calibrated against `rag_eval.json`. A different corpus or embedding model invalidates them. | comments at `RAG_THRESHOLD`, `NOTES_OVERRIDE_MIN = 0.68`, `min_score=0.70` |
| 3 | **Heuristics are hardcoded to the demo's data shape.** Calendar line regex, "profile" convention, personal/logistics word lists only make sense for this student. | `_CAL_LINE_RE`, `_PERSONAL_RE`, `_LOGISTICS_RE`, `profile_block` |
| 4 | **Embeddings come from Snowflake Arctic via `sentence-transformers`.** We want to drop that dependency and run a model we hold locally. | `router.py: EMBED_MODEL`, `SentenceTransformer(...)` |
| 5 | **No persistence.** The whole corpus is re-embedded on every launch. Fine for ~40 demo chunks, not for a real notes folder. | `Retriever.__init__` always calls `model.encode(...)` |
| 6 | **Markdown-`##`-only chunking.** A `.txt` file or a long section with no sub-headings chunks badly. | `load_chunks` |

## 2. Goals

1. A student runs one command pointing Gladius at **a folder of their own `.md` / `.txt`
   notes**, and retrieval works **without re-tuning any magic number**.
2. **Fully local, fully offline.** One-time local download of the embedding model, then the
   running system only reads local files. No API, no runtime network calls.
3. **Robust across corpora:** the gate adapts to the corpus and embedder instead of relying
   on constants fitted to the demo.
4. **Persistent index:** embed once, cache to disk, re-embed only changed files.
5. **Decoupled from demo heuristics:** profile / calendar / "about me" logic becomes optional
   and generic, so an arbitrary corpus still retrieves correctly.
6. **Provable:** a student can run an eval on *their* corpus and get hit-rate / recall /
   false-injection numbers, the same way we do today.

Out of scope for this doc: the application UI (moving off Streamlit to a real framework).
Everything here is a **UI-agnostic framework layer** the new app will call. File formats
beyond Markdown/TXT are explicitly deferred (students convert to `.md`/`.txt` for now).

## 3. Proposed design

### 3.1 Workspace, not a fixed corpus

Introduce a **workspace**: a directory of the student's notes that Gladius indexes.

- `GLADIUS_WORKSPACE=/path/to/my/notes` (env var / config key) replaces the hardcoded
  `CORPUS_DIR`. `data/student/` stays as the bundled sample workspace for the demo and tests.
- **Collections become generic.** Today they're the fixed folder names under
  `data/student/`. Generalize to: *top-level subfolder name = collection* (so a student can
  still organize by `courses/`, `lectures/`, whatever), with a single default collection for
  loose files at the root. `ROUTE_RAG` stops hardcoding collection names (see §3.5).
- Keep two **optional conventions**, both no-ops if absent: a `profile.md` (the "about me"
  block) and a `calendar.md` (dated lines). A real student opts in by creating them; nothing
  breaks if they don't.

### 3.2 Chunking that survives real files

Keep the good instinct (`##` section = chunk) but make it robust:

- Markdown: split on `##` as today, **but** further split any section whose token estimate
  exceeds a cap (~`MAX_CONTEXT_TOKENS`-aware) into overlapping sub-chunks.
- `.txt` and heading-less files: fall back to a token-bounded splitter with small overlap.
- Carry `source` + `heading` (or a synthesized heading from the first line) so the
  `[file · heading]` "sources used" display keeps working.

### 3.3 Local embedding model (drop Snowflake Arctic)

The embedder is shared by the router (centroids) and the retriever (chunk vectors), so this
is a cross-cutting change — see also `docs/specialists.md` §routing.

**Recommendation:** serve a **GGUF embedding model through the llama.cpp stack we already
build** (llama-server's embedding endpoint), e.g. `nomic-embed-text-v1.5` or
`bge-small-en-v1.5`. Benefits:

- one inference engine for generation *and* embeddings; no `sentence-transformers`, no
  Snowflake, no second Python ML stack in memory;
- the model is a local `.gguf` we download once — matches the offline thesis exactly.

Abstract this behind a small `Embedder` interface (`encode_query`, `encode_documents`) so
router and retriever share one instance, exactly as they share the Arctic model today. Each
model has its **own asymmetric prefix convention** (Arctic: `query` prefix vs none; nomic:
`search_query:` / `search_document:`; bge: an instruction prefix) — encode that in the
`Embedder`, don't scatter it.

> **Open decision:** which local embedding model. Trade-offs are dimension size (index RAM),
> retrieval quality on student notes, and GGUF availability. Defaulting to a small bge/nomic
> GGUF; revisit after the eval harness (§3.6) can measure candidates head-to-head.

### 3.4 Persistent index

- On index build, write chunk vectors (`.npy`) + chunk metadata (`.json`) into a cache dir
  keyed by `(embedding model id, file content hash)`.
- On launch, load the cache; re-embed **only** files whose hash changed (added/edited/
  deleted). First run embeds everything; subsequent runs are near-instant.
- Stay with **NumPy matmul** — it's a single dot product and trivially fast to tens of
  thousands of chunks (the current index is ~1.5 MB for ~40 chunks). Document the ceiling and
  name the local upgrade path (sqlite-vec / hnswlib / faiss, all offline) for when a student
  has a very large corpus. No hosted vector DB — ever.

### 3.5 Retrieval gating that calibrates itself

Replace the two fitted constants (`RAG_THRESHOLD`, `RAG_MIN_GAP`) and the scattered
per-route `min_score` values with a gate that **adapts to the corpus and embedder**:

1. **Primary signal — per-prompt outlier test.** Keep a chunk only if its score is a strong
   outlier above *this prompt's own* score distribution over the corpus (e.g. top score and a
   z-score / relative-gap test against the distribution). This is corpus- and
   embedder-relative, so it survives swapping the embedding model. The current `median + gap`
   rule is a crude version of this — promote it to the main mechanism.
2. **Optional per-corpus calibration.** At index time, estimate the on-topic vs off-topic
   score bands by sampling (chunk-vs-own-neighbourhood for "relevant", chunk-vs-random for
   "off-topic") and set the floor from *that corpus*, not a constant.
3. The absolute floor, if kept at all, is derived from the embedding model's score
   distribution, not pasted in.

Net: no number in the file should only be valid for `data/student/` + Arctic.

### 3.6 Decouple the demo heuristics

- `profile.md` / `calendar.md`: optional (§3.1). `upcoming()` / `profile_block()` run only if
  the files exist; otherwise skipped cleanly.
- `_PERSONAL_RE` / `_LOGISTICS_RE`: these exist to answer "is this prompt about the student's
  own corpus?" Replace the hand-written word lists with a **retrieval-score decision**: if the
  corpus answers the prompt strongly, treat it as a corpus question. That's embedder-relative
  and corpus-agnostic.
- `notes_route()` (reroute specialist → base when it's really a corpus question): keep the
  behaviour but drive it from the same retrieval-score signal, not the hardcoded
  `NOTES_OVERRIDE_ROUTES` + `0.68` constant.

### 3.7 Eval harness for *your* corpus

Generalize `evaluate()` so it reads an optional `eval.json` living **inside the workspace**
(expected headings per prompt + negative controls that should retrieve nothing). Report hit
rate, recall, and false-injection rate — the same three numbers we trust today. This is how
"it actually works" is demonstrated on real data instead of asserted. If a student has no
eval set, auto-generate negative controls (random off-topic prompts) so at least false
injection is measured.

## 4. File-level change list

| File | Change |
|---|---|
| `retriever.py` | workspace dir + generic collections; robust chunker; persistent index; adaptive gate; optional profile/calendar; retrieval-score "about me" decision; generalized `evaluate()` |
| `router.py` | swap `SentenceTransformer`/Arctic for the shared local `Embedder`; keep the asymmetric-prefix contract |
| new `embedder.py` | `Embedder` interface over llama.cpp embeddings (or chosen local model), with per-model prefix handling |
| `serve.sh` / `setup.sh` | download the embedding GGUF locally; (optionally) run llama-server with embeddings enabled |
| `requirements.txt` | likely drop `sentence-transformers` once the embedder moves to llama.cpp |
| `data/student/` | stays as the bundled sample workspace + its `eval.json` |

## 5. Phasing

1. **Embedder swap** behind the `Embedder` interface; re-run the existing RAG eval to
   re-establish a baseline on the new model. (Unblocks everything; also unblocks
   `docs/specialists.md`.)
2. **Adaptive gate** replacing the fitted constants; prove parity on `data/student/`.
3. **Workspace + robust chunking + persistence**; index an arbitrary external folder.
4. **Decouple heuristics**; generalized `evaluate()` + auto negative controls.

## 6. Risks / open questions

- **Re-tuning on a new embedder.** Dropping Arctic resets retrieval quality; the adaptive gate
  must be in place or we just move the magic numbers. Mitigated by doing the embedder swap and
  the eval harness first.
- **Embedding model choice** (§3.3) — unresolved; measure, don't guess.
- **Chunk quality on messy `.txt`.** Heading-less notes chunk worse; overlap + size cap help
  but won't match clean markdown.
- **Losing demo polish.** The profile/calendar/"what's due this week" behaviour is a big part
  of the current wow factor; keep it working for the sample workspace while making it optional.
