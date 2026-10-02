# Demo Script (~3 min)

## Before you go on

1. Quit Chrome, Docker or any VM app, and any extra Claude sessions you don't need. Every GB freed makes generation faster. Right now it runs at about 7 tok/s under memory pressure.
2. Check that only one model server is running: `pgrep -l llama-server` should print one line.
3. Clear the test chats so the sidebar is empty: `rm results/sessions.json`.
4. Run `PYTHON=/opt/miniconda3/envs/ml-env/bin/python ./run.sh`. It starts the server, warms every adapter, and opens the UI at http://localhost:8503. Pinning `PYTHON` keeps the conda env that every test ran on; plain `./run.sh` switches to `.venv` once `setup.sh` finishes.
5. Open the UI in **one** browser tab only. Two tabs overwrite each other's saved sessions.
6. In the sidebar, click **CLEAR ROUTER CACHE** and leave **Use my notes and schedule** and **Pipeline view** on.
7. Have the backup recording open in another window.

## Run of show

### 1. Problem (30 s)

Students can't afford API bills, and their 8 GB laptops can't run big models. Small local models fit, but they're mediocre at everything.

> "Gladius: one 3B model, four specialists, zero cloud, on the laptop you already own."

### 2. Live demo (90 s)

At the current speed, each answer takes 10–35 s, so do **four prompts live**. All of them were run through `retro.py` and checked.

| # | How | Expect | Point to |
|---|---|---|---|
| 1 | Click the **∑ MATH** starter | ∑ MATH | The pipeline trace lights up embed → cache → route → notes → generate. Answer: $587.52 |
| 2 | Click the **▤ SQL · BASE MODEL** starter | SQL, answered by base | "⇄ ADAPTER SWAPPED, NO RELOAD". Say: "We tried a SQL specialist. Our benchmark showed it lost to the base model, so SQL questions go to base." |
| 3 | Type `Write an email to my professor asking to move my exam to next week.` | ◆ BASE MODEL + 3 notes | **The RAG moment:** the email names CS 301 and Prof. Chen. Open **NOTES USED** to show the sources: your profile, the late policy and the syllabus, all read locally. About 7 s to the first token. |
| 4 | Click the **∑ MATH** starter again | ∑ MATH, ⚡ CACHE HIT | Router time drops to 0 ms; the embed stage shows SKIPPED |

**If you have time, or for Q&A:**
- **λ PYTHON starter:** a clean, code-only function.
- **✦ CREATIVE starter (Kierkegaard):** no notes are injected, by design.
- `Explain what a database index is to a beginner.`: routes to base with ⚠ LOW CONFIDENCE and SQL a close second, so it's measuring meaning, not keywords. It also pulls your CS 301 B+ tree notes.
- **Also answer with base model:** shows the specialist and base side by side.
- `What's due before the end of October?` or `If I bomb a linear algebra midterm, can the final replace it?`: the router picks math, but the trace shows "about your courses: math → base, with notes". It answers from your calendar and syllabus. About 10–15 s to the first token.

Keep pointing at the RAM meter in the top strip and sidebar. It reads about 3.1 GB at rest and up to about 3.6 GB with notes, of 8 GB. The disk line reads 2.02 GB base + 119 MB for 4 specialists.

### 3. Numbers (45 s)

Show the slides made from `results/charts/`:

- **disk.png:** four specialists for +119 MB, versus about 10 GB as five separate models.
- **ram.png:** 3.3 GB peak in the benchmark (about 3.6 GB live with notes), well under an 8 GB laptop.
- **quality.png:** math goes from 80% (base) to 90% (router) to 100% (always-correct adapter).
- **sql_adapter.png:** "We also tried a SQL specialist. It lost to the base model everywhere: 73% vs 93% on single-table questions. So we dropped it. Gladius only keeps a specialist that's measured to beat base."
- **From `results/summary.md`:** routing accuracy (94% held-out), router latency (~16 ms), and adapter swap overhead (under 50 ms, no reload).

### 4. Prior art (15 s)

LoraRetriever, LoRAX and vLLM do adapter routing and serving on servers and GPUs. Gladius brings it to an 8 GB student laptop with one command, fully offline.

## If the live demo breaks

- **The UI shows "MODEL SERVER OFFLINE":** run `curl -s localhost:8080/health`. If it's down, rerun `./run.sh`.
- **The first answer takes 15 s or more:** macOS paged the model out while it sat idle. Rerun `./run.sh` just before you go on; it re-warms every adapter.
- **Answers are very slow:** memory pressure. Quit apps, or switch to the recording.
- **There's a wrong route on stage:** use the **Specialist** dropdown in the sidebar (FORCE · …) to pick the specialist, and say the router flags low-confidence cases.
