"""Slide charts from results/results.json -> results/charts/*.png, plus a summary table.

    python charts.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent
RESULTS = ROOT / "results" / "results.json"
OUT = ROOT / "results" / "charts"

# Reference palette (dataviz skill), light mode. Categorical slots in fixed order.
SURFACE, TEXT, TEXT_2, GRID, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#b9b8b1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 13, "text.color": TEXT, "axes.labelcolor": TEXT_2,
    "xtick.color": TEXT_2, "ytick.color": TEXT_2, "axes.edgecolor": GRID,
    "axes.spines.top": False, "axes.spines.right": False,
})


def _finish(ax, title: str, path: Path):
    ax.set_title(title, loc="left", fontsize=16, fontweight="bold", pad=14)
    ax.grid(axis="x", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.figure.tight_layout()
    ax.figure.savefig(path, dpi=200)
    plt.close(ax.figure)
    print(f"wrote {path.relative_to(ROOT)}")


def disk_chart(r: dict):
    s = r["size"]
    n = len(s["adapters_mb"])
    labels = [f"{n + 1} separate models", f"Gladius: 1 base + {n} adapters"]
    values = [s["separate_models_mb"] / 1000, s["ours_total_mb"] / 1000]
    fig, ax = plt.subplots(figsize=(9, 3.2))
    bars = ax.barh(labels, values, color=[MUTED, SERIES[0]], height=0.5, edgecolor=SURFACE, linewidth=2)
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + 0.15, bar.get_y() + bar.get_height() / 2, f"{v:.1f} GB", va="center", color=TEXT)
    ax.set_xlabel("Disk (GB)")
    ax.set_xlim(0, max(values) * 1.15)
    _finish(ax, f"{n} specialists for +{sum(s['adapters_mb'].values()):.0f} MB", OUT / "disk.png")


def ram_chart(r: dict):
    ram = r["ram"]
    server, router = ram["server_idle_mb"] / 1000, ram["router_process_mb"] / 1000
    peak, budget = ram["peak_total_mb"] / 1000, ram.get("laptop_mb", 8000) / 1000
    fig, ax = plt.subplots(figsize=(9, 3.2))
    fig.subplots_adjust(left=0.04, right=0.97, top=0.78, bottom=0.42)
    extra = max(peak - server - router, 0)  # compute buffers that only exist while generating
    ax.barh([0], [server], color=SERIES[0], height=0.6, edgecolor=SURFACE, linewidth=2, label="llama-server at rest (model + adapters)")
    ax.barh([0], [router], left=[server], color=SERIES[1], height=0.6, edgecolor=SURFACE, linewidth=2, label="router + UI")
    ax.barh([0], [extra], left=[server + router], color=MUTED, height=0.6, edgecolor=SURFACE, linewidth=2, label="extra while generating")
    ax.axvline(budget, color=TEXT_2, linestyle="--", linewidth=1.5)
    ax.text(budget, 0.38, f"{budget:.0f} GB laptop ", color=TEXT_2, va="bottom", ha="right")
    ax.text(server / 2, 0, f"{server:.2f} GB", ha="center", va="center", color="white", fontweight="bold")
    ax.text(peak + 0.08, 0, f"{peak:.2f} GB peak", va="center", color=TEXT)
    ax.set_ylim(-0.5, 0.7)
    ax.set_xlim(0, max(server + router, peak, budget) * 1.05)
    ax.set_yticks([])
    ax.set_xlabel("GB")
    ax.grid(axis="x", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.38), ncol=3, frameon=False, fontsize=11)
    ax.set_title(f"Peak {peak:.2f} GB: {peak / budget:.0%} of an 8 GB laptop", loc="left", fontsize=16, fontweight="bold", pad=14)
    fig.savefig(OUT / "ram.png", dpi=200)
    plt.close(fig)
    print(f"wrote {(OUT / 'ram.png').relative_to(ROOT)}")


def quality_chart(r: dict):
    q = r["quality"]
    tasks = [t for t in q if t in r["size"]["adapters_mb"]]  # only routes with an adapter loaded
    configs = [("base", "Base model only"), ("router", "Gladius router"), ("oracle", "Always-correct adapter")]
    fig, ax = plt.subplots(figsize=(9, 4))
    width = 0.26
    for i, (key, label) in enumerate(configs):
        xs = [t + (i - 1) * width for t in range(len(tasks))]
        vals = [q[t][f"{key}_acc"] * 100 for t in tasks]
        bars = ax.bar(xs, vals, width, color=SERIES[i], edgecolor=SURFACE, linewidth=2, label=label)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 1.5, f"{v:.0f}%", ha="center", color=TEXT, fontsize=11)
    ax.set_xticks(range(len(tasks)), [f"{t} (n={q[t]['n']})" for t in tasks])
    ax.set_ylim(0, 115)
    ax.set_ylabel("Accuracy (%)")
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False)
    ax.set_title("Accuracy: base vs. routed vs. oracle", loc="left", fontsize=16, fontweight="bold", pad=14)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "quality.png", dpi=200)
    plt.close(fig)
    print(f"wrote {(OUT / 'quality.png').relative_to(ROOT)}")


def sql_adapter_chart(sql: dict):
    """The adapter we measured and dropped: SQL adapter vs base on both question sets."""
    sets = [("original", "Original 10\n(3 multi-table)"), ("single_table", "15 single-table\n(its training type)")]
    configs = [("base", "Base model"), ("sql", "SQL adapter")]
    fig, ax = plt.subplots(figsize=(9, 4))
    width = 0.34
    for i, (key, label) in enumerate(configs):
        xs = [x + (i - 0.5) * width for x in range(len(sets))]
        vals = [sql[s]["summary"][key]["accuracy"] * 100 for s, _ in sets]
        bars = ax.bar(xs, vals, width, color=SERIES[0] if key == "base" else MUTED, edgecolor=SURFACE, linewidth=2, label=label)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 1.5, f"{v:.0f}%", ha="center", color=TEXT, fontsize=11)
    ax.set_xticks(range(len(sets)), [label for _, label in sets])
    ax.set_ylim(0, 115)
    ax.set_ylabel("Accuracy (%)")
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False)
    ax.set_title("The SQL adapter lost to base everywhere, so we dropped it", loc="left", fontsize=16, fontweight="bold", pad=14)
    fig.tight_layout()
    fig.savefig(OUT / "sql_adapter.png", dpi=200)
    plt.close(fig)
    print(f"wrote {(OUT / 'sql_adapter.png').relative_to(ROOT)}")


def summary_table(r: dict) -> str:
    s, ram, rl, sw, rt = r["size"], r["ram"], r["router_latency"], r["swap"], r["routing"]
    gen = r["generation"]
    lines = [
        "| Metric | Value |", "|---|---|",
        f"| Disk: base + {len(s['adapters_mb'])} adapters | {s['ours_total_mb'] / 1000:.2f} GB (vs {s['separate_models_mb'] / 1000:.1f} GB as separate models) |",
        f"| Adapters total | {sum(s['adapters_mb'].values()):.0f} MB |",
        f"| Peak RAM (server + router) | {ram['peak_total_mb'] / 1000:.2f} GB ({ram['peak_total_mb'] / ram.get('laptop_mb', 8000):.0%} of an 8 GB laptop) |",
        f"| Routing accuracy, held-out | {rt['held_out_acc']:.0%} (n={rt['n']}) |",
        f"| Routing accuracy, leave-one-out | {rt['leave_one_out_acc']:.0%} |",
        f"| Router latency | {rl['route_ms_mean']:.0f} ms mean, {rl['route_ms_p95']:.0f} ms p95 |",
        f"| Cache-hit latency | {rl['cache_hit_ms_mean']:.1f} ms |",
        (f"| Adapter swap overhead | {sw['swap_overhead_ms']:.0f} ms (no reload) |" if sw["swap_overhead_ms"] >= 50 else
         "| Adapter swap overhead | under 50 ms, within run-to-run noise (no reload) |"),
        f"| Speed, base | {gen['base']['tok_per_s']:.1f} tok/s, first token {gen['base']['ttft_ms']:.0f} ms |",
    ]
    lines += [f"| Speed, {n} adapter | {g['tok_per_s']:.1f} tok/s |" for n, g in gen.items() if n != "base"]
    lines += [f"| {t} accuracy | base {q['base_acc']:.0%} · router {q['router_acc']:.0%} · oracle {q['oracle_acc']:.0%} |"
              for t, q in r["quality"].items()]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    results = json.loads(RESULTS.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    disk_chart(results)
    ram_chart(results)
    quality_chart(results)
    sql_path = ROOT / "results" / "sql_adapter.json"
    table = summary_table(results)
    if sql_path.exists():
        sql = json.loads(sql_path.read_text())
        sql_adapter_chart(sql)
        acc = {s: {k: v["accuracy"] for k, v in sql[s]["summary"].items()} for s in sql}
        table += (f"| SQL adapter (dropped) | {acc['single_table']['sql']:.0%} vs base {acc['single_table']['base']:.0%} "
                  f"on 15 single-table questions; {acc['original']['sql']:.0%} vs {acc['original']['base']:.0%} on the original 10 |\n")
    (ROOT / "results" / "summary.md").write_text(f"# Benchmark summary ({results['timestamp']})\n\n{table}")
    print(table)
