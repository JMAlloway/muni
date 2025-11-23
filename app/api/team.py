from typing import List, Optional
import re
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

import uuid
import datetime as dt
import asyncio
from app.auth.auth_utils import require_login
from app.auth.session import get_current_user_email
from app.core.db import AsyncSessionLocal
from app.core.settings import settings
from app.core.emailer import send_email

router = APIRouter(tags=["team"])

def _fmt_ts(val):
    if not val:
        return None
    try:
        return val.isoformat()
    except AttributeError:
        try:
            # if already a string, return as-is
            return str(val)
        except Exception:
            return None


def _ensure_premium_tier(tier: Optional[str], is_admin: bool = False):
    # Temporarily allow all tiers (admin or not) to use team features.
    return


@router.get("/api/team/members", response_class=JSONResponse)
async def list_team_members(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT id, team_id, tier, is_admin FROM users WHERE email = :email LIMIT 1"),
            {"email": user_email},
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id, team_id, tier, is_admin = row
        _ensure_premium_tier(tier, bool(is_admin))

        if not team_id:
            team_id = await _create_team(session, owner_id=user_id, name="Team")
            await session.execute(
                text("UPDATE users SET team_id = :team WHERE id = :uid"),
                {"team": team_id, "uid": user_id},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO team_members (id, team_id, user_id, invited_email, role, invited_at, accepted_at)
                    VALUES (:id, :team, :uid, :email, 'owner', :invited_at, :accepted_at)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "team": team_id,
                    "uid": user_id,
                    "email": user_email,
                    "invited_at": dt.datetime.utcnow(),
                    "accepted_at": dt.datetime.utcnow(),
                },
            )
            await session.commit()

        members = await session.execute(
            text(
                """
                SELECT
                    tm.id,
                    tm.invited_email,
                    tm.role,
                    tm.user_id,
                    tm.invited_at,
                    tm.accepted_at,
                    u.email AS user_email
                FROM team_members tm
                LEFT JOIN users u ON u.id = tm.user_id
                WHERE tm.team_id = :team
                """
            ),
            {"team": team_id},
        )
        data = []
        for m in members.fetchall():
            mid, invited_email, role, uid, invited_at, accepted_at, uemail = m
            data.append(
                {
                    "id": mid,
                    "invited_email": invited_email,
                    "role": role,
                    "user_id": uid,
                    "user_email": uemail,
                    "invited_at": _fmt_ts(invited_at),
                    "accepted_at": _fmt_ts(accepted_at),
                }
            )
    # end session
    return {"team_id": team_id, "members": data}


async def _create_team(session, owner_id: str, name: str) -> str:
    team_id = str(uuid.uuid4())
    await session.execute(
        text(
            """
            INSERT INTO teams (id, name, owner_user_id, created_at)
            VALUES (:id, :name, :owner, :created_at)
            """
        ),
        {"id": team_id, "name": name, "owner": owner_id, "created_at": dt.datetime.utcnow()},
    )
    return team_id


@router.post("/api/team/invite", response_class=JSONResponse)
async def invite_member(request: Request, payload: dict):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    invite_email = (payload.get("email") or "").strip().lower()
    if not invite_email or not re.match(r"[^@]+@[^@]+\.[^@]+", invite_email):
        raise HTTPException(status_code=400, detail="Valid email required")

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT id, team_id, tier, is_admin FROM users WHERE email = :email LIMIT 1"),
            {"email": user_email},
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id, team_id, tier, is_admin = row
        _ensure_premium_tier(tier, bool(is_admin))

        # ensure team exists
        if not team_id:
            team_id = await _create_team(session, owner_id=user_id, name="Team")
            await session.execute(
                text("UPDATE users SET team_id = :team WHERE id = :uid"),
                {"team": team_id, "uid": user_id},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO team_members (team_id, user_id, invited_email, role, accepted_at)
                    VALUES (:team, :uid, :email, 'owner', CURRENT_TIMESTAMP)
                    """
                ),
                {"team": team_id, "uid": user_id, "email": user_email},
            )

        # seat limit: owner + 2 more for professional; unlimited for enterprise
        seat_limit = 4 if (tier or "").lower() == "professional" else 50
        count_res = await session.execute(
            text("SELECT COUNT(*) FROM team_members WHERE team_id = :team"),
            {"team": team_id},
        )
        seat_count = count_res.scalar() or 0
        if seat_count >= seat_limit:
            raise HTTPException(status_code=403, detail="Seat limit reached for your plan.")

        await session.execute(
            text(
                """
                INSERT INTO team_members (id, team_id, invited_email, role, invited_at, accepted_at)
                VALUES (:id, :team, :email, 'member', :invited_at, NULL)
                ON CONFLICT(invited_email, team_id) DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "team": team_id,
                "email": invite_email,
                "invited_at": dt.datetime.utcnow(),
            },
        )
        await session.commit()

    # Send invite email (best-effort)
    try:
        base_url = "https://" + settings.PUBLIC_APP_HOST if settings.PUBLIC_APP_HOST else "http://localhost:8000"
        accept_url = f"{base_url}/team/accept"
        html_body = f"""
        <p>Hi,</p>
        <p><b>{user_email}</b> invited you to join their EasyRFP team.</p>
        <p>To accept, sign in with <b>{invite_email}</b> and click this link: <a href="{accept_url}">{accept_url}</a></p>
        <p>If you don't have an account yet, sign up with that email first, then click Accept.</p>
        """
        await asyncio.to_thread(send_email, invite_email, "EasyRFP team invite", html_body)
    except Exception:
        pass

    return {"ok": True, "team_id": team_id, "invited": invite_email}


