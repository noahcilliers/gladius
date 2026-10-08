# RAG eval: baseline

2026-10-07 23:34:09 · commit `63c2f61a71` on `claude/rag-evaluation-baseline-33d659` · prompts `c13ebc8f822a8490` · corpora `b29311c865313198` · today pinned to 2026-10-05

R = gold passages delivered to the model (for negatives: whether any corpus text was injected). A = answer matches every expected fact. `no-notes` is the same pipeline with notes off.

## All cases (58)

| Metric | no-notes | detailed | sparse | flat |
|---|---|---|---|---|
| Retrieval hit rate (note questions) | – | 78% | 53% | 47% |
| Gold recall (mean share of gold passages) | – | 70% | 46% | 37% |
| All gold passages delivered | – | 64% | 42% | 31% |
| False injection (negative controls) | – | 15% | 15% | 15% |
| Answer accuracy (all graded) | 25% | 73% | 55% | 53% |
| Answer accuracy, note questions | 9% | 67% | 44% | 42% |
| Answer accuracy, negative controls | 100% | 100% | 100% | 100% |
| Added prompt tokens (note questions, mean) | – | 460 | 379 | 467 |
| Specialist → base notes overrides | 0 | 8 | 5 | 4 |

## Original set (34): the prompts the current retriever's thresholds were tuned on

| Metric | no-notes | detailed | sparse | flat |
|---|---|---|---|---|
| Retrieval hit rate (note questions) | – | 85% | 59% | 52% |
| Gold recall (mean share of gold passages) | – | 71% | 47% | 36% |
| All gold passages delivered | – | 63% | 41% | 26% |
| False injection (negative controls) | – | 0% | 0% | 0% |
| Answer accuracy (all graded) | 25% | 78% | 53% | 56% |
| Answer accuracy, note questions | 11% | 74% | 44% | 48% |
| Answer accuracy, negative controls | 100% | 100% | 100% | 100% |
| Added prompt tokens (note questions, mean) | – | 523 | 427 | 547 |
| Specialist → base notes overrides | 0 | 5 | 3 | 3 |

## Heldout set (24): written for this eval, never used for tuning

| Metric | no-notes | detailed | sparse | flat |
|---|---|---|---|---|
| Retrieval hit rate (note questions) | – | 67% | 44% | 39% |
| Gold recall (mean share of gold passages) | – | 67% | 44% | 39% |
| All gold passages delivered | – | 67% | 44% | 39% |
| False injection (negative controls) | – | 33% | 33% | 33% |
| Answer accuracy (all graded) | 26% | 65% | 57% | 48% |
| Answer accuracy, note questions | 6% | 56% | 44% | 33% |
| Answer accuracy, negative controls | 100% | 100% | 100% | 100% |
| Added prompt tokens (note questions, mean) | – | 365 | 306 | 346 |
| Specialist → base notes overrides | 0 | 3 | 2 | 1 |

## Per case

