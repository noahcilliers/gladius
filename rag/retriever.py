"""Route-gated retrieval over the student's workspace (pipeline step 4b).

Chunks come from the workspace folder (rag/workspace.py: GLADIUS_WORKSPACE, default the
sample student in data/student), embedded once at startup with the router's Arctic Embed
model (no second model in memory). Each route decides which collections it may see and how
many chunks it gets; anything under RAG_THRESHOLD is dropped, so prompts unrelated to the
student's courses go through unchanged.

Run directly to index the workspace, and on the sample workspace also score retrieval on
data/rag_eval.json (no llama-server needed):
    python -m rag.retriever
"""

import datetime as dt
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rag.workspace import PROFILE_COLLECTION, SAMPLE_WORKSPACE, Chunk, load_chunks, workspace_dir
from settings import ROOT

_DDL_RE = re.compile(r"CREATE TABLE\s+(\w+)\s*\((.*?)\);", re.S | re.I)
_PROMPT_SCHEMA_RE = re.compile(r"CREATE TABLE|`\w+\s*\([^`]*\)`", re.I)
_CONSTRAINTS = ("primary", "foreign", "unique", "check", "constraint")

EVAL_PATH = ROOT / "data" / "rag_eval.json"  # written against the sample workspace

# Arctic scores every chunk ~0.40-0.55 even for off-topic prompts, so neither test works alone.
# A chunk is kept if it scores high outright, or stands well above this prompt's median chunk.
# Calibrated on data/rag_eval.json (off-topic tops out at 0.552 / +0.09; relevant >= 0.558 / +0.08).
RAG_THRESHOLD = 0.57
RAG_MIN_GAP = 0.14
MAX_CONTEXT_TOKENS = 900  # profile ~210 + upcoming ~150 + 2 chunks; leaves ~750 of the 2048 context for the question + answer
UPCOMING_DAYS = 10  # base route: calendar items due in this window are added to the profile (covers "next week")
_CAL_LINE_RE = re.compile(r"^- \w{3} (\w{3}) (\d{1,2})\b")
# Prompts about the student themself get the profile even when no chunk matches ("what's my week like?").
_PERSONAL_RE = re.compile(r"\b(my|me|i|i'm|im|schedule|plan|due|deadlines?|week|today|tomorrow|class(es)?|professor|prof)\b", re.I)

# Notes override: the router picks an adapter on topic words ("linear algebra", "LEFT JOIN"), so
# questions about the student's own courses often land on math/sql/creative, which see few or no
# notes. If a question is about the student and a note matches strongly, the base model answers it
# with notes. 0.68 sits above specialist prompts that merely contain "I" ("If I score 78, 85 and 91
# on three exams..." tops out at 0.645) and below personal course questions (0.70-0.76).
NOTES_OVERRIDE_ROUTES = ("math", "sql", "creative")
NOTES_OVERRIDE_MIN = 0.68
_ABOUT_STUDENT_RE = re.compile(r"\b(my|me|i|i'm|im|we|our|us|schedule|plan|due|deadlines?|week|today|tomorrow|"
                               r"class(es)?|professor|prof)\b", re.I)  # _PERSONAL_RE + we/our/us
# Logistics questions are answered by the profile's deadline list, not by a strong chunk match
# ("What's due before the end of October?" scores only 0.637). Narrow on purpose: "deadlines"
# alone also matches creative prompts ("why deadlines feel heavier at night").
_LOGISTICS_RE = re.compile(r"\bwhat'?s due\b|\bdue (?:date|before|by|on|this|next)\b|\boffice hours\b|"
                           r"\blate (?:policy|days?)\b|\bextension\b|\bregrade\b|\bsyllabus\b", re.I)


@dataclass(frozen=True)
class RouteRAG:
    profile: bool  # always prepend profile.md
    # The collections this route may search, or None for all of them (except "profile"). Names the
    # workspace doesn't have are dropped, and a list with none left falls back to all: these names are
    # the sample workspace's folders, so in a student's own folder every route searches everything.
    collections: tuple[str, ...] | None
    top_k: int
    min_score: float | None = None  # strict per-route cutoff instead of RAG_THRESHOLD / RAG_MIN_GAP
    schema_k: int = 0  # separate slot for the "schemas" collection, under the normal gate


