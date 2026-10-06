"""Gladius chat UI: retro 80s CRT theme, multiple sessions, live pipeline trace.

    ./run.sh                       # starts llama-server if needed, warms adapters, UI on http://localhost:8503

Only drawing lives here. The pipeline (routing, notes, generation) is core.pipeline and saved
chats are core.sessions; both work without Streamlit.
"""

import html

import requests
import streamlit as st

from core import Options, Pipeline, SessionStore

APP_NAME = "GLADIUS"  # the wordmark: change it here
TAGLINE = "ONE MODEL · FOUR SPECIALISTS · ZERO CLOUD"
LAPTOP_RAM_MB = 8000  # the target machine: an 8 GB laptop

ACCENT = "#ff8a1f"  # the one colour; keep in sync with --pink/--cyan in CSS and run.sh
ROUTES = {  # route -> (label, colour)
    "math": ("∑ MATH", ACCENT),
    "sql": ("▤ SQL · BASE MODEL", ACCENT),  # adapter dropped after losing to base
    "techwriter": ("¶ TECH WRITER", ACCENT),
    "creative": ("✦ CREATIVE", ACCENT),
    "coding": ("λ PYTHON", ACCENT),
    "base": ("◆ BASE MODEL", ACCENT),
}
CODE_ROUTES = {"sql": "sql", "coding": "python"}  # adapters that answer with bare code

STARTERS = [
    ("math", "A phone costs $640. It's 15% off, then 8% sales tax is added. What's the final price?"),
    ("techwriter", "Write technical documentation for the late_penalty() function in my CS 301 project."),
    ("coding", "Write a Python function that returns the second largest number in a list."),
    ("creative", "What would Kierkegaard think about group chats?"),
]

SWORD = r"""
      />___________________________
[#####[]___________________________>
      \>"""[1:]

WORDMARK = """\
 ██████╗ ██╗      █████╗ ██████╗ ██╗██╗   ██╗███████╗
██╔════╝ ██║     ██╔══██╗██╔══██╗██║██║   ██║██╔════╝
██║  ███╗██║     ███████║██║  ██║██║██║   ██║███████╗
██║   ██║██║     ██╔══██║██║  ██║██║██║   ██║╚════██║
╚██████╔╝███████╗██║  ██║██████╔╝██║╚██████╔╝███████║
 ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═════╝ ╚═╝ ╚═════╝ ╚══════╝"""

