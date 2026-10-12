"""The workspace: the folder of the student's own notes that Gladius indexes.

Set GLADIUS_WORKSPACE (in .env or the shell) to any folder on the machine; it defaults to the
bundled sample student in data/student. Relative paths are taken from the repo root.

Collections come from the layout: a file's top-level subfolder is its collection (`lectures/wk1.md`
→ "lectures"), and loose files at the root go in "general". Two optional conventions, both no-ops
when absent: a root `profile.md` (the "about me" block, collection "profile") and a `calendar.md`
anywhere, whose `- Mon Oct 6 ...` lines feed the upcoming-deadlines list.

Chunks follow the file's own structure (chunk_file), so notes don't have to be written for the
retriever: each chunk keeps the headings it sits under, and is embedded with them and its file path
(Chunk.breadcrumb) plus, once rag/context.py has run, a sentence from the model placing it in its file.
"""

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from settings import ROOT

SAMPLE_WORKSPACE = ROOT / "data" / "student"
EXTENSIONS = {".md", ".txt"}
# Folders a real notes directory carries that are never notes: VCS, editor state, dependencies.
IGNORE_DIRS = {"node_modules", "__pycache__", "venv", "site-packages"}
MAX_FILE_BYTES = 1_000_000  # ~250k tokens; anything bigger is an export or a log, not a note
# ~300 tokens. The embedder reads 512 (Arctic), and the breadcrumb and context sentence go first.
MAX_CHUNK_CHARS = 1200
OVERLAP_CHARS = 200  # repeated from the end of one part at the start of the next when a section is split
DEFAULT_COLLECTION = "general"
PROFILE_COLLECTION = "profile"

# CommonMark ATX headings; "#hashtag" (no space) isn't one, and a closing "##" run is dropped.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)(?:\s+#+)?\s*$")
_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class WorkspaceError(Exception):
    pass


@dataclass
class Chunk:
    collection: str  # top-level subfolder, "general" for loose root files, or "profile"
    source: str  # path relative to the workspace
    heading: str  # its own section heading; the file name for text before any heading
    body: str
    path: tuple[str, ...] = ()  # the headings of the sections around it, outermost (the file title) first
    lines: tuple[int, int] = (0, 0)  # first and last line in the file, counting from 1
    part: tuple[int, int] = (1, 1)  # (i, n) when a section too long for one chunk was split into n
    context: str = ""  # the model's sentence placing it in its file (rag/context.py), if written

    @property
    def breadcrumb(self) -> str:
        """Where it sits: "notes › math221 notes › MATH 221 Linear Algebra — lecture notes › Inverses"."""
        rel = Path(self.source)
        names = [*rel.parent.parts, re.sub(r"[_-]+", " ", rel.stem), *self.path]
        return " › ".join(names if self.heading == rel.stem else [*names, self.heading])

    @property
    def text(self) -> str:
        """What gets embedded: the breadcrumb, the context sentence if there is one, then the chunk."""
        return "\n".join(s for s in (self.breadcrumb, self.context, self.body) if s)

    @property
    def tag(self) -> str:
        part = f" ({self.part[0]}/{self.part[1]})" if self.part[1] > 1 else ""
        return f"{self.source} · {self.heading}{part}"


@dataclass
class Section:
    level: int  # 1-6 for "#" to "######", 0 for the file itself
    heading: str
    path: tuple[str, ...]  # headings of the sections it sits in, outermost first
    start: int  # index of its first line of text, the one after its heading
    end: int = 0  # where it stops along with its subsections
    children: list["Section"] = field(default_factory=list)

    @property
    def own_end(self) -> int:
        """Where its own text stops: at its first subsection."""
        return self.children[0].start - 1 if self.children else self.end


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


def read_lines(path: Path) -> list[str]:
    """The file's lines, with YAML front matter (Obsidian's `---` block) blanked out."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, min(len(lines), 100)):
            if lines[i].strip() in ("---", "..."):
                return [""] * (i + 1) + lines[i + 1:]
    return lines


def parse(lines: list[str]) -> Section:
    """The file's heading tree. Lines inside ``` fences are never headings (a `# comment` in code)."""
    root = Section(0, "", (), 0)
    stack, fenced = [root], False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            fenced = not fenced
        m = None if fenced else _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        while stack[-1].level >= level:
            stack.pop().end = i
        parent = stack[-1]
        sec = Section(level, m.group(2), parent.path + ((parent.heading,) if parent.level else ()), i + 1)
        parent.children.append(sec)
        stack.append(sec)
    for sec in stack:
        sec.end = len(lines)
    return root


def walk(sec: Section) -> Iterator[Section]:
    yield sec
    for child in sec.children:
        yield from walk(child)


