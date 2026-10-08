"""Context sentences: the base model says where each chunk sits before the chunk is embedded.

A chunk of real notes rarely says what it's about ("prof said the midterm covers ch 1-4"). The
breadcrumb (Chunk.breadcrumb) adds the file and headings; this adds what only reading the file
tells you: the course, the kind of document, the topic, the people and dates. The base model reads
the file and writes a sentence or two for each of its chunks (Anthropic's "contextual retrieval").

That's one model call per chunk, ~1-2 s each on an M4, so sentences are cached by chunk content in
cache/rag/contexts.json and only new or edited chunks go to the model. The retriever only reads the
cache: a chunk with no sentence yet is embedded with its breadcrumb alone.

    python -m rag.context            # sentences for the workspace's new and edited chunks
    python -m rag.context --redo     # rewrite them all (e.g. to try another model)

Needs llama-server (./serve.sh); uses the base model with every adapter off. A file too long for the
server's context (-c in serve.sh) is shown to the model a page at a time, with its outline.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

import requests

from engine import SERVER_URL
from rag.workspace import PROFILE_COLLECTION, Chunk, load_chunks, parse, read_lines, walk, workspace_dir
from settings import ROOT

CACHE_PATH = ROOT / "cache" / "rag" / "contexts.json"
PROMPT_VERSION = 1  # bump when PROMPT changes, so cached sentences are rewritten
MODES = ("llm", "path", "off")  # GLADIUS_RAG_CONTEXT, see context_mode()
MAX_CONTEXT_CHARS = 400  # keeps breadcrumb + sentence + chunk inside the embedder's 512 tokens
ANSWER_TOKENS = 100
PROMPT_TOKENS = 200  # the instructions and chat template, around the document and the chunk
OUTLINE_CHARS = 800  # a paged file's heading list, shown with each page
# The 3B model opens most answers with this whatever the prompt says. Every chunk would share the words.
_FILLER_RE = re.compile(r"^(?:this|the) chunk (?:fits (?:in|into|within)(?: the (?:overall )?document)? as|is situated (?:with)?in|is (?:taken )?from|"
                        r"comes from|belongs to|is)\s+(?:(?:a )?part of\s+)?", re.I)

PROMPT = """<document path="{source}">
{document}
</document>

Here is a chunk from that document:
<chunk>
{chunk}
</chunk>