# Local fonts only: the demo runs with Wi-Fi off, so nothing is fetched from a CDN.
CSS = """
<style>
:root{--bg:#090604;--panel:#110b06;--panel2:#1b1209;--line:#3d2610;--text:#f6e6d3;--dim:#a07f5f;
      --pink:#ff8a1f;--cyan:#ff8a1f;--amber:#ff8a1f;--green:#ff8a1f;
      --mono:"SF Mono",Menlo,Monaco,"Courier New",monospace}
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--bg)!important;color:var(--text)}
.stApp *{font-family:var(--mono)!important}
.stApp [data-testid="stIconMaterial"]{font-family:"Material Symbols Rounded"!important}
/* CRT scanlines + vignette */
.stApp::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:999999;
  background:repeating-linear-gradient(to bottom,rgba(255,255,255,.028) 0 1px,transparent 1px 3px),
             radial-gradient(ellipse at center,transparent 60%,rgba(0,0,0,.45) 100%)}
header[data-testid="stHeader"]{background:transparent!important}
/* The toolbar holds the button that reopens a collapsed sidebar, so hide its other items, not the bar. */
[data-testid="stToolbarActions"],[data-testid="stMainMenu"],[data-testid="stAppDeployButton"],
[data-testid="stDecoration"],[data-testid="stStatusWidget"],footer{display:none!important}
[data-testid="stExpandSidebarButton"]{color:var(--cyan)!important;border:1px solid var(--line);border-radius:4px;background:var(--panel)!important}
[data-testid="stExpandSidebarButton"]:hover{border-color:var(--cyan);box-shadow:0 0 12px rgba(255,138,31,.4)}
[data-testid="stExpandSidebarButton"] *{color:var(--cyan)!important}
[data-testid="stMainBlockContainer"]{max-width:880px;padding-top:2.2rem;padding-bottom:7rem}
[data-testid="stBottom"],[data-testid="stBottom"]>div,[data-testid="stBottomBlockContainer"]{background:var(--bg)!important}
[data-testid="stBottomBlockContainer"]{max-width:880px;padding-bottom:1.4rem}

/* sidebar */
[data-testid="stSidebar"]{background:var(--panel)!important;border-right:1px solid var(--line)}
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{padding-top:.4rem}
.brand pre{margin:0;line-height:1.15;font-size:11.5px;font-weight:700;overflow:visible;color:var(--cyan);text-shadow:0 0 8px rgba(255,138,31,.7);background:none;border:0;padding:0}
.brand .name{font-size:24px;font-weight:800;letter-spacing:.3em;margin-top:.5rem;
  background:linear-gradient(180deg,#ffe2bd 0%,#ff8a1f 50%,#d95300 100%);-webkit-background-clip:text;background-clip:text;color:transparent;
  filter:drop-shadow(0 0 10px rgba(255,138,31,.55))}
.brand .tag{color:var(--dim);font-size:8.5px;letter-spacing:.06em;margin-top:.35rem;white-space:nowrap}
.sec{color:var(--dim);font-size:10px;letter-spacing:.28em;margin:1.1rem 0 .2rem;border-bottom:1px dashed var(--line);padding-bottom:.3rem}

/* buttons */
.stButton button{background:transparent;border:1px solid var(--line);color:var(--text);border-radius:4px;
  font-size:12.5px;transition:all .12s;box-shadow:none}
.stButton button:hover{border-color:var(--cyan);color:var(--cyan);box-shadow:0 0 12px rgba(255,138,31,.35);background:rgba(255,138,31,.05)}
.stButton button:focus:not(:active){border-color:var(--cyan);color:var(--cyan)}
.st-key-new button{border-color:var(--pink);color:var(--pink);letter-spacing:.2em;font-weight:700;
  box-shadow:0 0 10px rgba(255,138,31,.25),inset 0 0 10px rgba(255,138,31,.08)}
.st-key-new button:hover{background:var(--pink);color:#090604;border-color:var(--pink);box-shadow:0 0 18px rgba(255,138,31,.7)}
[data-testid="stPopover"] button{background:transparent;border:1px solid var(--line);color:var(--text);border-radius:4px;font-size:12.5px}
[data-testid="stPopover"] button:hover{border-color:var(--pink);color:var(--pink);box-shadow:0 0 12px rgba(255,138,31,.35)}
[data-testid="stPopoverBody"]{background:var(--panel)!important;border:1px solid var(--line)}
.st-key-sessions [data-testid="stVerticalBlock"]{gap:.2rem}
.st-key-sessions [data-testid="stHorizontalBlock"]{gap:.25rem;align-items:center}
.st-key-sessions button{border-color:transparent;justify-content:flex-start;text-align:left;padding:.25rem .55rem;min-height:0;color:var(--dim)}
.st-key-sessions button div{justify-content:flex-start;width:100%}
.st-key-sessions button p{white-space:nowrap;text-align:left;overflow:hidden;text-overflow:ellipsis;font-size:12.5px}
.st-key-sessions button[kind="primary"]{background:var(--panel2);border-color:var(--line);border-left:2px solid var(--cyan);color:var(--cyan);
  text-shadow:0 0 8px rgba(255,138,31,.5)}
.st-key-sessions [data-testid="stColumn"]:last-child button{justify-content:center;color:var(--line);padding:.25rem 0}
.st-key-sessions [data-testid="stColumn"]:last-child button:hover{color:var(--pink);border-color:transparent;box-shadow:none;background:none}

/* widgets */
[data-testid="stSidebar"] label p{font-size:12px;color:var(--text)}
[data-baseweb="select"]>div{background:var(--panel2)!important;border-color:var(--line)!important;font-size:12.5px}
[data-testid="stExpander"] details{border:1px solid var(--line);border-radius:4px;background:var(--panel)}
[data-testid="stExpander"] summary p{font-size:12px;color:var(--dim);letter-spacing:.06em}

/* top strip */
.strip{display:flex;justify-content:space-between;gap:1rem;font-size:10.5px;letter-spacing:.2em;color:var(--dim);
  border-bottom:1px solid var(--line);padding-bottom:.55rem;margin-bottom:.4rem}
.strip .on{color:var(--green);text-shadow:0 0 8px var(--green)}
.strip .ttl{color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@keyframes blink{50%{opacity:.25}} .strip .dot{animation:blink 1.6s steps(1) infinite}

.strip .ram{color:var(--text);white-space:nowrap}.strip .ram .m{color:var(--green);letter-spacing:-1px;text-shadow:0 0 6px rgba(255,138,31,.6)}
.strip .ram .o{color:#4a2f14;letter-spacing:-1px}.strip .ram b{color:var(--cyan);font-weight:600}

/* pipeline trace */
.trace{display:grid;grid-template-columns:repeat(auto-fit,minmax(138px,1fr));gap:.45rem;margin:.6rem 0 .5rem}
.stage{border:1px solid var(--line);border-radius:4px;padding:.45rem .55rem;background:var(--panel);position:relative;min-height:4.3rem}
.stage .n{font-size:9px;letter-spacing:.22em;color:var(--dim)}
.stage .v{font-size:12.5px;font-weight:700;color:var(--text);margin:.2rem 0 .15rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stage .d{font-size:9.5px;line-height:1.45;color:var(--dim)}
.stage.done{border-color:var(--cyan);box-shadow:0 0 10px rgba(255,138,31,.22),inset 0 0 10px rgba(255,138,31,.06)}
.stage.done .n,.stage.done .v{color:var(--cyan)}.stage.done .v{text-shadow:0 0 8px rgba(255,138,31,.55)}
.stage.skip{border-style:dashed}.stage.skip .v{color:var(--dim)}
.stage.wait{opacity:.45}
@keyframes pulse{50%{box-shadow:0 0 18px rgba(255,138,31,.6),inset 0 0 14px rgba(255,138,31,.15)}}
.stage.run{border-color:var(--cyan);animation:pulse .9s ease-in-out infinite}.stage.run .n,.stage.run .v{color:var(--cyan)}

.rail{height:3px;background:var(--panel2);border-radius:2px;margin:.7rem 0 -.25rem;overflow:hidden}
.rail b{display:block;height:100%;width:0;background:var(--cyan);box-shadow:0 0 10px var(--cyan)}
@keyframes fill{from{width:0}to{width:80%}}
@keyframes shimmer{0%{opacity:1}50%{opacity:.45}100%{opacity:1}}
.rail.fill b{animation:fill 1.9s ease-out both}
.rail.gen b{width:90%;transition:width .6s;animation:shimmer 1s ease-in-out infinite}
.rail.full b{width:100%;transition:width .4s}
@keyframes reveal{from{opacity:.3;border-color:var(--line);box-shadow:none;filter:saturate(0)}}
.trace.seq .stage{animation:reveal .32s ease-out both;animation-delay:calc(var(--i)*.38s)}
.trace.seq .stage.run{animation:reveal .32s ease-out both,pulse .9s ease-in-out infinite;
  animation-delay:calc(var(--i)*.38s),calc(var(--i)*.38s + .32s)}
.stage.run .v:after{content:"";display:inline-block;width:.55em;height:1em;margin-left:.3em;background:var(--cyan);
  vertical-align:-.15em;animation:blink .7s steps(1) infinite}

/* hero */
.hero{text-align:center;margin:2.2rem 0 0}
.hero pre{display:inline-block;margin:0;line-height:1.05;font-size:11.5px;text-align:left;border:0;padding:0;
  background:linear-gradient(180deg,#ffe2bd 0%,#ff8a1f 45%,#d95300 100%);-webkit-background-clip:text;background-clip:text;color:transparent;
  filter:drop-shadow(0 0 14px rgba(255,138,31,.55))}
.hero .tag{color:var(--dim);font-size:11px;letter-spacing:.3em;margin-top:1rem}
.hero .ready{color:var(--green);font-size:12px;margin:2.2rem 0 .4rem;text-shadow:0 0 8px rgba(255,138,31,.6)}
.hero .ready b{animation:blink 1s steps(1) infinite;font-weight:400}
.st-key-starters button{height:100%;min-height:4.6rem;align-items:flex-start;justify-content:flex-start;text-align:left;
  background:var(--panel);padding:.6rem .75rem}
.st-key-starters button p{font-size:11.5px;line-height:1.5;color:var(--dim);white-space:normal!important;overflow:visible!important;text-align:left}
.st-key-starters button div{white-space:normal!important;overflow:visible!important;display:block;text-align:left}
.st-key-starters button p:first-child{color:var(--text);letter-spacing:.14em;font-weight:700;margin-bottom:.3rem}
.st-key-starters button:hover p{color:var(--cyan)}

/* chat */
.you{display:flex;justify-content:flex-end;margin:.9rem 0 .2rem}
.you div{max-width:82%;background:var(--panel2);border:1px solid var(--line);border-radius:10px 10px 2px 10px;
  padding:.6rem .85rem;font-size:13.5px;line-height:1.55;white-space:pre-wrap;word-break:break-word}
.rt{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;margin-top:.5rem}
.chip{font-size:11px;font-weight:700;letter-spacing:.16em;padding:.18rem .55rem;border:1px solid var(--c);color:var(--c);
  border-radius:3px;text-shadow:0 0 8px var(--c);box-shadow:0 0 10px color-mix(in srgb,var(--c) 35%,transparent),inset 0 0 8px color-mix(in srgb,var(--c) 12%,transparent)}
.flag{font-size:10.5px;letter-spacing:.1em;color:var(--amber)}.flag.hit{color:var(--green)}
.bars{font-size:10.5px;color:var(--dim);margin:.45rem 0 .1rem;display:grid;grid-template-columns:7.5em 1fr 3.4em;gap:.15rem .6rem;align-items:center;max-width:430px}
.bars i{display:block;height:5px;background:var(--panel2);border-radius:1px;overflow:hidden}
.bars i b{display:block;height:100%;background:var(--c);box-shadow:0 0 8px var(--c)}
.bars .w{color:var(--text)}
.bars i b{opacity:.38}.bars i.w b{opacity:1}
[data-testid="stCode"] code span{color:#ffb469!important}
.stats{font-size:10.5px;color:var(--dim);letter-spacing:.04em;border-top:1px dashed var(--line);padding-top:.45rem;margin:.3rem 0 .6rem}
.stats b{color:var(--cyan);font-weight:600}.stats .sw{color:var(--pink)}
.src{font-size:11px;color:var(--dim);line-height:1.7}.src b{color:var(--amber);font-weight:500}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li{font-size:13.5px;line-height:1.65}
[data-testid="stMarkdownContainer"] code{background:var(--panel2);color:var(--green)}
[data-testid="stCode"] pre,.stCode pre{background:#0d0805!important;border:1px solid var(--line);border-left:2px solid var(--green);border-radius:4px}

.err{border:1px solid var(--pink);color:var(--pink);padding:.8rem 1rem;border-radius:4px;font-size:13px;line-height:1.8;
  letter-spacing:.08em;text-shadow:0 0 8px rgba(255,138,31,.6);box-shadow:0 0 16px rgba(255,138,31,.25);margin:.8rem 0}
.err span{color:var(--dim);text-shadow:none;letter-spacing:0;font-size:12px}
/* input */
.st-key-homeinput{margin-bottom:.9rem}
[data-testid="stChatInput"]{background:var(--panel)!important;border:1px solid var(--line)!important;border-radius:8px;
  box-shadow:0 0 0 1px transparent,0 0 22px rgba(255,138,31,.12)}
[data-testid="stChatInput"]:focus-within{border-color:var(--pink)!important;box-shadow:0 0 22px rgba(255,138,31,.35)}
[data-testid="stChatInput"] *{background:transparent!important;border-color:transparent!important}
[data-testid="stChatInput"] textarea{color:var(--text)!important;caret-color:var(--pink);font-size:13.5px}
[data-testid="stChatInput"] textarea::placeholder{color:var(--dim)!important}
[data-testid="stChatInput"] button{color:var(--pink)!important}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px}::-webkit-scrollbar-track{background:transparent}
</style>
"""

