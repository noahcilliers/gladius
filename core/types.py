"""Data passed between the pipeline and whatever drives it."""

from dataclasses import dataclass, field


@dataclass
class Options:
    force: str = "auto"  # a route name to skip the router, or "auto"
    use_rag: bool = True  # search the student's notes and schedule


@dataclass
class Turn:
    """One prompt on its way through the pipeline. Each stage fills in its part."""

    prompt: str
    options: Options = field(default_factory=Options)
    routing: dict | None = None  # set by Pipeline.route
    rag: dict | None = None  # set by Pipeline.retrieve; None when notes are off
    model_prompt: str = ""  # the prompt plus any retrieved context: what the model sees
    answer: str = ""  # set by the caller, in whatever form it wants saved
    stats: dict | None = None  # set when Pipeline.stream finishes
    base_answer: str | None = None

    @property
    def route(self) -> str:
        return self.routing["route"]

    def to_dict(self) -> dict:
        """The shape saved in results/sessions.json and results/turns.jsonl."""
        return {"prompt": self.prompt, "routing": self.routing, "answer": self.answer,
                "stats": self.stats, "base_answer": self.base_answer, "rag": self.rag}
