"""The chat pipeline: route → notes override → retrieve → augment → generate.

Each stage is its own call, so a UI can draw the trace as the turn advances:

    turn = pipeline.route(prompt, Options(use_rag=True))
    pipeline.retrieve(turn)
    for chunk in pipeline.stream(turn): ...
"""

from collections.abc import Iterator

from core.types import Options, Turn
from engine import Engine, process_mem_mb
from retriever import Retriever
from router import Router


class Pipeline:
    def __init__(self, router: Router | None = None, engine: Engine | None = None,
                 retriever: Retriever | None = None):
        """Builds the real components unless given ones (e.g. fakes in a test)."""
        if router is None:
            router = Router()
            router.route("warm-up", use_cache=False)
        self.router = router
        self.engine = engine or Engine()
        self.retriever = retriever or Retriever(router)  # reuses the router's embedding model
        # The adapter llama-server ran last. It's server state, so it's shared by every session.
        self.last_route: str | None = None

    def route(self, prompt: str, options: Options | None = None) -> Turn:
        opts = options or Options()
        rr = self.router.route(prompt)
        auto = opts.force == "auto"
        route = rr.route if auto else opts.force
        # Questions about the student's own courses go to the base model with notes, even if the
        # router picked a specialist on topic words (retriever.notes_route). Never overrides a forced route.
        answer_route = self.retriever.notes_route(prompt, route) if opts.use_rag and auto else route
        routing = {"route": answer_route, "scores": rr.scores, "margin": rr.margin,
                   "low_confidence": rr.low_confidence, "cache": rr.cache, "latency_ms": rr.latency_ms,
                   "forced": not auto, "notes_override": route if answer_route != route else None}
        return Turn(prompt, opts, routing, model_prompt=prompt)

    def retrieve(self, turn: Turn) -> Turn:
        """Route on the raw prompt; the model sees it with any retrieved context added."""
        if turn.options.use_rag:
            ret = self.retriever.retrieve(turn.prompt, turn.route)
            turn.model_prompt = self.retriever.augment(turn.prompt, ret)
            turn.rag = {"sources": ret.sources, "scores": [h.score for h in ret.hits],
                        "profile": ret.profile, "latency_ms": ret.latency_ms}
        return turn

    def stream(self, turn: Turn) -> Iterator[str]:
        """Yield the answer as it streams; sets turn.stats once it's done. Raises
        requests.RequestException if llama-server goes away."""
        yield from self.engine.stream(turn.model_prompt, turn.route)
        turn.stats = {**self.engine.last_stats.__dict__, "app_mem_mb": process_mem_mb(),
                      "switched": self.last_route not in (None, turn.route)}
        self.last_route = turn.route

    def stream_base(self, turn: Turn) -> Iterator[str]:
        """The same prompt, base model only and without notes, for comparison."""
        return self.engine.stream(turn.prompt, "base")

    def has_adapter(self, route: str) -> bool:
        return self.engine.has_adapter(route)

    def memory_mb(self) -> float:
        """llama-server plus this process."""
        return self.engine.server_mem_mb() + process_mem_mb()

    def clear_cache(self):
        self.router.clear_cache()

    @property
    def n_chunks(self) -> int:
        return len(self.retriever.chunks)
