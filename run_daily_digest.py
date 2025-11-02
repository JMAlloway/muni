# run_daily_digest.py
import asyncio
from app.scheduler import job_daily_digest

if __name__ == "__main__":
    asyncio.run(job_daily_digest())
