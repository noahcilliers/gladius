# Pipeline: Where the Data Travels

One prompt, start to finish. Everything runs locally on the laptop.

```
                         ┌──────────────────────────────┐
  (1) user prompt ──────►│  Chat UI                     │
      "email my CS prof  └──────────────┬───────────────┘
       for an extension"                │ text
                                        ▼
                         ┌──────────────────────────────┐
                    (2)  │  Snowflake Arctic Embed (xs) │
                         │  text → 384-dim vector       │
                         └──────────────┬───────────────┘
                                        │ vector (reused by 3, 4, 4b)
                                        ▼
                         ┌──────────────────────────────┐
                    (3)  │  Semantic cache              │── hit ──┐
                         │  "seen something this close?"│         │
                         └──────────────┬───────────────┘         │
                                        │ miss                    │
                                        ▼                         │
                         ┌──────────────────────────────┐         │
                    (4)  │  Router                      │         │
                         │  vector · each centroid      │         │
                         │  → scores → pick best route  │         │
                         └──────────────┬───────────────┘         │
                                        │ route name ("base")     │
                                        │◄────────────────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                   (4b)  │  Retriever (student corpus)  │
                         │  route → which collections   │
                         │  vector · chunk vectors      │
                         │  → top-k above threshold     │
                         └──────────────┬───────────────┘
                                        │ route + context chunks
                                        ▼
                         ┌──────────────────────────────┐
                    (5)  │  Adapter manager             │
                         │  activate route's LoRA       │
                         │  (or none for "base")        │
                         └──────────────┬───────────────┘
                                        │ context block + original prompt
                                        ▼
                         ┌──────────────────────────────┐
                    (6)  │  Llama 3.2 3B (Q4) + LoRA    │
                         │  generates the answer        │
                         └──────────────┬───────────────┘
                                        │ answer + timings + RAM
                                        ▼
                    (7)  Chat UI shows answer, route, confidence,
                         cache hit/miss, sources used, swap ms, RAM
                                        │
                                        ▼
                    (8)  results.json  (benchmarks)
```

## Step by step

| # | Stage | Input | Output | Where it lives |
|---|---|---|---|---|
| 1 | Chat UI | user typing | prompt text | local web page |
| 2 | Embed | prompt text | 384-dim vector | `router.py` (Arctic Embed) |
| 3 | Cache lookup | vector | cached route, or miss | `router.py` (in memory) |
| 4 | Route | vector | route name + scores | `router.py` (centroids) |
| 4b | Retrieve | vector + route name | 0–k chunks + scores | `retriever.py` (numpy, in memory) |
| 5 | Activate adapter | route name | active LoRA set | runtime (llama.cpp / PEFT) |
| 6 | Generate | **context block + original prompt text** | answer text | base model + adapter |
| 7 | Display | answer + metadata | UI update | local web page |
| 8 | Log | timings, RAM, route, retrieval scores | appended row | `results.json` |

## Key points

