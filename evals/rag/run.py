"""RAG eval: the same prompts through the full chat pipeline, on each of the three corpora.

For every case in cases.json and every corpus in corpora/ (see build_corpora.py), the prompt goes
route → notes override → retrieve → augment → generate exactly as in the app, through
core.Pipeline. Each case is also answered once with notes off, as a no-RAG reference.

What gets scored, all from what the model was actually given (turn.model_prompt), so it holds for
any retriever, chunker or prompt template:
    gold delivered   a gold passage counts if any of its needles is in the model prompt
    hit rate         note questions that got at least one gold passage
    recall           mean share of gold passages delivered
    false injection  negative controls that got any corpus text at all
    answer accuracy  answers that match every regex in the case's `facts`

Raw outputs go to runs/<label>/results.jsonl and scores are recomputed from them on every read,
so a scoring fix re-scores old runs too. Needs ./serve.sh running unless --retrieval-only.

    python -m evals.rag.run --label baseline
    python -m evals.rag.run --label new-rag --retrieval-only     # no llama-server needed
    python -m evals.rag.run --validate                           # check cases.json against the corpora
    python -m evals.rag.compare baseline new-rag
"""

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))  # the app's modules (core, rag, router, engine) live at the repo root

from evals.rag import build_corpora  # noqa: E402
from evals.rag.build_corpora import CORPORA, VARIANTS, lock_hash  # noqa: E402

CASES_PATH = HERE / "cases.json"
RUNS = HERE / "runs"
REFERENCE = "no-notes"  # the pseudo-corpus for answers with notes turned off
# Every case is asked "today". The calendar runs Oct 6 – Dec 10, 2026, so this puts Midterm 1,
# HW3 and Problem Set 5 in "next week" for the deadline prompts.
TODAY = "2026-10-05"
MIN_MARKER_CHARS = 25  # corpus lines shorter than this ("- Week 1 (Aug 24): ...") are too generic to count

_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-", "‑": "-"})
_DDL_NAME_RE = re.compile(r"CREATE TABLE\s+(\w+)", re.I)


def normalize(text: str) -> str:
    """Lowercase, no markdown emphasis or backticks, ASCII dashes, single spaces. Applied to both
    sides of every match, so a template that strips ** or reflows text still matches."""
    text = text.translate(_DASHES).replace("*", "").replace("`", "")
    return " ".join(text.lower().split())


# ---------------------------------------------------------------- cases and corpora

def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text())["cases"]


def cases_hash() -> str:
    return hashlib.sha256(CASES_PATH.read_bytes()).hexdigest()[:16]


def corpus_texts(variant: str) -> dict[str, str]:
    root = CORPORA / variant
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in build_corpora.note_files(root)}


def corpus_markers(variant: str) -> list[str]:
    """Normalized strings whose presence in a model prompt means corpus text was injected: every
    body line of at least MIN_MARKER_CHARS, plus `create table <name>` for each schema table
    (the sql route rewrites DDL, so raw schema lines never appear verbatim)."""
    markers = set()
    for text in corpus_texts(variant).values():
        for line in text.splitlines():
            if not line.startswith("#") and len(norm := normalize(line)) >= MIN_MARKER_CHARS:
                markers.add(norm)
        markers.update(f"create table {m.group(1).lower()}" for m in _DDL_NAME_RE.finditer(text))
    return sorted(markers)


def validate(cases: list[dict]) -> list[str]:
    """Every needle must occur exactly once in every corpus and never in its own prompt, so a
    match means that passage, not a coincidence."""
    problems, ids = [], set()
    full = {v: normalize("\n".join(corpus_texts(v).values())) for v in VARIANTS}
    for case in cases:
        if case["id"] in ids:
            problems.append(f"{case['id']}: duplicate id")
        ids.add(case["id"])
        if case["set"] not in ("original", "heldout"):
            problems.append(f"{case['id']}: set must be original or heldout")
        for fact in case["facts"]:
            try:
                re.compile(fact)
            except re.error as e:
                problems.append(f"{case['id']}: bad fact regex {fact!r}: {e}")
        prompt = normalize(case["prompt"])
        for gold in case["gold"]:
            for needle in gold["needles"]:
                n = normalize(needle)
                if n in prompt:
                    problems.append(f"{case['id']}: needle {needle!r} is in the prompt itself")
                for v in VARIANTS:
                    if (count := full[v].count(n)) != 1:
                        problems.append(f"{case['id']}: needle {needle!r} occurs {count}× in {v}")
    return problems


# ---------------------------------------------------------------- scoring

