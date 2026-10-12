"""The persistent vector index: chunk vectors cached on disk by what was embedded.

A vector is a pure function of the text, the embedding model and how it was called, so each one is
stored under a hash of those (cache_key). On launch the retriever chunks the workspace, hashes every
chunk's text, and only the chunks whose hash isn't in the store go to the model. Edited chunks get a
new hash and re-embed; deleted ones are simply never asked for. Nothing here knows about files.

One store per embedding model, shared by every workspace, in cache/rag/vectors-<model>.npz. It is a
cache: deleting it only costs a re-embed. GLADIUS_RAG_INDEX=off embeds everything and writes nothing.
"""

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from settings import ROOT

CACHE_DIR = ROOT / "cache" / "rag"
FORMAT_VERSION = 1  # bump if what is stored for a key changes
MAX_ENTRIES = 50_000  # ~75 MB at 384 dims; past it, entries this load didn't use are dropped, oldest first


@dataclass
class EmbedStats:
    embedded: int  # chunks sent to the model this load
    cached: int  # chunks served from the store
    stored: int  # entries in the store after this load


def index_enabled() -> bool:
    return os.environ.get("GLADIUS_RAG_INDEX", "").strip().lower() != "off"


def cache_key(model_id: str, settings: str, text: str) -> str:
    """Same model, same call, same text: same vector. `settings` is whatever else changes the vector
    (normalization, a document prefix)."""
    raw = json.dumps([FORMAT_VERSION, model_id, settings, text], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class VectorStore:
    def __init__(self, model_id: str, settings: str = "", directory: Path = CACHE_DIR):
        self.model_id, self.settings = model_id, settings
        slug = re.sub(r"[^\w.-]+", "_", model_id)
        self.path = directory / f"vectors-{slug}.npz"
        self.keys: list[str] = []
        self.vecs = np.zeros((0, 0), dtype=np.float32)
        self._load()

    def _load(self):
        """Whatever is on disk, or an empty store if it's missing, unreadable or for another model."""
        try:
            with np.load(self.path, allow_pickle=False) as f:
                meta = json.loads(str(f["meta"]))
                keys, vecs = [str(k) for k in f["keys"]], f["vectors"]
        except (OSError, ValueError, KeyError):
            return
        if meta.get("model") != self.model_id or vecs.ndim != 2 or len(keys) != len(vecs):
            return
        self.keys, self.vecs = keys, vecs.astype(np.float32, copy=False)

    def embed(self, texts: list[str], encode: Callable[[list[str]], np.ndarray],
              save: bool = True) -> tuple[np.ndarray, EmbedStats]:
        """Vectors for `texts` in order. `encode` is called once, with only the texts not stored."""
        if not texts:
            return np.zeros((0, self.vecs.shape[1]), dtype=np.float32), EmbedStats(0, 0, len(self.keys))
        keys = [cache_key(self.model_id, self.settings, t) for t in texts]
        row = {k: i for i, k in enumerate(self.keys)}
        missing = list(dict.fromkeys(k for k in keys if k not in row))
        text_of = dict(zip(keys, texts))
        if missing:
            new = np.asarray(encode([text_of[k] for k in missing]), dtype=np.float32)
            if self.vecs.shape[1] not in (0, new.shape[1]):
                # The stored vectors are another size, so none of them can be mixed in: embed it all again.
                self.keys, self.vecs, row = [], np.zeros((0, 0), dtype=np.float32), {}
                missing = list(dict.fromkeys(keys))
                new = np.asarray(encode([text_of[k] for k in missing]), dtype=np.float32)
            base = len(self.keys)
            self.vecs = new if not len(self.keys) else np.vstack([self.vecs, new])
            self.keys += missing
            row.update({k: base + i for i, k in enumerate(missing)})
        out = self.vecs[[row[k] for k in keys]]
        stats = EmbedStats(len(missing), len(keys) - len(missing), len(self.keys))
        if missing:
            self._trim(set(keys))
            stats.stored = len(self.keys)
            if save:
                self.save()
        return out, stats

    def _trim(self, used: set[str]):
        excess = len(self.keys) - MAX_ENTRIES
        if excess <= 0:
            return
        drop = {k for k in self.keys if k not in used}  # oldest first: keys are in insertion order
        drop = set(list(k for k in self.keys if k in drop)[:excess])
        keep = [i for i, k in enumerate(self.keys) if k not in drop]
        self.keys, self.vecs = [self.keys[i] for i in keep], self.vecs[keep]

    def save(self):
        """Atomic: a reader sees the old file or the new one, never half of one."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "wb") as f:
            np.savez(f, vectors=self.vecs, keys=np.array(self.keys), meta=json.dumps(
                {"model": self.model_id, "settings": self.settings, "version": FORMAT_VERSION, "dim": int(self.vecs.shape[1])}))
        tmp.replace(self.path)
