"""Benchmarks: size, RAM, time and quality. Writes results/results.json.

Needs ./serve.sh running. Takes ~10-15 minutes on an 8 GB M1.
    python bench.py            # everything
    python bench.py --quick    # 3 prompts per task, for a smoke test
"""

import argparse
import json
import re
import sqlite3
import statistics
import threading
import time
from pathlib import Path

from engine import Engine, process_mem_mb
from router import Router

ROOT = Path(__file__).parent
BASE_MODEL = ROOT / "models" / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
OUT = ROOT / "results" / "results.json"
RAM_BUDGET_MB = 3000
TIMING_PROMPT = "Explain in three sentences why the sky is blue."


class PeakRam(threading.Thread):
    """Samples llama-server RSS + this process's RSS every 50 ms."""

    def __init__(self, engine: Engine):
        super().__init__(daemon=True)
        self.engine, self.peak_mb, self.stop = engine, 0.0, threading.Event()

    def run(self):
        while not self.stop.is_set():
            self.peak_mb = max(self.peak_mb, self.engine.server_mem_mb() + process_mem_mb())
            time.sleep(0.05)


def bench_size(engine: Engine) -> dict:
    base_mb = BASE_MODEL.stat().st_size / 1e6
    adapters = {n: (ROOT / "adapters" / f"{n}.gguf").stat().st_size / 1e6 for n in engine.adapter_ids}
    return {
        "base_mb": base_mb,
        "adapters_mb": adapters,
        "ours_total_mb": base_mb + sum(adapters.values()),
        "separate_models_mb": base_mb * (len(adapters) + 1),  # one full model per specialist + base
    }


def bench_router(router: Router, prompts: list[str]) -> dict:
    router.route("warm-up", use_cache=False)
    miss = [router.route(p, use_cache=False).latency_ms for p in prompts]
    router.clear_cache()
    for p in prompts:
        router.route(p)
    exact = [router.route(p).latency_ms for p in prompts]
    router.clear_cache()
    return {"route_ms_mean": statistics.mean(miss), "route_ms_p95": _p95(miss),
            "cache_hit_ms_mean": statistics.mean(exact)}


def bench_generation(engine: Engine, runs: int = 3) -> dict:
    out = {}
    for route in ["base", *engine.adapter_ids]:
        engine.generate(TIMING_PROMPT, route, max_tokens=64)  # warm-up, discarded
        stats = [engine.generate(TIMING_PROMPT, route, max_tokens=128)[1] for _ in range(runs)]
        out[route] = {"ttft_ms": statistics.mean(s.ttft_ms for s in stats),
                      "tok_per_s": statistics.mean(s.tok_per_s for s in stats)}
    return out


def bench_swap(engine: Engine, runs: int = 3) -> dict:
    """Time to first token when the adapter stays the same vs. when it changes."""
    names = list(engine.adapter_ids)
    same, switched = [], []
    for i in range(runs):
        a, b = names[i % len(names)], names[(i + 1) % len(names)]
        engine.generate(TIMING_PROMPT, a, max_tokens=1)
        same.append(engine.generate(TIMING_PROMPT, a, max_tokens=1)[1].ttft_ms)
        switched.append(engine.generate(TIMING_PROMPT, b, max_tokens=1)[1].ttft_ms)
    return {"ttft_same_adapter_ms": statistics.mean(same), "ttft_switched_adapter_ms": statistics.mean(switched),
            "swap_overhead_ms": statistics.mean(switched) - statistics.mean(same)}


def math_correct(answer_text: str, expected: float) -> bool:
    numbers = re.findall(r"-?\d[\d,]*\.?\d*", answer_text)
    if not numbers:
        return False
    return abs(float(numbers[-1].replace(",", "").rstrip(".")) - expected) < 0.01


def extract_sql(text: str) -> str:
    block = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    sql = block.group(1) if block else text
    stmt = re.search(r"(SELECT|WITH)\b.*?(;|$)", sql, re.S | re.I)
    return stmt.group(0).rstrip(";") if stmt else sql


def sql_rows(db: sqlite3.Connection, sql: str):
    rows = db.execute(sql).fetchall()
    return sorted(tuple(round(v, 2) if isinstance(v, float) else v for v in r) for r in rows)


