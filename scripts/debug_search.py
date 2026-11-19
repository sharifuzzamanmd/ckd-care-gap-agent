"""Debug: compare the question with every guideline note, directly and via Qdrant."""
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding
from qdrant_client import QdrantClient

QUESTION = "when should I send a patient to a kidney specialist"

# A. Score every note directly (no database)
notes = []
for f in sorted(Path("guidelines").glob("*.md")):
    for line in f.read_text().splitlines()[1:]:
        if line.strip():
            notes.append((f.name, line.strip()))

model = TextEmbedding("BAAI/bge-base-en-v1.5")
q = next(model.query_embed([QUESTION]))
passages = list(model.passage_embed([text for _, text in notes]))
scores = [float(np.dot(q, p) / (np.linalg.norm(q) * np.linalg.norm(p))) for p in passages]

print("A. Direct similarity (no Qdrant), best first:")
for s, (file, text) in sorted(zip(scores, notes), reverse=True):
    print(f"  {s:.3f}  {file:18} {text[:60]}")

# B. What Qdrant actually holds and returns
client = QdrantClient(url="http://localhost:6333")
stored = client.scroll("guidelines", limit=50)[0]
print(f"\nB. Qdrant holds {len(stored)} notes:")
for p in stored:
    print(f"  id {p.id}: {p.payload['file']:18} {p.payload['text'][:60]}")

print("\nC. Qdrant search results:")
for h in client.query_points("guidelines", query=q.tolist(), limit=3).points:
    print(f"  {h.score:.3f}  {h.payload['file']:18} {h.payload['text'][:60]}")