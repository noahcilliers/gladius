"""Retrieval over the student's own notes: the workspace (which folder, which files, how they
chunk), context sentences for the chunks, and the route-gated retriever on top of it. See docs/rag.md."""

from rag.workspace import WorkspaceError, workspace_dir

__all__ = ["Retriever", "WorkspaceError", "workspace_dir"]


def __getattr__(name):
    # Imported on first use, so `python -m rag.retriever` and `python -m rag.context` don't load the
    # module they run twice.
    if name == "Retriever":
        from rag.retriever import Retriever
        return Retriever
    raise AttributeError(f"module 'rag' has no attribute {name!r}")
