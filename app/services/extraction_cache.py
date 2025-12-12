import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from app.core.db_core import engine

logger = logging.getLogger("extraction_cache")

_CACHE_TTL_DAYS = 7
_MAX_TEXT_BYTES = 10_000_000  # 10 MB guard
_HASH_THREAD_THRESHOLD = 100_000  # async offload threshold (~100 KB)
_MAX_RESULT_BYTES = 1_000_000  # 1 MB per entry


class ExtractionCache:
    """
    Lightweight extraction cache keyed by a hash of the source text.
    Entries expire after _CACHE_TTL_DAYS.
    """

    @staticmethod
    def _hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _prepare_text(text: Any) -> bytes:
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        encoded = text.encode("utf-8", errors="ignore")
        if len(encoded) > _MAX_TEXT_BYTES:
            raise ValueError(f"text exceeds {_MAX_TEXT_BYTES} bytes")
        return encoded

    async def _hash_text(self, text: str) -> str:
        data = self._prepare_text(text)
        if len(data) > _HASH_THREAD_THRESHOLD:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._hash_bytes, data)
        return self._hash_bytes(data)

    async def get(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Return cached extraction payload for the text if present and not expired.
        """
        try:
            key = await self._hash_text(text)
        except ValueError as exc:
            logger.warning("extraction_cache.get rejected input: %s", exc)
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=_CACHE_TTL_DAYS)
        try:
            async with engine.begin() as conn:
                res = await conn.exec_driver_sql(
                    "SELECT result FROM extraction_cache WHERE hash = :h AND created_at >= :cutoff",
                    {"h": key, "cutoff": cutoff},
                )
                row = res.first()
        except Exception as exc:
            logger.warning("extraction_cache.get failed: %s", exc)
            return None

        if not row:
            return None

        raw = row[0]
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")

        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                logger.warning("extraction_cache.get decode error: %s", exc)
                return None
        elif isinstance(raw, dict):
            payload = raw
        else:
            logger.warning("extraction_cache.get unexpected payload type: %s", type(raw))
            return None

        return payload if isinstance(payload, dict) else None

    async def set(self, text: str, result: Dict[str, Any]) -> None:
        """
        Store extraction payload keyed by hashed text; best-effort cache.
        """
        if not isinstance(result, dict):
            logger.warning("extraction_cache.set rejected result type: %s", type(result))
            return

        try:
            key = await self._hash_text(text)
        except ValueError as exc:
            logger.warning("extraction_cache.set rejected input: %s", exc)
            return

        try:
            payload = json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            logger.warning("extraction_cache.set serialization failed: %s", exc)
            return

        if len(payload.encode("utf-8")) > _MAX_RESULT_BYTES:
            logger.warning("extraction_cache.set payload too large: %s bytes", len(payload.encode("utf-8")))
            return

        params = {"h": key, "r": payload}
        backend = engine.url.get_backend_name()
        if backend.startswith("mysql"):
            stmt = """
                INSERT INTO extraction_cache (hash, result, created_at)
                VALUES (:h, :r, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE result = VALUES(result), created_at = CURRENT_TIMESTAMP
            """
        else:
            # Works for SQLite/PostgreSQL
            stmt = """
                INSERT INTO extraction_cache (hash, result, created_at)
                VALUES (:h, :r, CURRENT_TIMESTAMP)
                ON CONFLICT(hash) DO UPDATE SET result = :r, created_at = CURRENT_TIMESTAMP
            """

        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(stmt, params)
        except Exception as exc:
            logger.warning("extraction_cache.set failed: %s", exc)
