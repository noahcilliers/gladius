# Student Sample Corpus

Fictional student data for the RAG step (pipeline step 4b). Nothing here is real.

## Layout

| Folder / file | Collection | Used by route |
|---|---|---|
| `profile.md` | `profile` | `base` (always prepended, not searched) |
| `courses/*.md` | `courses` | `base`, `creative` |
| `courses/calendar.md` | `courses` | also: lines dated in the next 10 days are added to the profile on `base` |
| `syllabi/*.md` | `syllabi` | `base`, `creative` (full syllabus: weekly schedule, policies, grading scale) |
| `notes/*.md` | `notes` | `base`, `creative` (Jordan's lecture notes, Aug 24 – Oct 2) |
| `schemas/*.md` | `schemas` | `sql` (only the best-matching single table is injected) |

## Authoring rules

- **One `##` section = one chunk.** This README is not indexed.
- **Headings stand alone here.** "CS 301 — Exam dates", not "Exams". Your own notes don't need this: each chunk is embedded with its file name and headings, and a sentence the model writes about where it sits (`python -m rag.context`). But these headings are what `data/rag_eval.json` matches on.
- **Keep chunks short:** about 50–200 tokens. Long chunks waste the context budget.
- **Repeat key facts** (course code, professor name) in each chunk that needs them, instead of relying on another chunk.

Calendar lines must start `- Tue Oct 6:` (weekday, month, day) to be picked up as upcoming deadlines.

To use your own notes, point `GLADIUS_WORKSPACE` at their folder instead (see `.env.example`). No re-training is needed. Chunks are re-embedded at startup.
