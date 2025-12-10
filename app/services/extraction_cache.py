import hashlib
import json
from typing import Optional, Dict, Any

from app.core.db_core import engine


class ExtractionCache:
    """
    Lightweight extraction cache keyed by a hash of the source text.
    Entries expire after 7 days (enforced in SQL query).
    """

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]

    async def get(self, text: str) -> Optional[Dict[str, Any]]:
        key = self._hash_text(text)
        async with engine.begin() as conn:
            try:
                res = await conn.exec_driver_sql(
                    "SELECT result FROM extraction_cache WHERE hash = :h AND created_at > datetime('now', '-7 days')",
                    {"h": key},
                )
                row = res.first()
            except Exception:
                row = None
        if not row:
            return None
        try:
            raw = row[0]
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return None

    async def set(self, text: str, result: Dict[str, Any]) -> None:
        key = self._hash_text(text)
        try:
            payload = json.dumps(result)
        except Exception:
            payload = "{}"
        async with engine.begin() as conn:
            try:
                await conn.exec_driver_sql(
                    """
                    INSERT INTO extraction_cache (hash, result, created_at)
                    VALUES (:h, :r, CURRENT_TIMESTAMP)
                    ON CONFLICT(hash) DO UPDATE SET result = :r, created_at = CURRENT_TIMESTAMP
                    """,
                    {"h": key, "r": payload},
                )
            except Exception:
                # Best-effort cache; ignore failures
                return
