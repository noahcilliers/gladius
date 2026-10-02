# Snowflake Arctic Embed: How the Router Uses It

## What it is

Snowflake's **Arctic Embed** is a family of open-source (Apache 2.0) sentence-embedding models. Each one takes text and returns a fixed-length vector. Texts that mean similar things get vectors that point in similar directions.

It does **not** generate text and knows nothing about our routes. It only answers: "how similar are these two pieces of text?"

## Which model

| Model | Approx. size | Notes |
|---|---|---|
| **`Snowflake/snowflake-arctic-embed-xs`** | ~22M params, ~90MB | **Default.** Fits the ≤100MB router budget |
| `Snowflake/snowflake-arctic-embed-m-v1.5` | ~436MB | Upgrade if xs misroutes; has GGUF/ONNX |
| `Snowflake/snowflake-arctic-embed-m-v2.0` | larger | Multilingual; needs `trust_remote_code=True` |

Start with xs. Only move up if leave-one-out accuracy is poor *after* adding more example prompts.

## Where it sits in the pipeline

It runs in two places:

1. **At startup:** embeds every prompt in example_prompts.md to build the route centroids.
2. **Per prompt:** embeds the user's prompt so the router can compare it to the centroids and the cache.

It never touches the LLM's input or output.

## How "learning the routes" works

There is no gradient training. The example prompts *are* the training data.

```
## sql examples (10 prompts) ──embed──► 10 vectors ──average──► SQL centroid
## math examples           ──embed──► vectors    ──average──► Math centroid
...one centroid per route (math, sql, techwriter, creative, base)
```

New prompt:

```
prompt ──embed──► vector ──cosine similarity vs each centroid──► highest score wins
```

This is a **nearest-centroid classifier**. Adding a new skill = add an adapter + ~20 example prompts. No retraining.

## Code

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("Snowflake/snowflake-arctic-embed-xs")

# Embed (normalized, so dot product == cosine similarity)
vecs = model.encode(texts, prompt_name="query", normalize_embeddings=True)
```

- `prompt_name="query"` adds Arctic's built-in query prefix. Use it for **both** example prompts and user prompts so they're embedded the same way.
- `normalize_embeddings=True` makes every vector length 1, so `centroid @ vec` is cosine similarity.

The full implementation (centroids, cache, leave-one-out eval) is in `router.py`.

## Tuning knobs (in router.py)

| Setting | Default | What it does | How to set it |
|---|---|---|---|
| `ROUTE_THRESHOLD` | 0.35 | Best score below this → fall back to `base` | Set between what small talk scores and what a clear math prompt scores |
| `MARGIN_WARN` | 0.03 | Top-1 minus top-2 below this → "low confidence" in UI | Look at ambiguous demo prompts |
| `CACHE_THRESHOLD` | 0.92 | Prompt this similar to a cached one → reuse route | High enough that different questions don't collide |

These defaults are guesses. Arctic scores often cluster in a narrow range, so calibrate after the first run.

## Measuring it

- **Routing accuracy:** leave-one-out over example_prompts.md (printed by `router.py`). Each prompt is scored against centroids built *without* it.
- **Latency:** `latency_ms` returned per route call. Expect single-digit to low tens of ms on CPU.
- **RAM:** measure process RSS before and after loading the model.
- **Cache hit rate:** hits ÷ total prompts.

## If accuracy is too low

1. Add more varied example prompts per route (biggest win, usually).
2. Switch to k-nearest-neighbors among individual examples.
3. Train logistic regression on the embeddings (scikit-learn, under a second). Also gives calibrated probabilities for the confidence bar.
4. Move to `arctic-embed-m-v1.5`.

## Setup tonight

```bash
pip install sentence-transformers numpy
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('Snowflake/snowflake-arctic-embed-xs')"
```

The second line downloads and caches the model so you're not relying on venue Wi-Fi.
