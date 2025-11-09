"""CLI helper to enrich opportunities with AI classifications."""

import json
import sqlite3
import sys
from pathlib import Path

# make "app" importable when running `python scripts/backfill_ai.py`
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.ai.classifier import classify_opportunity
from app.ai.extract_fields import extract_key_fields

DB_PATH = PROJECT_ROOT / "muni_local.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id,
               external_id,
               agency_name,
               title,
               description,
               full_text
        FROM opportunities
        WHERE ai_category IS NULL
           OR ai_fields_json IS NULL
    """)
    rows = cur.fetchall()

    print(f"Found {len(rows)} rows to enrich...")

    for r in rows:
        title = r["title"] or ""
        agency = r["agency_name"] or ""
        # prefer full_text if you have scraped PDFs/HTML there
        text_blob = r["full_text"] or r["description"] or title

        cat, conf = classify_opportunity(
            title=title,
            agency=agency,
            description=text_blob,
            llm_client=None,   # offline / no API for now
        )
        fields = extract_key_fields(text_blob, llm_client=None)

        cur.execute("""
            UPDATE opportunities
            SET
              ai_category = ?,
              ai_category_conf = ?,
              ai_fields_json = ?,
              ai_version = ?
            WHERE id = ?
        """, (
            cat,
            conf,
            json.dumps(fields),
            "v1.0",
            r["id"],
        ))

    conn.commit()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
