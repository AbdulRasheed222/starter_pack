"""Turn text into vectors for search."""

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

from app.config import Settings
from app.models import EMBEDDING_DIM

_WORD = re.compile(r"\w+", re.UNICODE)


class Embedder(Protocol):
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Runs an open embedding model on the CPU with ONNX. Downloaded on first use."""

    def __init__(self, model_name: str, cache_dir: str | None):
        from fastembed import TextEmbedding  # imported lazily: tests never load it

        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        self.dim = len(next(iter(self._model.embed(["dimension probe"]))))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([text]))).tolist()


class HashingEmbedder:
    """Deterministic bag-of-words vectors: no download and no understanding of meaning. Tests
    use it. Never judge search quality with it."""

    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in _WORD.findall(text.casefold()):
            digest = hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest()
            vector[int.from_bytes(digest, "big") % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@lru_cache
def _build(kind: str, model_name: str, cache_dir: str | None) -> Embedder:
    if kind == "hashing":
        return HashingEmbedder()
    if kind == "fastembed":
        return FastEmbedEmbedder(model_name, cache_dir)
    raise ValueError(f"Unknown EMBEDDER: {kind}")


def get_embedder(settings: Settings) -> Embedder:
    embedder = _build(settings.embedder, settings.embedding_model, settings.embedding_cache_dir)
    if embedder.dim != EMBEDDING_DIM:
        raise RuntimeError(
            f"{settings.embedding_model} makes {embedder.dim}-dimension vectors, but the "
            f"chunks table stores {EMBEDDING_DIM}. Change EMBEDDING_DIM in models.py and add a "
            "migration, then re-upload the documents."
        )
    return embedder
