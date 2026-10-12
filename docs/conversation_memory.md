# Conversation memory — continuity inside one chat

> Status: design / proposal. Target: a follow-up like "make it shorter" or "what about the
> second one?" works, in the conversation the student is having now, fully offline and inside
> the 2048-token window. Cross-conversation recall is explicitly out of scope.

## 1. Where it is today

Every request is stateless. `Engine.stream` sends a single `user` message, and `Router.route`
and `Retriever.retrieve` each see only the bare latest prompt. A follow-up with no topic words
therefore routes on nothing, retrieves nothing, and the model has no idea what "it" is.

Two details of the setup make this harder than "append the last N messages":

- `serve.sh` runs `-c 2048 -np 1`. The window is small and there is one slot.
- `Engine.stream` sends `cache_prompt: False` (a KV cache from another adapter isn't valid), so
  every token of history is re-read on every turn. History costs time-to-first-token, not just space.

## 2. Measurements

Measured with llama-server's own tokenizer on Llama-3.2-3B (2026-10-11). The answers are five
live base-model generations, a small sample.

| Text | chars / token | typical size |
|---|---|---|
| User prompts (34, `data/rag_eval.json`) | 4.17 | ~53 chars ≈ 13 tokens |
| Note chunks (67, prose) | 3.67 | ~480 chars ≈ 130 tokens |
| DDL schemas | 4.09 | |
| Model answers (5 generated) | 4.36 | 1,200–1,900 chars; **4 of 5 hit the 384-token cap** |

Planning figures: **4.0 chars/token for chat, 3.7 for anything containing notes**.
`retriever.estimate_tokens` uses `len // 4`, which undercounts notes by ~9%.

### The budget

| | tokens |
|---|---|
| Window (`-c`) | 2048 |
| Reserved for the answer (`max_tokens`) | −384 |
| Retrieval at its worst (900 estimated × 3.67/4) | −~980 |
| Framing + chat template | −~75 |
| The new question | −15 to −60 |
| **Left for history, full RAG turn** | **~550 (≈ 2,000 chars)** |
| Left for history, no retrieval (small talk, adapter routes with no hit) | ~1,500 (≈ 6,000 chars) |

One exchange is ~13 + 384 ≈ **400 tokens (~1,600 chars)**, and the assistant's answer is ~97%
of that. Verbatim history therefore fits **one** previous exchange on a full-RAG turn.

## 3. Design

Split by role, not just by age. The user's turns are almost free and the assistant's answers
are the expensive part.

| Piece | Form | Cost |
|---|---|---|
| Last assistant answer | verbatim, capped at ~800 chars | ~200 tok |
| Last user turn | verbatim | ~15 tok |
| Older exchanges | one sentence each, ≤ 200 chars | ~50 tok each |

### 3.1 One sentence per exchange, not a rolling summary

A rolling summary is rewritten every turn, drifts, and drops exact dates and numbers, which are
what a study assistant gets asked about. A sentence written once per exchange never changes.
The window can only hold four or five of them anyway, so there is nothing to merge: the oldest
simply fall off.

The sentence is written by the base model with every adapter at scale 0, using the same request
mechanics as `rag.context.ContextWriter` (temperature 0, seed 0, explicit `lora` list) and its
`clean()`. A separate prompt asks for "the user asked X; the assistant explained Y", in ≤ 200 chars.

### 3.2 When it is written

Exchange *k* is verbatim during turn *k+1* and needs its sentence from turn *k+2*. So the sentence
for *k* is written right after the answer to *k+1* finishes streaming, while the student is reading.
The `-np 1` slot is busy for ~1.5 s then; a very fast next message queues behind it.

If the sentence isn't ready (server busy, call failed, writer off), fall back to the user's turn
cut at 150 chars: `User asked: …`. Memory degrades to "what you asked" instead of failing.

### 3.3 Assembling the prompt

Retrieval keeps priority. History gets whatever is left:

```
budget = min(HISTORY_MAX_TOKENS, N_CTX - ANSWER_RESERVE - tokens(augmented prompt) - OVERHEAD)
```

using 3.7 chars/token so it never overshoots. Fill in this order, stopping when it's full:

1. the new question and its retrieved context (as today)
2. the last user turn and last answer (answer cut to fit, at a sentence boundary)
3. older sentences, newest first

Rendered as an `## Earlier in this conversation` block inside the existing augmented prompt for the
base route, with the last exchange as real prior `messages` for chat-template routes.
`Engine.stream` gains an optional `history` argument.

### 3.4 Storage

A per-conversation append-only log, **not** the vector cache from `rag.md` §3.4:

| | Vector cache (`cache/rag/`) | Conversation log |
|---|---|---|
| Nature | derived, content-addressed | primary data |
| If deleted | rebuilds itself | gone for good |
| Written | at index build | every turn |

`data/conversations/<timestamp>-<id>.jsonl`, one JSON object per line: `{"turn", "route", "user",
"assistant", "sources"}` for a turn and `{"summary_of": turn, "text", "model"}` for a sentence.
A conversation is never re-summarized, so the sentences need no content-hash cache. This is a
simplification of reusing `ContextCache` outright.

Plaintext on disk is personal data. The folder is gitignored, and "new conversation" and "delete
this conversation" are first-class operations.

## 4. Routes

The first draft of this plan said the adapters "can't take history". That overstated it. What the
code actually has:

| Route | Loaded adapter | Request format | Can carry prior messages? |
|---|---|---|---|
| `base` | none | chat template | yes |
| `sql` | **none** (dropped; the base model answers) | chat template, bare DDL + question | yes |
| `math`, `creative` | yes | chat template, prompt as-is | yes, mechanically |
| `coding` | yes | chat template, `Complete the following Python function:` prefix on the latest turn | yes, mechanically |
| `techwriter` | yes | chat template, `augment()` builds request → source → section list | yes, but it copies context back verbatim |
| `sql` **with** an adapter | (would be) | raw `/completion`, `### Context / ### Question / ### SQL` | **no**, no message list exists |

So only a raw-completion adapter is structurally incompatible, and none is loaded. The real
concern is different and **unmeasured**: the adapters were fine-tuned on single-turn data, so
whether a prior turn helps or hurts them is something to test, not assume. `techwriter`'s
copy-back behaviour is the one with a known reason to expect harm.

Therefore history is a **declared per-route setting**, the same way `RAW_PROMPT_ROUTES` and
`CHAT_PROMPT_ROUTES` already are:

```python
ROUTE_HISTORY = {"base": True, "sql": True, "math": False, "creative": False,
                 "coding": False, "techwriter": False}
```

- Ships on for `base` and `sql`, since they are the base model in a chat template.
- Ships off for adapters until the conversation eval (§6) shows it doesn't regress them; flip
  one route at a time.
- A route set to `False` still *records* the exchange, so a later follow-up on `base` knows what
  was said.
- **Follow-up routing.** A prompt with no routing signal of its own (short, anaphoric, scoring
  near the base tie-break) inherits the previous turn's route. Otherwise "why?" after a math
  answer goes to `base` and answers without the math context.

## 5. Problems and limits

1. **Capped answers are lossy.** "Make it shorter" on a 1,800-char answer rewrites an 800-char
   truncation. Fixing this means stopping generation earlier, which is a separate decision.
2. **The 3B model summarizes itself.** It tends to restate its own mistakes as fact, and the
   sentence is then trusted more than the raw answer would have been.
3. **Retrieval still sees the bare follow-up.** "When is it due?" retrieves nothing. That needs
   query condensation (rewrite to a standalone question), which is another model call and its own
   eval. Not in this change.
4. **History competes with RAG.** Retrieval has priority by construction, so on a full-RAG turn
   the student gets one exchange of memory, not five. That is the cost of a 2048 window; raising
   `-c` trades RAM and TTFT.
5. **Eval hygiene.** `evaluate()` runs with history off, so `data/rag_eval.json` numbers stay
   comparable.

## 6. Evaluation

`data/conversation_eval.json`: short scripted conversations (2–4 turns) where the last turn is a
follow-up. Each case names facts the answer must contain or the heading retrieval must still hit.

- **Follow-up resolution:** the answer reflects the earlier turn (history on vs off).
- **No regression:** first turns are identical with history on and off, by construction; assert it.
- **Cost:** TTFT delta with history on, on a full-RAG turn and on a no-retrieval turn.
- **Per route:** the same cases run with each adapter route's flag on, to decide the flip.

## 7. File-level change list

| File | Change |
|---|---|
| new `rag/history.py` | `Conversation` (append, render under a token budget), JSONL log, sentence writer reusing `ContextWriter` mechanics |
| `engine.py` | `stream(..., history=None)`; `ROUTE_HISTORY` |
| `rag/retriever.py` | `augment()` takes the rendered history; budget accounts for it |
| `router.py` | follow-up inherits the previous route when there is no signal |
| `.gitignore` | `data/conversations/` |
| `data/conversation_eval.json` | new eval set |

## 8. Phasing

1. `Conversation` + log + budgeted render, `base` and `sql` only, with the user-turn fallback
   in place of model sentences. Ship and measure TTFT.
2. Model-written sentences after the answer finishes.
3. Follow-up route inheritance.
4. Conversation eval; flip adapter routes one at a time.
5. Later, separately: query condensation for retrieval.
