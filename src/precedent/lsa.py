"""Offline text embeddings (TF-IDF + truncated SVD, a.k.a. LSA).

No model download, no API key, deterministic.  The vectors go into Relate's native vector index so
hybrid retrieval (full-text + vector + graph expansion) works on a fresh clone with zero setup.
Swap in a neural embedder later by writing vectors of another dimension into the same property.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

import numpy as np

_TOKEN = re.compile(r"[a-z][a-z0-9_]{2,}")
_STOP = frozenset(
    """the and for that this with from are was were has have had not but all can its into than then them
    they their there these those which what when where who whom will would should could may might must
    also only any each other such more most some one two via per use used using uses new now out our we
    you your yes how why does did done doing been being both either neither""".split()
)


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        parts = [p for p in tok.split("_") if len(p) > 2] or [tok]
        out.extend(p for p in parts if p not in _STOP)
    return out


class LSA:
    def __init__(self, vocab: dict[str, int], idf: np.ndarray, components: np.ndarray):
        self.vocab = vocab
        self.idf = idf.astype(np.float32)
        self.components = components.astype(np.float32)  # (k, V)

    @property
    def dim(self) -> int:
        return int(self.components.shape[0])

    # ------------------------------------------------------------------ fit / transform
    @classmethod
    def fit(cls, docs: list[str], k: int = 96, min_df: int = 2, max_features: int = 20000) -> LSA:
        toks = [tokenize(d) for d in docs]
        df: Counter[str] = Counter()
        for t in toks:
            df.update(set(t))
        keep = [w for w, c in df.most_common() if c >= min_df][:max_features]
        keep.sort()
        vocab = {w: i for i, w in enumerate(keep)}
        n = len(docs)
        idf = np.array([math.log((1 + n) / (1 + df[w])) + 1.0 for w in keep], dtype=np.float32)
        x = cls._tfidf_matrix(toks, vocab, idf)
        k = max(2, min(k, x.shape[0] - 1, x.shape[1] - 1))
        # Deterministic SVD; sign of each component fixed so repeated builds are identical.
        _u, _s, vt = np.linalg.svd(x, full_matrices=False)
        comps = vt[:k].copy()
        for i in range(comps.shape[0]):
            j = int(np.argmax(np.abs(comps[i])))
            if comps[i, j] < 0:
                comps[i] = -comps[i]
        return cls(vocab, idf, comps)

    @staticmethod
    def _tfidf_matrix(toks: list[list[str]], vocab: dict[str, int], idf: np.ndarray) -> np.ndarray:
        x = np.zeros((len(toks), len(vocab)), dtype=np.float32)
        for r, t in enumerate(toks):
            for w, c in Counter(t).items():
                j = vocab.get(w)
                if j is not None:
                    x[r, j] = (1.0 + math.log(c)) * idf[j]
        norms = np.linalg.norm(x, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return x / norms

    def transform(self, texts: list[str]) -> np.ndarray:
        x = self._tfidf_matrix([tokenize(t) for t in texts], self.vocab, self.idf)
        v = x @ self.components.T
        norms = np.linalg.norm(v, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (v / norms).astype(np.float32)

    # ------------------------------------------------------------------ persistence
    def save(self, path: Path) -> None:
        words = np.array(sorted(self.vocab, key=self.vocab.get))
        np.savez_compressed(path, words=words, idf=self.idf, components=self.components)

    @classmethod
    def load(cls, path: Path) -> LSA:
        z = np.load(path, allow_pickle=False)
        vocab = {str(w): i for i, w in enumerate(z["words"])}
        return cls(vocab, z["idf"], z["components"])
