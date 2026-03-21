from __future__ import annotations

import hashlib
import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer

_EMBEDDING_MODEL_UNAVAILABLE = False


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    model_name = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    global _EMBEDDING_MODEL_UNAVAILABLE
    if not texts:
        return []
    if _EMBEDDING_MODEL_UNAVAILABLE:
        return [_hash_embedding(text) for text in texts]
    try:
        model = get_embedder()
        vectors = model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()
    except Exception:
        # Deterministic fallback keeps retrieval functional in restricted envs.
        _EMBEDDING_MODEL_UNAVAILABLE = True
        return [_hash_embedding(text) for text in texts]


def _hash_embedding(text: str, dims: int = 384) -> list[float]:
    values = [0.0] * dims
    words = text.lower().split()
    if not words:
        return values
    for word in words:
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if (digest[4] % 2 == 0) else -1.0
        values[idx] += sign
    norm = sum(v * v for v in values) ** 0.5
    if norm <= 0:
        return values
    return [v / norm for v in values]
