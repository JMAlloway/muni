"""Kick off the daily email digest job manually."""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.core.scheduler import job_daily_digest

if __name__ == "__main__":
    asyncio.run(job_daily_digest())