def score(case: dict, row: dict, markers: list[str] | None) -> dict:
    """Scores for one result row. `markers` is None for the no-notes reference."""
    out = {}
    if markers is not None:
        # What the model saw besides the question itself.
        context = normalize(row["model_prompt"].replace(case["prompt"], "", 1))
        delivered = [any(normalize(n) in context for n in g["needles"]) for g in case["gold"]]
        out["injected_lines"] = sum(m in context for m in markers)
        out["context_tokens"] = max(0, len(row["model_prompt"]) - len(case["prompt"])) // 4
        if case["gold"]:
            out["delivered"] = delivered
            out["hit"] = any(delivered)
            out["recall"] = sum(delivered) / len(delivered)
        else:
            out["clean"] = out["injected_lines"] == 0
    if row.get("answer") is not None and case["facts"]:
        answer = normalize(row["answer"])
        matched = [bool(re.search(f, answer, re.I)) for f in case["facts"]]
        out["facts_matched"] = matched
        out["correct"] = all(matched)
    return out


def _rate(xs: list) -> float | None:
    return sum(xs) / len(xs) if xs else None


def metrics(rows: list[dict], cases: dict[str, dict]) -> dict:
    """Aggregate scores for one corpus. Rows must already carry `scores`."""
    pos = [r for r in rows if cases[r["case"]]["gold"]]
    neg = [r for r in rows if not cases[r["case"]]["gold"]]
    graded = [r for r in rows if "correct" in r["scores"]]
    return {
        "n": len(rows), "n_pos": len(pos), "n_neg": len(neg),
        "hit_rate": _rate([r["scores"]["hit"] for r in pos if "hit" in r["scores"]]),
        "recall": _rate([r["scores"]["recall"] for r in pos if "recall" in r["scores"]]),
        "full_recall": _rate([r["scores"]["recall"] == 1 for r in pos if "recall" in r["scores"]]),
        "false_injection": _rate([not r["scores"]["clean"] for r in neg if "clean" in r["scores"]]),
        "answer_acc": _rate([r["scores"]["correct"] for r in graded]),
        "answer_acc_pos": _rate([r["scores"]["correct"] for r in graded if cases[r["case"]]["gold"]]),
        "answer_acc_neg": _rate([r["scores"]["correct"] for r in graded if not cases[r["case"]]["gold"]]),
        "context_tokens_pos": _rate([r["scores"]["context_tokens"] for r in pos if "context_tokens" in r["scores"]]),
        "notes_overrides": sum(bool(r["routing"].get("notes_override")) for r in rows),
        "retrieve_ms": _rate([r["retrieve_ms"] for r in rows]),
    }


# ---------------------------------------------------------------- loading a run

def load_run(run: str | Path) -> tuple[dict, list[dict]]:
    """(manifest, rows) for a run label or directory, with every row re-scored."""
    run_dir = Path(run) if Path(run).is_dir() else RUNS / str(run)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines() if line.strip()]
    cases = {c["id"]: c for c in load_cases()}
    markers = {v: corpus_markers(v) for v in VARIANTS}
    rows = [r for r in rows if r["case"] in cases]
    for r in rows:
        r["scores"] = score(cases[r["case"]], r, None if r["corpus"] == REFERENCE else markers[r["corpus"]])
    return manifest, rows


def by_corpus(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["corpus"], []).append(r)
    order = [REFERENCE, *VARIANTS]
    return {k: out[k] for k in sorted(out, key=lambda k: order.index(k) if k in order else 99)}


# ---------------------------------------------------------------- reports

def pct(x: float | None) -> str:
    return "–" if x is None else f"{x:.0%}"


METRIC_ROWS = [  # (key, label, formatter)
    ("hit_rate", "Retrieval hit rate (note questions)", pct),
    ("recall", "Gold recall (mean share of gold passages)", pct),
    ("full_recall", "All gold passages delivered", pct),
    ("false_injection", "False injection (negative controls)", pct),
    ("answer_acc", "Answer accuracy (all graded)", pct),
    ("answer_acc_pos", "Answer accuracy, note questions", pct),
    ("answer_acc_neg", "Answer accuracy, negative controls", pct),
    ("context_tokens_pos", "Added prompt tokens (note questions, mean)", lambda x: "–" if x is None else f"{x:.0f}"),
    ("notes_overrides", "Specialist → base notes overrides", lambda x: str(x)),
]


def metrics_table(groups: dict[str, list[dict]], cases: dict[str, dict]) -> list[str]:
    ms = {k: metrics(v, cases) for k, v in groups.items()}
    lines = ["| Metric | " + " | ".join(ms) + " |", "|---|" + "---|" * len(ms)]
    for key, label, fmt in METRIC_ROWS:
        lines.append(f"| {label} | " + " | ".join(fmt(m[key]) for m in ms.values()) + " |")
    return lines


