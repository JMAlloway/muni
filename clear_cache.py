#!/usr/bin/env python
"""Quick script to clear extraction cache. Run with: python clear_cache.py"""
import os
import psycopg2

db_url = os.getenv("DATABASE_URL", "")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if not db_url:
    print("ERROR: DATABASE_URL not set")
    exit(1)

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("DELETE FROM extraction_cache")
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    print(f"✓ Cleared {deleted} cached extractions")
except Exception as e:
    print(f"ERROR: {e}")