st.set_page_config(page_title=APP_NAME, page_icon="🗡️", layout="centered", initial_sidebar_state="expanded")
st.html(CSS)


@st.cache_resource(show_spinner="BOOTING SPECIALISTS…")
def load() -> Pipeline:
    return Pipeline()


# ---------- sessions ----------

def start_session():
    st.session_state.active = st.session_state.store.start()


def delete_session(sid: str):
    st.session_state.store.delete(sid)
    if st.session_state.active == sid:
        st.session_state.active = None


def clear_sessions():
    st.session_state.store.clear()
    st.session_state.active = None


# ---------- rendering ----------

def esc(text) -> str:
    return html.escape(str(text))


def render_user(prompt: str):
    st.html(f'<div class="you"><div>{esc(prompt)}</div></div>')


def render_route(r: dict, chip: bool = True):
    label, colour = ROUTES.get(r["route"], (r["route"].upper(), ACCENT))
    flags = ""
    if r["low_confidence"]:
        flags += '<span class="flag">⚠ LOW CONFIDENCE</span>'
    if r["cache"] != "miss":
        flags += f'<span class="flag hit">⚡ CACHE HIT ({esc(r["cache"]).upper()})</span>'
    bars = ""
    for name, score in list(r["scores"].items())[:3]:
        c = ROUTES.get(name, ("", ACCENT))[1]
        win = ' class="w"' if name == r["route"] else ""
        bars += (f'<span{win}>{esc(name)}</span><i{win}><b style="width:{min(max(score, 0), 1):.0%};--c:{c}"></b></i>'
                 f'<span{win}>{score:.3f}</span>')
    head = f'<div class="rt"><span class="chip" style="--c:{colour}">{label}</span>{flags}</div>' if chip else ""
    st.html(f'{head}<div class="bars">{bars}</div>')