def cell(case: dict, s: dict) -> str:
    parts = []
    if "delivered" in s:
        parts.append(f"R {sum(s['delivered'])}/{len(s['delivered'])}")
    elif "clean" in s:
        parts.append("R clean" if s["clean"] else f"R **injected** ({s['injected_lines']})")
    if "correct" in s:
        parts.append("A ✓" if s["correct"] else "A ✗")
    return " · ".join(parts) or "·"


def write_reports(run_dir: Path):
    manifest, rows = load_run(run_dir)
    ran = {r["case"] for r in rows}
    cases_list = [c for c in load_cases() if c["id"] in ran]  # a --cases run reports only its cases
    cases = {c["id"]: c for c in cases_list}
    groups = by_corpus(rows)
    m = manifest
    head = [
        f"# RAG eval: {m['label']}",
        "",
        f"{m['timestamp']} · commit `{m['git']['commit'][:10]}`{' (dirty)' if m['git']['dirty'] else ''} on "
        f"`{m['git']['branch']}` · cases `{m['cases_hash']}` · corpora `{m['corpora_lock']}` · today pinned to {m['today']}"
        + (" · **retrieval only**" if m["retrieval_only"] else ""),
        "",
        "R = gold passages delivered to the model (for negatives: whether any corpus text was injected). "
        "A = answer matches every expected fact. `no-notes` is the same pipeline with notes off.",
        "",
        f"## All cases ({len(cases_list)})",
        "",
        *metrics_table(groups, cases),
    ]
    for set_name, blurb in (("original", "the prompts the current retriever's thresholds were tuned on"),
                            ("heldout", "written for this eval, never used for tuning")):
        sub = {k: [r for r in v if cases[r["case"]]["set"] == set_name] for k, v in groups.items()}
        n = sum(c["set"] == set_name for c in cases_list)
        head += ["", f"## {set_name.capitalize()} set ({n}): {blurb}", "", *metrics_table(sub, cases)]

    head += ["", "## Per case", "", "| Case | Set | Routed → answered by | " + " | ".join(groups) + " |",
             "|---|---|---|" + "---|" * len(groups)]
    index = {(r["corpus"], r["case"]): r for r in rows}
    for c in cases_list:
        routes = sorted({_route_label(index[(k, c["id"])]) for k in groups if (k, c["id"]) in index and k != REFERENCE})
        cells = [cell(c, index[(k, c["id"])]["scores"]) if (k, c["id"]) in index else "" for k in groups]
        head.append(f"| `{c['id']}` | {c['set'][:4]} | {' / '.join(routes)} | " + " | ".join(cells) + " |")
    (run_dir / "summary.md").write_text("\n".join(head) + "\n")
    (run_dir / "summary.json").write_text(json.dumps({
        "label": m["label"], "cases_hash": m["cases_hash"], "corpora_lock": m["corpora_lock"],
        "all": {k: metrics(v, cases) for k, v in groups.items()},
        **{s: {k: metrics([r for r in v if cases[r["case"]]["set"] == s], cases) for k, v in groups.items()}
           for s in ("original", "heldout")},
    }, indent=1) + "\n")

    if not m["retrieval_only"]:
        out = [f"# Answers: {m['label']}", "", "Every response, grouped by case. Model prompts are in results.jsonl.", ""]
        for c in cases_list:
            out += [f"## `{c['id']}` ({c['set']})", "", f"> {c['prompt']}", ""]
            for k in groups:
                if (k, c["id"]) not in index:
                    continue
                r = index[(k, c["id"])]
                out += [answer_block(k, c, r), ""]
        (run_dir / "answers.md").write_text("\n".join(out))


def _route_label(r: dict) -> str:
    over = r["routing"].get("notes_override")
    return f"{over} → {r['route']}" if over else r["route"]


def answer_block(corpus: str, case: dict, r: dict) -> str:
    s = r["scores"]
    missed = [f for f, ok in zip(case["facts"], s.get("facts_matched", [])) if not ok]
    sources = ", ".join(f"`{x}`" for x in (r.get("rag") or {}).get("sources", [])) or "none"
    meta = f"**{corpus}** · {_route_label(r)} · {cell(case, s)}"
    if corpus != REFERENCE:
        meta += f" · {s.get('context_tokens', 0)} context tokens · sources: {sources}"
    if missed:
        meta += " · missed facts: " + ", ".join(f"`{f}`" for f in missed)
    return f"{meta}\n\n~~~~text\n{(r.get('answer') or '').strip()}\n~~~~"


