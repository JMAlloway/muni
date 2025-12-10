import json
import math
from typing import Any, Dict, List, Optional

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:
    SentenceTransformer = None  # optional dependency

from app.core.db_core import engine


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_score(q1: str, q2: str) -> float:
    s1 = set(q1.lower().split())
    s2 = set(q2.lower().split())
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


class ResponseLibrary:
    def __init__(self):
        self.model = None
        if SentenceTransformer:
            try:
                self.model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                self.model = None

    def _embed(self, text: str) -> Optional[List[float]]:
        if not self.model or not text:
            return None
        try:
            vec = self.model.encode(text)
            return [float(x) for x in vec.tolist()]  # type: ignore[attr-defined]
        except Exception:
            return None

    async def store_response(self, user: dict, question: str, answer: str, metadata: Dict[str, Any]) -> int:
        embedding = self._embed(question) or []
        embed_json = json.dumps(embedding)
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                """
                INSERT INTO response_library (user_id, team_id, question, answer, metadata, embedding)
                VALUES (:uid, :team_id, :q, :a, :m, :e)
                """,
                {
                    "uid": user["id"],
                    "team_id": user.get("team_id"),
                    "q": question,
                    "a": answer,
                    "m": json.dumps(metadata or {}),
                    "e": embed_json,
                },
            )
            row = await conn.exec_driver_sql("SELECT last_insert_rowid()")
            rid = row.scalar() or 0
        return rid

    async def find_similar(self, user: dict, question: str, threshold: float = 0.65) -> List[Dict[str, Any]]:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(
                """
                SELECT id, question, answer, metadata, embedding
                FROM response_library
                WHERE user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL)
                ORDER BY created_at DESC
                LIMIT 200
                """,
                {"uid": user["id"], "team_id": user.get("team_id")},
            )
            rows = [dict(r._mapping) for r in res.fetchall()]

        q_embed = self._embed(question)
        matches = []
        for row in rows:
            emb = []
            try:
                emb = json.loads(row.get("embedding") or "[]")
            except Exception:
                emb = []
            sim = _cosine(q_embed, emb) if q_embed and emb else _keyword_score(question, row.get("question") or "")
            if sim >= threshold:
                meta = {}
                try:
                    meta = json.loads(row.get("metadata") or "{}")
                except Exception:
                    meta = {}
                matches.append(
                    {
                        "id": row.get("id"),
                        "question": row.get("question"),
                        "answer": row.get("answer"),
                        "similarity": round(sim, 3),
                        "metadata": meta,
                    }
                )
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        return matches
