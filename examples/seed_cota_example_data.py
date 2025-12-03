"""
Seed database with real COTA RFP example data

This demonstrates the complete flow:
1. Company content library (past COTA projects, certifications)
2. Response templates (trained on COTA wins)
3. RFP response to COTA TSI RFP 2024-TSI-08
4. Questions extracted from RFP
5. AI-generated responses using templates + content library

Run this to populate database with realistic example data.
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import uuid

from app.domain.response_models import (
    CompanyContentLibrary,
    ResponseTemplate,
    RFPResponse,
    ResponseQuestion,
    ResponseComment,
    ResponseFeedback
)


async def seed_example_data():
    """Seed database with COTA RFP example"""

    # Use your existing database connection
    from app.core.settings import settings
    engine = create_async_engine(settings.DB_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("=" * 80)
        print("SEEDING DATABASE WITH COTA RFP EXAMPLE DATA")
        print("=" * 80)
        print()

        # Sample user and team IDs (use your actual user IDs in production)
        user_id = "user_acme_123"
        team_id = "team_acme"
        opportunity_id = "opp_cota_tsi_2024"  # Links to your opportunities table

        # ====================================================================
        # STEP 1: Create Content Library (Company's Past Projects & Certs)
        # ====================================================================

        print("📚 Step 1: Creating Content Library...")
        print()

        # COTA Project 1
        project_1 = CompanyContentLibrary(
            id=str(uuid.uuid4()),
            user_id=user_id,
            team_id=team_id,
            content_type="past_project",
            title="COTA Cleveland Avenue BRT Shelters - Phase 1",
            description="Installation of 18 enhanced bus shelters with real-time displays along BRT corridor",
            tags=["cota", "brt", "bus_shelters", "transit", "active_service", "tsi"],
            keywords=["transit", "bus shelter", "brt", "cleveland avenue", "real-time displays"],
            data={
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
                "duration_days": 120,
                "scope": [
                    "Installed 18 enhanced bus shelters with real-time information displays",
                    "Constructed ADA-compliant concrete pads (12' x 60')",
                    "Installed LED pedestrian lighting at all stations",
                    "Sidewalk improvements and curb ramps",
                    "Landscaping and site restoration"
                ],
                "achievements": [
                    "Maintained 99.8% on-time bus service during construction",
                    "Zero service disruptions or complaints",
                    "Completed 2 weeks ahead of schedule despite 8 rain delays",
                    "Coordinated with 8 active bus routes"
                ],
                "categories": ["Transit", "BRT", "TSI", "Shelters", "ADA"],
                "location": "Cleveland Avenue, Columbus OH",
                "performance_metrics": {
                    "on_time": True,
                    "on_budget": True,
                    "ahead_of_schedule_days": 14,
                    "change_orders": 2,
                    "change_order_value": 45000,
                    "change_order_percent": 2.5,
                    "dbe_participation": 21.8,
                    "safety_incidents": 0,
                    "service_disruptions": 0
                },
                "challenges_overcome": [
                    "Worked around OSU football game days",
                    "Managed utility conflicts discovered during excavation",
                    "Adjusted schedule for 8 rain delays"
                ]
            },
            searchable_text="COTA Cleveland Avenue BRT bus shelters transit supportive infrastructure real-time displays ADA concrete pads pedestrian lighting active service",
            use_count=12,
            wins_when_used=8,
            total_uses=12,
            win_rate=0.67,
            last_used=datetime.utcnow() - timedelta(days=15)
        )

        # COTA Project 2
        project_2 = CompanyContentLibrary(
            id=str(uuid.uuid4()),
            user_id=user_id,
            team_id=team_id,
            content_type="past_project",
            title="COTA Easton Transit Center Improvements",
            description="Complete reconstruction of transfer center with 8 bus bays and passenger amenities",
            tags=["cota", "transit_center", "bus_bays", "phased_construction"],
            keywords=["transit center", "bus bay", "transfer center", "phased construction"],
            data={
                "project_name": "COTA Easton Transit Center Improvements",
                "client": "Central Ohio Transit Authority",
                "client_contact": {
                    "name": "Mike Chen",
                    "title": "Facilities Director",
                    "phone": "(614) 555-0145",
                    "email": "mchen@cota.com"
                },
                "contract_value": 950000,
                "completion_date": "2021-11-30",
                "scope": [
                    "Complete reconstruction of transfer center",
                    "8 bus bay reconstruction",
                    "Passenger shelter replacement",
                    "Site lighting upgrades (LED)",
                    "Signage and wayfinding installation"
                ],
                "achievements": [
                    "Phased construction maintained all 12 bus routes during construction",
                    "Zero service disruptions",
                    "Temporary bus operations plan approved by COTA Operations"
                ],
                "performance_metrics": {
                    "on_time": True,
                    "on_budget": True,
                    "dbe_participation": 22.3,
                    "safety_incidents": 0
                }
            },
            searchable_text="COTA Easton transit center bus bays phased construction active service",
            use_count=8,
            wins_when_used=6,
            total_uses=8,
            win_rate=0.75
        )

        # Certification: ODOT Prequalification
        cert_odot = CompanyContentLibrary(
            id=str(uuid.uuid4()),
            user_id=user_id,
            team_id=team_id,
            content_type="certification",
            title="ODOT Prequalification",
            description="Ohio Department of Transportation prequalification in multiple work types",
            tags=["odot", "prequalification", "certification"],
            keywords=["odot", "prequalification", "roadway", "concrete", "traffic"],
            data={
                "cert_name": "ODOT Prequalification",
                "cert_number": "R, D, T, 1",
                "work_types": ["Roadway (R)", "Concrete (D)", "Traffic (T)", "Bridges (1)"],
                "issue_date": "2023-01-01",
                "expiry_date": "2025-12-31",
                "prequalification_limits": {
                    "roadway": 15000000,
                    "concrete": 15000000,
                    "traffic": 5000000
                }
            },
            searchable_text="ODOT prequalification roadway concrete traffic bridges certification"
        )

        # Key Personnel: Project Manager
        personnel_pm = CompanyContentLibrary(
            id=str(uuid.uuid4()),
            user_id=user_id,
            team_id=team_id,
            content_type="key_personnel",
            title="Robert Anderson - Project Manager",
            description="Senior Project Manager with 12 years managing transit infrastructure projects",
            tags=["project_manager", "transit", "cota_experience"],
            keywords=["project manager", "transit", "cota", "pe", "pmp"],
            data={
                "name": "Robert Anderson",
                "title": "Project Manager",
                "years_experience": 12,
                "education": "BS Civil Engineering, Ohio State University",
                "certifications": ["PE Ohio #67890", "PMP", "OSHA 30-hour"],
                "relevant_projects": [
                    "COTA Cleveland Avenue BRT Shelters",
                    "COTA Easton Transit Center",
                    "Lancaster Transit Terminal"
                ],
                "cota_projects_managed": 8,
                "cota_projects_value": 12000000,
                "bio": "Robert has managed 8 COTA projects totaling $12M over past 5 years. Former COTA maintenance supervisor with deep understanding of transit operations."
            },
            searchable_text="Robert Anderson project manager PE PMP COTA transit"
        )

        # Safety Record
        safety = CompanyContentLibrary(
            id=str(uuid.uuid4()),
            user_id=user_id,
            team_id=team_id,
            content_type="safety_record",
            title="Company Safety Record",
            description="Current safety statistics and certifications",
            tags=["safety", "emr", "osha"],
            keywords=["safety", "emr", "osha", "lost time accident"],
            data={
                "current_emr": 0.78,
                "industry_average_emr": 1.0,
                "days_since_lost_time_accident": 847,
                "osha_recordable_rate": 1.2,
                "industry_osha_rate": 3.4,
                "zero_incidents_cota_projects": 5,
                "year_range": "2019-2024",
                "training_hours_annual": 2400,
                "certifications": [
                    "OSHA 30-hour (all supervisors)",
                    "OSHA 10-hour (all field personnel)",
                    "ODOT Work Zone Traffic Control",
                    "First Aid/CPR/AED"
                ]
            },
            searchable_text="safety record EMR OSHA lost time accident training"
        )

        # Add all to session
        session.add_all([project_1, project_2, cert_odot, personnel_pm, safety])
        await session.flush()

        print(f"   ✓ Created {project_1.title}")
        print(f"   ✓ Created {project_2.title}")
        print(f"   ✓ Created {cert_odot.title}")
        print(f"   ✓ Created {personnel_pm.title}")
        print(f"   ✓ Created {safety.title}")
        print()

        # ====================================================================
        # STEP 2: Create Response Templates (The Secret Sauce!)
        # ====================================================================

        print("📋 Step 2: Creating Response Templates...")
        print()

        # Template 1: Transit Infrastructure Experience
        template_transit = ResponseTemplate(
            id=str(uuid.uuid4()),
            user_id=None,  # System template
            is_system_template=True,
            title="Transit Infrastructure Experience - COTA/Transit Agencies",
            category="experience",
            subcategory="transit_experience",
            description="Proven template for describing transit infrastructure experience. Optimized for COTA RFPs.",
            keywords=["transit", "bus shelter", "brt", "tsi", "active service", "cota", "experience"],
            question_patterns=[
                "describe.*transit.*experience",
                "bus shelter.*installation",
                "transit infrastructure",
                "active.*transit.*corridor"
            ],
            agency_specific="COTA",
            content="""[COMPANY_NAME] has extensive experience delivering transit infrastructure projects for COTA and other Central Ohio transit agencies. We understand the unique challenges of working within active bus routes while maintaining service reliability.