# The adapters were fine-tuned without injected context, so only routes that benefit get any.
# The sql route is answered by the base model (the SQL adapter was dropped). Schemas get their own
# slot and go in as bare DDL; notes/syllabus prose only on a strong match (>= 0.68), because notes
# outscore schemas on plain text-to-SQL questions. If a raw-format SQL adapter returns, set
# top_k=0 : prose breaks engine.sql_prompt.
ROUTE_RAG = {
    "sql": RouteRAG(profile=False, collections=("courses", "syllabi", "notes"), top_k=1, min_score=0.68, schema_k=1),
    "base": RouteRAG(profile=True, collections=None, top_k=2),
    # The creative adapter writes worse with loose context ("What would Kierkegaard think about group
    # chats?" pulled reading notes at 0.59 and answered in the student's voice). Strong matches only.
    "creative": RouteRAG(profile=False, collections=("courses", "syllabi", "notes"), top_k=1, min_score=0.70),
    # "Can the final replace my linear algebra midterm?" routes to math, so math gets context too, but
    # only on a strong match: GSM8K word problems score up to 0.66 against unrelated notes; personal
    # questions about MATH 221 score >= 0.70.
    "math": RouteRAG(profile=False, collections=("courses", "syllabi", "notes"), top_k=2, min_score=0.70),
    # "Write documentation for my late_penalty function": the code lives in notes/ and scores ~0.75-0.81.
    # Strong matches only, so product-brief and datasheet prompts (the adapter's home turf) get no context.
    "techwriter": RouteRAG(profile=False, collections=("notes",), top_k=1, min_score=0.70),
}
NO_RAG = RouteRAG(profile=False, collections=(), top_k=0)


@dataclass
class Hit:
    chunk: Chunk
    score: float


@dataclass
class Retrieval:
    route: str
    hits: list[Hit]  # chunks injected, best first
    profile: bool
    latency_ms: float

    @property
    def sources(self) -> list[str]:
        return (["profile.md"] if self.profile else []) + [h.chunk.tag for h in self.hits]


def _today() -> dt.date:
    """GLADIUS_TODAY=YYYY-MM-DD pins the date for demos and benchmarks."""
    pinned = os.environ.get("GLADIUS_TODAY")
    return dt.date.fromisoformat(pinned) if pinned else dt.date.today()


def estimate_tokens(text: str) -> int:
    return len(text) // 4


