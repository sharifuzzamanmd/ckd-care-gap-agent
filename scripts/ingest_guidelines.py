"""Split my guideline notes into lines, embed them, and store them in Qdrant."""
import os
from pathlib import Path
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

COLLECTION = "guidelines"
embedder = TextEmbedding("BAAI/bge-base-en-v1.5")  # small, runs on CPU
client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))

chunks = []
for f in Path("guidelines").glob("*.md"):
    lines = f.read_text().splitlines()
    source = lines[0].lstrip("# ").strip()
    for line in lines[1:]:
        if line.strip():
            chunks.append({"text": line.strip(), "source": source, "file": f.name})

vectors = list(embedder.passage_embed([c["text"] for c in chunks]))
if client.collection_exists(COLLECTION):
    client.delete_collection(COLLECTION)
client.create_collection(COLLECTION, vectors_config=models.VectorParams(
    size=len(vectors[0]), distance=models.Distance.COSINE))
client.upsert(COLLECTION, points=[
    models.PointStruct(id=i, vector=v.tolist(), payload=c)
    for i, (v, c) in enumerate(zip(vectors, chunks))])
print(f"Stored {len(chunks)} guideline passages")