@router.post("/api/team/accept", response_class=JSONResponse)
async def accept_invite(request: Request):
    """
    Call once the invited user signs in; it binds their user_id and email.
    """
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT id FROM users WHERE email = :email LIMIT 1"),
            {"email": user_email},
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = row[0]

        res = await session.execute(
            text(
                """
                SELECT team_id FROM team_members
                WHERE invited_email = :email
                ORDER BY invited_at DESC LIMIT 1
                """
            ),
            {"email": user_email},
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No pending invite")
        team_id = row[0]

        await session.execute(
            text(
                """
                UPDATE team_members
                SET user_id = :uid, accepted_at = CURRENT_TIMESTAMP
                WHERE team_id = :team AND invited_email = :email
                """
            ),
            {"team": team_id, "email": user_email, "uid": user_id},
        )
        await session.execute(
            text("UPDATE users SET team_id = :team WHERE id = :uid"),
            {"team": team_id, "uid": user_id},
        )
        await session.commit()

    return {"ok": True, "team_id": team_id}


@router.get("/api/team/notes", response_class=JSONResponse)
async def list_notes(request: Request, opportunity_id: str):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT team_id, tier, id, is_admin FROM users WHERE email = :email LIMIT 1"),
            {"email": user_email},
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        team_id, tier, user_id, is_admin = row
        _ensure_premium_tier(tier, bool(is_admin))
        if not team_id:
            return {"notes": []}

        res = await session.execute(
            text(
                """
                SELECT bn.id, bn.body, bn.mentions, bn.author_user_id, bn.created_at, u.email AS author_email
                FROM bid_notes bn
                LEFT JOIN users u ON u.id = bn.author_user_id
                WHERE bn.team_id = :team AND bn.opportunity_id = :oid
                ORDER BY bn.created_at ASC
                LIMIT 50
                """
            ),
            {"team": team_id, "oid": opportunity_id},
        )
        notes = []
        for n in res.fetchall():
            raw_mentions = n[2]
            try:
                parsed_mentions = json.loads(raw_mentions) if isinstance(raw_mentions, str) else (raw_mentions or [])
            except Exception:
                parsed_mentions = []
            notes.append(
                {
                    "id": n[0],
                    "body": n[1],
                    "mentions": parsed_mentions,
                    "author_user_id": n[3],
                    "created_at": _fmt_ts(n[4]),
                    "author_email": n[5],
                }
            )
    return {"notes": notes}


@router.post("/api/team/notes", response_class=JSONResponse)
async def add_note(request: Request, payload: dict):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = (payload.get("body") or "").strip()
    opportunity_id = payload.get("opportunity_id")
    if not body or not opportunity_id:
        raise HTTPException(status_code=400, detail="Body and opportunity_id required")

    mentions = [m.lower() for m in re.findall(r"@([a-zA-Z0-9._-]+)", body)]

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT id, team_id, tier, is_admin FROM users WHERE email = :email LIMIT 1"),
            {"email": user_email},
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id, team_id, tier, is_admin = row
        _ensure_premium_tier(tier, bool(is_admin))
        if not team_id:
            raise HTTPException(status_code=403, detail="No team assigned")

        final_mentions: List[str] = []
        if mentions:
            res = await session.execute(
                text(
                    """
                    SELECT COALESCE(u.email, tm.invited_email) AS handle
                    FROM team_members tm
                    LEFT JOIN users u ON u.id = tm.user_id
                    WHERE tm.team_id = :team
                    """
                ),
                {"team": team_id},
            )
            handles = {h[0].split("@")[0].lower(): h[0] for h in res.fetchall() if h[0]}
            for m in mentions:
                if m in handles:
                    final_mentions.append(handles[m])

        await session.execute(
            text(
                """
                INSERT INTO bid_notes (id, team_id, opportunity_id, author_user_id, body, mentions, created_at)
                VALUES (:id, :team, :oid, :author, :body, :mentions, :created_at)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "team": team_id,
                "oid": opportunity_id,
                "author": user_id,
                "body": body,
                "mentions": json.dumps(final_mentions),
                "created_at": dt.datetime.utcnow(),
            },
        )
        await session.commit()

    return {"ok": True}