def bench_quality(engine: Engine, router: Router, limit: int | None) -> dict:
    math_items = json.loads((ROOT / "data" / "eval_math.json").read_text())[:limit]
    sql_spec = json.loads((ROOT / "data" / "eval_sql.json").read_text())
    sql_items = sql_spec["questions"][:limit]
    db = sqlite3.connect(":memory:")
    db.executescript(sql_spec["schema"])
    for stmt in sql_spec["seed"]:
        db.execute(stmt)

    tasks = {
        "math": [(m["question"] + " Give the final answer as a number on the last line.",
                  lambda text, m=m: math_correct(text, m["answer"])) for m in math_items],
        "sql": [(f"Given this SQLite schema:\n{sql_spec['schema']}\n\n{q['question']}\nReturn only the SQL query.",
                 lambda text, q=q: _sql_ok(db, text, q["sql"])) for q in sql_items],
    }

    results = {}
    for task, items in tasks.items():
        rows = []
        for prompt, check in items:
            routed = router.route(prompt, use_cache=False).route
            answers = {"base": engine.generate(prompt, "base", max_tokens=384)[0],
                       "oracle": engine.generate(prompt, task, max_tokens=384)[0]}
            # At temperature 0 the router's answer equals whichever config it picked.
            answers["router"] = (answers["oracle"] if routed == task else answers["base"] if routed == "base"
                                 else engine.generate(prompt, routed, max_tokens=384)[0])
            rows.append({"prompt": prompt, "routed": routed, **{f"{k}_correct": check(v) for k, v in answers.items()},
                         "answers": answers})
            print(f"  {task:<5} routed={routed:<10} " + " ".join(f"{k}={'✓' if rows[-1][f'{k}_correct'] else '✗'}" for k in answers))
        results[task] = {
            "n": len(rows),
            **{f"{k}_acc": sum(r[f"{k}_correct"] for r in rows) / len(rows) for k in ("base", "oracle", "router")},
            "routing_acc": sum(r["routed"] == task for r in rows) / len(rows),
            "items": rows,
        }
    return results


def held_out_prompts() -> dict[str, list[str]]:
    held_out = json.loads((ROOT / "data" / "route_eval.json").read_text())
    held_out.pop("_note", None)
    held_out["math"] = [m["question"] for m in json.loads((ROOT / "data" / "eval_math.json").read_text())]
    sql_spec = json.loads((ROOT / "data" / "eval_sql.json").read_text())
    held_out["sql"] = [f"Given this SQLite schema:\n{sql_spec['schema']}\n\n{q['question']}" for q in sql_spec["questions"]]
    return held_out


def bench_routing(router: Router) -> dict:
    held_out = held_out_prompts()
    per_route, misses = {}, []
    for route, prompts in held_out.items():
        got = [router.route(p, use_cache=False).route for p in prompts]
        per_route[route] = sum(g == route for g in got) / len(got)
        misses += [{"expected": route, "got": g, "prompt": p[-80:]} for g, p in zip(got, prompts) if g != route]
    total = sum(len(p) for p in held_out.values())
    loo_acc, _ = router.leave_one_out()
    return {"held_out_acc": 1 - len(misses) / total, "n": total, "per_route": per_route,
            "leave_one_out_acc": loo_acc, "misses": misses}


def _sql_ok(db, text, reference) -> bool:
    try:
        return sql_rows(db, extract_sql(text)) == sql_rows(db, reference)
    except Exception:
        return False


def _p95(xs):
    return sorted(xs)[max(0, int(len(xs) * 0.95) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="3 prompts per task")
    args = ap.parse_args()

    engine = Engine()
    idle_server_mb = engine.server_mem_mb()
    router = Router()
    ram = PeakRam(engine)
    ram.start()

    results = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    print("size...");     results["size"] = bench_size(engine)
    print("routing...");  results["routing"] = bench_routing(router)
    print("router latency..."); results["router_latency"] = bench_router(router, [p for ps in held_out_prompts().values() for p in ps])
    print("generation speed..."); results["generation"] = bench_generation(engine, runs=1 if args.quick else 3)
    print("adapter swap..."); results["swap"] = bench_swap(engine, runs=1 if args.quick else 3)
    print("quality...");  results["quality"] = bench_quality(engine, router, limit=3 if args.quick else None)

    ram.stop.set()
    results["ram"] = {"server_idle_mb": idle_server_mb, "router_process_mb": process_mem_mb(),
                      "peak_total_mb": ram.peak_mb, "budget_mb": RAM_BUDGET_MB,
                      "under_budget": ram.peak_mb <= RAM_BUDGET_MB}

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {OUT}")
    print(json.dumps({k: v for k, v in results.items() if k != "quality"}, indent=2, default=str)[:3000])
    for task, q in results["quality"].items():
        print(f"{task}: base {q['base_acc']:.0%} | router {q['router_acc']:.0%} | oracle {q['oracle_acc']:.0%} | routing {q['routing_acc']:.0%}")


if __name__ == "__main__":
    main()
