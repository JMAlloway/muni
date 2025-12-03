"""
Database models for RFP Response Module

This schema handles the complete RFP response workflow:
1. Users create responses to opportunities they're tracking
2. AI extracts questions from RFPs
3. AI matches questions to templates
4. AI generates draft responses using company content library
5. Users edit and collaborate on responses
6. System tracks outcomes for AI training
"""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Boolean, TIMESTAMP, JSON, Float, Integer, ForeignKey
import uuid
import datetime as dt

# Use existing Base from domain models
from app.domain.models import Base


# ============================================================================
# CONTENT LIBRARY - Company's reusable content (past projects, certs, etc.)
# ============================================================================

class CompanyContentLibrary(Base):
    """
    Stores reusable company content for populating RFP responses.

    Example: COTA project from Acme Infrastructure
    - content_type: "past_project"
    - title: "COTA Cleveland Avenue BRT Shelters - Phase 1"
    - data: {project details, contact info, lessons learned}

    This is the "training data" that makes AI responses specific and credible.
    """
    __tablename__ = "company_content_library"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, index=True)  # Owner
    team_id: Mapped[str | None] = mapped_column(String, index=True)  # Team-shared content

    # Content classification
    content_type: Mapped[str] = mapped_column(String, index=True)
    # Types: "past_project", "certification", "insurance", "key_personnel",
    #        "safety_record", "equipment_list", "reference", "capability_statement"

    # Metadata
    title: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)  # ["cota", "brt", "shelters", "transit"]

    # Structured data (varies by content_type)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    """
    Example for past_project:
    {
        "project_name": "COTA Cleveland Avenue BRT Shelters - Phase 1",
        "client": "Central Ohio Transit Authority",
        "client_contact": {
            "name": "Jane Wilson",
            "title": "Capital Projects Manager",
            "phone": "(614) 555-0100",
            "email": "jwilson@cota.com"
        },
        "contract_value": 1800000,
        "completion_date": "2023-08-15",
        "scope": [
            "Installed 18 enhanced bus shelters with real-time displays",
            "Constructed ADA-compliant concrete pads (12' x 60')",
            "Installed LED pedestrian lighting"
        ],
        "achievements": [
            "Maintained 99.8% on-time bus service during construction",
            "Zero service disruptions",
            "Completed 2 weeks ahead of schedule"
        ],
        "categories": ["Transit", "BRT", "TSI"],
        "performance_metrics": {
            "on_time": true,
            "on_budget": true,
            "change_orders": 2,
            "change_order_value": 45000,
            "dbe_participation": 0.218,
            "safety_incidents": 0
        }
    }

    Example for certification:
    {
        "cert_name": "ODOT Prequalification",
        "cert_number": "R, D, T, 1",
        "work_types": ["Roadway", "Concrete", "Traffic", "Bridges"],
        "issue_date": "2023-01-01",
        "expiry_date": "2025-12-31",
        "document_url": "s3://bucket/odot_prequalification.pdf"
    }

    Example for key_personnel:
    {
        "name": "Robert Anderson",
        "title": "Project Manager",
        "years_experience": 12,
        "education": "BS Civil Engineering, Ohio State University",
        "certifications": ["PE Ohio #67890", "PMP", "OSHA 30-hour"],
        "relevant_projects": ["proj_001", "proj_002"],
        "bio": "Robert has managed 8 COTA projects totaling $12M..."
    }
    """

    # Attachments (PDFs, images, etc.)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    # [{"name": "ODOT_Cert.pdf", "url": "s3://...", "size": 1024}]

    # Searchability
    searchable_text: Mapped[str] = mapped_column(Text)  # Full-text search index
    keywords: Mapped[list] = mapped_column(JSON, default=list)  # For AI matching

    # Usage tracking
    use_count: Mapped[int] = mapped_column(Integer, default=0)  # How many times used in responses
    last_used: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Quality signals for AI
    wins_when_used: Mapped[int] = mapped_column(Integer, default=0)  # Track if this content leads to wins
    total_uses: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float | None] = mapped_column(Float)  # Calculated: wins_when_used / total_uses

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)


# ============================================================================
# TEMPLATES - Pre-built response templates (the "training data")
# ============================================================================

class ResponseTemplate(Base):
    """
    Reusable response templates built from successful past responses.

    Example: COTA Transit Infrastructure Experience template
    - Trained on 15 successful COTA bids from 2019-2024
    - Win rate: 67%
    - Contains proven structure and language that works for COTA

    Templates are the SECRET SAUCE - they encode what actually wins.
    """
    __tablename__ = "response_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Ownership
    user_id: Mapped[str | None] = mapped_column(String, index=True)  # NULL = system template
    team_id: Mapped[str | None] = mapped_column(String, index=True)  # Team-shared templates
    is_system_template: Mapped[bool] = mapped_column(Boolean, default=False)  # Pre-built by us

    # Template metadata
    title: Mapped[str] = mapped_column(String, index=True)
    # e.g., "Transit Infrastructure Experience - COTA/Transit Agencies"

    category: Mapped[str] = mapped_column(String, index=True)
    # e.g., "experience", "safety", "schedule", "dbe", "qualifications"

    subcategory: Mapped[str | None] = mapped_column(String)
    # e.g., "transit_experience", "safety_transit", "dbe_participation"

    description: Mapped[str | None] = mapped_column(Text)
    # Human-readable explanation of what this template is for

    # Matching criteria
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    # ["transit", "bus shelter", "active service", "cota", "brt"]

    question_patterns: Mapped[list] = mapped_column(JSON, default=list)
    # Regex patterns for matching questions: ["describe.*transit.*experience", "bus shelter.*installation"]

    agency_specific: Mapped[str | None] = mapped_column(String, index=True)
    # "COTA", "City of Columbus", "Franklin County", NULL (generic)

    # Template content
    content: Mapped[str] = mapped_column(Text)
    """
    The actual template text with placeholders.

    Example:
    [COMPANY NAME] has extensive experience delivering transit infrastructure projects
    for COTA and other Central Ohio transit agencies...

    RELEVANT TRANSIT PROJECTS:
    [INSERT PAST PROJECTS WITH tags:transit,cota]

    KEY CAPABILITIES DEMONSTRATED:
    ✓ Work within active transit service areas without disruption
    ...
    """

    variables: Mapped[dict] = mapped_column(JSON, default=dict)
    """
    Defines what data to pull from content library:
    {
        "company_name": "company_profile.name",
        "projects": {
            "source": "past_projects",
            "filter": {"tags": ["transit", "cota"]},
            "limit": 3
        },
        "certifications": {
            "source": "certifications",
            "filter": {"cert_name": "ODOT Prequalification"}
        }
    }
    """

    # Attachments that should accompany this response
    required_attachments: Mapped[list] = mapped_column(JSON, default=list)
    # ["company_overview", "safety_record", "past_project_photos"]

    # Performance tracking (THE GOLD - this is what makes templates valuable)
    trained_on: Mapped[str | None] = mapped_column(String)
    # "15 successful COTA bids from 2019-2024"

    win_rate: Mapped[float | None] = mapped_column(Float)
    # 0.67 = 67% of responses using this template won the bid

    use_count: Mapped[int] = mapped_column(Integer, default=0)
    wins_count: Mapped[int] = mapped_column(Integer, default=0)
    losses_count: Mapped[int] = mapped_column(Integer, default=0)

    avg_score: Mapped[float | None] = mapped_column(Float)
    # Average evaluation score from RFP reviewers (if known)

    avg_user_rating: Mapped[float | None] = mapped_column(Float)
    # User satisfaction: 1-5 stars

    # Version control
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_version_id: Mapped[str | None] = mapped_column(String)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)  # Highlight in UI

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    last_used: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


# ============================================================================
# RFP RESPONSES - User's response to a specific opportunity
# ============================================================================

class RFPResponse(Base):
    """
    A user's response to a specific opportunity.

    Example: Response to COTA TSI RFP 2024-TSI-08
    - Links to opportunity_id (from existing opportunities table)
    - Contains multiple sections (executive summary, qualifications, etc.)
    - Tracks compliance with RFP requirements
    - Records win/loss outcome for AI training
    """
    __tablename__ = "rfp_responses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Links to existing opportunity
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    # References opportunities.id (existing table)

    # Ownership
    user_id: Mapped[str] = mapped_column(String, index=True)
    team_id: Mapped[str | None] = mapped_column(String, index=True)

    # Response metadata
    title: Mapped[str] = mapped_column(String)
    # e.g., "Response to COTA TSI - Cleveland Avenue BRT"

    rfp_number: Mapped[str | None] = mapped_column(String)
    # e.g., "2024-TSI-08"

    # Status tracking
    status: Mapped[str] = mapped_column(String, default="draft", index=True)
    # draft, in_review, ready_to_submit, submitted, won, lost, no_bid

    version: Mapped[int] = mapped_column(Integer, default=1)

    # Content sections (the actual response content)
    sections: Mapped[dict] = mapped_column(JSON, default=dict)
    """
    Each section is a question/requirement from the RFP:
    {
        "executive_summary": {
            "question_id": "q_001",
            "question_text": "Provide executive summary...",
            "content": "Acme Infrastructure Solutions is pleased to submit...",
            "word_count": 245,
            "page_count": 0.5,
            "template_id": "tmpl_123",
            "ai_generated": true,
            "user_edited": true,
            "edit_count": 3,
            "confidence": 0.87,
            "last_edited_by": "user_456",
            "last_edited_at": "2024-03-10T14:30:00Z"
        },
        "firm_qualifications": {
            "question_id": "q_002",
            "question_text": "Describe your firm's experience...",
            "content": "...",
            "template_id": "tmpl_124",
            ...
        }
    }
    """

    # RFP Requirements extracted by AI
    requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    """
    Requirements extracted from RFP that we need to meet:
    {
        "mandatory": [
            {
                "id": "req_001",
                "name": "ODOT Prequalification (R, D, T)",
                "description": "Must be ODOT prequalified in Roadway, Concrete, Traffic",
                "type": "certification",
                "status": "met",
                "evidence": "content_lib_123",  # References content library item
                "verified_at": "2024-03-10T10:00:00Z"
            },
            {
                "id": "req_002",
                "name": "Transit Infrastructure Experience (5 years)",
                "type": "experience",
                "status": "met",
                "evidence": "proj_001, proj_002, proj_003"
            }
        ],
        "scored": [
            {
                "id": "scored_001",
                "name": "DBE Participation",
                "points_possible": 10,
                "points_estimated": 10,
                "our_commitment": "22.4%",
                "requirement": "18%"
            }
        ]
    }
    """

    # Compliance tracking
    compliance_score: Mapped[float | None] = mapped_column(Float)
    # 0.0 - 1.0: percentage of requirements met

    requirements_met: Mapped[int] = mapped_column(Integer, default=0)
    requirements_total: Mapped[int] = mapped_column(Integer, default=0)

    missing_requirements: Mapped[list] = mapped_column(JSON, default=list)
    # ["ODOT Prequalification", "MBE Certification"]

    # Collaboration
    collaborators: Mapped[list] = mapped_column(JSON, default=list)
    # ["user_123", "user_456"] - user_ids with access

    comments_count: Mapped[int] = mapped_column(Integer, default=0)

    # Export/submission tracking
    exports: Mapped[list] = mapped_column(JSON, default=list)
    """
    Track when user exported for submission:
    [
        {
            "format": "docx",
            "timestamp": "2024-03-15T09:00:00Z",
            "user_id": "user_123",
            "file_size": 2048576,
            "sections_included": ["all"]
        }
    ]
    """

    # Important dates
    started_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    due_date: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # OUTCOME TRACKING - This is critical for AI training!
    result: Mapped[str | None] = mapped_column(String, index=True)
    # "won", "lost", "no_bid", "withdrawn", "cancelled"

    result_date: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    contract_value: Mapped[float | None] = mapped_column(Float)
    # If won, how much was the contract worth?

    result_notes: Mapped[str | None] = mapped_column(Text)
    # Why did we win/lose? Feedback from client?

    evaluation_score: Mapped[float | None] = mapped_column(Float)
    # If RFP had scored evaluation, what was our score?

    # User feedback (for improving AI)
    user_satisfaction: Mapped[int | None] = mapped_column(Integer)
    # 1-5 stars: how helpful was the AI?

    time_saved_hours: Mapped[float | None] = mapped_column(Float)
    # User estimate of time saved vs manual writing

    would_use_again: Mapped[bool | None] = mapped_column(Boolean)

    feedback_text: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)


# ============================================================================
# RESPONSE QUESTIONS - Individual questions from RFPs
# ============================================================================

class ResponseQuestion(Base):
    """
    Individual questions extracted from RFP that need answers.

    Example from COTA TSI RFP:
    - question_number: "3.2.1"
    - question_text: "Describe your firm's experience with transit infrastructure..."
    - question_type: "experience"
    - matched_template: template for transit experience
    """
    __tablename__ = "response_questions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rfp_response_id: Mapped[str] = mapped_column(String, index=True)
    # Links to rfp_responses.id

    # Question details
    question_number: Mapped[str | None] = mapped_column(String)
    # e.g., "3.2.1", "Question 5", "Section A"

    question_text: Mapped[str] = mapped_column(Text)
    # Full text of the question

    section: Mapped[str | None] = mapped_column(String)
    # e.g., "Firm Qualifications", "Project Approach"

    # AI classification
    question_type: Mapped[str] = mapped_column(String, index=True)
    # "qualifications", "experience", "technical_approach", "management", "safety",
    # "schedule", "dbe", "pricing", "references", "certifications"

    keywords: Mapped[list] = mapped_column(JSON, default=list)
    # ["transit", "bus shelter", "experience", "active service"]

    # Requirements
    page_limit: Mapped[str | None] = mapped_column(String)
    # "5 pages", "2 pages maximum", "No limit"

    word_limit: Mapped[int | None] = mapped_column(Integer)

    requires_attachment: Mapped[bool] = mapped_column(Boolean, default=False)

    points_possible: Mapped[int | None] = mapped_column(Integer)
    # If RFP has scored evaluation: "30 points"

    # Response
    answer: Mapped[str | None] = mapped_column(Text)
    # The actual response text

    word_count: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[float | None] = mapped_column(Float)

    # Template matching
    matched_template_id: Mapped[str | None] = mapped_column(String, index=True)
    # References response_templates.id

    match_confidence: Mapped[float | None] = mapped_column(Float)
    # 0.0 - 1.0: How confident is the match?

    # AI generation
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_suggested_answer: Mapped[str | None] = mapped_column(Text)

    # User interaction
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edit_count: Mapped[int] = mapped_column(Integer, default=0)
    regeneration_count: Mapped[int] = mapped_column(Integer, default=0)

    # Attachments for this question
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    # [{"name": "Past_Projects.pdf", "content_lib_id": "content_123"}]

    # Status
    status: Mapped[str] = mapped_column(String, default="pending")
    # "pending", "ai_generated", "user_edited", "ready", "needs_review"

    assigned_to: Mapped[str | None] = mapped_column(String)
    # Team member assigned to write this section

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)


# ============================================================================
# RESPONSE COMMENTS - Team collaboration on sections
# ============================================================================

class ResponseComment(Base):
    """
    Comments and feedback on specific sections of the response.
    Enables team collaboration.
    """
    __tablename__ = "response_comments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rfp_response_id: Mapped[str] = mapped_column(String, index=True)
    question_id: Mapped[str | None] = mapped_column(String, index=True)
    # NULL = comment on overall response

    author_user_id: Mapped[str] = mapped_column(String, index=True)

    comment_text: Mapped[str] = mapped_column(Text)

    comment_type: Mapped[str] = mapped_column(String, default="general")
    # "general", "suggestion", "question", "approval", "concern"

    mentions: Mapped[list] = mapped_column(JSON, default=list)
    # ["user_123", "user_456"] - @mentioned users

    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[str | None] = mapped_column(String)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)


# ============================================================================
# AI TRAINING DATA - Track what works for continuous improvement
# ============================================================================

class ResponseFeedback(Base):
    """
    Tracks user interactions and outcomes to improve AI over time.
    This is the SECRET to making AI better than generic AI.

    Every user edit, win, and loss teaches the AI what works.
    """
    __tablename__ = "response_feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rfp_response_id: Mapped[str] = mapped_column(String, index=True)
    question_id: Mapped[str | None] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)

    # What did AI predict?
    template_used: Mapped[str | None] = mapped_column(String, index=True)
    ai_response: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[float | None] = mapped_column(Float)

    # What did user change?
    user_response: Mapped[str | None] = mapped_column(Text)
    edit_distance: Mapped[int | None] = mapped_column(Integer)
    # Levenshtein distance: how much did user change?

    sections_regenerated: Mapped[list] = mapped_column(JSON, default=list)
    # Which sections did user ask to regenerate?

    # Time metrics
    time_to_first_edit: Mapped[int | None] = mapped_column(Integer)
    # Seconds until user started editing

    time_spent_editing: Mapped[int | None] = mapped_column(Integer)
    # Total seconds user spent on this section

    # User signals
    user_rating: Mapped[int | None] = mapped_column(Integer)
    # 1-5 stars on this specific response

    was_helpful: Mapped[bool | None] = mapped_column(Boolean)
    # Thumbs up/down

    # Behavioral signals
    user_accepted_as_is: Mapped[bool] = mapped_column(Boolean, default=False)
    # Did user use AI response without edits?

    user_deleted_and_rewrote: Mapped[bool] = mapped_column(Boolean, default=False)
    # Did user throw away AI response and start over?

    # Outcome (the GOLD for training)
    rfp_result: Mapped[str | None] = mapped_column(String, index=True)
    # "won", "lost", "no_bid"

    rfp_result_date: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Learning signals
    should_reinforce: Mapped[bool | None] = mapped_column(Boolean)
    # If won + user didn't change much = reinforce this pattern

    should_improve: Mapped[bool | None] = mapped_column(Boolean)
    # If lost or user heavily edited = improve this pattern

    improvement_notes: Mapped[str | None] = mapped_column(Text)
    # AI-generated notes on what to improve

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
