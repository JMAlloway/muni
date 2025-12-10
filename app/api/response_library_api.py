from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_helpers import ensure_user_can_access_opportunity, require_user_with_team
from app.services.response_library import ResponseLibrary

router = APIRouter(prefix="/api/response-library", tags=["response-library"])

lib = ResponseLibrary()


@router.get("/search")
async def search(question: str, threshold: float = 0.65, user=Depends(require_user_with_team)):
    matches = await lib.find_similar(user, question, threshold)
    return {"results": matches}


@router.post("/store")
async def store(payload: dict, user=Depends(require_user_with_team)):
    question = (payload or {}).get("question", "")
    answer = (payload or {}).get("answer", "")
    metadata = (payload or {}).get("metadata", {}) or {}
    if not question or not answer:
        raise HTTPException(status_code=400, detail="question and answer are required")
    rid = await lib.store_response(user, question, answer, metadata)
    return {"id": rid}