- **The vector never reaches the LLM.** It is used to pick the route and the chunks. The LLM gets text: retrieved chunks plus the original prompt.
- **One embedding, three jobs.** The step 2 vector is used by the cache, the router and the retriever. RAG adds no extra embedding call per prompt.
- **Routing is unaffected by RAG.** The router only sees the raw prompt, so centroids and leave-one-out accuracy don't change.
- **Two models, two jobs.** Arctic Embed (~90MB) decides *who* answers and *what context* they get. Llama 3.2 3B (~2GB) *does* the answering.
- **Cache hit skips step 4 only.** Embedding still runs (it's needed to check the cache), and retrieval still runs, because the cache stores routes, not context.
- **Student data never leaves the laptop.** Schedules, deadlines and grades stay local. This is part of the pitch.

## Step 4b: Retrieval

### Corpus

Lives in `data/student/` (see its README). Three collections, one per folder:

| Collection | Source | Used for |
|---|---|---|
| `profile` | `profile.md` | Who the student is: major, courses, professors, weekly schedule |
| `courses` | `courses/*.md` | Syllabi, deadlines, late policies, exam dates, assignment specs |
| `schemas` | `schemas/*.md` | Class database schemas (for the `sql` route) |

Chunking: **one `##` section = one chunk**. Headings are written to stand alone (e.g. "CS 301 — Exam dates"), so a chunk makes sense without its file.

### Route-gated retrieval

The LoRA adapters were fine-tuned on prompts without injected context. Giving every adapter a long preamble could make some of them worse. So each route decides what it gets:

| Route | Always prepend profile? | Search collections | top-k | Why |
|---|---|---|---|---|
| `base` | yes | `courses` | 3 | Personal questions: emails, deadlines, study plans |
| `sql` | no | `schemas` | 1 | Text-to-SQL adapters are trained on *schema + question*, so this matches their training format |
| `creative` | no | `courses` | 2 | Essay prompts and reading lists, only if they clear the threshold |
| `math` | no | — | 0 | GSM8K-style adapter; keep its input clean |
| `techwriter` | no | — | 0 | Not student-specific |

A chunk is injected only if its score ≥ `RAG_THRESHOLD`. If nothing clears it, the prompt goes through unchanged, so "derivative of x³·sin(x)" stays clean.

### Embedding: query vs. document

Arctic Embed is **asymmetric**:
- **User prompt:** `prompt_name="query"` (the same vector the router already computed).
- **Corpus chunks:** **no prefix**.

The router uses the query prefix on both sides because example prompts *are* queries. Retrieval compares a query to documents, so the chunks must be embedded without it.

```python
# startup
chunk_vecs = model.encode(chunk_texts, normalize_embeddings=True)            # no prefix

# per prompt (prompt_vec comes from step 2)
cfg = ROUTE_RAG[route]                                   # from the table above
idx = [i for i, c in enumerate(chunks) if c.collection in cfg.collections]
scores = chunk_vecs[idx] @ prompt_vec
picked = [chunks[idx[j]] for j in scores.argsort()[::-1][:cfg.top_k]
          if scores[j] >= RAG_THRESHOLD]
```

### Prompt assembly (step 6 input)

```
<system>
You are a study assistant for this student. Use the context below if it is relevant.
If the context doesn't answer the question, say so instead of guessing.

## Student profile
...profile.md (base route only)...

## Context
[courses/cs301.md · CS 301 — Late policy and extensions]
...
</system>
<user> original prompt </user>
```

The UI lists the `[file · heading]` tags under the answer as "sources used".

### Tuning knobs (in `retriever.py`)

| Setting | Default | What it does |
|---|---|---|
| `RAG_THRESHOLD` | 0.30 | Chunks scoring below this are dropped. Calibrate like `ROUTE_THRESHOLD` |
| `MAX_CONTEXT_TOKENS` | 700 | Hard cap on the context block (profile ~120 + 3 chunks × ~200) |
| `ROUTE_RAG` | table above | Per-route profile / collections / top-k |

The defaults are guesses. Calibrate them on the personal eval prompts in `example_prompts.md`.

### Budget impact

- **Index RAM:** negligible. 1,000 chunks × 384 dims × 4 bytes ≈ 1.5MB. No vector DB.
- **Retrieval latency:** one matrix multiply, well under 1ms.
- **The real cost is context length.** Every injected token uses KV cache (≤ 0.75GB budget) and adds time to first token. `MAX_CONTEXT_TOKENS` keeps this bounded. Report TTFT with and without RAG.

## Startup (once)

```
example_prompts.md ──► Arctic Embed (query prefix) ──► vectors ──► average per route ──► centroids
data/student/**.md ──► split on "##" ──► Arctic Embed (no prefix) ──► chunk vectors + metadata
base GGUF + adapter files ──► loaded into runtime
```
