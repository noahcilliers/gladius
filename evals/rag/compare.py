"""Compare two RAG eval runs (e.g. the baseline and the new retriever) case by case.

Both runs are re-scored with the current scoring code, metrics are shown side by side per corpus,
and every case whose retrieval or answer changed is listed with both answers. Refuses runs made
with different cases or corpora, since their numbers wouldn't measure the same thing.

    python -m evals.rag.compare baseline new-rag          # prints, and writes runs/new-rag/compare_vs_baseline.md
"""

import argparse
import sys
from pathlib import Path

from evals.rag.run import (METRIC_ROWS, REFERENCE, RUNS, answer_block, by_corpus, cell, load_cases, load_run,
                           metrics)


def _delta(key: str, a, b) -> str:
    if a is None or b is None:
        return ""
    if key in ("context_tokens_pos", "notes_overrides"):
        d = b - a
        return f" ({d:+.0f})" if round(d) else ""
    d = round((b - a) * 100)
    return f" ({d:+d})" if d else ""


def comparability(ma: dict, mb: dict) -> tuple[list[str], list[str]]:
    """(blocking problems, warnings) for comparing run a with run b."""
    blocking = [f"{k} differs: {ma.get(k)} vs {mb.get(k)}" for k in ("cases_hash", "corpora_lock", "today")
                if ma.get(k) != mb.get(k)]
    warnings = []
    sa, sb = ma.get("server") or {}, mb.get("server") or {}
    if sa and sb:
        if Path(sa.get("model_path", "")).name != Path(sb.get("model_path", "")).name or sa.get("model_bytes") != sb.get("model_bytes"):
            warnings.append("different base model file")
        if [x.get("sha256") for x in sa.get("adapters", [])] != [x.get("sha256") for x in sb.get("adapters", [])]:
            warnings.append("different LoRA adapters")
        if sa.get("build_info") != sb.get("build_info"):
            warnings.append(f"different llama-server build ({sa.get('build_info')} vs {sb.get('build_info')})")
    if ma.get("retrieval_only") != mb.get("retrieval_only"):
        warnings.append("one run is retrieval-only, so answer metrics only exist for the other")
    for m in (ma, mb):
        if m["git"]["dirty"]:
            warnings.append(f"{m['label']} ran with uncommitted app changes: {', '.join(m['git']['dirty_files'][:5])}")
        if m.get("case_filter"):
            warnings.append(f"{m['label']} is a partial run (--cases {m['case_filter']})")
    return blocking, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("a", help="the reference run (label or directory), e.g. baseline")
    ap.add_argument("b", help="the run to compare against it")
    ap.add_argument("--allow-mismatch", action="store_true", help="compare even if cases or corpora differ")
    args = ap.parse_args()

    ma, rows_a = load_run(args.a)
    mb, rows_b = load_run(args.b)
    blocking, warnings = comparability(ma, mb)
    if blocking and not args.allow_mismatch:
        sys.exit("Not comparable:\n  " + "\n  ".join(blocking) + "\n(--allow-mismatch to compare anyway)")
    cases_list = load_cases()
    cases = {c["id"]: c for c in cases_list}
    ga, gb = by_corpus(rows_a), by_corpus(rows_b)
    corpora = [k for k in gb if k in ga]
    la, lb = ma["label"], mb["label"]

    out = [f"# {lb} vs {la}", "",
           f"`{la}`: commit `{ma['git']['commit'][:10]}`, {ma['timestamp']}  ",
           f"`{lb}`: commit `{mb['git']['commit'][:10]}`, {mb['timestamp']}  ",
           f"cases `{mb['cases_hash']}` · corpora `{mb['corpora_lock']}` · cells read {la} → {lb} (change in points)", ""]
    out += [f"> ⚠️ {w}" for w in blocking + warnings] + ([""] if blocking or warnings else [])

    for scope, keep in (("All cases", lambda c: True), ("Original set", lambda c: c["set"] == "original"),
                        ("Heldout set", lambda c: c["set"] == "heldout")):
        out += [f"## {scope}", "", "| Metric | " + " | ".join(corpora) + " |", "|---|" + "---|" * len(corpora)]
        msa = {k: metrics([r for r in ga[k] if keep(cases[r["case"]])], cases) for k in corpora}
        msb = {k: metrics([r for r in gb[k] if keep(cases[r["case"]])], cases) for k in corpora}
        for key, label, fmt in METRIC_ROWS:
            vals = [f"{fmt(msa[k][key])} → {fmt(msb[k][key])}{_delta(key, msa[k][key], msb[k][key])}" for k in corpora]
            out.append(f"| {label} | " + " | ".join(vals) + " |")
        out.append("")

    ia = {(r["corpus"], r["case"]): r for r in rows_a}
    ib = {(r["corpus"], r["case"]): r for r in rows_b}
    changed = []
    for c in cases_list:
        for k in corpora:
            ra, rb = ia.get((k, c["id"])), ib.get((k, c["id"]))
            if ra and rb and cell(c, ra["scores"]) != cell(c, rb["scores"]):
                changed.append((c, k, ra, rb))
    out += [f"## Cases that changed ({len(changed)})", "", f"| Case | Corpus | {la} | {lb} |", "|---|---|---|---|"]
    out += [f"| `{c['id']}` | {k} | {cell(c, ra['scores'])} | {cell(c, rb['scores'])} |" for c, k, ra, rb in changed]
    print("\n".join(out))

    if not (ma["retrieval_only"] or mb["retrieval_only"]):
        out += ["", "## Answers for the changed cases", ""]
        for c, k, ra, rb in changed:
            if k == REFERENCE and ra.get("answer") == rb.get("answer"):
                continue
            out += [f"### `{c['id']}` on {k}", "", f"> {c['prompt']}", "",
                    f"*{la}*: " + answer_block(k, c, ra), "", f"*{lb}*: " + answer_block(k, c, rb), ""]
    run_dir = Path(args.b) if Path(args.b).is_dir() else RUNS / args.b
    path = run_dir / f"compare_vs_{la}.md"
    path.write_text("\n".join(out) + "\n")
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
