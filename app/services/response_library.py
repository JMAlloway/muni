import json
import math
import asyncio
import logging
from typing import Any, Dict, List, Optional

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except ImportError:
    SentenceTransformer = None  # optional dependency

from app.core.db_core import engine

logger = logging.getLogger("response_library")

MAX_QUESTION_LEN = 2000
MAX_ANSWER_LEN = 6000
SEARCH_LIMIT = 200
TOP_RESULTS = 50

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
    """
    Lightweight response library with optional embedding support.
    Embeddings are best-effort; operations are bounded for safety.
    """

    def __init__(self):
        self.model = None
        self._model_loaded = False

    async def _ensure_model(self):
        if self._model_loaded:
            return self.model
        if not SentenceTransformer:
            return None
        try:
            self.model = await asyncio.to_thread(SentenceTransformer, "all-MiniLM-L6-v2")
            self._model_loaded = True
            return self.model
        except Exception as exc:
            logger.warning("response_library model load failed: %s", exc)
            self.model = None
            self._model_loaded = True
            return None

    async def _embed(self, text: str) -> Optional[List[float]]:
        if not text:
            return None
        model = await self._ensure_model()
        if not model:
            return None
        try:
            vec = await asyncio.to_thread(model.encode, text)
            return [float(x) for x in vec.tolist()]  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("response_library embed failed: %s", exc)
            return None

    async def store_response(self, user: dict, question: str, answer: str, metadata: Dict[str, Any]) -> int:
        question = (question or "")[:MAX_QUESTION_LEN]
        answer = (answer or "")[:MAX_ANSWER_LEN]
        embedding = await self._embed(question) or []
        embed_json = json.dumps(embedding)
        meta_json = json.dumps(metadata or {})
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
                    "m": meta_json,
                    "e": embed_json,
                },
            )
            row = await conn.exec_driver_sql("SELECT last_insert_rowid()")
            rid = row.scalar() or 0
        return rid

    async def find_similar(self, user: dict, question: str, threshold: float = 0.65) -> List[Dict[str, Any]]:
        question = (question or "")[:MAX_QUESTION_LEN]
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(
                """
                SELECT id, question, answer, metadata, embedding
                FROM response_library
                WHERE user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL)
                ORDER BY created_at DESC
                LIMIT :lim
                """,
                {"uid": user["id"], "team_id": user.get("team_id"), "lim": SEARCH_LIMIT},
            )
            rows = [dict(r._mapping) for r in res.fetchall()]

        q_embed = await self._embed(question)
        matches = []
        for row in rows:
            try:
                emb = json.loads(row.get("embedding") or "[]")
            except Exception:
                emb = []
            sim = _cosine(q_embed, emb) if q_embed and emb else _keyword_score(question, row.get("question") or "")
            if sim >= threshold:
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
        return matches[:TOP_RESULTS]
