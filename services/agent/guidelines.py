"""Search my guideline notes by meaning."""
import os
from fastembed import TextEmbedding
from qdrant_client import QdrantClient

_embedder = TextEmbedding("BAAI/bge-base-en-v1.5")
_client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))


def search(question: str, k: int = 2) -> list[dict]:
    """Return the k guideline lines closest in meaning to the question."""
    vector = next(_embedder.query_embed([question])).tolist()
    hits = _client.query_points("guidelines", query=vector, limit=k).points
    return [{"text": h.payload["text"], "source": h.payload["source"], "score": round(h.score, 3)}
            for h in hits]