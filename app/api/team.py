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
from app.storage import create_presigned_get
from app.core.emailer import send_email
from app.api.notifications import create_notification, send_team_notification

router = APIRouter(tags=["team"])
ALLOWED_ROLES = {"owner", "manager", "member", "viewer"}

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


async def _current_role(session, team_id: str, user_id: str) -> str:
    role_res = await session.execute(
        text("SELECT role FROM team_members WHERE team_id = :team AND user_id = :uid LIMIT 1"),
        {"team": team_id, "uid": user_id},
    )
    return (role_res.scalar() or "").lower()


def _can_invite(role: str, is_admin: bool) -> bool:
    if is_admin:
        return True
    return role in {"owner", "manager"}


def _can_remove(role: str, target_role: str, is_admin: bool) -> bool:
    if is_admin:
        return True
    if role == "owner":
        return True
    if role == "manager" and target_role not in {"owner", "manager"}:
        return True
    return False


async def _ensure_team_feature_access(session, user_email: str):
    """
    Require that the team owner is Professional/Enterprise (or the user is platform admin).
    Returns (user_id, team_id).
    """
    res = await session.execute(
        text("SELECT id, team_id, tier, is_admin FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
        {"email": user_email},
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    user_id, team_id, tier, is_admin = row

    # Admin override
    if bool(is_admin):
        return user_id, team_id

    allowed_tiers = {"professional", "enterprise"}
    # If the user is the owner (team_id), look up owner tier; otherwise, use the owner tier of their team.
    owner_tier = (tier or "").strip().lower()
    if team_id:
        owner_res = await session.execute(
            text(
                """
                SELECT COALESCE(u.tier, u.Tier) AS owner_tier
                FROM teams t
                LEFT JOIN users u ON u.id = t.owner_user_id
                WHERE t.id = :team
                LIMIT 1
                """
            ),
            {"team": team_id},
        )
        o_row = owner_res.fetchone()
        if o_row and o_row[0]:
            owner_tier = (o_row[0] or "").strip().lower()

    if owner_tier not in allowed_tiers:
        raise HTTPException(status_code=403, detail="Team features require a Professional or Enterprise owner.")

    return user_id, team_id


@router.get("/api/team/members", response_class=JSONResponse)
async def list_team_members(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncSessionLocal() as session:
        user_id, team_id = await _ensure_team_feature_access(session, user_email)

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
    invite_role = (payload.get("role") or "member").strip().lower()
    if invite_role not in ALLOWED_ROLES:
        invite_role = "member"
    if invite_role == "owner":
        raise HTTPException(status_code=400, detail="Cannot invite a new owner")
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
        role = None
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
            role = "owner"

        if not role:
            role = await _current_role(session, team_id, user_id)
        if not _can_invite(role, bool(is_admin)):
            raise HTTPException(status_code=403, detail="Only owners or managers can invite members.")
        if role == "manager" and invite_role in {"owner", "manager"}:
            raise HTTPException(status_code=403, detail="Managers can only invite members or viewers.")

        # seat limit: owner + 2 more for professional; unlimited for enterprise
        owner_tier_val = None
        if team_id:
            owner_tier_res = await session.execute(
                text(
                    """
                    SELECT COALESCE(u.tier, u.Tier) FROM teams t
                    LEFT JOIN users u ON u.id = t.owner_user_id
                    WHERE t.id = :team LIMIT 1
                    """
                ),
                {"team": team_id},
            )
            owner_tier_val = (owner_tier_res.scalar() or "").lower()
        seat_limit = 4 if owner_tier_val == "professional" else 50
        count_res = await session.execute(
            text("SELECT COUNT(*) FROM team_members WHERE team_id = :team"),
            {"team": team_id},
        )
        seat_count = count_res.scalar() or 0
        if seat_count >= seat_limit:
            raise HTTPException(status_code=403, detail="Seat limit reached for your plan.")

        invited_user_id = None
        invited_user_res = await session.execute(
            text("SELECT id FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
            {"email": invite_email},
        )
        invited_user_row = invited_user_res.fetchone()
        if invited_user_row:
            invited_user_id = invited_user_row[0]

        team_name = "Team"
        try:
            tname_res = await session.execute(
                text("SELECT name FROM teams WHERE id = :team LIMIT 1"), {"team": team_id}
            )
            tname_row = tname_res.fetchone()
            if tname_row and tname_row[0]:
                team_name = tname_row[0]
        except Exception:
            team_name = "Team"

        await session.execute(
            text(
                """
                INSERT INTO team_members (id, team_id, invited_email, role, invited_at, accepted_at)
                VALUES (:id, :team, :email, :role, :invited_at, NULL)
                ON CONFLICT(invited_email, team_id) DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "team": team_id,
                "email": invite_email,
                "role": invite_role,
                "invited_at": dt.datetime.utcnow(),
            },
        )

        # If the invited person already has an account, create an in-app notification.
        if invited_user_id:
            try:
                await create_notification(
                    session,
                    recipient_user_id=invited_user_id,
                    notif_type="team_invite",
                    title="Team invitation",
                    body=f"{user_email} invited you to join {team_name}",
                    metadata={"team_id": team_id, "inviter_email": user_email},
                )
            except Exception:
                pass

        await session.commit()

    # Send invite email (best-effort)
    try:
        base_url = "https://" + settings.PUBLIC_APP_HOST if settings.PUBLIC_APP_HOST else "http://localhost:8000"
        accept_url = f"{base_url}/team/accept?email={invite_email}"
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

        # Look for a pending invite matching this email (case-insensitive)
        res = await session.execute(
            text(
                """
                SELECT team_id FROM team_members
                WHERE lower(invited_email) = lower(:email) AND accepted_at IS NULL
                ORDER BY invited_at DESC LIMIT 1
                """
            ),
            {"email": user_email},
        )
        row = res.fetchone()
        if not row:
            # If no pending invite, see if the user already has a membership record; if so, ensure linkage.
            fallback = await session.execute(
                text(
                    """
                    SELECT team_id FROM team_members
                    WHERE user_id = :uid OR lower(invited_email) = lower(:email)
                    ORDER BY accepted_at DESC NULLS LAST, invited_at DESC
                    LIMIT 1
                    """
                ),
                {"uid": user_id, "email": user_email},
            )
            frow = fallback.fetchone()
            if not frow:
                raise HTTPException(status_code=404, detail="No pending invite")
            team_id = frow[0]
        else:
            team_id = row[0]

        await session.execute(
            text(
                """
                UPDATE team_members
                SET user_id = :uid, accepted_at = CURRENT_TIMESTAMP
                WHERE team_id = :team AND lower(invited_email) = lower(:email)
                """
            ),
            {"team": team_id, "email": user_email, "uid": user_id},
        )
        await session.execute(
            text("UPDATE users SET team_id = :team WHERE id = :uid"),
            {"team": team_id, "uid": user_id},
        )
        # Clean up other pending invites for this email (only keep the accepted one)
        await session.execute(
            text(
                """
                DELETE FROM team_members
                WHERE invited_email = :email AND accepted_at IS NULL AND team_id != :team
                """
            ),
            {"email": user_email, "team": team_id},
        )
        await session.commit()

    return {"ok": True, "team_id": team_id}


@router.post("/api/team/members/{member_id}/remove", response_class=JSONResponse)
async def remove_member(request: Request, member_id: str):
    """
    Remove a pending invite or accepted member from the current team.
    Only the team owner/manager (or platform admin) can perform this action.
    """
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncSessionLocal() as session:
        # Identify caller + role
        user_res = await session.execute(
            text("SELECT id, team_id, is_admin FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
            {"email": user_email},
        )
        user_row = user_res.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id, team_id, is_admin = user_row
        if not team_id:
            raise HTTPException(status_code=403, detail="No team assigned")

        caller_role = await _current_role(session, team_id, user_id)

        # Load target member
        target_res = await session.execute(
            text(
                """
                SELECT id, team_id, user_id, invited_email, role
                FROM team_members
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": member_id},
        )
        target = target_res.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")

        _, target_team_id, target_user_id, target_email, target_role = target
        if target_team_id != team_id:
            raise HTTPException(status_code=403, detail="Cannot modify another team")
        if (target_role or "").lower() == "owner":
            raise HTTPException(status_code=400, detail="Cannot remove the team owner.")
        if target_user_id == user_id and not bool(is_admin):
            raise HTTPException(status_code=400, detail="You cannot remove yourself.")
        if not _can_remove(caller_role, (target_role or "").lower(), bool(is_admin)):
            raise HTTPException(status_code=403, detail="Insufficient role to remove this member.")

        await session.execute(text("DELETE FROM team_members WHERE id = :id"), {"id": member_id})
        if target_user_id:
            await session.execute(
                text("UPDATE users SET team_id = NULL WHERE id = :uid AND team_id = :team"),
                {"uid": target_user_id, "team": team_id},
            )
        await session.commit()

    return {"ok": True, "removed": target_email or target_user_id}


@router.post("/api/team/members/{member_id}/role", response_class=JSONResponse)
async def update_member_role(request: Request, member_id: str, payload: dict):
    """
    Update a member's role. Owner or platform admin only.
    Cannot change the owner; manager cannot promote/demote.
    """
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    new_role = (payload.get("role") or "").strip().lower()
    if new_role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if new_role == "owner":
        raise HTTPException(status_code=400, detail="Cannot promote via API")

    async with AsyncSessionLocal() as session:
        user_res = await session.execute(
            text("SELECT id, team_id, is_admin FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
            {"email": user_email},
        )
        user_row = user_res.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id, team_id, is_admin = user_row
        if not team_id:
            raise HTTPException(status_code=403, detail="No team assigned")

        caller_role = await _current_role(session, team_id, user_id)
        if caller_role != "owner" and not bool(is_admin):
            raise HTTPException(status_code=403, detail="Only the team owner can change roles.")

        target_res = await session.execute(
            text(
                """
                SELECT id, team_id, user_id, invited_email, role
                FROM team_members
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": member_id},
        )
        target = target_res.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")

        _, target_team_id, target_user_id, target_email, target_role = target
        if target_team_id != team_id:
            raise HTTPException(status_code=403, detail="Cannot modify another team")
        if (target_role or "").lower() == "owner":
            raise HTTPException(status_code=400, detail="Cannot change owner role.")

        await session.execute(
            text("UPDATE team_members SET role = :role WHERE id = :id"),
            {"role": new_role, "id": member_id},
        )
        await session.commit()

    return {"ok": True, "role": new_role}


@router.get("/api/team/notes", response_class=JSONResponse)
async def list_notes(request: Request, opportunity_id: str):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncSessionLocal() as session:
        user_id, team_id = await _ensure_team_feature_access(session, user_email)
        if not team_id:
            return {"notes": []}

        res = await session.execute(
            text(
                """
                SELECT bn.id, bn.body, bn.mentions, bn.author_user_id, bn.created_at, u.email AS author_email, u.avatar_key
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
                    "avatar_url": create_presigned_get(n[6]) if n[6] else None,
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
        user_id, team_id = await _ensure_team_feature_access(session, user_email)
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
        # notify team about note
        note_title = "New bid note"
        note_body = f"{user_email} added a note on opportunity {opportunity_id}"
        try:
            await send_team_notification(
                session,
                team_id=team_id,
                exclude_user_id=user_id,
                notif_type="bid_note",
                title=note_title,
                body=note_body,
                metadata={"opportunity_id": opportunity_id},
            )
        except Exception:
            pass
        await session.commit()

    return {"ok": True}