class Retriever:
    def __init__(self, router, root: Path | None = None, threshold: float = RAG_THRESHOLD, min_gap: float = RAG_MIN_GAP):
        """`router` is a router.Router; its embedding model is reused, not reloaded. `root` defaults
        to the configured workspace (GLADIUS_WORKSPACE)."""
        self.router = router
        self.threshold = threshold
        self.min_gap = min_gap
        self.root = root or workspace_dir()
        self.chunks, self.skipped = load_chunks(self.root)
        # Bold markers cost tokens and the model doesn't need them.
        self.profile = "\n\n".join(c.body for c in self.chunks if c.collection == PROFILE_COLLECTION).replace("**", "")
        self.calendar = [line for c in self.chunks if c.source.endswith("calendar.md")
                         for line in c.body.splitlines() if _CAL_LINE_RE.match(line)]
        # Arctic is asymmetric: queries get the "query" prefix (router.embed), documents get none.
        self.vecs = router.model.encode(
            [c.text for c in self.chunks], normalize_embeddings=True, convert_to_numpy=True
        )
        self.collections = np.array([c.collection for c in self.chunks])
        self.searchable = tuple(str(c) for c in dict.fromkeys(self.collections) if c != PROFILE_COLLECTION)

    def scope(self, collections: tuple[str, ...] | None) -> tuple[str, ...]:
        """A route's collections as this workspace has them (see RouteRAG.collections)."""
        present = tuple(c for c in collections or () if c in self.searchable)
        return present or self.searchable

    def retrieve(self, prompt: str, route: str, query_vec: np.ndarray | None = None) -> Retrieval:
        t0 = time.perf_counter()
        cfg = ROUTE_RAG.get(route, NO_RAG)
        hits = []
        if route == "sql" and _PROMPT_SCHEMA_RE.search(prompt):
            cfg = NO_RAG  # self-contained SQL question: it brings its own schema and needs no notes
        schema_k = cfg.schema_k
        if cfg.top_k or schema_k:
            vec = query_vec if query_vec is not None else self.router.embed([prompt])[0]
            hits = self.search(vec, ("schemas",), schema_k) if schema_k else []
            hits += self.search(vec, self.scope(cfg.collections), cfg.top_k, cfg.min_score) if cfg.top_k else []
            budget = MAX_CONTEXT_TOKENS - (estimate_tokens(self.profile_block()) if cfg.profile else 0)
            kept = []
            for h in hits:  # drop the weakest chunks first if the context budget runs out
                budget -= estimate_tokens(h.chunk.text)
                if budget < 0:
                    break
                kept.append(h)
            hits = kept
        # Small talk ("hey whats up") skips the ~300-token profile, which keeps first-token time low.
        # A workspace with no profile.md and nothing coming up in calendar.md has no profile to add.
        profile = cfg.profile and bool(hits or _PERSONAL_RE.search(prompt)) and bool(self.profile_block())
        return Retrieval(route, hits, profile, (time.perf_counter() - t0) * 1000)

    def notes_route(self, prompt: str, route: str, query_vec: np.ndarray | None = None) -> str:
        """The route that should answer: "base" for questions about the student's own courses that
        the router sent to a specialist (see NOTES_OVERRIDE_MIN), otherwise `route` unchanged."""
        if route not in NOTES_OVERRIDE_ROUTES:
            return route
        if _LOGISTICS_RE.search(prompt):
            return "base"
        if not _ABOUT_STUDENT_RE.search(prompt):
            return route
        vec = query_vec if query_vec is not None else self.router.embed([prompt])[0]
        return "base" if self.search(vec, self.scope(("courses", "syllabi", "notes")), 1, NOTES_OVERRIDE_MIN) else route

    def search(self, vec: np.ndarray, collections: tuple[str, ...], k: int, min_score: float | None = None) -> list[Hit]:
        if not self.chunks:
            return []
        all_scores = self.vecs @ vec
        floor = min_score if min_score is not None else min(self.threshold, float(np.median(all_scores)) + self.min_gap)
        idx = np.flatnonzero(np.isin(self.collections, collections))
        scores = all_scores[idx]
        order = np.argsort(-scores)[:k]
        return [Hit(self.chunks[idx[j]], float(scores[j])) for j in order if scores[j] >= floor]

    def upcoming(self, today: dt.date, days: int = UPCOMING_DAYS) -> list[str]:
        """Calendar lines dated today..today+days. Semantic search can't tell which deadlines are
        "next week", so time-sensitive prompts ("make me a study plan") get them this way."""
        out = []
        for line in self.calendar:
            month, day = _CAL_LINE_RE.match(line).groups()
            date = dt.datetime.strptime(f"{month} {day} {today.year}", "%b %d %Y").date()
            if 0 <= (date - today).days <= days:
                out.append(line)
        return out

    def profile_block(self, today: dt.date | None = None) -> str:
        today = today or _today()
        due = self.upcoming(today)
        block = self.profile
        if due:
            block += f"\n\nComing up in the next {UPCOMING_DAYS} days:\n" + "\n".join(due)
        return block

    def augment(self, prompt: str, r: Retrieval) -> str:
        """The prompt the model sees. Unchanged when nothing was retrieved."""
        if not r.hits and not r.profile:
            return prompt
        if r.route == "techwriter":
            # The tech-writer adapter copies the context back verbatim under the study-assistant
            # framing. Request first, then the source, then the sections to write: it documents it.
            source = "\n\n".join(h.chunk.body for h in r.hits)
            return (f"{prompt}\n\nHere is the source material from my notes:\n\n{source}\n\n"
                    "Write the documentation now, with sections for Overview, Parameters, Return values and Example.")
        schemas = [h for h in r.hits if h.chunk.collection == "schemas"] if r.route == "sql" else []
        prose = [h for h in r.hits if h not in schemas]
        ddl = "\n".join(schema_ddl(h.chunk.body, prompt) for h in schemas)
        if not prose and not r.profile:
            return f"{ddl}\n\n{prompt}"  # bare schema + question, the text-to-SQL training format
        today = _today()
        parts = [
            f"You are this student's study assistant. Today is {today:%A, %B %-d, %Y}. Use the notes below "
            "only if relevant; if they don't answer a course question, say so. Don't mention the notes."
        ]
        if r.profile:
            parts.append(f"## Student profile\n{self.profile_block(today)}")
        if prose:
            parts.append("## Context\n" + "\n\n".join(f"[{h.chunk.tag}]\n{h.chunk.body}" for h in prose))
        parts.append(f"## Request\n{ddl}\n\n{prompt}" if ddl else f"## Request\n{prompt}")
        return "\n\n".join(parts)