RELEVANT TRANSIT PROJECTS:

[INSERT_PROJECTS:type=past_project,tags=cota+transit,limit=3]

KEY CAPABILITIES DEMONSTRATED:
✓ Work within active transit service areas without disruption
✓ FTA compliance and reporting (5307, 5309, Buy America)
✓ ODOT prequalification maintained (R, D, T work types)
✓ DBE program expertise and successful participation
✓ Real-time coordination with transit operations staff
✓ Traffic control in urban corridors with high pedestrian activity

Our team includes former COTA maintenance staff who understand agency priorities, communication protocols, and operational constraints firsthand.

[INSERT_PERSONNEL:title=project_manager,tags=cota_experience]

We have successfully completed [COUNT_PROJECTS:tags=cota] projects for COTA totaling [SUM_VALUE:tags=cota] with zero service disruptions.""",
            variables={
                "company_name": {"source": "company_profile", "field": "name"},
                "projects": {
                    "source": "past_projects",
                    "filter": {"tags": ["cota", "transit"]},
                    "limit": 3,
                    "sort": "completion_date DESC"
                },
                "personnel": {
                    "source": "key_personnel",
                    "filter": {"tags": ["cota_experience"]},
                    "limit": 1
                }
            },
            trained_on="15 successful COTA bids from 2019-2024",
            win_rate=0.67,
            use_count=15,
            wins_count=10,
            losses_count=5,
            avg_score=78.5,
            avg_user_rating=4.3,
            is_active=True,
            is_featured=True
        )

        # Template 2: Safety in Transit Areas
        template_safety = ResponseTemplate(
            id=str(uuid.uuid4()),
            is_system_template=True,
            title="Safety Plan - Transit Active Service Areas",
            category="safety",
            subcategory="safety_transit",
            description="Safety approach specifically for working in active transit service areas",
            keywords=["safety", "active service", "transit operations", "bus operations", "work zone"],
            question_patterns=[
                "safety.*active.*transit",
                "traffic control.*transit",
                "maintain.*service.*construction"
            ],
            agency_specific="COTA",
            content="""Safety is our highest priority, especially when working in active transit service areas where buses, pedestrians, and construction activities converge.

