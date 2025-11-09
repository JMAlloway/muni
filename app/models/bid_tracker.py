from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.domain.models import Base

class UserBidTracker(Base):
    __tablename__ = "user_bid_trackers"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    opportunity_id = Column(Integer, index=True, nullable=False)
    status = Column(String(24), default="prospecting")  # prospecting|deciding|drafting|submitted|won|lost
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('user_id', 'opportunity_id', name='uq_user_opportunity'),)

class UserUpload(Base):
    __tablename__ = "user_uploads"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    opportunity_id = Column(Integer, index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    mime = Column(String(128))
    size = Column(Integer)
    storage_key = Column(Text, nullable=False)  # S3 key or local path
    version = Column(Integer, default=1)
    source_note = Column(Text, default="user-upload")  # label for audit
    created_at = Column(DateTime, default=datetime.utcnow)
