from pydantic import BaseModel, EmailStr
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: EmailStr
    is_admin: bool

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PreferenceIn(BaseModel):
    counties: list[str] = []
    categories: list[str] = []
    keywords: list[str] = []
    cadence: str = "daily"

class PreferenceOut(PreferenceIn):
    id: str

class OpportunityOut(BaseModel):
    id: str
    source: str
    source_url: str
    title: str
    summary: str | None = None
    category: str | None = None
    agency_name: str | None = None
    location_geo: str | None = None
    posted_date: datetime | None = None
    due_date: datetime | None = None
    prebid_date: datetime | None = None
    status: str
