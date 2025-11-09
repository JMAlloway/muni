from fastapi import APIRouter, Depends, Request
from app.core.scheduler import job_daily_digest
from app.ingest.runner import run_ingestors_once
from app.ingest.municipalities import city_columbus
from app.core.db_core import save_opportunities
from app.core.settings import settings
from app.auth.session import get_current_user_email
from fastapi import HTTPException, status

# paste this here if you didn't create deps_webadmin.py
async def require_web_admin(request: Request):
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    if email.strip().lower() != settings.ADMIN_EMAIL.strip().lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    return email

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/run-ingestors")
async def run_now(user=Depends(require_web_admin)):
    count = await run_ingestors_once()
    return {"ingested": count}

@router.post("/send-digest-now")
async def send_digest_now(user=Depends(require_web_admin)):
    await job_daily_digest()
    return {"status": "sent"}

@router.post("/run-columbus")
async def run_columbus(user=Depends(require_web_admin)):
    items = await city_columbus.fetch()
    written = await save_opportunities(items)
    return {
        "source": "city_columbus",
        "scraped": len(items),
        "processed": written,
    }
