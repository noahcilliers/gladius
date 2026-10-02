"""Client for llama-server: generate with exactly one LoRA adapter active per request.

All adapters are loaded once by serve.sh. Each request sends a scale per adapter
(1.0 for the chosen route, 0.0 for the rest), so switching adapters is a request
parameter rather than a model reload.
"""

import ctypes
import json
import os
import re
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psutil
import requests

SERVER_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8080")

# CREATE TABLE statements, or `table(col, ...)` signatures in backticks.
_SCHEMA_RE = re.compile(r"CREATE TABLE\s+\w+\s*\((?:[^()]|\([^()]*\))*\)\s*;?|`(\w+\s*\([^`]*\))`", re.I)


# Instructions around the question that the adapter never saw in training. Left in,
# they make it invent extra WHERE filters.
_SQL_BOILERPLATE_RE = re.compile(r"given (?:this|the following)(?: \w+)? schemas?:?|return only the sql(?: query)?\.?", re.I)


def _varchar_ddl(ddl: str) -> str:
    """sql-create-context schemas type every column VARCHAR with no constraints. Real
    types (INTEGER PRIMARY KEY, REAL...) make the adapter invent WHERE filters."""
    m = re.match(r"(?:CREATE TABLE\s+)?(\w+)\s*\((.*)\)", ddl.strip().rstrip(";"), re.S | re.I)
    if not m:
        return ddl
    cols = [c.split()[0] for c in re.split(r",(?![^(]*\))", m.group(2)) if c.strip()]
    return f"CREATE TABLE {m.group(1)} ({', '.join(c + ' VARCHAR' for c in cols)})"


def sql_prompt(prompt: str) -> str:
    """BY-ALF/llama-3.2-3b-sql-lora was trained on b-mc2/sql-create-context in this
    raw format, without the chat template: VARCHAR schema, then a bare question.
    Matching it took the adapter from 2/10 to 8/10 on data/eval_sql.json."""
    schema = "\n".join(_varchar_ddl(m.group(1) or m.group(0)) for m in _SCHEMA_RE.finditer(prompt))
    question = _SCHEMA_RE.sub(lambda m: m.group(1) or "", prompt)
    question = " ".join(_SQL_BOILERPLATE_RE.sub("", question).split())
    return f"### Context:\n{schema}\n### Question:\n{question}\n### SQL:\n"


def coding_prompt(prompt: str) -> str:
    """yusifnuri/Llama-3.2-3B-Instruct_code_generation was trained on HumanEval with
    this exact prefix, via the chat template."""
    return f"Complete the following Python function: {prompt}"


RAW_PROMPT_ROUTES = {"sql": sql_prompt}
# Adapters trained with the chat template but a fixed instruction prefix.
CHAT_PROMPT_ROUTES = {"coding": coding_prompt}


@dataclass
class GenStats:
    route: str
    ttft_ms: float  # request sent -> first token received
    total_ms: float
    tokens: int
    tok_per_s: float
    server_mem_mb: float