| Case | Set | Routed → answered by | no-notes | detailed | sparse | flat |
|---|---|---|---|---|---|---|
| `cs301-extension-email` | orig | base | A ✗ | R 2/2 · A ✓ | R 1/2 · A ✓ | R 2/2 · A ✓ |
| `math221-midterm-when-what` | orig | base | A ✗ | R 1/3 · A ✓ | R 1/3 · A ✓ | R 1/3 · A ✓ |
| `study-plan-next-week` | orig | base | A ✗ | R 1/5 · A ✓ | R 1/5 · A ✗ | R 1/5 · A ✓ |
| `due-before-end-of-october` | orig | math → base | A ✗ | R 1/4 · A ✗ | R 1/4 · A ✗ | R 1/4 · A ✗ |
| `okafor-office-hours` | orig | base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `chen-midterm-content` | orig | base | A ✗ | R 1/2 · A ✓ | R 1/2 · A ✗ | R 1/2 · A ✗ |
| `where-vs-having` | orig | base | A ✓ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `left-join-acts-inner` | orig | sql / sql → base | A ✗ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `hw3-q4-hints` | orig | base | A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `3nf-like-in-class` | orig | base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✗ | R 0/1 · A ✗ |
| `null-space-basis` | orig | base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 0/1 · A ✗ |
| `quiz-subspace-test` | orig | math → base | A ✓ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 1/1 · A ✓ |
| `heidegger-standing-reserve` | orig | creative | A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 0/1 · A ✓ |
| `lindqvist-good-thesis` | orig | creative | A ✗ | R 1/2 · A ✗ | R 0/2 · A ✗ | R 1/2 · A ✓ |
| `outline-heidegger-essay` | orig | base | A ✗ | R 2/2 · A ✓ | R 2/2 · A ✓ | R 1/2 · A ✓ |
| `sql-enrollment-counts` | orig | sql | A ✗ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `sql-bike-station-rides` | orig | base | A ✗ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `chatgpt-databases-homework` | orig | base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `ai-philosophy-essay` | orig | creative → base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 0/1 · A ✗ |
| `final-replaces-midterm` | orig | math / math → base | A ✗ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `a-minus-databases` | orig | sql | A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `reading-after-winner` | orig | creative | A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `cs301-after-midterm` | orig | base | A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `phil-absences` | orig | base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `missed-lab` | orig | base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `linear-algebra-textbook` | orig | base | A ✗ | R 1/2 · A ✓ | R 2/2 · A ✓ | R 1/2 · A ✓ |
| `linear-algebra-regrade` | orig | base | A ✗ | R 1/1 · A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `neg-small-talk` | orig | base | · | R clean | R clean | R clean |
| `neg-capital-australia` | orig | base | A ✓ | R clean · A ✓ | R clean · A ✓ | R clean · A ✓ |
| `neg-dragon-story` | orig | creative | A ✓ | R clean · A ✓ | R clean · A ✓ | R clean · A ✓ |
| `neg-autumn-haiku` | orig | creative | · | R clean | R clean | R clean |
| `neg-derivative` | orig | math | A ✓ | R clean · A ✓ | R clean · A ✓ | R clean · A ✓ |
| `neg-pages-per-day` | orig | math | A ✓ | R clean · A ✓ | R clean · A ✓ | R clean · A ✓ |
| `neg-bus-percent` | orig | math | A ✓ | R clean · A ✓ | R clean · A ✓ | R clean · A ✓ |
| `h-cs301-ta` | held | sql | A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `h-chen-email` | held | base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `h-project-team` | held | sql / sql → base | A ✗ | R 0/1 · A ✗ | R 1/1 · A ✓ | R 0/1 · A ✗ |
| `h-not-in-nulls` | held | math | A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `h-sql-clause-order` | held | sql | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `h-inverse-okafor` | held | math → base | A ✗ | R 1/1 · A ✓ | R 0/1 · A ✓ | R 1/1 · A ✓ |
| `h-rank-nullity` | held | math / math → base | A ✗ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `h-calculator-midterm` | held | base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 0/1 · A ✗ |
| `h-essay1-example-tech` | held | base | A ✗ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `h-theuth-myth` | held | creative | A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `h-silver-chalice` | held | creative | A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `h-reading-response` | held | base | A ✗ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `h-late-penalty-docs` | held | techwriter | A ✗ | R 1/1 · A ✗ | R 1/1 · A ✗ | R 1/1 · A ✗ |
| `h-library-shift` | held | base | A ✗ | R 1/1 · A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `h-db-software` | held | base | A ✗ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `h-candidate-vs-superkey` | held | base | A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ | R 1/1 · A ✓ |
| `h-final-weight-math` | held | math | A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `h-essay2-due-prompt` | held | creative / creative → base | A ✗ | R 1/1 · A ✓ | R 0/1 · A ✗ | R 0/1 · A ✗ |
| `h-neg-photosynthesis` | held | base | A ✓ | R **injected** (26) · A ✓ | R **injected** (26) · A ✓ | R **injected** (30) · A ✓ |
| `h-neg-palindrome` | held | coding | A ✓ | R clean · A ✓ | R clean · A ✓ | R clean · A ✓ |
| `h-neg-austen` | held | creative | A ✓ | R clean · A ✓ | R clean · A ✓ | R clean · A ✓ |
| `h-neg-jazz-cat` | held | creative | · | R clean | R clean | R clean |
| `h-neg-train-speed` | held | math | A ✓ | R clean · A ✓ | R clean · A ✓ | R clean · A ✓ |
| `h-neg-banana-bread` | held | base | A ✓ | R **injected** (18) · A ✓ | R **injected** (19) · A ✓ | R **injected** (19) · A ✓ |
