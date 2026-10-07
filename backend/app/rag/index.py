"""Qdrant collections with two vectors per point: dense (meaning) + BM25 sparse (exact words)."""

from functools import lru_cache

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models

from app.config import get_settings

PRODUCTS = "products"
POLICIES = "policies"
DENSE = "dense"
SPARSE = "bm25"


@lru_cache
def client() -> QdrantClient:
    s = get_settings()
    if s.qdrant_url:
        return QdrantClient(url=s.qdrant_url)
    return QdrantClient(path=str(s.qdrant_path))


@lru_cache
def dense_model() -> TextEmbedding:
    s = get_settings()
    return TextEmbedding(s.dense_model, cache_dir=str(s.embed_cache_dir))


@lru_cache
def sparse_model() -> SparseTextEmbedding:
    s = get_settings()
    return SparseTextEmbedding(s.sparse_model, cache_dir=str(s.embed_cache_dir))


def embed_query(text: str) -> tuple[list[float], models.SparseVector]:
    # bge models expect an instruction prefix on queries; query_embed adds it
    dense = next(iter(dense_model().query_embed(text))).tolist()
    sp = next(iter(sparse_model().query_embed(text)))
    return dense, models.SparseVector(indices=sp.indices.tolist(), values=sp.values.tolist())


def recreate(name: str) -> None:
    c = client()
    if c.collection_exists(name):
        c.delete_collection(name)
    dim = dense_model().embedding_size
    c.create_collection(
        name,
        vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
        # IDF is computed by Qdrant over the collection, which is what makes the sparse vector BM25
        sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )


def upsert(name: str, ids: list[int], texts: list[str], payloads: list[dict]) -> None:
    dense = [v.tolist() for v in dense_model().passage_embed(texts)]
    sparse = list(sparse_model().passage_embed(texts))
    points = [
        models.PointStruct(
            id=i,
            vector={
                DENSE: d,
                SPARSE: models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist()),
            },
            payload=p,
        )
        for i, d, s, p in zip(ids, dense, sparse, payloads, strict=True)
    ]
    client().upsert(name, points=points)