OUR TRANSIT-SPECIFIC SAFETY APPROACH:

1. PRE-CONSTRUCTION COORDINATION
   - Attend COTA's mandatory safety orientation
   - Site visit with COTA Operations Manager to understand service patterns
   - Identify peak service hours and adjust work windows accordingly
   - Pre-approval of traffic control plans by COTA Safety & Operations

2. DAILY SAFETY PROTOCOLS
   - Morning coordination call with COTA Operations (7:00 AM)
   - Work zone setup completed before morning peak (before 6:30 AM)
   - Dedicated spotter for all bus movements through work zones
   - Two-way radio communication with COTA dispatch
   - Real-time work zone adjustments based on service needs

3. SAFETY RECORD
[INSERT_SAFETY_RECORD]

4. WORKFORCE SAFETY
   - 100% high-visibility clothing (ANSI Class 3) for all personnel
   - Daily toolbox talks emphasizing transit-specific hazards
   - "Bus approaching" warning system (audible alert)
   - Drug and alcohol testing: pre-employment, random (50% annually), post-incident

We maintain a zero-tolerance policy for safety violations. Any employee observed working unsafely is removed from the project immediately.""",
            variables={
                "safety_record": {
                    "source": "safety_record",
                    "fields": ["current_emr", "days_since_lost_time_accident", "zero_incidents_cota_projects"]
                }
            },
            trained_on="COTA safety requirements, 10 successful submissions",
            win_rate=0.71,
            use_count=10,
            wins_count=7,
            losses_count=3,
            avg_user_rating=4.5
        )

        session.add_all([template_transit, template_safety])
        await session.flush()

        print(f"   ✓ Created template: {template_transit.title} (Win rate: {template_transit.win_rate*100:.0f}%)")
        print(f"   ✓ Created template: {template_safety.title} (Win rate: {template_safety.win_rate*100:.0f}%)")
        print()

        # ====================================================================
        # STEP 3: Create RFP Response to COTA TSI RFP
        # ====================================================================

        print("📝 Step 3: Creating RFP Response...")
        print()

        rfp_response = RFPResponse(
            id=str(uuid.uuid4()),
            opportunity_id=opportunity_id,  # Links to opportunities table
            user_id=user_id,
            team_id=team_id,
            title="Response to COTA TSI - Cleveland Avenue BRT Corridor",
            rfp_number="2024-TSI-08",
            status="draft",
            version=1,
            sections={
                "firm_qualifications": {
                    "question_id": "q_001",
                    "question_text": "Describe your firm's experience with transit infrastructure projects.",
                    "content": "[AI WILL GENERATE THIS USING template_transit]",
                    "word_count": 0,
                    "template_id": str(template_transit.id),
                    "ai_generated": False,
                    "user_edited": False,
                    "confidence": 0.87
                },
                "safety_approach": {
                    "question_id": "q_002",
                    "question_text": "How does your firm ensure safety in active transit service areas?",
                    "content": "[AI WILL GENERATE THIS USING template_safety]",
                    "word_count": 0,
                    "template_id": str(template_safety.id),
                    "ai_generated": False,
                    "user_edited": False,
                    "confidence": 0.89
                }
            },
            requirements={
                "mandatory": [
                    {
                        "id": "req_001",
                        "name": "Transit Infrastructure Experience (5 years minimum)",
                        "description": "Minimum 5 years experience with transit infrastructure projects",
                        "type": "experience",
                        "status": "met",
                        "evidence": str(project_1.id),
                        "verified_at": datetime.utcnow().isoformat()
                    },
                    {
                        "id": "req_002",
                        "name": "ODOT Prequalification (R, D, T)",
                        "description": "Must be ODOT prequalified in Roadway, Concrete, Traffic",
                        "type": "certification",
                        "status": "met",
                        "evidence": str(cert_odot.id),
                        "verified_at": datetime.utcnow().isoformat()
                    },
                    {
                        "id": "req_003",
                        "name": "Bonding Capacity ($3.2M)",
                        "description": "Bonding capacity for full contract value",
                        "type": "financial",
                        "status": "met",
                        "evidence": "bonding_capacity_15M",
                        "verified_at": datetime.utcnow().isoformat()
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
            },
            compliance_score=1.0,
            requirements_met=3,
            requirements_total=3,
            missing_requirements=[],
            collaborators=[user_id],
            comments_count=0,
            due_date=datetime.utcnow() + timedelta(days=15)  # Due in 15 days
        )

        session.add(rfp_response)
        await session.flush()

        print(f"   ✓ Created RFP Response: {rfp_response.title}")
        print(f"      Status: {rfp_response.status}")
        print(f"      Compliance: {rfp_response.requirements_met}/{rfp_response.requirements_total} requirements met")
        print(f"      Due: {rfp_response.due_date.strftime('%Y-%m-%d')}")
        print()

        # ====================================================================
        # STEP 4: Create Questions Extracted from RFP
        # ====================================================================

        print("❓ Step 4: Creating RFP Questions...")
        print()

        question_1 = ResponseQuestion(
            id=str(uuid.uuid4()),
            rfp_response_id=rfp_response.id,
            question_number="3.2.1",
            question_text="Describe your firm's experience with transit infrastructure projects. Include specific examples of bus shelter installations, pedestrian improvements, and work within active transit corridors.",
            section="Firm Qualifications",
            question_type="experience",
            keywords=["transit", "bus shelter", "pedestrian improvements", "active corridor", "experience"],
            page_limit="5 pages maximum",
            requires_attachment=False,
            points_possible=30,
            matched_template_id=str(template_transit.id),
            match_confidence=0.92,
            ai_generated=False,
            status="pending"
        )

        question_2 = ResponseQuestion(
            id=str(uuid.uuid4()),
            rfp_response_id=rfp_response.id,
            question_number="3.2.2",
            question_text="How does your firm ensure safety when working in active transit service areas? Describe your traffic control approach and coordination with transit operations.",
            section="Firm Qualifications",
            question_type="safety",
            keywords=["safety", "active service", "traffic control", "transit operations", "coordination"],
            page_limit="2 pages maximum",
            requires_attachment=False,
            points_possible=10,
            matched_template_id=str(template_safety.id),
            match_confidence=0.94,
            status="pending"
        )

        session.add_all([question_1, question_2])
        await session.flush()

        print(f"   ✓ Question {question_1.question_number}: {question_1.question_text[:60]}...")
        print(f"      Matched template: {template_transit.title} (confidence: {question_1.match_confidence*100:.0f}%)")
        print()
        print(f"   ✓ Question {question_2.question_number}: {question_2.question_text[:60]}...")
        print(f"      Matched template: {template_safety.title} (confidence: {question_2.match_confidence*100:.0f}%)")
        print()

        # ====================================================================
        # STEP 5: Commit Everything
        # ====================================================================

        await session.commit()

        print("=" * 80)
        print("✅ DATABASE SEEDED SUCCESSFULLY!")
        print("=" * 80)
        print()
        print("Summary:")
        print(f"   • Content Library Items: 5 (2 projects, 1 cert, 1 personnel, 1 safety)")
        print(f"   • Response Templates: 2 (67-71% win rates)")
        print(f"   • RFP Responses: 1 (COTA TSI 2024-TSI-08)")
        print(f"   • Questions: 2 (both matched to templates)")
        print()
        print("Next Steps:")
        print("   1. View data in database")
        print("   2. Run AI generation to populate response sections")
        print("   3. Test template matching with new questions")
        print("   4. Export to Word document")
        print()


if __name__ == "__main__":
    asyncio.run(seed_example_data())
