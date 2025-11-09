from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from app.auth.session import SESSION_COOKIE_NAME, parse_session_token, create_session_token, get_current_user_email

router = APIRouter(prefix="/debug", tags=["debug"])

@router.get("/echo", response_class=PlainTextResponse)
def echo(request: Request):
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    parsed = parse_session_token(raw)
    who = get_current_user_email(request)
    return "\n".join([
        f"Host: {request.headers.get('host')}",
        f"Cookie header present: {bool(request.headers.get('cookie'))}",
        f"{SESSION_COOKIE_NAME} present: {bool(raw)}",
        f"parsed_email: {parsed}",
        f"helper_email: {who}",
    ])

@router.get("/set")
def set_cookie_simple():
    token = create_session_token("admin@example.com")
    resp = RedirectResponse("/debug/echo", status_code=303)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,     # True in prod HTTPS
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    return resp

@router.get("/clear")
def clear_cookie():
    resp = RedirectResponse("/debug/echo", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return resp