class Engine:
    ADAPTERS_TTL_S = 2.0

    def __init__(self, url: str = SERVER_URL):
        self.url = url
        self._adapter_ids: dict[str, int] = {}
        self._adapters_at = float("-inf")
        self.adapter_ids  # fail fast if the server is down
        self.server = _find_server_process()
        self.last_stats: GenStats | None = None

    @property
    def adapter_ids(self) -> dict[str, int]:
        """Adapter name -> id, re-read from the server every couple of seconds. A UI that
        outlives a server restart would otherwise keep the old numbering and switch on
        the wrong adapter (ids shift when one is added or dropped)."""
        if time.monotonic() - self._adapters_at > self.ADAPTERS_TTL_S:
            adapters = requests.get(f"{self.url}/lora-adapters", timeout=5).json()
            self._adapter_ids = {Path(a["path"]).stem: a["id"] for a in adapters}
            self._adapters_at = time.monotonic()
        return self._adapter_ids

    def has_adapter(self, route: str) -> bool:
        return route in self.adapter_ids

    def lora_for(self, route: str) -> list[dict]:
        return [{"id": i, "scale": 1.0 if name == route else 0.0} for name, i in self.adapter_ids.items()]

    def stream(self, prompt: str, route: str, max_tokens: int = 384, temperature: float = 0.0) -> Iterator[str]:
        """Yield answer text as it streams. Sets self.last_stats when done."""
        body = {
            "lora": self.lora_for(route),
            "stream": True,
            "temperature": temperature,
            "seed": 0,
            # The KV cache from a different adapter isn't valid for this one.
            "cache_prompt": False,
        }
        # Adapter-specific prompt formats only apply when that adapter is loaded; a route
        # without one (e.g. a dropped adapter) is plain base model + chat template.
        if route in RAW_PROMPT_ROUTES and self.has_adapter(route):
            # Adapters trained without the chat template get their own raw format.
            endpoint = "/completion"
            body |= {"prompt": RAW_PROMPT_ROUTES[route](prompt), "n_predict": max_tokens, "stop": ["###", "\n\n"]}
        else:
            fmt = CHAT_PROMPT_ROUTES.get(route) if self.has_adapter(route) else None
            endpoint = "/v1/chat/completions"
            body |= {"messages": [{"role": "user", "content": fmt(prompt) if fmt else prompt}], "max_tokens": max_tokens}

        t0 = time.perf_counter()
        ttft_ms, n_chunks, timings = None, 0, None
        with requests.post(f"{self.url}{endpoint}", json=body, stream=True, timeout=600) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith(b"data: "):
                    continue
                data = line[len(b"data: "):]
                if data == b"[DONE]":
                    break
                chunk = json.loads(data)
                timings = chunk.get("timings") or timings
                if "choices" in chunk:
                    text = (chunk["choices"] or [{}])[0].get("delta", {}).get("content")
                else:
                    text = chunk.get("content")
                if text:
                    if ttft_ms is None:
                        ttft_ms = _ms(t0)
                    n_chunks += 1
                    yield text
        total_ms = _ms(t0)

        tokens = timings["predicted_n"] if timings else n_chunks
        tok_per_s = timings["predicted_per_second"] if timings else n_chunks / max(total_ms - (ttft_ms or 0), 1) * 1000
        self.last_stats = GenStats(
            route=route,
            ttft_ms=ttft_ms or total_ms,
            total_ms=total_ms,
            tokens=tokens,
            tok_per_s=tok_per_s,
            server_mem_mb=self.server_mem_mb(),
        )

    def generate(self, prompt: str, route: str, **kwargs) -> tuple[str, GenStats]:
        text = "".join(self.stream(prompt, route, **kwargs))
        return text, self.last_stats

    def server_mem_mb(self) -> float:
        if self.server is None or not self.server.is_running():
            self.server = _find_server_process()
        return footprint_mb(self.server.pid) if self.server else 0.0


def process_mem_mb() -> float:
    return footprint_mb(os.getpid())


class _RusageInfoV2(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [(name, ctypes.c_uint64) for name in (
        "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups", "ri_pageins",
        "ri_wired_size", "ri_resident_size", "ri_phys_footprint", "ri_proc_start_abstime",
        "ri_proc_exit_abstime", "ri_child_user_time", "ri_child_system_time", "ri_child_pkg_idle_wkups",
        "ri_child_interrupt_wkups", "ri_child_pageins", "ri_child_elapsed_abstime",
        "ri_diskio_bytesread", "ri_diskio_byteswritten")]


_libproc = ctypes.CDLL("/usr/lib/libproc.dylib") if sys.platform == "darwin" else None


def footprint_mb(pid: int) -> float:
    """Physical footprint (Activity Monitor's "Memory"), which includes Metal GPU
    buffers on Apple Silicon. RSS misses those. Falls back to RSS off macOS."""
    if _libproc is not None:
        info = _RusageInfoV2()
        if _libproc.proc_pid_rusage(pid, 2, ctypes.byref(info)) == 0:  # 2 = RUSAGE_INFO_V2
            return info.ri_phys_footprint / 1e6
    return psutil.Process(pid).memory_info().rss / 1e6


def _find_server_process() -> psutil.Process | None:
    for p in psutil.process_iter(["name"]):
        if p.info["name"] == "llama-server":
            return p
    return None


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000
