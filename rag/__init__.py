"""Retrieval over the student's own notes: the workspace (which folder, which files, how they
chunk) and the route-gated retriever on top of it. See docs/rag.md."""

from rag.retriever import Retriever
from rag.workspace import WorkspaceError, workspace_dir

__all__ = ["Retriever", "WorkspaceError", "workspace_dir"]