def stage(name: str, value: str, detail: str, state: str = "done") -> str:
    return f'<div class="stage {state}"><div class="n">{name}</div><div class="v">{value}</div><div class="d">{detail}</div></div>'


def trace_html(r: dict, rag: dict | None | bool, s: dict | None, phase: str = "done") -> str:
    """The request's path through the pipeline. `phase` is the live step: "notes",
    "waiting" (prompt sent, no token yet), "streaming" or "done". `rag` is False while pending."""
    exact = r["cache"] == "exact"
    out = [stage("1 · EMBED", "SKIPPED" if exact else "1 VECTOR",
                 "exact repeat, no embedding needed" if exact else "Arctic Embed xs · reused by cache, router and notes",
                 "skip" if exact else "done")]
    out.append(stage("2 · CACHE", "MISS" if r["cache"] == "miss" else f"⚡ HIT · {esc(r['cache']).upper()}",
                     "new prompt, route it" if r["cache"] == "miss" else "routing decision reused"))
    top = next(iter(r["scores"].values()))
    how = "forced by you" if r.get("forced") else f"margin {r['margin']:.3f}" + (" · ⚠ low confidence" if r["low_confidence"] else "")
    if r.get("notes_override"):
        how = f"about your courses: {esc(r['notes_override'])} → base, with notes"
    out.append(stage("3 · ROUTE", f"{ROUTES.get(r['route'], (r['route'].upper(),))[0]} {r['scores'].get(r['route'], top):.3f}",
                     f"{r['latency_ms']:.0f} ms embed + route · {how}"))
    if rag is False:
        out.append(stage("4 · NOTES", "SEARCHING…", "local files only", "run"))
    elif rag is None:
        out.append(stage("4 · NOTES", "OFF", "notes switched off", "skip"))
    elif rag["sources"]:
        n = len(rag["sources"])
        out.append(stage("4 · NOTES", f"{n} SOURCE{'S' if n != 1 else ''}", f"{rag['latency_ms']:.1f} ms · local files, nothing uploaded"))
    else:
        out.append(stage("4 · NOTES", "NONE NEEDED", f"{rag['latency_ms']:.1f} ms · nothing relevant for this route", "skip"))
    if s is None:
        value, detail, state = {"waiting": ("LOADING PROMPT…", "adapter switched on, waiting for first token", "run"),
                                "streaming": ("STREAMING…", "tokens arriving", "run")}.get(phase, ("QUEUED", "", "wait"))
        out.append(stage("5 · GENERATE", value, detail, state))
    else:
        swap = "adapter swapped, no reload" if s["switched"] else "same adapter"
        out.append(stage("5 · GENERATE", f"{s['tok_per_s']:.1f} TOK/S",
                         f"first token {s['ttft_ms'] / 1000:.2f} s · {s['tokens']} tokens · {swap}"))
    # "waiting" is drawn once the fast stages are finished: they light up left to right
    # (CSS, staggered by --i) while the model loads the prompt, then the rail tracks generation.
    out = [o.replace('<div class="stage ', f'<div style="--i:{i}" class="stage ', 1) for i, o in enumerate(out)]
    rail = {"waiting": "fill", "streaming": "gen", "done": "full"}.get(phase, "")
    return (f'<div class="rail {rail}"><b></b></div>'
            f'<div class="trace{" seq" if phase == "waiting" else ""}">{"".join(out)}</div>')


