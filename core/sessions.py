"""Saved chats. Sessions persist in results/sessions.json (so a browser refresh keeps
them); every turn is also appended to results/turns.jsonl."""

import json
import time
import uuid
from pathlib import Path

from core.types import Turn

RESULTS = Path(__file__).parent.parent / "results"
SESSIONS_PATH = RESULTS / "sessions.json"
TURNS_LOG = RESULTS / "turns.jsonl"


def new_session() -> dict:
    return {"id": uuid.uuid4().hex[:8], "title": "", "created": time.time(), "turns": []}


class SessionStore:
    def __init__(self, path: Path = SESSIONS_PATH, log_path: Path = TURNS_LOG):
        self.path = path
        self.log_path = log_path
        try:
            self.sessions: list[dict] = json.loads(path.read_text()) or [new_session()]
        except (OSError, ValueError):
            self.sessions = [new_session()]

    def get(self, sid: str | None) -> dict | None:
        return next((s for s in self.sessions if s["id"] == sid), None)

    def start(self) -> str:
        """The id of an empty session to chat in. Reuses one instead of stacking blanks."""
        empty = next((s for s in self.sessions if not s["turns"]), None)
        if empty is None:
            empty = new_session()
            self.sessions.insert(0, empty)
        return empty["id"]

    def delete(self, sid: str):
        self.sessions = [s for s in self.sessions if s["id"] != sid]
        self.save()

    def clear(self):
        """Wipe every saved chat (for a clean sidebar before a demo)."""
        self.sessions = []
        self.save()

    def save(self):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps([s for s in self.sessions if s["turns"]]))

    def add_turn(self, session: dict, turn: Turn) -> dict:
        record = {"ts": time.time(), **turn.to_dict()}
        session["turns"].append(record)
        session["title"] = session["title"] or (turn.prompt[:40] + ("…" if len(turn.prompt) > 40 else ""))
        self.save()
        with self.log_path.open("a") as f:
            f.write(json.dumps({**record, "session": session["id"]}) + "\n")
        return record
