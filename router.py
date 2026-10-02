"""Embedding router: decides which LoRA adapter should answer a prompt.

Nearest-centroid classifier over Snowflake Arctic Embed vectors. Each route's
centroid is the mean embedding of its example prompts in docs/example_prompts.md.
A two-level cache (exact text, then semantic) reuses past routing decisions.

Run directly to print leave-one-out routing accuracy and route the demo prompts:
    python router.py
"""

import os
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import psutil

EMBED_MODEL = "Snowflake/snowflake-arctic-embed-xs"
EXAMPLES_PATH = Path(__file__).parent / "docs" / "example_prompts.md"
ROUTES = ("math", "sql", "techwriter", "creative", "coding", "base")

# Arctic scores cluster in ~0.58-0.80, and adapter and base scores overlap, so an
# absolute threshold misroutes real adapter prompts. A small tie-break toward base
# works better (leave-one-out 90.4% -> 94.2%); the threshold is only a safety net.
ROUTE_THRESHOLD = 0.55  # best score below this -> fall back to base
BASE_BIAS = 0.01  # added to the base score before ranking
MARGIN_WARN = 0.03  # top-1 minus top-2 below this -> low confidence
CACHE_THRESHOLD = 0.92  # cached prompt at least this similar -> reuse its route

DEMO_PROMPTS = [
    "Write a query to calculate each student's GPA, then explain the math.",
    "Write a poem about prime numbers.",
    "Explain what a database index is to a beginner.",
    "Write a product brief, but make it philosophical.",
    "hey whats up",
    "What is 2 + 2?",
]


def load_examples(path: Path = EXAMPLES_PATH) -> dict[str, list[str]]:
    """Parse `## <route>` sections of bullet points from the examples markdown."""
    examples: dict[str, list[str]] = {}
    current = None
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            name = line[3:].split()[0].lower()
            current = name if name in ROUTES else None
        elif current and line.startswith("- "):
            examples.setdefault(current, []).append(line[2:].strip())
    return examples


@dataclass
class RouteResult:
    route: str  # adapter to use ("base" = no adapter)
    scores: dict[str, float]  # cosine similarity per route, highest first
    margin: float  # top-1 minus top-2 score
    low_confidence: bool
    cache: str  # "miss", "exact" or "semantic"
    latency_ms: float  # embed + score (or cache lookup) time

    @property
    def confidence(self) -> float:
        return next(iter(self.scores.values()))


class Router:
    def __init__(
        self,
        examples: dict[str, list[str]] | None = None,
        threshold: float = ROUTE_THRESHOLD,
        margin_warn: float = MARGIN_WARN,
        cache_threshold: float = CACHE_THRESHOLD,
    ):
        from sentence_transformers import SentenceTransformer

        # CPU, not MPS: the model is tiny (~22M params), and MPS reserves ~1 GB of GPU memory.
        self.model = SentenceTransformer(EMBED_MODEL, device="cpu")
        self.examples = examples or load_examples()
        self.names = list(self.examples)
        self.example_vecs = {r: self.embed(p) for r, p in self.examples.items()}
        self.centroids = np.stack([_unit(v.mean(axis=0)) for v in self.example_vecs.values()])

        self.threshold = threshold
        self.margin_warn = margin_warn
        self.cache_threshold = cache_threshold
        self.clear_cache()

    def embed(self, texts: list[str]) -> np.ndarray:
        # Same query prefix for examples and user prompts, so they embed the same way.
        return self.model.encode(
            texts, prompt_name="query", normalize_embeddings=True, convert_to_numpy=True
        )

    def clear_cache(self):
        self._exact: dict[str, RouteResult] = {}
        self._cache_vecs: list[np.ndarray] = []
        self._cache_results: list[RouteResult] = []
        self.cache_lookups = 0
        self.cache_hits = 0

    def route(self, prompt: str, use_cache: bool = True) -> RouteResult:
        t0 = time.perf_counter()
        key = prompt.strip().lower()

        if use_cache:
            self.cache_lookups += 1
            if key in self._exact:  # skips embedding entirely
                self.cache_hits += 1
                return replace(self._exact[key], cache="exact", latency_ms=_ms(t0))

        vec = self.embed([prompt])[0]

        if use_cache and self._cache_vecs:
            sims = np.stack(self._cache_vecs) @ vec
            i = int(sims.argmax())
            if sims[i] >= self.cache_threshold:
                self.cache_hits += 1
                return replace(self._cache_results[i], cache="semantic", latency_ms=_ms(t0))

        result = self._decide(self.centroids @ vec)
        result.latency_ms = _ms(t0)

        if use_cache:
            self._exact[key] = result
            self._cache_vecs.append(vec)
            self._cache_results.append(result)
        return result

    def _decide(self, raw_scores: np.ndarray) -> RouteResult:
        raw_scores = raw_scores.copy()
        if "base" in self.names:
            raw_scores[self.names.index("base")] += BASE_BIAS
        order = np.argsort(-raw_scores)
        scores = {self.names[i]: float(raw_scores[i]) for i in order}
        top, second = raw_scores[order[0]], raw_scores[order[1]]
        best = self.names[order[0]]
        return RouteResult(
            route=best if top >= self.threshold else "base",
            scores=scores,
            margin=float(top - second),
            low_confidence=bool(top - second < self.margin_warn),
            cache="miss",
            latency_ms=0.0,
        )

    def leave_one_out(self) -> tuple[float, list[tuple[str, str, str]]]:
        """Score each example against centroids built without it."""
        sums = {r: v.sum(axis=0) for r, v in self.example_vecs.items()}
        counts = {r: len(v) for r, v in self.example_vecs.items()}
        misses, total = [], 0
        for route, vecs in self.example_vecs.items():
            for i, vec in enumerate(vecs):
                cents = np.stack([
                    _unit((sums[r] - vec) / (counts[r] - 1) if r == route else sums[r] / counts[r])
                    for r in self.names
                ])
                predicted = self._decide(cents @ vec).route
                total += 1
                if predicted != route:
                    misses.append((route, predicted, self.examples[route][i]))
        return 1 - len(misses) / total, misses


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


def _rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / 1e6


if __name__ == "__main__":
    router = Router()
    counts = ", ".join(f"{r}={len(p)}" for r, p in router.examples.items())
    print(f"Loaded {EMBED_MODEL}: process RSS {_rss_mb():.0f} MB | examples: {counts}")

    acc, misses = router.leave_one_out()
    print(f"\nLeave-one-out routing accuracy: {acc:.1%}")
    for expected, got, prompt in misses:
        print(f"  expected {expected:<10} got {got:<10} {prompt[:70]}")

    router.route("warm-up", use_cache=False)
    print(f"\n{'route':<10} {'top-1':<17} {'top-2':<17} {'ms':>6}  prompt")
    for prompt in DEMO_PROMPTS + [DEMO_PROMPTS[0]]:
        r = router.route(prompt)
        (n1, s1), (n2, s2) = list(r.scores.items())[:2]
        flag = " (low conf)" if r.low_confidence else ""
        cache = "" if r.cache == "miss" else f" [cache:{r.cache}]"
        print(f"{r.route:<10} {n1:<10} {s1:.3f}  {n2:<10} {s2:.3f}  {r.latency_ms:6.1f}  {prompt[:45]}{flag}{cache}")