def pending_trace_html() -> str:
    """Shown the instant a prompt is sent, before the router has answered."""
    names = ["1 · EMBED", "2 · CACHE", "3 · ROUTE", "4 · NOTES", "5 · GENERATE"]
    boxes = [stage(n, "EMBEDDING…" if i == 0 else "QUEUED", "", "run" if i == 0 else "wait") for i, n in enumerate(names)]
    return f'<div class="rail"><b></b></div><div class="trace">{"".join(boxes)}</div>'


def strip_html(title: str) -> str:
    """Top status strip with the live RAM meter (llama-server + this UI)."""
    total_mb = pipeline.memory_mb()
    return (f'<div class="strip"><span class="on"><span class="dot">●</span> LOCAL · OFFLINE</span>'
            f'<span class="ttl">{esc(title or "NEW SESSION").upper()}</span>'
            f'<span class="ram">RAM {meter(total_mb / LAPTOP_RAM_MB, 14)} <b>{total_mb / 1000:.2f}</b> / 8 GB</span></div>')


def render_sources(rag: dict | None):
    if rag and rag["sources"]:
        with st.expander(f"▸ NOTES USED ({len(rag['sources'])}) · retrieval {rag['latency_ms']:.0f} ms · nothing left this laptop"):
            scores = [None] * rag["profile"] + rag["scores"]
            st.html('<div class="src">' + "<br>".join(
                esc(src) + ("" if sc is None else f" · <b>{sc:.3f}</b>") for src, sc in zip(rag["sources"], scores)) + "</div>")


