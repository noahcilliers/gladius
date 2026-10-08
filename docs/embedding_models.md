# Embedding models

> Status: analysis / proposal (2026-10-07). Feeds the open decision in
> [`rag.md`](rag.md) §3.3 and the shared embedder in [`architecture.md`](architecture.md).

## Summary

Move the runtime to llama.cpp first and keep Arctic; change the model only after measuring.
"Swap the embedding model" is really two decisions:

- **Runtime:** sentence-transformers + torch → llama.cpp's embedding server. This is where
  almost all the benefit is (about 450 MB RAM, and torch leaves the shipped app).
- **Model:** Snowflake Arctic Embed xs → something else. This is where almost all the cost
  is: every tuned threshold and eval baseline resets.

Arctic Embed is already fully offline. It is an Apache-2.0 model we download, not a Snowflake
service. It is a plain BERT model, so llama.cpp should be able to serve it as a GGUF. That
makes the runtime change possible without the model change.

## What Arctic costs today

The Python ML stack around Arctic costs about 470 MB of RAM; the model itself only costs
about 20 MB. Measured on 2026-10-07 in the project `.venv` (CPU, sentence-transformers):

| Measure | Value |
|---|---|
| RAM after importing torch + sentence-transformers | ~470 MB |
| RAM added by loading arctic-embed-xs | ~20 MB |
| Share of current peak RAM (3.31 GB, [`results/summary.md`](../results/summary.md)) | ~15% |
| Disk: torch + transformers in site-packages | ~700 MB (587 MB + 115 MB) |
| Encode latency | 3.5 ms per prompt |
| Embedding size | 384 dimensions |
| Max input | 512 tokens |
| Longest chunk in the sample corpus | ~225 tokens (69 chunks) |

Arctic is asymmetric: queries get the prefix
`Represent this sentence for searching relevant passages: `, documents get none. The router
uses the query prefix on both sides.

## Benefits

The runtime change gives the packaging and RAM win; a new model mainly buys longer inputs and
some retrieval quality.

**From the llama.cpp runtime (any model):**

- About 450 MB of RAM back at runtime.
- torch and transformers become dev-only (still needed to convert adapters). The backend then
  freezes to about 30–60 MB ([`architecture.md`](architecture.md) §5.2).
- One inference engine for both generation and embeddings.

**From a different model:**

- **Longer inputs.** 512 tokens becomes 8192 (nomic-embed-text-v1.5) or 32k
  (Qwen3-Embedding-0.6B). No effect on the sample corpus. Real notes sections will exceed 512
  and be silently cut off, unless the chunk-size cap in [`rag.md`](rag.md) §3.2 lands first.
- **Some retrieval quality.** Arctic-xs is the smallest model in its family. bge-small and
  nomic score a few points higher on public retrieval benchmarks (approximate, from memory).
  Whether that shows on our 21-prompt RAG eval is unknown.

## Costs and risks

The big cost of a new model is losing every tuned number and every eval baseline at once.

1. **Tuned thresholds break.** About nine constants were fitted to Arctic's score range, which
   bunches around 0.58–0.80. A new model scores differently, so all of them become wrong
   together:
    - [`router.py`](../router.py): `ROUTE_THRESHOLD` 0.55, `BASE_BIAS` 0.01, `MARGIN_WARN`
      0.03, `CACHE_THRESHOLD` 0.92.
    - [`rag/retriever.py`](../rag/retriever.py): `RAG_THRESHOLD` 0.57, `RAG_MIN_GAP` 0.14,
      `NOTES_OVERRIDE_MIN` 0.68, per-route `min_score` 0.68 / 0.70.
2. **Eval baselines reset.** Routing 95% leave-one-out and 94% held-out (n=35). RAG 90% hit
   rate, 82% recall, 0/4 false injections.
3. **Query prefixes stop being automatic.** sentence-transformers adds Arctic's prefix via
   `prompt_name="query"`. With llama.cpp we prepend it by hand, and each model differs: nomic
   uses `search_query:` / `search_document:` (likely `classification:` for the router); Qwen3
   puts an instruction line on queries only. A wrong prefix raises no error; quality just
   drops. Same trap as the adapter prompt format.
