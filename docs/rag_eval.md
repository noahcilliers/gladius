# RAG eval: baseline for the real-RAG rewrite

> Status: harness done, baseline recorded for the current retriever. This is the acceptance
> test for the rewrite in [`docs/rag.md`](rag.md): run it on the new code and compare.
>
> **The code lives on the `rag_eval` branch, not `main`.** That covers the harness, the three
> corpora, the cases and the recorded baseline run, all under `evals/rag/`. Every `evals/rag/…` path
> below refers to that branch.

## 1. Why

The current retriever works on the sample student in `data/student/`, but that corpus was written
*for* it. Every `##` heading names the course and spells out what the section answers:

```
## CS 301 Database Systems syllabus — Letter grade cutoffs (percent needed for an A, B, C) and regrade requests
```

`data/student/README.md` even makes this an authoring rule ("Headings must stand alone"). Real
notes don't look like that. The 90% hit rate quoted in `docs/rag.md` measures the retriever on
notes shaped to suit it, using prompts its thresholds were fit to. This eval measures how much of
that number is the retriever and how much is the headings, so the new implementation can be judged
on equal terms.

## 2. Setup

### 2.1 Three corpora, one variable

All three are in `evals/rag/corpora/`. The bodies are byte-identical, and so are the file names
and folders. **Only the headings change.**

| Corpus | Headings | Same section, as titled there |
|---|---|---|
| `detailed` | the demo's retrieval-tuned headings (frozen copy of `data/student`, minus its README) | `## CS 301 Database Systems syllabus — Collaboration and AI tool policy` |
| `sparse` | short headings a student would write for themselves (`evals/rag/sparse_headings.json`) | `## Collaboration` |
| `flat` | none: every `#` and `##` line removed | *(just the paragraphs)* |

`evals/rag/build_corpora.py` derives `sparse` and `flat` from `detailed`, and `corpora.lock`
pins a hash of every file. The harness refuses to run if any corpus drifts from the lock.

### 2.2 Cases

`evals/rag/cases.json` has 58 prompts, reported in two sets:

- **original (34)**: every prompt in `data/rag_eval.json`. The current thresholds
  (`RAG_THRESHOLD = 0.57`, `RAG_MIN_GAP = 0.14`, `NOTES_OVERRIDE_MIN = 0.68`, per-route
  `min_score`) were hand-fit to these, so this set flatters the baseline.
- **heldout (24)**: written for this eval and never used to tune anything. 18 are questions
  answerable from the notes (TA name, the NOT IN / NULL trap, rank–nullity, the silver chalice,
  `late_penalty` docs, the library shift…) and 6 are off-topic controls.

Each case has:

- **`gold`**: the passages the model needs. Each passage is identified by short verbatim
  *needles* from its body text, not by its heading. Bodies are the same in every corpus, so the
  labels hold whatever the headings or the chunker. `--validate` checks that every needle occurs
  exactly once per corpus and never in its own prompt. An empty `gold` marks a negative control.
- **`facts`**: regexes a correct answer must all match, for example `oct(ober)?\.? 13` for "when
  is my linear algebra midterm".

### 2.3 What runs

Every prompt goes through the real chat pipeline, `core.Pipeline`: route → notes override →
retrieve → augment → generate, with the LoRA adapters on llama-server. That runs once per corpus,
plus once with notes off as a no-RAG reference. Each run writes `evals/rag/runs/<label>/`:

- `summary.md`: metrics and a per-case grid
- `answers.md`: every response, with route, sources and missed facts
- `results.jsonl`: raw rows, including the exact model prompt
- `manifest.json`: commit, hashes, pinned date, server build, adapter hashes, retriever constants

### 2.4 Metrics

Everything is scored from **what the model was actually given** (`turn.model_prompt`), never
from retriever internals. So the same scoring works for any chunker, embedder or prompt template.

| Metric | Meaning |
|---|---|
| Retrieval hit rate | note questions where at least one gold passage reached the model |
| Gold recall | mean share of a question's gold passages that reached the model |
| All gold delivered | note questions where every gold passage reached the model |
| False injection | negative controls whose prompt contained any corpus text (the profile block counts) |
| Answer accuracy | answers matching every expected fact (a coarse check, so read `answers.md` too) |
| Added prompt tokens | context cost per question: (model prompt − question) / 4 chars |
| Notes overrides | prompts the router sent to a specialist and `notes_route()` sent back to base |

Scores are recomputed from the raw rows every time a run is loaded. A scoring fix re-scores old
runs too, so comparisons stay fair.

### 2.5 Reproducibility

- **Fixed inputs:** the prompts, needles and fact regexes; the corpora (hash-locked).
- **Fixed date:** "today" is pinned to Mon 2026-10-05, a week before Midterm 1.
- **Deterministic decoding:** temperature 0, seed 0, no prompt cache.
- **Clean routing:** the router cache is reset before every case.
- **Offline embeddings:** the embedding model loads from the local cache (`HF_HUB_OFFLINE=1`).
- **Not fixed:** latency. It depends on what else is running.

`compare.py` refuses to compare runs whose case or corpus hashes differ. It warns if the base
model, adapters or llama.cpp build changed.

## 3. Baseline: the current retriever

Recorded at commit `63c2f61` (the `rag/`, `core/`, `router.py` and `engine.py` code is
identical on `main` at `113c215`). Full results are in `evals/rag/runs/baseline/`.

### 3.1 Retrieval