def render_stats(r: dict, s: dict):
    total_mb = s["server_mem_mb"] + s["app_mem_mb"]
    swap = '<span class="sw">⇄ ADAPTER SWAPPED, NO RELOAD</span>' if s["switched"] else "SAME ADAPTER"
    st.html(f'<div class="stats">ROUTER <b>{r["latency_ms"]:.0f} ms</b> · FIRST TOKEN <b>{s["ttft_ms"] / 1000:.2f} s</b> · '
            f'<b>{s["tok_per_s"]:.1f}</b> TOK/S · {swap} · RAM <b>{total_mb / 1000:.2f} GB</b> '
            f'({total_mb / LAPTOP_RAM_MB:.0%} OF 8 GB)</div>')


def display_stream(chunks, route: str):
    """Fence code routes as code blocks; escape $ elsewhere so prices don't render as LaTeX."""
    lang = CODE_ROUTES.get(route) if pipeline.has_adapter(route) else None
    if lang:
        yield f"```{lang}\n"
        yield from chunks
        yield "\n```"
    else:
        for chunk in chunks:
            yield chunk.replace("$", r"\$")


def render_turn(turn: dict):
    render_user(turn["prompt"])
    if show_trace:  # the trace replaces the route chip
        st.html(trace_html(turn["routing"], turn.get("rag"), turn["stats"]))
    render_route(turn["routing"], chip=not show_trace)
    st.markdown(turn["answer"])
    render_sources(turn.get("rag"))
    render_stats(turn["routing"], turn["stats"])
    if turn.get("base_answer"):
        with st.expander("▸ SAME PROMPT, BASE MODEL ONLY"):
            st.markdown(turn["base_answer"])


