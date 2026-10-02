# Pipeline: Where the Data Travels

One prompt, start to finish. Everything runs locally on the laptop.

```
                         ┌──────────────────────────────┐
  (1) user prompt ──────►│  Chat UI                     │
      "find avg GPA      └──────────────┬───────────────┘
       per major"                       │ text
                                        ▼
                         ┌──────────────────────────────┐
                    (2)  │  Snowflake Arctic Embed (xs) │
                         │  text → 384-dim vector       │
                         └──────────────┬───────────────┘
                                        │ vector
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
                                        │ route name ("sql")      │
                                        │◄────────────────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                    (5)  │  Adapter manager             │
                         │  activate "sql" LoRA         │
                         │  (or none for "base")        │
                         └──────────────┬───────────────┘
                                        │ original prompt text
                                        ▼
                         ┌──────────────────────────────┐
                    (6)  │  Llama 3.2 3B (Q4) + LoRA    │
                         │  generates the answer        │
                         └──────────────┬───────────────┘
                                        │ answer + timings + RAM
                                        ▼
                    (7)  Chat UI shows answer, route, confidence,
                         cache hit/miss, swap ms, RAM
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
| 5 | Activate adapter | route name | active LoRA set | runtime (llama.cpp / PEFT) |
| 6 | Generate | **original prompt text** | answer text | base model + adapter |
| 7 | Display | answer + metadata | UI update | local web page |
| 8 | Log | timings, RAM, route | appended row | `results.json` |

## Key points

- **The vector never reaches the LLM.** It is only used to decide the route. The LLM gets the original text.
- **Two models, two jobs.** Arctic Embed (~90MB) decides *who* answers. Llama 3.2 3B (~2GB) *does* the answering.
- **One-time setup, not per prompt:** example_prompts.md → embed → centroids. Built once at startup.
- **Cache hit skips step 4 only.** Embedding still runs, because you need the vector to check the cache.

## Startup (once)

```
example_prompts.md ──► Arctic Embed ──► vectors ──► average per route ──► centroids (in memory)
base GGUF + adapter files ──► loaded into runtime
```