| | detailed | sparse | flat |
|---|---|---|---|
| Retrieval hit rate, all 45 note questions | **78%** | **53%** | **44%** |
| … original set (27, tuned) | 85% | 59% | 48% |
| … heldout set (18, untuned) | 67% | 44% | 39% |
| Gold recall | 70% | 46% | 35% |
| All gold delivered | 64% | 42% | 29% |
| False injection, all 13 controls | 15% | 15% | 15% |
| … original (7) / heldout (6) | 0% / 33% | 0% / 33% | 0% / 33% |
| Added prompt tokens per note question | 460 | 379 | 467 |
| Notes overrides (specialist → base) | 8 | 5 | 4 |
| Chunks indexed | 69 | 69 | 29 |

Sanity check: on the original set with `detailed`, this eval scores 23/27 note questions. The
repo's own heading-based eval (`python -m rag.retriever`) scores 22/27 end to end. The one
difference is "Make me a study plan for next week": its deadlines reach the model through the
profile block's 10-day calendar window rather than through a retrieved chunk, and this eval counts
that.

### 3.2 Answers

*Filled in from `evals/rag/runs/baseline/summary.md` once the baseline run finishes.*

### 3.3 What the baseline shows

1. **Headings do most of the work.** Shortening the headings to what a student would write
   costs a third of the hits. Removing them costs nearly half. Typical losses:
   - "From my lecture notes, what's the difference between WHERE and HAVING?" hits with the
     `GROUP BY, HAVING vs WHERE` heading and misses with `GROUP BY`.
   - The two SQL schema prompts lose their schema entirely. A schema chunk's body is bare DDL, so
     "University class database schema" in the heading was carrying all the meaning.
   - "If I bomb a linear algebra midterm, can the final replace it?" depends on the heading's
     "final-exam replacement rule".
2. **The thresholds are fit to the original prompts.** Even with the tuned headings, the hit rate
   drops from 85% (original) to 67% (heldout). False injection is 0% on the original controls but
   33% on the new ones:
   - "Explain how photosynthesis works." scored 0.61 against the linear-algebra elimination notes
     and the Heidegger notes, which is over the 0.57 threshold.
   - "Give me a recipe for banana bread." got the whole student profile, because `_PERSONAL_RE`
     matches "me".
3. **Routing and retrieval are tangled.** When the router sends a course question to a
   specialist, `notes_route()` only sends it back to base with notes if a chunk scores ≥ 0.68.
   These miss on every corpus, even with the tuned headings, because they reach a specialist
   adapter with no notes:
   - "Who is the TA for my databases class?" (routed to sql)
   - "What's the trap with NOT IN and NULLs?" (routed to math)
   - "What are we reading in philosophy after Winner?" (routed to creative)

   Weaker headings make it worse: fewer of these questions get sent back (8 → 5 → 4).
4. **Heading-less files chunk badly.** With no `##` to split on, `flat` falls back to paragraph
   packs of up to 1,600 chars. That gives 29 chunks instead of 69, with titles like
   `cs301_notes (2/5)`. Both schemas land in a single chunk. Each pack spans several topics, so it
   scores lower against any single question and costs more tokens when it is injected.
5. **Multi-passage questions are capped.** The base route injects at most 2 chunks plus the
   profile. So "When is my linear algebra midterm and what does it cover?" gets 1 of its 3 gold
   passages on every corpus, and the deadline questions get 1 of 4–5.

What the rewrite should move: `sparse` and `flat` toward `detailed` (heading-independent
retrieval), heldout toward original (no overfitting), and false injection to 0 without losing hits.

## 4. Running it on the new implementation

First bring the eval into the branch being measured, without merging anything else:

```bash
git fetch origin && git checkout origin/rag_eval -- evals
```

Then:

```bash
./serve.sh                                          # any worktree's; the harness uses LLAMA_URL (default :8080)
python -m evals.rag.run --label new-rag             # ~35 min on an M4; --retrieval-only takes ~10 s
python -m evals.rag.compare baseline new-rag        # writes runs/new-rag/compare_vs_baseline.md
```

`compare` prints the metrics side by side per corpus and lists every case whose retrieval or
answer changed, with both answers.

Rules:

- Don't edit `cases.json`, `corpora/`, `sparse_headings.json` or `corpora.lock` on the branch
  being measured. If the cases need to change, change them on `main` and re-run the baseline at
  the old commit, so both runs use the same cases.
- The harness only touches the app through `core.Pipeline` (`route`, `retrieve`, `stream`),
  `core.Options(use_rag=…)`, the `turn` fields `model_prompt`, `route`, `routing` and `rag`, and
  the `GLADIUS_WORKSPACE` env var. If the rewrite changes those, adapt `run_case()` and the
  `Pipeline(...)` line in `evals/rag/run.py`, and nothing else.
- A persistent index cache written into the workspace is fine, as long as it lives in a hidden
  folder; the corpus lock ignores hidden paths.

Other flags: `--corpora`, `--cases` (partial run), `--no-reference`, `--resume`, `--report`,
`--validate`.

## 5. Known limits

- **The bodies are retrieval-friendly too.** Course codes and professor names are repeated in
  every section, so even `flat` is easier than real notes. A fourth corpus with rewritten bodies
  is the natural next step.
- **Folder names and file conventions are kept.** `courses/`, `syllabi/`, `notes/`, `schemas/`,
  `profile.md` and `calendar.md` are the same in every corpus, because the current `ROUTE_RAG`
  and profile logic depend on them.
- **Fact matching is coarse.** A correct answer phrased differently can miss a regex, and a wrong
  answer can match one. It's good for spotting trends across 58 cases; read the answers for
  individual verdicts.
- **llama.cpp can differ by a token** across builds or hardware. The manifest records both.
