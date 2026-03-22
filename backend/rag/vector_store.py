from __future__ import annotations

from uuid import uuid4

from .chroma_collection import delete_chunks_for_doc_id, get_collection


def _embed_texts(texts: list[str]):
    from .embedding import embed_texts

    return embed_texts(texts)


def _distance_to_score(distance: float | int | None) -> float:
    if distance is None:
        return 0.0
    val = 1.0 - float(distance)
    if val < 0:
        return 0.0
    if val > 1:
        return 1.0
    return val


def _chroma_metadata(metadata: dict) -> dict:
    """Chroma metadata: no None values."""
    out: dict = {}
    for key, val in metadata.items():
        if val is None:
            out[key] = ""
        else:
            out[key] = val
    return out


def upsert_text_records(records: list[dict]) -> int:
    if not records:
        return 0
    collection = get_collection()
    docs = [r["document"] for r in records]
    vectors = _embed_texts(docs)
    ids = [r.get("id") or str(uuid4()) for r in records]
    metadatas = [_chroma_metadata(r["metadata"]) for r in records]
    collection.upsert(ids=ids, documents=docs, metadatas=metadatas, embeddings=vectors)
    return len(records)


def query_case(
    case_id: str,
    query: str,
    top_k: int = 5,
    type_filter: str | None = None,
) -> list[dict]:
    collection = get_collection()
    query_embedding = _embed_texts([query])[0]
    if type_filter:
        where: dict = {"$and": [{"case_id": case_id}, {"type": type_filter}]}
    else:
        where = {"case_id": case_id}
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
    )

    docs = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    ids = result.get("ids", [[]])[0]
    output: list[dict] = []
    for idx, doc in enumerate(docs):
        md = metadatas[idx] or {}
        distance = distances[idx] if idx < len(distances) else None
        output.append(
            {
                "id": ids[idx] if idx < len(ids) else "",
                "document": doc,
                "metadata": md,
                "distance": float(distance) if distance is not None else None,
                "score": _distance_to_score(distance),
            }
        )
    return output
