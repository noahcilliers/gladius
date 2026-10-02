# Hackathon Plan: Local Specialists on an 8GB Laptop

**Theme:** Open Source AI
**Format:** 4 hours (idea, execution, demo/presentation)
**Working name:** _TBD_ (e.g. "SkillSwap", "PocketExperts", "AdapterRouter")

---

## 1. Pitch

Students can't afford API bills, and their laptops can't run big models. Small local models (1–3B) fit in memory but are mediocre at everything.

**Our answer:** one small base model plus a set of tiny "skill" adapters (math, code/SQL, writing, etc.). For each prompt, a lightweight router picks the right specialist and hot-swaps it in. You get specialist-quality answers for roughly the memory cost of one small model, on an 8GB laptop, fully offline, fully open source.

> "Three specialists for the price of one model, on the laptop you already own."

---

## 2. Hard Constraint: 8GB RAM

The 8GB laptop is the target user's machine. The OS and browser take a big share, so we budget conservatively.

| Component | Budget |
|---|---|
| OS + browser + everything else | ~4–5 GB (not ours) |
| Base model (1.5–3B, 4-bit) | ≤ 2.0 GB |
| Adapters (each, LoRA rank ~8–16) | ≤ 50 MB each, ≤ 150 MB total |
| Embedding model for router | ≤ 100 MB |
| KV cache + runtime overhead | ≤ 0.75 GB |
| **Total framework peak RAM target** | **≤ 3 GB** |

Rules:
- Every benchmark reports **peak RAM**; anything over 3 GB is a failure.
- Disk footprint for base model + all adapters should stay **≤ 2.5 GB**.
- No GPU required. The demo should work on a base-model MacBook Air.

---

## 3. Architecture

```
prompt
  │
  ▼
[Semantic cache] ── hit ──► cached adapter choice
  │ miss
  ▼
[Router] embed prompt → cosine sim vs adapter centroids
  │
  ├─ best sim ≥ threshold → load/apply that adapter
  └─ below threshold       → base model only
  │
  ▼
[Base model + active adapter] → generate
  │
  ▼
(stretch) entropy check on first ~20 tokens → re-route if very uncertain
```

### Components
1. **Base model:** one small instruct model, 4-bit quantized (e.g. a ~1.5–3B Qwen/Llama-class model via MLX or Ollama).
2. **Adapters:** 2–3 LoRA adapters trained for that exact base model. Each needs a task where the improvement is easy to see:
   - Math word problems (GSM8K-style)
   - SQL / code
   - One domain or style adapter (e.g. study-guide/flashcard formatting)
3. **Router:** a small sentence-embedding model. Each adapter gets a centroid built from 20–50 example prompts. Similarity to the nearest centroid is the "confidence."
4. **Semantic cache:** stores (prompt embedding → routing decision). If a new prompt is within the similarity threshold of a cached one, it reuses the decision and skips routing. We track hit rate.
5. **UI:** a simple local chat page that shows, for each prompt, the chosen adapter, confidence bar, cache hit/miss, swap time, and RAM.

### Terminology note
Adapters may be *trained* with QLoRA, but at inference this is **LoRA adapter routing on a quantized base**. Pitch it that way.

---

## 4. Benchmarks

The framework tracks four things: **size, RAM, time, and quality**.

### 4.1 Size (disk)
| Setup | What we measure |
|---|---|
| Base model only | GB on disk |
| Base + N adapters (ours) | GB on disk |
| N separate full fine-tuned models (hypothetical) | N × base size |

Headline: "3 specialists = base + ~X MB, versus 3× the base as separate models."

### 4.2 RAM
- Peak RAM during load, routing, swap, and generation
- Steady-state RAM with all adapters warm vs. loaded on demand
- Pass/fail against the 3 GB budget

### 4.3 Time
- Router latency (embed + similarity), ms
- Cache-hit latency, ms
- Adapter swap time, ms
- Time to first token
- Tokens/sec (base vs. with adapter)
- End-to-end latency per prompt

### 4.4 Quality
A small, honest eval: ~20–25 prompts per task.

| Config | Math acc. | SQL acc. | Routing acc. |
|---|---|---|---|
| Base only | | | n/a |
| Always correct adapter (oracle) | | | 100% |
| **Our router** | | | |

- **Routing accuracy:** did the router pick the intended adapter?
- **Gap to oracle:** how much quality the router loses vs. perfect routing.

### Measurement notes
- Peak memory: use the runtime's peak-memory API (MLX exposes one) plus process RSS (`psutil`).
- Timing: `time.perf_counter()` around each stage; average over several runs and discard the first (warm-up).
- Fix seed and `temperature=0` for quality evals.
- All results go to one `results.json` that drives the charts in the demo.

---

## 5. Pre-Hackathon Prep (check rules first)

- [ ] Confirm whether pre-built components / pre-trained adapters are allowed
- [ ] Pick base model; confirm it runs on target hardware under the RAM budget
- [ ] Get 2–3 adapters for that exact base (download from Hugging Face, or train tonight with `mlx_lm.lora` if allowed)
- [ ] Write 20–50 example prompts per adapter (router centroids)
- [ ] Prepare eval sets (~20–25 prompts per task, with answers)
- [ ] Install everything and download weights tonight; don't rely on venue Wi-Fi

---

## 6. 4-Hour Timeline

| Time | Goal | Done when |
|---|---|---|
| 0:00–0:45 | Base model + adapters load; measure swap time and RAM | One adapter swap works and has a number |
| 0:45–1:45 | Router + semantic cache | Prompts route correctly with a confidence score |
| 1:45–2:45 | UI showing routing decision, confidence, swap time, RAM | Live demo works end to end |
| 2:45–3:30 | Run benchmarks, generate charts from `results.json` | Size/RAM/time/quality tables filled |
| 3:30–4:00 | Slides + rehearse demo twice | Under time limit, backup video recorded |

**Cut order if behind:** entropy re-routing → cache → third adapter → UI polish. Never cut the benchmarks.

---

## 7. Demo Script (~3 min)

1. **Problem (30s):** students, 8GB laptops, no API budget, small models are mediocre.
2. **Live demo (90s):** three prompts (math, SQL, casual chat). Show the router picking a specialist, the confidence bar, swap time, and RAM staying under budget. Run one prompt twice to show a cache hit.
3. **Numbers (45s):** size chart (base + adapters vs. separate models), RAM under 3 GB, routing overhead in ms, accuracy base vs. routed vs. oracle.
4. **Prior art + positioning (15s):** LoraRetriever, LoRAX, and vLLM do adapter routing/serving for servers and research. We bring it to an 8GB student laptop with one command.

**Backup:** screen recording of a working run, in case the live demo fails.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Adapter swap is slow | Keep adapters warm (they're small) or use one Ollama model per adapter |
| Adapters don't visibly help | Choose tasks with obvious gains; verify before the event |
| Over RAM budget | Drop to a 1.5B base; reduce context length |
| Router misroutes | More centroid examples; lower threshold falls back to base |
| Venue hardware/Wi-Fi | Everything downloaded and tested beforehand |

---

## 9. Stretch Goals
- Entropy-based re-routing mid-generation
- Mixing two adapters for cross-domain prompts
- "Add your own skill": drop a new adapter + 20 example prompts into a folder and it's routable
- One-command install script
