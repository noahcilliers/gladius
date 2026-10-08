"""Build the three eval corpora from corpora/detailed, and lock them.

    detailed  the sample student as authored for the demo: every `##` heading names the course
              and spells out the section ("CS 301 Database Systems syllabus — Letter grade
              cutoffs (percent needed for an A, B, C) and regrade requests").
    sparse    the same sections with the short headings a student would write ("## Grades"),
              from sparse_headings.json.
    flat      the same text with every heading line removed.

Bodies are byte-identical across the three, so headings are the only thing that changes.
corpora/detailed is a frozen copy of data/student (minus its README) and is never regenerated;
sparse/ and flat/ are derived from it. corpora.lock records a hash of every file so a run can
prove it used the same corpora as the baseline.

    python -m evals.rag.build_corpora           # rewrite sparse/, flat/ and corpora.lock
    python -m evals.rag.build_corpora --check   # fail if anything on disk drifted from the lock
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
CORPORA = HERE / "corpora"
VARIANTS = ("detailed", "sparse", "flat")
HEADINGS_PATH = HERE / "sparse_headings.json"
LOCK_PATH = HERE / "corpora.lock"

_HEADING_RE = re.compile(r"^#{1,6} ")


def note_files(root: Path) -> list[Path]:
    """Every file in a corpus, sorted. Hidden files and folders (e.g. an index cache a future
    retriever writes into the workspace) aren't part of the corpus."""
    return sorted(p for p in root.rglob("*") if p.is_file()
                  and not any(part.startswith(".") for part in p.relative_to(root).parts))


def _lines_outside_code(text: str):
    """(line, is_in_fenced_code) for each line, so `# comment` inside ``` isn't a heading."""
    fenced = False
    for line in text.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
            yield line, True
        else:
            yield line, fenced


def to_sparse(text: str, rel: str, headings: dict[str, dict[str, str]]) -> str:
    mapping = headings.get(rel, {})
    out = []
    for line, code in _lines_outside_code(text):
        if not code and _HEADING_RE.match(line):
            if line not in mapping:
                raise SystemExit(f"{rel}: no sparse heading for {line!r} in {HEADINGS_PATH.name}")
            line = mapping[line]
        out.append(line)
    return "\n".join(out)


def to_flat(text: str) -> str:
    kept = [line for line, code in _lines_outside_code(text) if code or not _HEADING_RE.match(line)]
    flat = re.sub(r"\n{3,}", "\n\n", "\n".join(kept))  # a dropped heading leaves a double gap
    return flat.lstrip("\n")


def derive() -> dict[str, dict[str, str]]:
    """{variant: {relative path: text}} for all three corpora, built from detailed/."""
    headings = json.loads(HEADINGS_PATH.read_text())
    headings.pop("_note", None)
    detailed = CORPORA / "detailed"
    out = {v: {} for v in VARIANTS}
    for path in note_files(detailed):
        rel = path.relative_to(detailed).as_posix()
        text = path.read_text(encoding="utf-8")
        out["detailed"][rel] = text
        out["sparse"][rel] = to_sparse(text, rel, headings)
        out["flat"][rel] = to_flat(text)
    unused = set(headings) - set(out["detailed"])
    if unused:
        raise SystemExit(f"{HEADINGS_PATH.name} names files that aren't in corpora/detailed: {sorted(unused)}")
    return out


def digest(texts: dict[str, dict[str, str]]) -> dict[str, str]:
    return {f"{v}/{rel}": hashlib.sha256(t.encode()).hexdigest()
            for v in VARIANTS for rel, t in sorted(texts[v].items())}


def on_disk() -> dict[str, dict[str, str]]:
    return {v: {p.relative_to(CORPORA / v).as_posix(): p.read_text(encoding="utf-8")
                for p in note_files(CORPORA / v)} for v in VARIANTS}


def lock_hash() -> str:
    """One hash for the whole locked corpus set; runs record it in their manifest."""
    return hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest()[:16]


def check() -> list[str]:
    """Problems with the corpora on disk; empty when they match the lock exactly."""
    if not LOCK_PATH.exists():
        return [f"{LOCK_PATH.name} is missing; run python -m evals.rag.build_corpora"]
    locked = json.loads(LOCK_PATH.read_text())
    actual = digest(on_disk())
    problems = [f"changed: {k}" for k in sorted(locked.keys() & actual.keys()) if locked[k] != actual[k]]
    problems += [f"missing: {k}" for k in sorted(locked.keys() - actual.keys())]
    problems += [f"unexpected: {k}" for k in sorted(actual.keys() - locked.keys())]
    if not problems and digest(derive()) != actual:
        problems.append("sparse/ or flat/ no longer match what detailed/ + sparse_headings.json produce")
    return problems


def build():
    texts = derive()
    for v in ("sparse", "flat"):
        shutil.rmtree(CORPORA / v, ignore_errors=True)
        for rel, text in texts[v].items():
            dest = CORPORA / v / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
    LOCK_PATH.write_text(json.dumps(digest(texts), indent=1) + "\n")
    for v in VARIANTS:
        n_head = sum(1 for t in texts[v].values() for line, code in _lines_outside_code(t)
                     if not code and _HEADING_RE.match(line))
        chars = sum(len(t) for t in texts[v].values())
        print(f"{v:<9} {len(texts[v])} files, {n_head:>2} heading lines, {chars:,} chars")
    print(f"Wrote {LOCK_PATH.relative_to(HERE.parent.parent)} ({lock_hash()})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="verify the corpora against corpora.lock")
    args = ap.parse_args()
    if args.check:
        problems = check()
        for p in problems:
            print(p)
        print("corpora OK" if not problems else f"{len(problems)} problem(s)")
        sys.exit(1 if problems else 0)
    build()