In one or two sentences, say where this chunk fits in the document so a search engine can find it: \
the course or subject, the kind of document (lecture notes, syllabus, assignment...) and what the chunk \
covers. Use names, course codes and dates from the document even if the chunk leaves them out. Start \
with the course or subject, not with "This chunk". Reply with the sentences only."""


def context_mode() -> str:
    """What chunks are embedded with: "llm" (breadcrumb + cached sentence, the default), "path"
    (breadcrumb only) or "off" (heading only, as before). Set GLADIUS_RAG_CONTEXT to compare."""
    mode = os.environ.get("GLADIUS_RAG_CONTEXT", "").strip().lower() or "llm"
    if mode not in MODES:
        raise ValueError(f"GLADIUS_RAG_CONTEXT must be one of {', '.join(MODES)}, not {mode!r}")
    return mode


def needs_context(c: Chunk) -> bool:
    return c.collection != PROFILE_COLLECTION  # the profile is prepended, never searched


def cache_key(c: Chunk) -> str:
    """Same file, headings and text: same sentence. Editing a chunk, or moving its file, rewrites it."""
    raw = json.dumps([PROMPT_VERSION, c.source, c.path, c.heading, c.part, c.body], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class ContextCache:
    """Sentences by cache_key, shared by every workspace. Entries for deleted chunks stay (~300 bytes each)."""

    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        try:
            self.entries = json.loads(path.read_text())
        except (OSError, ValueError):
            self.entries = {}

    def get(self, c: Chunk) -> str | None:
        entry = self.entries.get(cache_key(c))
        return entry["context"] if entry else None

    def put(self, c: Chunk, context: str, model: str):
        self.entries[cache_key(c)] = {"context": context, "model": model, "source": c.source}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, ensure_ascii=False, indent=1))
        tmp.replace(self.path)  # never a half-written cache, even on Ctrl-C


class ContextWriter:
    """Writes the sentences with llama-server's base model."""

    def __init__(self, url: str = SERVER_URL):
        self.url = url
        props = requests.get(f"{url}/props", timeout=5).json()
        self.n_ctx = props["default_generation_settings"]["n_ctx"]
        self.model = Path(props.get("model_path", "unknown")).name
        # Every loaded adapter at scale 0: without this the server's own scales (1.0) apply.
        resp = requests.get(f"{url}/lora-adapters", timeout=5)
        self.lora = [{"id": a["id"], "scale": 0.0} for a in resp.json()] if resp.ok else []

    def tokens(self, text: str) -> int:
        return len(requests.post(f"{self.url}/tokenize", json={"content": text}, timeout=30).json()["tokens"])

    def documents(self, lines: list[str], chunks: list[Chunk]) -> list[str]:
        """What the model reads for each chunk: the whole file if it fits beside the chunk, else the
        file's outline and the page the chunk starts on. Chunks on the same page get the same text,
        so llama-server's prompt cache reads it once."""
        text = "\n".join(lines).strip()
        n = max(self.tokens(text), 1)
        chars_per_token = len(text) / n
        longest = max(len(c.body) for c in chunks) / chars_per_token
        budget = self.n_ctx - PROMPT_TOKENS - ANSWER_TOKENS - int(longest)
        if n <= budget:
            return [text] * len(chunks)
        outline = "\n".join("  " * (s.level - 1) + s.heading for s in walk(parse(lines)) if s.level)
        if len(outline) > OUTLINE_CHARS:
            outline = outline[:OUTLINE_CHARS].rsplit("\n", 1)[0] + "\n  ..."
        outline = f"Outline:\n{outline}\n\n" if outline else ""
        page_chars = int(budget * chars_per_token * 0.9) - len(outline)  # 0.9: chars per token varies
        pages = _pages(lines, max(page_chars, 500))
        out = []
        for c in chunks:
            start, end = next(p for p in pages if p[0] <= c.lines[0] - 1 < p[1]) if c.lines[0] else pages[0]
            page = "\n".join(lines[start:end]).strip()
            out.append(f"{outline}[lines {start + 1}-{end} of {len(lines)}]\n{page}")
        return out

    def write(self, c: Chunk, document: str) -> str:
        body = {
            "messages": [{"role": "user", "content": PROMPT.format(source=c.source, document=document, chunk=c.body)}],
            "max_tokens": ANSWER_TOKENS,
            "temperature": 0,
            "seed": 0,
            "cache_prompt": True,  # the document comes first, so the next chunk reuses it
            "lora": self.lora,
        }
        resp = requests.post(f"{self.url}/v1/chat/completions", json=body, timeout=600)
        resp.raise_for_status()
        return clean(resp.json()["choices"][0]["message"]["content"])


def _pages(lines: list[str], max_chars: int) -> list[tuple[int, int]]:
    """(start, end) line ranges of at most ~max_chars, cut at a heading if there's one in the second
    half of the page, else at a blank line, else wherever it's full."""
    pages, start, size, heading_at, blank_at = [], 0, 0, None, None
    for i, line in enumerate(lines):
        if size + len(line) > max_chars and i > start:
            cut = heading_at or blank_at or i
            pages.append((start, cut))
            start, heading_at, blank_at = cut, None, None
            size = sum(len(x) + 1 for x in lines[cut:i])
        if i > start and size > max_chars // 2:
            if line.startswith("#"):
                heading_at = i
            elif not line.strip():
                blank_at = i
        size += len(line) + 1
    return pages + [(start, len(lines))]