def chunk_file(path: Path, root: Path) -> list[Chunk]:
    """Every heading starts a section. A section that fits in MAX_CHUNK_CHARS keeps its subsections
    with it; a longer one is split at them. The top level is always split, so each `##` section of a
    note with a `#` title is its own chunk, as is text before the first heading. Text that is still
    too long (a long section, a .txt file) is cut between paragraphs, then lines, then sentences,
    and each part after the first repeats the last OVERLAP_CHARS or so of the one before."""
    rel = path.relative_to(root)
    collection, source = collection_of(rel), str(rel)
    lines = read_lines(path)
    doc = parse(lines)
    title = doc.children[0] if len(doc.children) == 1 else None  # a lone top heading is the file's title
    chunks = []
    for sec, end in _units(doc, title, lines):
        heading = sec.heading or path.stem
        whole = "\n".join(lines[sec.start:end]).strip()
        if not whole:
            continue
        blocks = _blocks(lines, sec.start, end)
        parts = [blocks] if len(whole) <= MAX_CHUNK_CHARS else _pack(blocks)
        for i, part in enumerate(parts, 1):
            body = whole if len(parts) == 1 else _join(part).strip()
            chunks.append(Chunk(collection, source, heading, body, sec.path,
                                (part[0].first + 1, part[-1].last + 1), (i, len(parts))))
    return chunks


def _units(sec: Section, title: Section | None, lines: list[str]) -> Iterator[tuple[Section, int]]:
    """(section, end) for each run of lines that becomes one chunk, or several if it's too long."""
    if sec.level and sec is not title and sec.children and \
            len("\n".join(lines[sec.start:sec.end]).strip()) <= MAX_CHUNK_CHARS:
        yield sec, sec.end  # small enough to keep its subsections
        return
    yield sec, sec.own_end
    for child in sec.children:
        yield from _units(child, title, lines)


@dataclass
class _Block:
    text: str
    first: int  # line indexes in the file
    last: int
    sep: str = "\n\n"  # what joins it to the block before: a blank line, a newline, or a space


def _blocks(lines: list[str], start: int, end: int) -> list[_Block]:
    """Paragraphs, with a fenced code block kept whole. One over MAX_CHUNK_CHARS is cut into its
    lines, and a line that is still too long into sentences."""
    paragraphs, cur, fenced = [], [], False
    for i in range(start, end):
        if _FENCE_RE.match(lines[i]):
            fenced = not fenced
        if lines[i].strip() or fenced:
            cur.append(i)
        elif cur:
            paragraphs.append(cur)
            cur = []
    paragraphs += [cur] if cur else []

    blocks = []
    for para in paragraphs:
        text = "\n".join(lines[i] for i in para)
        if len(text) <= MAX_CHUNK_CHARS:
            blocks.append(_Block(text, para[0], para[-1]))
            continue
        for k, i in enumerate(para):
            for j, (piece, sep) in enumerate(_sentences(lines[i])):
                blocks.append(_Block(piece, i, i, sep if j else "\n\n" if k == 0 else "\n"))
    return blocks


def _sentences(line: str) -> list[tuple[str, str]]:
    """(piece, separator before it) for a line, cut into sentences only if it's over MAX_CHUNK_CHARS."""
    if len(line) <= MAX_CHUNK_CHARS:
        return [(line, "")]
    pieces = []
    for sentence in filter(None, _SENTENCE_RE.split(line)):
        sep = " "
        while len(sentence) > MAX_CHUNK_CHARS:  # no sentence breaks at all: cut it anywhere
            pieces.append((sentence[:MAX_CHUNK_CHARS], sep))
            sentence, sep = sentence[MAX_CHUNK_CHARS:], ""
        pieces.append((sentence, sep))
    return pieces


def _join(blocks: list[_Block]) -> str:
    return blocks[0].text + "".join(b.sep + b.text for b in blocks[1:])


def _pack(blocks: list[_Block]) -> list[list[_Block]]:
    """Greedily fill parts up to MAX_CHUNK_CHARS; each new part starts with the end of the last."""
    parts, cur = [], []
    for b in blocks:
        if cur and len(_join(cur)) + len(b.sep) + len(b.text) > MAX_CHUNK_CHARS:
            parts.append(cur)
            cur = _overlap(cur)
            if cur and len(_join(cur)) + len(b.sep) + len(b.text) > MAX_CHUNK_CHARS:
                cur = []
        cur.append(b)
    return parts + [cur] if cur else parts


def _overlap(blocks: list[_Block]) -> list[_Block]:
    """The end of a full part, to repeat: whole blocks up to OVERLAP_CHARS, else the last block's
    final sentences."""
    tail = []
    for b in reversed(blocks):
        if len(_join([b, *tail])) > OVERLAP_CHARS:
            break
        tail.insert(0, b)
    if tail:
        return tail
    last, keep = blocks[-1], []
    for sentence in reversed([s for s in _SENTENCE_RE.split(last.text) if s]):
        if len(" ".join([sentence, *keep])) > OVERLAP_CHARS:
            break
        keep.insert(0, sentence)
    return [_Block(" ".join(keep), last.last, last.last)] if keep else []


def profile_text(root: Path) -> str:
    """The root profile.md without its headings, or "" if there isn't one: the "about me" block."""
    path = root / "profile.md"
    if not path.is_file() or path.is_symlink():
        return ""
    try:
        lines = read_lines(path)
    except OSError:
        return ""
    texts = ("\n".join(lines[s.start:s.own_end]).strip() for s in walk(parse(lines)))
    return "\n\n".join(t for t in texts if t)


def load_chunks(root: Path) -> tuple[list[Chunk], list[tuple[Path, str]]]:
    files, skipped = scan(root)
    chunks = []
    for path in files:
        try:
            chunks += chunk_file(path, root)
        except OSError as e:  # e.g. macOS hasn't granted access to Documents/Desktop yet
            skipped.append((path, e.strerror or type(e).__name__))
    return chunks, skipped
