# Student Sample Corpus

Fictional student data for the RAG step (pipeline step 4b). Nothing here is real.

## Layout

| Folder / file | Collection | Used by route |
|---|---|---|
| `profile.md` | `profile` | `base` (always prepended, not searched) |
| `courses/*.md` | `courses` | `base`, `creative` |
| `schemas/*.md` | `schemas` | `sql` |

## Authoring rules

- **One `##` section = one chunk.** The `#` title line and this README are not indexed.
- **Headings must stand alone.** Write "CS 301 — Exam dates", not "Exams". The heading is embedded with the chunk, and the retriever never sees the file name.
- **Keep chunks short:** about 50–200 tokens. Long chunks waste the context budget.
- **Repeat key facts** (course code, professor name) in each chunk that needs them, instead of relying on another chunk.

To add your own data, replace these files and keep the rules above. No re-training is needed. Chunks are re-embedded at startup.