def clean(text: str) -> str:
    """The first paragraph, on one line, without a "Context:" label, cut at a sentence if too long."""
    text = " ".join(text.strip().split("\n\n")[0].split())
    text = re.sub(r"^(?:context|here is[^:]*):\s*", "", text, flags=re.I)
    text = _FILLER_RE.sub("", text)
    text = text[:1].upper() + text[1:]
    if len(text) > MAX_CONTEXT_CHARS:
        cut = text.rfind(". ", 0, MAX_CONTEXT_CHARS)
        text = text[:cut + 1] if cut > 0 else text[:MAX_CONTEXT_CHARS]
    return text


def write_contexts(root: Path, todo: list[Chunk], cache: ContextCache, writer: ContextWriter,
                   log: Callable[[str], None] = print, show: bool = False) -> dict:
    """Write and cache a sentence for each chunk in `todo`, a file at a time. The cache is saved after
    every chunk, so stopping loses nothing."""
    by_file: dict[str, list[Chunk]] = {}
    for c in todo:
        by_file.setdefault(c.source, []).append(c)
    t0, done, failed = time.perf_counter(), 0, []
    for k, (source, cs) in enumerate(by_file.items(), 1):
        t_file = time.perf_counter()
        documents = writer.documents(read_lines(root / source), cs)
        for c, document in zip(cs, documents):
            try:
                context = writer.write(c, document)
            except requests.HTTPError as e:  # e.g. still over the context size: keep going without it
                failed.append((c.tag, str(e)))
                continue
            cache.put(c, context, writer.model)
            cache.save()
            done += 1
            if show:
                log(f"    {c.tag}\n      → {context}")
        elapsed = time.perf_counter() - t0
        left = elapsed / done * (len(todo) - done - len(failed)) if done else 0
        log(f"  [{done + len(failed)}/{len(todo)}] {source}: {len(cs)} in {time.perf_counter() - t_file:.1f}s"
            f"{f', ~{left / 60:.0f} min left' if left > 90 else ''}")
    return {"written": done, "failed": failed, "seconds": time.perf_counter() - t0}


def main():
    ap = argparse.ArgumentParser(description="Write context sentences for the workspace's chunks (needs llama-server).")
    ap.add_argument("--redo", action="store_true", help="rewrite every sentence, not just the missing ones")
    ap.add_argument("--limit", type=int, help="stop after this many chunks (to try the prompt)")
    ap.add_argument("--show", action="store_true", help="print each sentence as it's written")
    args = ap.parse_args()

    if context_mode() != "llm":
        print(f"GLADIUS_RAG_CONTEXT={context_mode()}: chunks are embedded without context sentences.")
        return
    root = workspace_dir()
    chunks = [c for c in load_chunks(root)[0] if needs_context(c)]
    cache = ContextCache()
    todo = [c for c in chunks if args.redo or cache.get(c) is None][:args.limit]
    if not todo:
        print(f"Context sentences: all {len(chunks)} chunks in {root} have one.")
        return
    try:
        writer = ContextWriter()
    except requests.RequestException:
        print(f"Context sentences: {len(todo)} chunks need one, but llama-server isn't running at {SERVER_URL}. "
              "Start it with ./serve.sh and run python -m rag.context.")
        sys.exit(1)
    eta = len(todo) * 1.8  # seconds, M4
    print(f"Writing context sentences for {len(todo)} of {len(chunks)} chunks in {root} ({writer.model}, "
          f"~{f'{eta / 60:.0f} min' if eta > 90 else f'{eta:.0f} s'}). Ctrl-C stops; finished ones are kept.")
    try:
        res = write_contexts(root, todo, cache, writer, show=args.show)
    except KeyboardInterrupt:
        print("\nStopped. Run python -m rag.context again to finish; chunks without a sentence use their breadcrumb.")
        return
    except requests.ConnectionError:
        print(f"\nllama-server at {SERVER_URL} went away. Finished sentences are kept; run python -m rag.context again.")
        sys.exit(1)
    print(f"Wrote {res['written']} in {res['seconds']:.0f}s ({res['seconds'] / max(res['written'], 1):.2f}s each)")
    for tag, err in res["failed"]:
        print(f"  failed: {tag}: {err}")


if __name__ == "__main__":
    main()