def meter(fraction: float, width: int = 18) -> str:
    filled = round(min(max(fraction, 0), 1) * width)
    return f'<span class="m">{"█" * filled}</span><span class="o">{"░" * (width - filled)}</span>'


# ---------- app ----------

def offline(detail: str):
    st.html('<div class="err">&gt; MODEL SERVER OFFLINE<br><span>' + esc(detail) + '</span><br>'
            '<span>Start it with ./run.sh (or ./serve.sh), then send the prompt again.</span></div>')


try:
    pipeline = load()
except requests.RequestException as e:
    offline(f"llama-server did not answer on startup ({type(e).__name__}).")
    st.stop()
if "store" not in st.session_state:
    st.session_state.store = SessionStore()
    st.session_state.active = None
store = st.session_state.store
if store.get(st.session_state.active) is None:
    start_session()
session = store.get(st.session_state.active)

with st.sidebar:
    st.html(f'<div class="brand"><pre>{SWORD}</pre><div class="name">{APP_NAME}</div>'
            f'<div class="tag">{TAGLINE}</div></div>')
    with st.container(key="new"):
        st.button("＋ NEW SESSION", width="stretch", on_click=start_session)

    st.html('<div class="sec">SESSIONS</div>')
    with st.container(key="sessions"):
        for s in store.sessions:
            if not s["turns"] and s["id"] != session["id"]:
                continue
            name, x = st.columns([7, 1])
            # Button labels are markdown: backticks and $ would render as code and LaTeX.
            label = (s["title"] or "new session").replace("`", "").replace("$", r"\$")
            name.button(("▸ " if s["id"] == session["id"] else "  ") + label, key=f"s_{s['id']}",
                        type="primary" if s["id"] == session["id"] else "secondary", width="stretch",
                        on_click=lambda sid=s["id"]: st.session_state.update(active=sid))
            if s["turns"]:
                x.button("✕", key=f"x_{s['id']}", help="Delete session", on_click=delete_session, args=(s["id"],))

    st.html('<div class="sec">CONTROLS</div>')
    force = st.selectbox("Specialist", ["auto"] + list(ROUTES), label_visibility="collapsed",
                         format_func=lambda r: "AUTO · router decides" if r == "auto" else f"FORCE · {ROUTES[r][0]}")
    use_rag = st.checkbox("Use my notes and schedule", value=True,
                          help=f"Searches {pipeline.n_chunks} local chunks in data/student/. Nothing leaves this laptop.")
    compare = st.checkbox("Also answer with base model")
    show_trace = st.toggle("Pipeline view", value=True, help="Show every request's path: embed, cache, route, notes, generate.")

    if st.button("CLEAR ROUTER CACHE", width="stretch"):
        pipeline.clear_cache()
        st.rerun()
    saved = sum(1 for s in store.sessions if s["turns"])
    # Behind a popover so a stray click mid-demo can't wipe the sidebar.
    # Swapping to a plain button once empty also closes the popover after a clear.
    if saved:
        with st.popover("CLEAR ALL SESSIONS", width="stretch"):
            st.button(f"DELETE {saved} SESSION{'S' * (saved != 1)}", key="clear_all", width="stretch",
                      on_click=clear_sessions)
    else:
        st.button("CLEAR ALL SESSIONS", key="clear_none", width="stretch", disabled=True)