# ---------------------------------------------------------------- running

def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def build_manifest(label: str, args, engine) -> dict:
    """Everything needed to tell whether two runs are comparable."""
    import rag.retriever as retriever_mod  # whatever the current implementation exposes
    import router as router_mod

    # Dirty = uncommitted changes to the app. The eval's own files are covered by the hashes below.
    dirty = [line for line in _git("status", "--porcelain").splitlines() if not line[3:].startswith("evals/")]
    manifest = {
        "label": label,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git": {"commit": _git("rev-parse", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
                "dirty": bool(dirty), "dirty_files": dirty[:50]},
        "cases_hash": cases_hash(),
        "corpora_lock": lock_hash(),
        "harness_hash": hashlib.sha256(b"".join((HERE / f).read_bytes() for f in ("run.py", "build_corpora.py"))).hexdigest()[:16],
        "today": TODAY,
        "corpora": list(args.corpora),
        "case_filter": args.cases,
        "retrieval_only": args.retrieval_only,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "embed_model": getattr(router_mod, "EMBED_MODEL", None),
        # Module-level constants of the retriever (thresholds, budgets), to see what was tuned.
        "retriever_constants": {k: v for k, v in vars(retriever_mod).items()
                                if k.isupper() and not k.startswith("_") and isinstance(v, (int, float, str, tuple))},
        "env": {k: os.environ.get(k) for k in ("GLADIUS_WORKSPACE", "GLADIUS_TODAY", "LLAMA_URL", "HF_HUB_OFFLINE")},
    }
    if engine is not None:
        import requests

        props = requests.get(f"{engine.url}/props", timeout=5).json()
        adapters = requests.get(f"{engine.url}/lora-adapters", timeout=5).json()
        # The server reports paths relative to the folder serve.sh ran in, usually the main checkout.
        proc = _server_process(engine.url)
        server_dir = Path(proc.cwd()) if proc else Path.cwd()
        model_path = server_dir / props.get("model_path", "")
        manifest["server"] = {
            "url": engine.url,
            "cmdline": proc.cmdline() if proc else None,
            "build_info": props.get("build_info"),
            "model_path": str(model_path),
            "model_bytes": model_path.stat().st_size if model_path.is_file() else None,
            "n_ctx": (props.get("default_generation_settings") or {}).get("n_ctx"),
            "adapters": [{"id": a["id"], "path": a["path"], "sha256": _sha256_file(server_dir / a["path"])}
                         for a in adapters],
        }
    return manifest


def _server_process(url: str):
    """The llama-server process behind `url`, matched on its --port (several can run at once,
    e.g. one per worktree), or None."""
    import psutil

    port = int(url.rsplit(":", 1)[-1].split("/")[0]) if url.count(":") > 1 else 8080
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            args = p.info["cmdline"] or []
            if p.info["name"] == "llama-server" and int(args[args.index("--port") + 1] if "--port" in args else 8080) == port:
                p.cwd()  # raises if we can't inspect it
                return p
        except (psutil.Error, ValueError, IndexError):
            continue
    return None


class _NoEngine:
    """Stands in for engine.Engine in --retrieval-only runs, so llama-server needn't be up."""
    url = None


