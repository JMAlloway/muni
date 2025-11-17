from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Iterable, List, Set, Tuple

from sqlalchemy import text

from app.core.db_core import engine
from app.onboarding.interests import get_interest_profile

OPEN_STATUS_CLAUSE = "(status IS NULL OR TRIM(LOWER(status)) LIKE 'open%')"


async def fetch_landing_snapshot(
    sample_limit: int = 3,
) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    """Return headline stats + a few sample opportunities for marketing."""
    now = dt.datetime.utcnow()
    soon = now + dt.timedelta(days=7)
    recent = now - dt.timedelta(days=1)

    async with engine.begin() as conn:
        stats_res = await conn.exec_driver_sql(
            """
            SELECT
                COUNT(*) AS total_open,
                SUM(
                    CASE
                        WHEN due_date IS NOT NULL
                             AND due_date <= :soon
                             AND (status IS NULL OR TRIM(LOWER(status)) LIKE 'open%')
                        THEN 1 ELSE 0
                    END
                ) AS closing_soon,
                SUM(
                    CASE
                        WHEN date_added IS NOT NULL
                             AND date_added >= :recent
                        THEN 1 ELSE 0
                    END
                ) AS added_recent
            FROM opportunities
            WHERE status IS NULL OR TRIM(LOWER(status)) LIKE 'open%'
            """,
            {"soon": soon, "recent": recent},
        )
        stats_row = stats_res.first()
        stats = {
            "total_open": int(stats_row[0] or 0),
            "closing_soon": int(stats_row[1] or 0),
            "added_recent": int(stats_row[2] or 0),
        }

        preview_res = await conn.exec_driver_sql(
            """
            SELECT
                id,
                external_id,
                title,
                agency_name,
                due_date,
                COALESCE(ai_category, category) AS category,
                ai_summary,
                summary
            FROM opportunities
            WHERE status IS NULL OR TRIM(LOWER(status)) LIKE 'open%'
            ORDER BY (due_date IS NULL) ASC, due_date ASC, date_added DESC
            LIMIT :limit
            """,
            {"limit": sample_limit},
        )
        preview = [dict(row._mapping) for row in preview_res.fetchall()]

    return stats, preview


async def fetch_interest_feed(
    interest_key: str,
    limit: int = 7,
    agencies: Iterable[str] | None = None,
) -> List[Dict[str, Any]]:
    """Return personalized opportunities for the welcome dashboard."""
    profile = get_interest_profile(interest_key)
    categories = profile["categories"]
    rows = await _query_opportunities(
        limit=limit,
        categories=categories,
        agencies=agencies,
    )

    if len(rows) < limit and profile["tags"]:
        exclude_ids = {row["id"] for row in rows if row.get("id")}
        fallback = await _query_opportunities_by_tags(
            limit=limit - len(rows),
            tags=profile["tags"],
            exclude_ids=exclude_ids,
        )
        rows.extend(fallback)

    return rows


async def get_top_agencies(limit: int = 6) -> List[Dict[str, Any]]:
    """Return agencies with the most open opportunities."""
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT agency_name, COUNT(*) AS total
            FROM opportunities
            WHERE agency_name IS NOT NULL AND agency_name != ''
            GROUP BY agency_name
            ORDER BY total DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
        rows = res.fetchall()
    return [
        {"agency": row[0], "count": int(row[1] or 0)}
        for row in rows
        if row[0]
    ]


async def _query_opportunities(
    *,
    limit: int,
    categories: Iterable[str] | None = None,
    agencies: Iterable[str] | None = None,
    exclude_ids: Set[str] | None = None,
) -> List[Dict[str, Any]]:
    filters = [OPEN_STATUS_CLAUSE]
    params: Dict[str, Any] = {"limit": limit}

    if categories:
        clauses, cat_params = _build_in_clause(
            "LOWER(COALESCE(ai_category, category))",
            (c.lower() for c in categories),
            prefix="cat",
        )
        if clauses:
            filters.append(clauses)
            params.update(cat_params)

    if agencies:
        clauses, agency_params = _build_in_clause(
            "LOWER(agency_name)",
            (a.lower() for a in agencies),
            prefix="agency",
        )
        if clauses:
            filters.append(clauses)
            params.update(agency_params)

    if exclude_ids:
        placeholders = []
        for idx, value in enumerate(exclude_ids):
            key = f"exclude_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        if placeholders:
            filters.append(f"id NOT IN ({', '.join(placeholders)})")

    where_sql = " AND ".join(f"({clause})" for clause in filters)

    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            f"""
            SELECT
                id,
                external_id,
                title,
                agency_name,
                COALESCE(ai_category, category) AS category,
                due_date,
                ai_summary,
                summary,
                source_url
            FROM opportunities
            WHERE {where_sql}
            ORDER BY (due_date IS NULL) ASC, due_date ASC, date_added DESC
            LIMIT :limit
            """,
            params,
        )
        rows = res.fetchall()

    return [dict(row._mapping) for row in rows]


async def _query_opportunities_by_tags(
    *,
    limit: int,
    tags: Iterable[str],
    exclude_ids: Set[str] | None = None,
) -> List[Dict[str, Any]]:
    tag_clauses = []
    params: Dict[str, Any] = {"limit": limit}
    tags_clean = [t.strip().lower() for t in tags if t.strip()]
    for idx, tag in enumerate(tags_clean):
        key = f"tag_{idx}"
        params[key] = f"%{tag}%"
        tag_clauses.append(f"LOWER(COALESCE(ai_tags_json, '')) LIKE :{key}")

    if not tag_clauses:
        return []

    filters = [OPEN_STATUS_CLAUSE]
    filters.append("(" + " OR ".join(tag_clauses) + ")")

    if exclude_ids:
        placeholders = []
        for idx, value in enumerate(exclude_ids):
            key = f"tag_exclude_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        if placeholders:
            filters.append(f"id NOT IN ({', '.join(placeholders)})")

    where_sql = " AND ".join(f"({clause})" for clause in filters)

    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            f"""
            SELECT
                id,
                external_id,
                title,
                agency_name,
                COALESCE(ai_category, category) AS category,
                due_date,
                ai_summary,
                summary,
                source_url
            FROM opportunities
            WHERE {where_sql}
            ORDER BY (due_date IS NULL) ASC, due_date ASC, date_added DESC
            LIMIT :limit
            """,
            params,
        )
        rows = res.fetchall()

    return [dict(row._mapping) for row in rows]


def _build_in_clause(
    column: str, values: Iterable[str], *, prefix: str
) -> Tuple[str, Dict[str, Any]]:
    vals = [v for v in values if v]
    if not vals:
        return "", {}
    placeholders = []
    params: Dict[str, Any] = {}
    for idx, value in enumerate(vals):
        key = f"{prefix}_{idx}"
        placeholders.append(f":{key}")
        params[key] = value
    clause = f"{column} IN ({', '.join(placeholders)})"
    return clause, params