PLACEHOLDER = "Ask a math, SQL, writing, coding or everyday question…"
strip = st.empty()  # redrawn while tokens stream, so the RAM meter is live
strip.html(strip_html(session["title"]))

prompt = st.session_state.pop("pending", None)
if session["turns"]:
    prompt = st.chat_input(PLACEHOLDER, key="chat_input") or prompt  # pinned to the bottom
elif not prompt:
    # Home screen: the prompt bar sits under the wordmark, with the starter cards below it.
    # A chat_input inside a container renders in place instead of pinning to the bottom.
    home = st.empty()
    with home.container():
        st.html(f'<div class="hero"><pre>{WORDMARK}</pre><div class="tag">{TAGLINE}</div>'
                '<div class="ready">&gt; READY. PICK A SPECIALIST OR JUST ASK<b>█</b></div></div>')
        with st.container(key="homeinput"):
            prompt = st.chat_input(PLACEHOLDER, key="home_input")
        with st.container(key="starters"):
            for col, (route, text) in zip(st.columns(len(STARTERS)), STARTERS):
                col.button(f"{ROUTES[route][0]}\n\n{text}", key=f"st_{route}", width="stretch",
                           on_click=lambda t=text: st.session_state.update(pending=t))
    if prompt:
        home.empty()

for turn in session["turns"]:
    render_turn(turn)

if prompt:
    render_user(prompt)
    trace = st.empty()
    if show_trace:
        trace.html(pending_trace_html())
    turn = pipeline.route(prompt, Options(force=force, use_rag=use_rag))
    render_route(turn.routing, chip=not show_trace)
    pipeline.retrieve(turn)

    def live(chunks):
        """Advance the trace on the first token and keep the RAM meter moving."""
        for i, chunk in enumerate(chunks):
            if i == 0 and show_trace:
                trace.html(trace_html(turn.routing, turn.rag, None, "streaming"))
            if i % 12 == 0:
                strip.html(strip_html(session["title"] or prompt[:40]))
            yield chunk

    if show_trace:
        trace.html(trace_html(turn.routing, turn.rag, None, "waiting"))
    try:
        # Saved as displayed (code fences, escaped $), since saved turns are redrawn with st.markdown.
        turn.answer = st.write_stream(display_stream(live(pipeline.stream(turn)), turn.route))
    except requests.RequestException as e:
        offline(f"The connection dropped while generating ({type(e).__name__}). This turn was not saved.")
        st.stop()
    render_sources(turn.rag)
    if show_trace:
        trace.html(trace_html(turn.routing, turn.rag, turn.stats))
    strip.html(strip_html(session["title"] or prompt[:40]))
    render_stats(turn.routing, turn.stats)
    if compare and turn.route != "base":
        with st.expander("▸ SAME PROMPT, BASE MODEL ONLY", expanded=True):
            try:
                turn.base_answer = st.write_stream(display_stream(pipeline.stream_base(turn), "base"))
            except requests.RequestException:
                turn.base_answer = None

    first = not session["turns"]
    store.add_turn(session, turn)
    if first:
        st.rerun()  # the sidebar was drawn before this session had a title