def main():
    ap = argparse.ArgumentParser(description="Run the RAG eval on the three corpora.")
    ap.add_argument("--label", help="run name; results go to evals/rag/runs/<label>/")
    ap.add_argument("--corpora", default=",".join(VARIANTS), help="comma-separated subset of " + ",".join(VARIANTS))
    ap.add_argument("--cases", help="comma-separated case ids (a partial run; for debugging)")
    ap.add_argument("--retrieval-only", action="store_true", help="skip generation (no llama-server needed)")
    ap.add_argument("--no-reference", action="store_true", help="skip the notes-off answers")
    ap.add_argument("--resume", action="store_true", help="keep finished rows in an existing run and do the rest")
    ap.add_argument("--force", action="store_true", help="overwrite an existing run")
    ap.add_argument("--validate", action="store_true", help="only check cases.json and the corpora")
    ap.add_argument("--report", metavar="RUN", help="only rewrite summary.md / answers.md for an existing run")
    args = ap.parse_args()
    args.corpora = [c for c in args.corpora.split(",") if c]

    cases = load_cases()
    problems = build_corpora.check() + validate(cases)
    if args.validate or problems:
        for p in problems:
            print(p)
        print(f"{len(cases)} cases, corpora {lock_hash()}: " + ("OK" if not problems else f"{len(problems)} problem(s)"))
        sys.exit(1 if problems else 0)
    if args.report:
        write_reports(Path(args.report) if Path(args.report).is_dir() else RUNS / args.report)
        return
    if not args.label:
        ap.error("--label is required")
    if unknown := set(args.corpora) - set(VARIANTS):
        ap.error(f"unknown corpora: {sorted(unknown)}")
    if args.cases:
        wanted = set(args.cases.split(","))
        if unknown := wanted - {c["id"] for c in cases}:
            ap.error(f"unknown case ids: {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in wanted]

    run_dir = RUNS / args.label
    results_path = run_dir / "results.jsonl"
    if run_dir.exists() and not (args.resume or args.force):
        sys.exit(f"{run_dir} exists; pass --resume to finish it or --force to start over")
    if args.force and results_path.exists():
        results_path.unlink()
    run_dir.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.resume and results_path.exists():
        kept = []
        for line in results_path.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:  # the row being written when the run was killed
                continue
            kept.append(line)
            done.add((r["corpus"], r["case"]))
        results_path.write_text("".join(f"{line}\n" for line in kept))

    # Pinned before the app's modules are imported, and set in-process so .env can't override them.
    os.environ["GLADIUS_TODAY"] = TODAY
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # use the cached embedding model; no network
    from core import Options, Pipeline
    from router import Router

    engine = None
    if not args.retrieval_only:
        from engine import Engine
        engine = Engine()
        for route in ["base", *engine.adapter_ids]:  # cold weights make the first answers slow
            engine.generate("Hi", route, max_tokens=4)
    router = Router()
    router.route("warm-up", use_cache=False)

    manifest = build_manifest(args.label, args, engine)
    if args.resume and (run_dir / "manifest.json").exists():
        old = json.loads((run_dir / "manifest.json").read_text())
        for key in ("cases_hash", "corpora_lock"):
            if old[key] != manifest[key]:
                sys.exit(f"can't resume: {key} changed since this run started ({old[key]} → {manifest[key]})")
        manifest["timestamp"] = old["timestamp"]
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str) + "\n")

    plan = ([] if args.retrieval_only or args.no_reference else [REFERENCE]) + args.corpora
    memo: dict[tuple[str, str], str] = {}  # (route, model prompt) -> answer; greedy decoding, so identical inputs repeat
    t_start = time.perf_counter()
    with results_path.open("a") as out:
        for corpus in plan:
            os.environ["GLADIUS_WORKSPACE"] = str(CORPORA / (corpus if corpus != REFERENCE else VARIANTS[0]))
            t0 = time.perf_counter()
            pipeline = Pipeline(router=router, engine=engine or _NoEngine())
            print(f"\n== {corpus}: {pipeline.n_chunks} chunks from {pipeline.workspace} "
                  f"({(time.perf_counter() - t0) * 1000:.0f} ms to index)")
            for case in cases:
                if (corpus, case["id"]) in done:
                    continue
                row = run_case(pipeline, router, case, corpus, Options, generate=engine is not None, memo=memo)
                out.write(json.dumps(row, default=str) + "\n")
                out.flush()
                markers = None if corpus == REFERENCE else corpus_markers(corpus)
                print(f"  {cell(case, score(case, row, markers)):<22} {_route_label(row):<18} {case['id']}")
    print(f"\nDone in {(time.perf_counter() - t_start) / 60:.1f} min")
    write_reports(run_dir)
    print(f"Wrote {run_dir.relative_to(REPO)}/summary.md" + ("" if args.retrieval_only else " and answers.md"))
    print((run_dir / "summary.md").read_text().split("## Original")[0])


def run_case(pipeline, router, case: dict, corpus: str, Options, generate: bool, memo: dict) -> dict:
    """One prompt through the app's pipeline: the only place the harness touches app code."""
    router.clear_cache()  # each case routes from scratch, whatever ran before it
    t0 = time.perf_counter()
    turn = pipeline.route(case["prompt"], Options(use_rag=corpus != REFERENCE))
    pipeline.retrieve(turn)
    row = {"corpus": corpus, "case": case["id"], "route": turn.route, "routing": turn.routing,
           "rag": turn.rag, "model_prompt": turn.model_prompt,
           "retrieve_ms": (time.perf_counter() - t0) * 1000, "answer": None}
    if generate:
        key = (turn.route, turn.model_prompt)
        if key in memo:
            row |= {"answer": memo[key], "reused_answer": True}
        else:
            t1 = time.perf_counter()
            row["answer"] = memo[key] = "".join(pipeline.stream(turn))
            row |= {"generate_ms": (time.perf_counter() - t1) * 1000, "stats": turn.stats}
    return row


if __name__ == "__main__":
    main()
