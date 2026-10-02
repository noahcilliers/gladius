"""Does the SQL adapter beat the base model anywhere? Writes results/sql_adapter.json.

Compares the sql adapter with the base model on:
  - data/eval_sql.json          (10 questions, 3 of them multi-table)
  - data/eval_sql_single.json   (15 single-table questions: the adapter's training distribution)
Metrics: accuracy (SQL extracted, then executed), "runs as-is" (raw output executes
correctly with no extraction), tokens per answer, and total answer time.

    python eval_sql_adapter.py     # needs ./serve.sh running
"""

import json
import re
import sqlite3
import statistics
from pathlib import Path

from bench import _sql_ok, sql_eval_prompt, sql_rows
from engine import Engine

ROOT = Path(__file__).parent


def runs_as_is(db, text: str, reference: str) -> bool:
    try:
        return sql_rows(db, text.strip().rstrip(";")) == sql_rows(db, reference)
    except Exception:
        return False


def main():
    spec = json.loads((ROOT / "data" / "eval_sql.json").read_text())
    single = json.loads((ROOT / "data" / "eval_sql_single.json").read_text())["questions"]
    db = sqlite3.connect(":memory:")
    db.executescript(spec["schema"])
    for stmt in spec["seed"]:
        db.execute(stmt)

    def n_tables(sql: str) -> int:
        return sum(bool(re.search(rf"\b{t}\b", sql)) for t in ("students", "courses", "enrollments"))

    engine = Engine()
    if not engine.has_adapter("sql"):
        raise SystemExit("The sql adapter isn't loaded (it was dropped from serve.sh). Add adapters/sql.gguf "
                         "back to its --lora list to rerun this comparison; results/sql_adapter.json has the last run.")
    sets = {"original": spec["questions"], "single_table": single}
    out = {}
    for set_name, questions in sets.items():
        rows = []
        for q in questions:
            prompt = sql_eval_prompt(spec, q) + "\nReturn only the SQL query."
            row = {"question": q["question"], "tables": n_tables(q["sql"])}
            for route in ("sql", "base"):
                text, s = engine.generate(prompt, route, max_tokens=256)
                row[route] = {"correct": _sql_ok(db, text, q["sql"]), "runs_as_is": runs_as_is(db, text, q["sql"]),
                              "tokens": s.tokens, "total_ms": s.total_ms, "answer": text}
            rows.append(row)
            print(f"  {set_name:<12} tables={row['tables']} sql={'✓' if row['sql']['correct'] else '✗'} "
                  f"base={'✓' if row['base']['correct'] else '✗'}  {q['question'][:60]}")
        summary = {}
        for route in ("sql", "base"):
            summary[route] = {
                "accuracy": statistics.mean(r[route]["correct"] for r in rows),
                "runs_as_is": statistics.mean(r[route]["runs_as_is"] for r in rows),
                "tokens_mean": statistics.mean(r[route]["tokens"] for r in rows),
                "total_ms_mean": statistics.mean(r[route]["total_ms"] for r in rows),
            }
        out[set_name] = {"summary": summary, "rows": rows}

    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "sql_adapter.json").write_text(json.dumps(out, indent=2))
    print()
    for set_name, res in out.items():
        print(f"{set_name} (n={len(res['rows'])})")
        for route, s in res["summary"].items():
            print(f"  {route:<5} accuracy {s['accuracy']:.0%} | runs as-is {s['runs_as_is']:.0%} | "
                  f"{s['tokens_mean']:.0f} tokens | {s['total_ms_mean'] / 1000:.1f} s per answer")


if __name__ == "__main__":
    main()
