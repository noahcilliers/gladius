# Gladius

```text
            ▄▄▄
            ███▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
▄███▄▄▄▄▄▄▄▄█████████████████████████████████████████▄▄▄
█████▓▒▓▒▓▒▓███▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒██████████━━╸
▀███▀▀▀▀▀▀▀▀█████████████████████████████████████████▀▀▀
            ███▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
            ▀▀▀

     ██████╗ ██╗      █████╗ ██████╗ ██╗██╗   ██╗███████╗
    ██╔════╝ ██║     ██╔══██╗██╔══██╗██║██║   ██║██╔════╝
    ██║  ███╗██║     ███████║██║  ██║██║██║   ██║███████╗
    ██║   ██║██║     ██╔══██║██║  ██║██║██║   ██║╚════██║
    ╚██████╔╝███████╗██║  ██║██████╔╝██║╚██████╔╝███████║
     ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═════╝ ╚═╝ ╚═════╝ ╚══════╝

     ▓▒░  one model · five specialists · zero cloud  ░▒▓
```

Short, sharp, specialist AI on the laptop you already own. Fully local, fully offline, fully open source.

## Problem

Students can't afford API bills, and their 8 GB laptops can't run big models. Small local models (1–3B) fit in memory, but they're mediocre at everything.

## The idea

Run **one small base model plus a set of tiny skill adapters** (math, SQL, coding, technical writing, creative). For each prompt, a lightweight router picks the right specialist and switches it on. You get specialist-quality answers for roughly the memory cost of one model.

- **Five specialists, one model:** the adapters add about 128 MB to a 2 GB base model, instead of five more 2 GB models.
- **Stays under 3 GB of RAM**, so it runs next to your browser on an 8 GB machine. No GPU needed.
- **Your data stays local:** schedules, syllabi and grades are read from local files and never uploaded.
- **Every response is measured:** route, confidence, time, RAM and quality compared with the plain base model.

## Pipeline

```
prompt
  │
  ▼
Embed (Arctic Embed xs) ──► Semantic cache ── hit ──┐
  │ miss                                            │
  ▼                                                 │
Router: nearest centroid → route + confidence       │
  │◄────────────────────────────────────────────────┘
  ▼
Retriever: route-gated chunks from your local notes
  │
  ▼
Llama 3.2 3B (Q4) + chosen LoRA adapter → answer
  │
  ▼
UI: answer · route · confidence · cache · time · RAM
```

1. **Embed:** the prompt becomes one vector, which the cache, router and retriever all reuse.
2. **Cache:** if a near-identical prompt was seen before, the earlier routing decision is reused.
3. **Route:** cosine similarity against each skill's centroid (the average of about 20 example prompts). Low scores fall back to the base model.
4. **Retrieve:** routes that benefit pull matching chunks from `data/student/` (for example, syllabus deadlines for an email to a professor, or a schema for SQL).
5. **Generate:** every adapter is preloaded in `llama-server`, and each request turns one on, so switching adapters doesn't reload anything.

Details: [docs/pipeline.md](docs/pipeline.md) · Plan and benchmarks: [docs/plan.md](docs/plan.md)

## Download

> _Coming soon: one-command install and packaged download._

<!-- TODO: download links / install script -->

## Run from source

```bash
./serve.sh              # terminal 1: llama-server with base model + adapters
streamlit run app.py    # terminal 2: chat UI
python bench.py         # optional: writes results/results.json
```

## Stack

| Layer | Choice |
|---|---|
| Base model | Llama 3.2 3B Instruct, GGUF Q4_K_M |
| Adapters | LoRA (GGUF): math, SQL, coding, techwriter, creative ([sources](docs/example_prompts.md)) |
| Inference | llama.cpp `llama-server` |
| Router + retrieval embeddings | Snowflake Arctic Embed xs via sentence-transformers |
| Vector math | NumPy (in memory, no vector DB) |
| UI | Streamlit |
| Metrics | psutil, `time.perf_counter` |

MIT License
