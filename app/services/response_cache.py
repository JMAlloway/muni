"""
Cache for generated RFP response answers.
Prevents redundant API calls when regenerating identical sections.
"""
import hashlib
import json
import logging
from typing import Any, Dict, Optional

from app.core.db_core import engine

logger = logging.getLogger("response_cache")

# Cache TTL in days
CACHE_TTL_DAYS = 7


class ResponseCache:
    """Hash-based cache for generated RFP answers."""

    @staticmethod
    def _make_hash(question: str, context_summary: str) -> str:
        """Create a hash key from question + context."""
        content = f"{question}::{context_summary}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _summarize_context(context: Dict[str, Any]) -> str:
        """Create a stable summary of context for hashing."""
        # Include key factors that would change the answer
        parts = []

        # Company profile key fields
        profile = context.get("company_profile", {})
        if profile.get("legal_name"):
            parts.append(f"company:{profile['legal_name']}")

        # Win themes
        themes = context.get("win_themes", [])
        if themes:
            theme_ids = sorted([str(t.get("id", "")) for t in themes])
            parts.append(f"themes:{','.join(theme_ids)}")

        # Knowledge docs
        docs = context.get("knowledge_docs", [])
        if docs:
            doc_ids = sorted([str(d.get("id", "")) for d in docs])
            parts.append(f"docs:{','.join(doc_ids)}")

        # Custom instructions
        if context.get("custom_instructions"):
            parts.append(f"instructions:{context['custom_instructions'][:100]}")

        return "|".join(parts)

    async def get(self, question: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached answer if available."""
        try:
            context_summary = self._summarize_context(context)
            cache_hash = self._make_hash(question, context_summary)

            async with engine.begin() as conn:
                res = await conn.exec_driver_sql(
                    """
                    SELECT result FROM response_cache
                    WHERE hash = :hash
                      AND created_at > datetime('now', :ttl)
                    """,
                    {"hash": cache_hash, "ttl": f"-{CACHE_TTL_DAYS} days"},
                )
                row = res.first()
                if row and row[0]:
                    logger.info(f"Response cache hit for hash={cache_hash[:16]}")
                    return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception as e:
            logger.warning(f"Response cache get failed: {e}")
        return None

    async def set(self, question: str, context: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Cache a generated answer."""
        try:
            context_summary = self._summarize_context(context)
            cache_hash = self._make_hash(question, context_summary)
            result_json = json.dumps(result, ensure_ascii=False)

            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    """
                    INSERT OR REPLACE INTO response_cache (hash, result, created_at)
                    VALUES (:hash, :result, CURRENT_TIMESTAMP)
                    """,
                    {"hash": cache_hash, "result": result_json},
                )
                logger.info(f"Response cache set for hash={cache_hash[:16]}")
        except Exception as e:
            logger.warning(f"Response cache set failed: {e}")