def schema_ddl(body: str, prompt: str, max_tables: int = 4) -> str:
    """The tables the prompt touches, best match first, as `CREATE TABLE t (a, b, c);` with no
    comments, types or constraints. The sql route is answered by the base model since the SQL
    adapter was dropped; base handles multi-table schemas (the adapter invented joins on them).
    Set max_tables=1 if a single-table text-to-SQL adapter comes back."""
    tables = {}
    for m in _DDL_RE.finditer(re.sub(r"--[^\n]*", "", body)):
        cols = [c.split()[0] for c in re.split(r",(?![^(]*\))", m.group(2))
                if c.strip() and c.split()[0].lower() not in _CONSTRAINTS]
        tables[m.group(1)] = (f"CREATE TABLE {m.group(1)} ({', '.join(cols)});", cols)
    if not tables:
        return ""
    words = re.findall(r"\w+", prompt.lower())

    def overlap(name: str, cols: list[str]) -> int:
        # 6-char stems so "enrolled" matches enrollments and "starting" matches start_station_id.
        parts = {w for part in [name, *cols] for w in part.lower().split("_") if len(w) >= 3 and w != "id"}
        stems = {w.rstrip("s")[:6] for w in parts}
        return sum(any(w.startswith(st) for w in words) for st in stems)

    ranked = sorted(tables, key=lambda t: -overlap(t, tables[t][1]))  # stable: ties keep file order
    touched = [t for t in ranked if overlap(t, tables[t][1])] or ranked
    return "\n".join(tables[t][0] for t in touched[:max_tables])


def evaluate(retriever: Retriever, router, cases: list[dict]) -> dict:
    """Recall of expected headings, plus negative controls that should retrieve nothing."""
    rows = []
    for case in cases:
        route = router.route(case["prompt"], use_cache=False).route
        r = retriever.retrieve(case["prompt"], case.get("route", route))
        got = [h.chunk.heading for h in r.hits]
        expected = case["expected"]
        found = [e for e in expected if e in got]
        ok = (not got) if not expected else bool(found)
        # End to end: what the app injects, using the router's pick after the notes override.
        answered_by = retriever.notes_route(case["prompt"], route)
        live = [h.chunk.heading for h in retriever.retrieve(case["prompt"], answered_by).hits]
        ok_live = (not live) if not expected else any(e in live for e in expected)
        rows.append({**case, "routed": route, "answered_by": answered_by, "got": got, "scores": [round(h.score, 3) for h in r.hits],
                     "recall": len(found) / len(expected) if expected else float(not got), "ok": ok,
                     "ok_live": ok_live})
    return {
        "hit_rate": sum(r["ok"] for r in rows) / len(rows),
        "hit_rate_live": sum(r["ok_live"] for r in rows) / len(rows),
        "recall": sum(r["recall"] for r in rows) / len(rows),
        "routing_acc": sum(r["routed"] == r["route"] for r in rows) / len(rows),
        "items": rows,
    }


if __name__ == "__main__":
    from router import Router

    router = Router()
    t0 = time.perf_counter()
    retriever = Retriever(router)
    counts = {str(c): int((retriever.collections == c).sum()) for c in dict.fromkeys(retriever.collections)}
    print(f"Workspace {retriever.root}")
    print(f"Indexed {len(retriever.chunks)} chunks {counts} in {(time.perf_counter() - t0) * 1000:.0f} ms, "
          f"index {retriever.vecs.nbytes / 1024:.0f} KB")
    for path, reason in retriever.skipped:
        print(f"  skipped {path.relative_to(retriever.root)} ({reason})")
    if retriever.root != SAMPLE_WORKSPACE.resolve():
        raise SystemExit(f"{EVAL_PATH.name} is written for the sample workspace, so no eval here.")

    cases = json.loads(EVAL_PATH.read_text())["cases"]
    res = evaluate(retriever, router, cases)
    for row in res["items"]:
        mark = "✓" if row["ok"] else "✗"
        route = row["routed"] if row["routed"] == row["route"] else f"{row['routed']}≠{row['route']}"
        print(f"\n{mark} [{route}] {row['prompt']}")
        for heading, score in zip(row["got"], row["scores"]):
            star = "*" if heading in row["expected"] else " "
            print(f"   {star} {score:.3f}  {heading}")
        missing = [e for e in row["expected"] if e not in row["got"]]
        if missing:
            print(f"     missing: {missing}")
    live_misses = [row["prompt"] for row in res["items"] if row["ok"] and not row["ok_live"]]
    for prompt in live_misses:
        print(f"  routed elsewhere, no context: {prompt}")
    print(f"\nEnd to end (actual route) hit rate {res['hit_rate_live']:.0%}")
    print(f"Hit rate {res['hit_rate']:.0%} · mean recall {res['recall']:.0%} · routing {res['routing_acc']:.0%} "
          f"({len(cases)} prompts, threshold {RAG_THRESHOLD}, min gap {RAG_MIN_GAP})")
