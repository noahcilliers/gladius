# Demo Script (~3 min)

## Before you go on

1. Quit Chrome, Docker or any VM app, and any extra Claude sessions you don't need. Every GB freed makes generation faster. Right now it runs at about 7 tok/s under memory pressure.
2. Check that only one model server is running: `pgrep -l llama-server` should print one line. Also check that only one UI is running: `pgrep -lf "streamlit run"` should show port 8503 only.
3. Run `PYTHON=/opt/miniconda3/envs/ml-env/bin/python ./run.sh`. It starts the server, warms every adapter, and opens the UI at http://localhost:8503. Pinning `PYTHON` keeps the conda env that every test ran on; plain `./run.sh` switches to `.venv` once `setup.sh` finishes.
4. Open the UI in **one** browser tab only. Two tabs overwrite each other's saved sessions.
5. In the sidebar, click **CLEAR ALL SESSIONS → DELETE N SESSIONS** so the sidebar is empty, then click **CLEAR ROUTER CACHE**. The cache isn't saved with the sessions; if you skip it, prompt 1 already shows a cache hit and spoils prompt 4.
6. Leave **Use my notes and schedule** and **Pipeline view** on, and **Specialist** on AUTO.
7. Have the backup recording open in another window.

## Run of show

### 1. Problem (30 s)

Students can't afford API bills, and their 8 GB laptops can't run big models. Small local models fit, but they're mediocre at everything.

> "Gladius: one 3B model, four specialists, zero cloud, on the laptop you already own."

### 2. Live demo (90 s)

At the current speed, each answer takes 10–35 s, so do **four prompts live**.

| # | How | Expect | Point to |
|---|---|---|---|
| 1 | Click the **∑ MATH** starter | ∑ MATH | The pipeline trace lights up embed → cache → route → notes → generate. Answer: $587.52 |
| 2 | Click the **¶ TECH WRITER** starter (`late_penalty()`) | ¶ TECH WRITER + notes | "⇄ ADAPTER SWAPPED, NO RELOAD". It documents code from your own project notes: Overview, Parameters, Return values, Example. Check: 2 free late days, 20% off per extra day, `late_penalty(90, 3, 2)` → `(72.0, 0)` |
| 3 | Type `Write an email to Prof. Chen asking for an extension on HW3.` | ◆ BASE MODEL + notes | **The RAG moment:** the email names Prof. Chen and CS 301, the Oct 9 deadline, and asks at least 48 hours ahead. Open **NOTES USED** to show the sources, all read locally. |
| 4 | Click the **∑ MATH** starter again | ∑ MATH, ⚡ CACHE HIT | Router time drops to 0 ms; the embed stage shows SKIPPED |

Fallback for #3 if the email runs long or goes off track: `when is my linear algebra class?` (about 12 s, answers Tue/Thu 13:00–14:15).

**If you have time, or for Q&A:**
- **λ PYTHON starter:** a clean, code-only function.
- `What's due before the end of October?`: answers from your calendar across all three courses. About 15 s to the first token.
- `If I bomb a linear algebra midterm, can the final replace it?`: answers from the MATH 221 syllabus (the final replaces your lowest midterm if it's higher).
- **Also answer with base model:** shows the specialist and base side by side.
- `hey whats up`: base model, low confidence, no course notes pulled in.

Keep pointing at the RAM meter in the top strip and sidebar. It reads about 3.1 GB at rest and up to about 3.6 GB with notes, of 8 GB.

### 3. Numbers (45 s)

Show the slides made from `results/charts/`:

- **disk.png:** four specialists for +119 MB, versus about 10 GB as five separate models.
- **ram.png:** 3.3 GB peak in the benchmark (about 3.6 GB live with notes), well under an 8 GB laptop.
- **quality.png:** math goes from 80% (base) to 90% (router) to 100% (always-correct adapter).
- **From `results/summary.md`:** routing accuracy (94% held-out), router latency (~16 ms), and adapter swap overhead (under 50 ms, no reload).

### 4. Prior art (15 s)

LoraRetriever, LoRAX and vLLM do adapter routing and serving on servers and GPUs. Gladius brings it to an 8 GB student laptop with one command, fully offline.

## Practice prompts

Run these before the demo and fill in the **Time** column (seconds to the full answer). Clear all sessions when you're done practising.

### Tested: these gave good answers

| Prompt | Route | Check for | Last time | Time |
|---|---|---|---|---|
| ∑ MATH starter (phone $640, 15% off, 8% tax) | math | $587.52 | 16 s | |
| λ PYTHON starter (second largest number) | coding | Code only, handles lists shorter than 2 | 15 s | |
| `write a recursive factorial python function` | coding | Clean recursive function | 7 s | |
| `What is 15% of 240?` | math | 36 | 20 s | |
| `when is my linear algebra class?` | base + notes | MATH 221, Tue/Thu 13:00–14:15 | 12 s | |
| `What did Prof. Chen say would be on the databases midterm?` | base + notes | Relational model, SQL joins/subqueries/GROUP BY/HAVING, ER diagrams | 12 s | |
| `What's due before the end of October?` | base + notes | Oct 6 PHIL reading response through Oct 30 CS 301 HW4 | 35 s | |
| `If I bomb a linear algebra midterm, can the final replace it?` | base + notes | The final replaces the lowest midterm if it's higher | 20 s | |

### Not tested yet: try these first

| Prompt | Expected route | Check for | Time |
|---|---|---|---|
| ¶ TECH WRITER starter (`late_penalty()` docs) | techwriter + notes | 2 free late days, 20%/day, returns (score, free days left), `late_penalty(90, 3, 2)` → `(72.0, 0)` | |
| `Write an email to Prof. Chen asking for an extension on HW3.` | base + notes | Prof. Chen, CS 301, HW3 due Fri Oct 9, asking at least 48 h ahead | |
| `When are Prof. Okafor's office hours?` | base + notes | Mon/Wed 13:00–14:00, Science Center 305 | |
| `Help me outline my Heidegger essay.` | creative + notes | Gestell (enframing), 1,500 words, 3+ citations, one counterargument, due Oct 16 | |
| `Write a poem about prime numbers.` | creative (math close second) | Shows the router weighing meaning, not keywords | |
| `hey whats up` | base, low confidence | No course notes injected (profile only) | |

### Avoid on stage

| Prompt | Why |
|---|---|
| ✦ CREATIVE starter (Kierkegaard) | Took 62 s and opened with a stray "The student's response:" line |
| Follow-ups like `what does the factorial(n-1) line do?` | Routed to math with low confidence and drifted into Fibonacci |
| `Explain what a database index is to a beginner.` | Good answer but 41 s |
| `Write an email to my professor asking to move my exam to next week.` | 34 s, and it mixed up the exam with the HW3 deadline. Name the professor and assignment instead (prompt #3 above) |

## If the live demo breaks

- **The UI shows "MODEL SERVER OFFLINE":** run `curl -s localhost:8080/health`. If it's down, rerun `./run.sh`.
- **The first answer takes 15 s or more:** macOS paged the model out while it sat idle. Rerun `./run.sh` just before you go on; it re-warms every adapter.
- **Answers are very slow:** memory pressure. Quit apps, or switch to the recording.
- **There's a wrong route on stage:** use the **Specialist** dropdown in the sidebar (FORCE · …) to pick the specialist, and say the router flags low-confidence cases.
- **Old sessions came back after clearing:** another tab was still open and saved its copy. Close every other tab, then clear again.
