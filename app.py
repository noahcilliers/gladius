"""Local chat UI: shows which specialist answered, how confident the router was,
and what it cost in time and RAM.

    ./serve.sh                     # terminal 1
    streamlit run app.py           # terminal 2
"""

import json
import time
from pathlib import Path

import streamlit as st

from engine import Engine, process_mem_mb
from router import Router

RAM_BUDGET_MB = 3000
TURNS_LOG = Path(__file__).parent / "results" / "turns.jsonl"
ROUTE_LABELS = {
    "math": "🧮 Math",
    "sql": "🗄️ SQL",
    "techwriter": "📄 Tech writer",
    "creative": "🎨 Creative",
    "base": "💬 Base model",
}

st.set_page_config(page_title="PocketExperts", page_icon="🧠", layout="wide")


@st.cache_resource
def load():
    router = Router()
    router.route("warm-up", use_cache=False)
    return router, Engine()


def adapter_sizes_mb() -> dict[str, float]:
    return {p.stem: p.stat().st_size / 1e6 for p in sorted(Path("adapters").glob("*.gguf"))}


def render_route(r: dict):
    st.markdown(f"**{ROUTE_LABELS.get(r['route'], r['route'])}**"
                + ("  ·  ⚠️ low confidence" if r["low_confidence"] else "")
                + ("" if r["cache"] == "miss" else f"  ·  ⚡ cache hit ({r['cache']})"))
    for name, score in list(r["scores"].items())[:3]:
        st.progress(min(max(score, 0.0), 1.0), text=f"{name}  {score:.3f}")


def render_stats(r: dict, s: dict):
    total_mb = s["server_mem_mb"] + s["app_mem_mb"]
    c = st.columns(5)
    c[0].metric("Router", f"{r['latency_ms']:.0f} ms")
    c[1].metric("First token", f"{s['ttft_ms']:.0f} ms")
    c[2].metric("Speed", f"{s['tok_per_s']:.1f} tok/s")
    c[3].metric("Adapter swap", "0 ms reload" if s["switched"] else "—",
                help="All adapters stay loaded; switching is a per-request scale change.")
    c[4].metric("RAM", f"{total_mb / 1000:.2f} GB", f"{'under' if total_mb <= RAM_BUDGET_MB else 'OVER'} 3 GB budget",
                delta_color="normal" if total_mb <= RAM_BUDGET_MB else "inverse")


def render_turn(turn: dict):
    with st.chat_message("user"):
        st.write(turn["prompt"])
    with st.chat_message("assistant"):
        render_route(turn["routing"])
        st.markdown(turn["answer"])
        render_stats(turn["routing"], turn["stats"])
        if turn.get("base_answer"):
            with st.expander("Same prompt, base model only"):
                st.markdown(turn["base_answer"])


router, engine = load()
st.session_state.setdefault("turns", [])
st.session_state.setdefault("last_route", None)

with st.sidebar:
    st.title("🧠 PocketExperts")
    st.caption("One 3B model, four LoRA specialists, fully offline.")
    force = st.selectbox("Route", ["auto"] + list(ROUTE_LABELS), format_func=lambda r: "Auto (router)" if r == "auto" else ROUTE_LABELS[r])
    compare = st.checkbox("Also answer with base model (compare)")

    st.subheader("Memory")
    server_mb, app_mb = engine.server_mem_mb(), process_mem_mb()
    total_mb = server_mb + app_mb
    st.progress(min(total_mb / RAM_BUDGET_MB, 1.0), text=f"{total_mb / 1000:.2f} / 3.00 GB")
    st.caption(f"llama-server {server_mb:.0f} MB · router + UI {app_mb:.0f} MB")

    st.subheader("Disk")
    sizes = adapter_sizes_mb()
    base_mb = Path("models/Llama-3.2-3B-Instruct-Q4_K_M.gguf").stat().st_size / 1e6
    st.caption(f"Base model {base_mb / 1000:.2f} GB + {len(sizes)} adapters {sum(sizes.values()):.0f} MB")
    st.caption(" · ".join(f"{n} {mb:.0f} MB" for n, mb in sizes.items()))

    st.subheader("Router cache")
    rate = router.cache_hits / router.cache_lookups if router.cache_lookups else 0.0
    st.caption(f"{router.cache_hits} hits / {router.cache_lookups} lookups ({rate:.0%})")
    if st.button("Clear chat + cache"):
        st.session_state.turns = []
        st.session_state.last_route = None
        router.clear_cache()
        st.rerun()

for turn in st.session_state.turns:
    render_turn(turn)

prompt = st.chat_input("Ask a math, SQL, tech-writing, creative, or everyday question")
if prompt:
    rr = router.route(prompt)
    routing = {"route": rr.route if force == "auto" else force, "scores": rr.scores, "margin": rr.margin,
               "low_confidence": rr.low_confidence, "cache": rr.cache, "latency_ms": rr.latency_ms}

    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        render_route(routing)
        answer = st.write_stream(engine.stream(prompt, routing["route"]))
        gs = engine.last_stats
        stats = {**gs.__dict__, "app_mem_mb": process_mem_mb(),
                 "switched": st.session_state.last_route not in (None, routing["route"])}
        render_stats(routing, stats)
        base_answer = None
        if compare and routing["route"] != "base":
            with st.expander("Same prompt, base model only", expanded=True):
                base_answer = st.write_stream(engine.stream(prompt, "base"))

    turn = {"ts": time.time(), "prompt": prompt, "routing": routing, "answer": answer,
            "stats": stats, "base_answer": base_answer}
    st.session_state.turns.append(turn)
    st.session_state.last_route = routing["route"]
    TURNS_LOG.parent.mkdir(exist_ok=True)
    with TURNS_LOG.open("a") as f:
        f.write(json.dumps(turn) + "\n")