4. **llama-server config traps.** Pooling must match the model: CLS for Arctic and bge, mean
   for nomic, last-token for Qwen3. For BERT-style models the batch size (`-ub`) must fit the
   whole input. The default is 512, so a long-context model needs `-c` and `-ub` raised to get
   long context.
5. **A second process.** One llama-server serves one model, so embeddings need their own
   instance to start, health-check and shut down. Each embed adds about 1 ms of localhost HTTP.
6. **Bigger index.** 384 dimensions become 768 or 1024. Trivial at student scale:
   10k chunks × 1024 dims × 4 bytes ≈ 40 MB.

## Candidate models

Arctic-xs, bge-small and nomic are small BERT-style encoders; Qwen3-Embedding-0.6B is a much
larger decoder model. Arctic-xs RAM is measured; the other sizes are approximate, from memory.

| Model | Params | Dims | Max input (tokens) | Weights in RAM (approx.) | Pooling | Query / document prefix | Retuning needed |
|---|---|---|---|---|---|---|---|
| snowflake-arctic-embed-xs (current) | 22M | 384 | 512 | ~20 MB (measured) · ~90 MB F32 GGUF | CLS | `Represent this sentence for searching relevant passages: ` / none | None if GGUF scores match |
| bge-small-en-v1.5 | 33M | 384 | 512 | ~70 MB F16 | CLS | Instruction prefix / none | All thresholds |
| nomic-embed-text-v1.5 | 137M | 768 (can truncate to 256/512) | 8192 | ~150 MB Q8 · ~275 MB F16 | Mean | `search_query:` / `search_document:` | All thresholds |
| Qwen3-Embedding-0.6B | 600M | 1024 (can truncate) | 32k | ~650 MB Q8 | Last token | `Instruct: …\nQuery:` / none | All thresholds |

## Llama-style (decoder) embedders

If "Llama architecture" means an embedder built on a decoder LLM, only Qwen3-Embedding-0.6B is
realistic on an 8 GB machine.

- **Reusing our Llama-3.2-3B base:** no extra RAM, but don't. It isn't trained for embeddings,
  so it retrieves badly. It gives 3072-dimension vectors. With `-np 1`, every embed would wait
  behind text generation.
- **Llama/Mistral-based embedders** (e5-mistral, LLM2Vec-Llama-3, NV-Embed) are 7–8B
  parameters. They don't fit next to the 3B model.
- **Qwen3-Embedding-0.6B** has official GGUFs, 32k context and instruction support, and is
  clearly stronger than Arctic-xs. It is about 30× the size and slower per embed (estimated
  tens of ms, not measured). First-time indexing of a large folder takes minutes, not seconds.
  Its ~650 MB roughly cancels what dropping torch saves.

## Recommendation

Do the runtime change and the model change as two separate steps, so each can be measured on
its own.

1. **Change the runtime, keep the model.** Convert arctic-embed-xs to an unquantized
   (F32/F16) GGUF with llama.cpp's `convert_hf_to_gguf.py`. Serve it from a second
   llama-server with `--embeddings --pooling cls`. Put it behind the planned `Embedder`
   interface, then re-run `router.py` and the RAG eval. If the numbers match, we get the
   ~450 MB and packaging win with no retuning.
2. **Build the self-adjusting gate** ([`rag.md`](rag.md) §3.5) so thresholds stop being tied
   to one model.
3. **Then compare models.** A/B bge-small, nomic-v1.5 and Qwen3-Embedding-0.6B on the routing
   and RAG evals. Choose on recall and false injections, not public benchmark scores.

If dropping the Snowflake name is a goal in itself, step 1 still helps. It separates "did the
runtime change break anything" from "is the new model better".

## Open questions

- Does llama.cpp's BERT tokenizer match Hugging Face's closely enough that Arctic scores carry
  over? Step 1 answers this.
- Is dropping Arctic a goal in itself, or only dropping sentence-transformers?
