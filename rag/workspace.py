"""The workspace: the folder of the student's own notes that Gladius indexes.

Set GLADIUS_WORKSPACE (in .env or the shell) to any folder on the machine; it defaults to the
bundled sample student in data/student. Relative paths are taken from the repo root.

Collections come from the layout: a file's top-level subfolder is its collection (`lectures/wk1.md`
→ "lectures"), and loose files at the root go in "general". Two optional conventions, both no-ops
when absent: a root `profile.md` (the "about me" block, collection "profile") and a `calendar.md`
anywhere, whose `- Mon Oct 6 ...` lines feed the upcoming-deadlines list.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from settings import ROOT

SAMPLE_WORKSPACE = ROOT / "data" / "student"
EXTENSIONS = {".md", ".txt"}
# Folders a real notes directory carries that are never notes: VCS, editor state, dependencies.
IGNORE_DIRS = {"node_modules", "__pycache__", "venv", "site-packages"}
MAX_FILE_BYTES = 1_000_000  # ~250k tokens; anything bigger is an export or a log, not a note
MAX_CHUNK_CHARS = 1600  # ~400 tokens, for files with no `##` sections to split on
DEFAULT_COLLECTION = "general"
PROFILE_COLLECTION = "profile"

_PARA_RE = re.compile(r"\n\s*\n")


class WorkspaceError(Exception):
    pass


@dataclass
class Chunk:
    collection: str  # top-level subfolder, "general" for loose root files, or "profile"
    source: str  # path relative to the workspace
    heading: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.heading}\n{self.body}"

    @property
    def tag(self) -> str:
        return f"{self.source} · {self.heading}"


def workspace_dir() -> Path:
    raw = os.environ.get("GLADIUS_WORKSPACE", "").strip()
    path = Path(raw).expanduser() if raw else SAMPLE_WORKSPACE
    path = (ROOT / path if not path.is_absolute() else path).resolve()
    if not path.is_dir():
        raise WorkspaceError(f"GLADIUS_WORKSPACE is not a folder: {path}")
    return path


def scan(root: Path) -> tuple[list[Path], list[tuple[Path, str]]]:
    """The note files under `root`, sorted, and the files passed over with the reason.
    Hidden files and folders, symlinks, READMEs and oversized files are not indexed."""
    files, skipped = [], []
    for dirpath, dirnames, filenames in os.walk(root):  # doesn't follow symlinked folders
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in IGNORE_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if name.startswith(".") or path.suffix.lower() not in EXTENSIONS or name == "README.md":
                continue
            if path.is_symlink():
                skipped.append((path, "symlink"))
            elif path.stat().st_size > MAX_FILE_BYTES:
                skipped.append((path, f"over {MAX_FILE_BYTES // 1_000_000} MB"))
            else:
                files.append(path)
    return sorted(files), skipped


def collection_of(rel: Path) -> str:
    if len(rel.parts) > 1:
        return rel.parts[0]
    return PROFILE_COLLECTION if rel.name == "profile.md" else DEFAULT_COLLECTION


def chunk_file(path: Path, root: Path) -> list[Chunk]:
    """One `##` section = one chunk; the `#` title and anything before the first `##` are dropped.
    A file with no `##` sections (any .txt, a flat note) is split into paragraph runs instead."""
    rel = path.relative_to(root)
    collection, source = collection_of(rel), str(rel)
    text = path.read_text(encoding="utf-8", errors="replace")
    chunks, heading, lines = [], None, []
    for line in text.splitlines() + ["## "]:
        if line.startswith("## "):
            if heading and "\n".join(lines).strip():
                chunks.append(Chunk(collection, source, heading, "\n".join(lines).strip()))
            heading, lines = line[3:].strip(), []
        elif heading is not None:
            lines.append(line)
    if chunks:
        return chunks

    title = path.stem
    if text.startswith("# "):
        first, _, text = text.partition("\n")
        title = first[2:].strip() or title
    parts = _pack(_PARA_RE.split(text.strip()))
    return [Chunk(collection, source, title if len(parts) == 1 else f"{title} ({i}/{len(parts)})", body)
            for i, body in enumerate(parts, 1)]


def _pack(paragraphs: list[str]) -> list[str]:
    """Greedily join paragraphs into chunks of at most MAX_CHUNK_CHARS; hard-split any longer one."""
    out, cur = [], ""
    for para in (p.strip() for p in paragraphs):
        while len(para) > MAX_CHUNK_CHARS:
            cut = para.rfind("\n", 0, MAX_CHUNK_CHARS)
            cut = cut if cut > 0 else MAX_CHUNK_CHARS
            out += [cur] if cur else []
            out.append(para[:cut].strip())
            cur, para = "", para[cut:].strip()
        if cur and len(cur) + len(para) + 2 > MAX_CHUNK_CHARS:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n\n{para}" if cur else para
    return [c for c in out + [cur] if c]


def load_chunks(root: Path) -> tuple[list[Chunk], list[tuple[Path, str]]]:
    files, skipped = scan(root)
    chunks = []
    for path in files:
        try:
            chunks += chunk_file(path, root)
        except OSError as e:  # e.g. macOS hasn't granted access to Documents/Desktop yet
            skipped.append((path, e.strerror or type(e).__name__))
    return chunks, skipped
