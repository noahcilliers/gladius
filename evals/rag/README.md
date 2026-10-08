# RAG eval

The same 58 prompts through the full chat pipeline, on three versions of the sample notes that
differ only in their headings (`corpora/detailed`, `sparse`, `flat`). Method, metrics and the
baseline results are in [`docs/rag_eval.md`](../../docs/rag_eval.md).

```bash
python -m evals.rag.run --label new-rag             # needs ./serve.sh; ~35 min on an M4
python -m evals.rag.run --label new-rag --retrieval-only   # ~10 s, no llama-server
python -m evals.rag.compare baseline new-rag        # side by side vs the recorded baseline
python -m evals.rag.run --validate                  # check cases.json against the corpora
```

| File | What it is |
|---|---|
| `cases.json` | prompts, gold passages (body needles), expected answer facts |
| `corpora/` | the three corpora; `detailed` is frozen, the others come from `build_corpora.py` |
| `sparse_headings.json` | the short heading for every section in `sparse` |
| `corpora.lock` | hash of every corpus file; runs refuse to start if it doesn't match |
| `run.py` | runs the eval and writes `runs/<label>/` (summary, answers, raw rows, manifest) |
| `compare.py` | compares two runs case by case |
| `runs/baseline/` | the current retriever, recorded before the rewrite |

Don't edit `cases.json` or anything under `corpora/` on a branch you're measuring. `compare.py`
refuses runs whose case or corpus hashes differ from the baseline's.
