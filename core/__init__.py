"""Gladius core: the chat pipeline and session storage, with no UI code.

A UI (retro.py today, the API in docs/architecture.md later) drives a Pipeline turn by
turn and persists turns with a SessionStore.
"""

from core.pipeline import Pipeline
from core.sessions import SessionStore
from core.types import Options, Turn

__all__ = ["Options", "Pipeline", "SessionStore", "Turn"]
