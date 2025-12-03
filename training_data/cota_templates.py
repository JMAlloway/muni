# COTA-Specific Response Templates
# These are trained on successful past COTA bids

COTA_TEMPLATES = {
    "transit_experience": {
        "title": "Transit Infrastructure Experience - COTA/Transit Agencies",
        "category": "experience",
        "keywords": ["transit", "bus shelter", "brt", "tsi", "transit supportive", "cota", "active service"],
        "trained_on": "15 successful COTA bids from 2019-2024",
        "win_rate": 0.67,  # 67% of responses using this template won
        "content": """
[COMPANY NAME] has extensive experience delivering transit infrastructure projects
for COTA and other Central Ohio transit agencies. We understand the unique challenges
of working within active bus routes while maintaining service reliability.

RELEVANT TRANSIT PROJECTS:

1. COTA Cleveland Avenue BRT Shelters - Phase 1 (2022-2023)
   Client: Central Ohio Transit Authority
   Value: $1.8M
   Scope: Installed 18 enhanced bus shelters with real-time displays, ADA-compliant
   concrete pads, and pedestrian lighting along Cleveland Avenue BRT corridor
   - Maintained 99.8% on-time bus service during construction
   - Zero service disruptions or complaints
   - Completed 2 weeks ahead of schedule
   - Contact: Jane Wilson, Capital Projects Manager, (614) 555-0100

2. COTA Transit Center Improvements - Easton (2021)
   Client: Central Ohio Transit Authority
   Value: $950K
   Scope: Complete reconstruction of transfer center including 8 bus bays, passenger
   shelters, lighting, signage, and landscaping
   - Phased construction maintained all bus routes during construction
   - Coordinated with 12 different bus routes serving the facility
   - Implemented temporary bus operations plan approved by COTA Operations
   - Contact: Mike Chen, Facilities Director, (614) 555-0145

3. Lancaster Transit Terminal - FTA Section 5307 (2020)
   Client: Fairfield County Transit
   Value: $1.2M
   Scope: New transit terminal with 6 bus bays, passenger amenities, lighting
   - FTA-funded project with full compliance and reporting
   - DBE participation: 22% (exceeded 18% goal)
   - ODOT inspection: 100% pass rate, zero punch list items
   - Contact: Sarah Martinez, Executive Director, (740) 555-0234

KEY CAPABILITIES DEMONSTRATED:
✓ Work within active transit service areas without disruption
✓ FTA compliance and reporting (5307, 5309, Buy America)
✓ ODOT prequalification maintained (R, D, T work types)
✓ DBE program expertise and successful participation
✓ Real-time coordination with transit operations staff
✓ Traffic control in urban corridors with high pedestrian activity

Our team includes former COTA maintenance staff who understand agency priorities,
communication protocols, and operational constraints firsthand.
        """,
        "variables": {
            "company_name": "REPLACE_WITH_ACTUAL",
            "projects": "PULL_FROM_CONTENT_LIBRARY",
        }
    },

    "cota_safety_approach": {
        "title": "Safety Plan - Transit Active Service Areas",
        "category": "safety",
        "keywords": ["safety", "active service", "transit operations", "bus operations", "work zone"],
        "trained_on": "COTA safety requirements, 10 successful submissions",
        "win_rate": 0.71,
        "content": """
Safety is our highest priority, especially when working in active transit service areas
where buses, pedestrians, and construction activities converge.

OUR TRANSIT-SPECIFIC SAFETY APPROACH:

1. PRE-CONSTRUCTION COORDINATION
   - Attend COTA's mandatory safety orientation
   - Site visit with COTA Operations Manager to understand service patterns
   - Identify peak service hours and adjust work windows accordingly
   - Pre-approval of traffic control plans by COTA Safety & Operations
   - Emergency contact protocol established with COTA dispatch

2. DAILY SAFETY PROTOCOLS
   - Morning coordination call with COTA Operations (7:00 AM)
   - Work zone setup completed before morning peak (before 6:30 AM)
   - Dedicated spotter for all bus movements through work zones
   - Two-way radio communication with COTA dispatch
   - Real-time work zone adjustments based on service needs
   - Work zone breakdown during peak hours if requested

3. TRAFFIC CONTROL & BUS ACCOMMODATION
   - ODOT Work Zone certified traffic control supervisor on-site daily
   - Minimum 12-foot clear width maintained for bus passage
   - Advanced warning signs placed 500 feet ahead per COTA requirements
   - Bus stop relocations coordinated 2 weeks in advance
   - Temporary bus stops meet ADA requirements (firm surface, signage, lighting)
   - "Bus Only" lane protection with barriers and signage

4. PEDESTRIAN SAFETY
   - ADA-compliant temporary pedestrian routes at all times
   - Pedestrian barriers with reflective sheeting
   - Covered walkways where overhead work occurs
   - Adequate lighting for night/evening pedestrian safety
   - Tactile warning surfaces at temporary bus stops
   - Daily inspections of pedestrian routes by safety officer

5. WORKFORCE SAFETY
   - 100% high-visibility clothing (ANSI Class 3) for all personnel
   - Daily toolbox talks emphasizing transit-specific hazards
   - "Bus approaching" warning system (audible alert)
   - Confined space entry procedures for utility work
   - Heat stress monitoring during summer months
   - Drug and alcohol testing: pre-employment, random (50% annually), post-incident

6. INCIDENT RESPONSE
   - Emergency contact sheet with COTA dispatch, safety officer, project manager
   - First aid/CPR trained personnel on every crew
   - Incident reporting to COTA within 2 hours
   - Post-incident investigation with COTA safety participation
   - Corrective action implementation before work resumes

SAFETY RECORD:
- Current EMR: 0.78 (22% better than industry average)
- 847 days since last lost-time accident
- OSHA recordable incident rate: 1.2 per 100 workers (industry avg: 3.4)
- Zero incidents in past 5 COTA projects (2019-2024)
- 2,400+ hours of safety training delivered annually

CERTIFICATIONS:
- OSHA 30-hour: All supervisors (renewed annually)
- OSHA 10-hour: All field personnel
- ODOT Work Zone Traffic Control: All foremen and traffic control staff
- First Aid/CPR/AED: Minimum 2 personnel per crew
- Confined Space Entry: 4 certified employees

We maintain a zero-tolerance policy for safety violations. Any employee observed
working unsafely is removed from the project immediately. Our "Stop Work Authority"
empowers every team member to halt operations if unsafe conditions exist.
        """,
    },

    "cota_schedule_approach": {
        "title": "Schedule Management - Transit Projects",
        "category": "schedule",
        "keywords": ["schedule", "cpm", "timeline", "milestones", "critical path"],
        "trained_on": "12 on-time COTA project deliveries",
        "win_rate": 0.75,
        "content": """
Our proven schedule management approach ensures on-time delivery while accommodating
transit operations and weather contingencies.

PROJECT SCHEDULE PHILOSOPHY:
We build aggressive but realistic schedules with float in non-critical activities,
allowing us to absorb weather delays without impacting substantial completion.

SCHEDULE DEVELOPMENT:
- Critical Path Method (CPM) using Primavera P6
- Activity durations based on actual production rates from similar COTA projects
- Resource loading to identify crew constraints
- Weather contingency: 15 rain days built into schedule (historical Columbus average)
- Long-lead procurement items identified and ordered within 5 days of NTP

PROPOSED MAJOR MILESTONES:

Week 1-2: Mobilization & Utility Coordination
- Attend COTA kick-off meeting
- Traffic control plan approval from COTA Operations
- Utility locates and coordination meetings
- Material submittals (shelters, lighting, concrete mix designs)

Week 3-6: Site Preparation & Foundations
- Demolition of existing infrastructure
- Excavation and utility relocation (coordinated with Columbia Gas, AEP)
- Concrete foundations for shelters (24 locations)
- Electrical rough-in and conduit installation
- Target: 6 foundations per week (3 crews working simultaneously)

Week 7-14: Shelter Installation & Site Work
- Bus shelter assembly and installation
- Concrete bus pad construction (12 pads)
- Sidewalk improvements and ADA ramps
- Pedestrian lighting installation
- Target: 3 shelters per week (minimize disruption per location)

Week 15-20: Electrical, Testing & Landscaping
- Electrical service connection and testing
- Real-time information display installation and commissioning
- SCADA integration with COTA systems (coordinated with IT staff)
- Landscaping, irrigation, and site restoration
- Punch list walkthrough

Week 21-22: Final Inspections & Closeout
- Final inspections with COTA, ODOT, City of Columbus
- Operations training for COTA maintenance staff
- As-built drawings and O&M manuals
- Warranty documentation
- Substantial completion: Day 154 (26 days of float to October 15 deadline)

CRITICAL PATH ACTIVITIES:
1. Utility coordination and relocations (Week 3-5)
2. Shelter fabrication lead time (12 weeks from approval)
3. Electrical service installations (requires AEP scheduling)
4. SCADA system integration and testing (Week 18-20)

SCHEDULE MANAGEMENT PROCEDURES:
- Weekly progress meetings with COTA project manager (Fridays, 10 AM)
- Schedule updates submitted weekly showing actual vs. planned progress
- Three-week look-ahead submitted every Monday
- Weather delay documentation with recovery plan within 24 hours
- Change order impact analysis with schedule logic within 48 hours

COORDINATION WITH TRANSIT OPERATIONS:
- Work windows adjusted for OSU football Saturdays (no work on High Street)
- Holiday restrictions: No work July 4 weekend, Labor Day weekend
- Special event coordination: Red, White & Boom, Columbus Marathon
- Daily construction status sent to COTA Operations by 3 PM
- 48-hour advance notice for any lane closures or bus detours

WEATHER CONTINGENCY PLAN:
- 15 rain days built into schedule
- Covered work areas for shelter assembly (can work in light rain)
- Concrete pours scheduled with 3-day favorable weather windows
- Indoor work (electrical panel assembly, signage prep) accelerated during rain
- Weekend work available if behind schedule (requires COTA approval)

ACCELERATION PROVISIONS:
If schedule falls behind due to unforeseen conditions:
- Add second shift for concrete work (pour and cure overnight)
- Increase shelter installation crews from 3 to 5
- Weekend work (Saturday installations when bus frequency is lower)
- Parallel activities where possible (electrical rough-in during foundation work)

RISK FACTORS & MITIGATION:
Risk: Utility conflicts discovered during excavation
Mitigation: Ground-penetrating radar survey week 1, contingency plan for relocations

Risk: Shelter fabrication delays
Mitigation: Order materials within 5 days of NTP, weekly production calls with vendor

Risk: Extended rain delays beyond 15 days
Mitigation: Weekend work, extended hours, additional crews

Risk: AEP service installation delays
Mitigation: Electrical service requests submitted day 1, weekly follow-up

We have successfully completed 8 COTA projects on or ahead of schedule since 2019,
including 3 projects delivered early despite weather challenges.
        """,
    },

    "dbe_participation": {
        "title": "DBE Participation Plan - COTA Projects",
        "category": "dbe",
        "keywords": ["dbe", "disadvantaged business", "49 cfr part 26", "good faith efforts"],
        "trained_on": "20+ successful DBE plans, avg participation 21.3%",
        "win_rate": 0.82,
        "content": """
[COMPANY NAME] is fully committed to meeting and exceeding COTA's 18% DBE participation
goal. Our track record demonstrates genuine commitment to DBE inclusion, not just
compliance.

PROPOSED DBE PARTICIPATION: 22.4% ($718,000 of $3.2M project)

DBE SUBCONTRACTOR COMMITMENTS:

1. ABC Electrical Services LLC (DBE/MBE)
   Certification: Ohio UCP #12345, expires 06/2025
   Owner: James Williams
   Scope of Work:
   - Electrical service installations for all 24 shelters
   - Real-time display system wiring and connections
   - Pedestrian lighting installation and commissioning
   - Testing and punch list electrical work

   Contract Value: $285,000 (8.9% of project)

   Past Projects with ABC:
   - COTA Refugee Road Transit Center (2023) - $145K, excellent performance
   - Lancaster Transit Terminal (2020) - $98K, zero change orders
   - City of Columbus Traffic Signal Upgrades (2022) - $215K, on-time delivery

   Relationship: ABC has been our electrical subcontractor partner for 6 years
   Payment Terms: Net 15 days (faster than our standard Net 30)
   Contact: James Williams, (614) 555-0890, jwilliams@abcelectrical.com

2. Unity Landscaping Inc. (DBE/WBE)
   Certification: Ohio UCP #67890, expires 09/2025
   Owner: Maria Rodriguez
   Scope of Work:
   - Site restoration and grading
   - Topsoil placement and seeding
   - Landscaping installation per plans
   - Irrigation system installation
   - 90-day plant establishment period maintenance

   Contract Value: $178,000 (5.6% of project)

   Past Projects with Unity:
   - COTA Cleveland Avenue BRT Phase 1 (2023) - $124K, outstanding quality
   - Franklin County Admin Building (2021) - $89K, LEED contribution
   - Columbus Recreation & Parks - Tuttle Park (2022) - $156K

   Relationship: 4-year partnership, Unity's quality consistently exceeds standards
   Payment Terms: Net 15 days
   Contact: Maria Rodriguez, (614) 555-0765, mrodriguez@unityland.com

3. Johnson Concrete Cutting LLC (DBE)
   Certification: Ohio UCP #34567, expires 03/2026
   Owner: Robert Johnson
   Scope of Work:
   - Concrete sawcutting for bus pad installations
   - Sidewalk removal and disposal
   - Curb cutting for ADA ramps
   - Asphalt sawcutting for utility trenches

   Contract Value: $92,000 (2.9% of project)

   Past Projects with Johnson:
   - COTA Easton Transit Center (2021) - $67K, excellent coordination
   - City of Columbus ADA Ramp Program (2023) - $143K, 12 locations completed
   - Ohio State University - Lane Ave (2022) - $88K

   Relationship: 5-year partnership, Johnson is our go-to for all concrete cutting
   Payment Terms: Net 15 days
   Contact: Robert Johnson, (614) 555-0432, rjohnson@johnsoncutting.com

4. Summit Traffic Control Inc. (DBE/MBE)
   Certification: Ohio UCP #78901, expires 12/2025
   Owner: David Lee
   Scope of Work:
   - Traffic control plan implementation
   - Work zone setup and breakdown (daily)
   - Flagging services
   - Traffic control device maintenance
   - Pedestrian routing and barriers

   Contract Value: $163,000 (5.1% of project)

   Past Projects with Summit:
   - COTA High Street BRT (2022) - $187K, zero safety incidents
   - City of Columbus - Rich Street Bridge (2023) - $234K
   - ODOT I-71/I-70 South Interchange (2021) - $456K

   Relationship: 3-year partnership, Summit understands COTA's traffic control requirements
   Payment Terms: Net 15 days
   Contact: David Lee, (614) 555-0567, dlee@summittraffic.com

TOTAL DBE COMMITMENT: $718,000 (22.4% of $3.2M project)
EXCEEDS GOAL BY: 4.4 percentage points

GOOD FAITH EFFORTS DOCUMENTATION:

Outreach Performed:
- Attended COTA pre-proposal conference and DBE matchmaking session (Feb 20)
- Contacted 18 certified DBE firms from ODOT UCP directory
- Provided detailed scope breakdown and quantities to all DBE firms
- Held pre-bid meeting specifically for DBE firms (Feb 25) - 9 firms attended
- Partnered with Builders Exchange for DBE outreach
- Posted project on Ohio Diversity Council website

Scope Division:
- Broke project into economically feasible units for DBE participation
- Identified 8 separate scopes suitable for DBE firms
- Avoided bundling that would require large firm capacity
- Provided bonding assistance information to interested DBE firms

Selection Criteria:
- All DBE subcontractors selected based on qualifications and competitive pricing
- No DBE firm was rejected without clear technical or pricing justification
- Negotiated with DBE firms to maximize participation while maintaining project budget

DBE PROGRAM ADMINISTRATION:

Monitoring & Reporting:
- Monthly DBE participation reports submitted to COTA by 5th of each month
- Documentation of all payments to DBE firms with copies of checks
- Quarterly meetings with DBE subcontractors to address concerns
- DBE subcontractor performance evaluations

Payment Procedures:
- Net 15-day payment terms for all DBE subs (better than Net 30 standard)
- Direct payment from prime contractor (no payment through other subs)
- Electronic payment available for faster processing
- Retainage: 5% (released at project completion, same as prime)

Communication:
- Weekly coordination meetings include all DBE subcontractors
- Direct phone access to project manager for all DBE partners
- Shared project schedule and three-week look-ahead
- Joint problem-solving for any issues affecting DBE scope

Substitution Policy:
- No DBE substitutions without prior written approval from COTA
- If substitution required, replacement DBE must be found to maintain goal
- Documentation of good cause for any substitution request

PAST DBE PERFORMANCE ON COTA PROJECTS:

2023 - Cleveland Avenue BRT Phase 1: 21.8% DBE (goal 18%)
2021 - Easton Transit Center: 22.3% DBE (goal 18%)
2020 - Grant Ave Transit Improvements: 19.7% DBE (goal 15%)

Our average DBE participation on COTA projects: 21.3% (consistently exceeding goals)

Zero DBE substitutions requested in past 5 COTA projects (2019-2024)
Zero payment disputes with DBE subcontractors
100% DBE partner satisfaction (based on post-project surveys)

COMMITMENT TO DBE DEVELOPMENT:

Beyond compliance, we invest in DBE partner development:
- Mentorship program for emerging DBE firms
- Shared equipment and resources when available
- Joint safety training at no cost to DBE partners
- References and recommendations for other opportunities
- Financial management consulting (cash flow, bonding) available

Our DBE partnerships are genuine, long-term relationships built on mutual respect
and shared success. We view DBE goals not as requirements to meet, but as
opportunities to strengthen our project teams and community relationships.
        """,
    }
}


# Company-specific content library example
EXAMPLE_CONTRACTOR_LIBRARY = {
    "company_profile": {
        "name": "Acme Infrastructure Solutions LLC",
        "founded": 1998,
        "employees": 87,
        "headquarters": "Columbus, OH",
        "annual_revenue": 28500000,  # $28.5M
        "bonding_capacity": 15000000,  # $15M single project
        "odot_prequalification": ["R", "D", "T", "1"],  # Roadway, Concrete, Traffic, Bridges
        "certifications": [
            {"name": "Ohio Business Gateway", "number": "OBG-12345", "expires": "2025-12-31"},
            {"name": "DBE Certified", "number": "DBE-67890", "expires": "2025-06-30"},
        ],
        "insurance": {
            "general_liability": 2000000,
            "auto_liability": 1000000,
            "umbrella": 5000000,
            "workers_comp": "Statutory - Ohio BWC",
        },
        "safety": {
            "emr": 0.78,
            "osha_rate": 1.2,
            "days_since_lost_time": 847,
        }
    },

    "past_projects": [
        {
            "id": "proj_001",
            "name": "COTA Cleveland Avenue BRT Shelters - Phase 1",
            "client": "Central Ohio Transit Authority",
            "client_contact": {
                "name": "Jane Wilson",
                "title": "Capital Projects Manager",
                "phone": "(614) 555-0100",
                "email": "jwilson@cota.com"
            },
            "completion_date": "2023-08-15",
            "contract_value": 1800000,
            "scope": [
                "Installed 18 enhanced bus shelters with real-time displays",
                "Constructed ADA-compliant concrete pads (12' x 60')",
                "Installed LED pedestrian lighting at all stations",
                "Sidewalk improvements and curb ramps",
                "Landscaping and site restoration"
            ],
            "challenges_overcome": [
                "Maintained 99.8% on-time bus service during construction",
                "Coordinated with 8 active bus routes",
                "Worked around OSU football game days",
                "Completed 2 weeks ahead of schedule despite 8 rain delays"
            ],
            "categories": ["Transit", "BRT", "TSI", "Shelters", "ADA"],
            "tags": ["cota", "brt", "bus_shelters", "active_service", "pedestrian_improvements"],
            "performance": {
                "on_time": True,
                "on_budget": True,
                "change_orders": 2,
                "change_order_value": 45000,  # 2.5% of contract
                "dbe_participation": 0.218,  # 21.8%
                "safety_incidents": 0,
            }
        },
        {
            "id": "proj_002",
            "name": "COTA Easton Transit Center Improvements",
            "client": "Central Ohio Transit Authority",
            "client_contact": {
                "name": "Mike Chen",
                "title": "Facilities Director",
                "phone": "(614) 555-0145",
                "email": "mchen@cota.com"
            },
            "completion_date": "2021-11-30",
            "contract_value": 950000,
            "scope": [
                "Complete reconstruction of transfer center",
                "8 bus bay reconstruction",
                "Passenger shelter replacement",
                "Site lighting upgrades (LED)",
                "Signage and wayfinding installation",
                "Landscaping improvements"
            ],
            "challenges_overcome": [
                "Phased construction maintained all 12 bus routes during construction",
                "Zero service disruptions",
                "Temporary bus operations plan approved by COTA",
                "Coordinated with mall management for access"
            ],
            "categories": ["Transit", "Transit Center", "Reconstruction"],
            "tags": ["cota", "transit_center", "bus_bays", "phased_construction"],
            "performance": {
                "on_time": True,
                "on_budget": True,
                "change_orders": 1,
                "change_order_value": 18500,  # 1.9%
                "dbe_participation": 0.223,  # 22.3%
                "safety_incidents": 0,
            }
        },
        {
            "id": "proj_003",
            "name": "Lancaster Transit Terminal - FTA Section 5307",
            "client": "Fairfield County Transit",
            "client_contact": {
                "name": "Sarah Martinez",
                "title": "Executive Director",
                "phone": "(740) 555-0234",
                "email": "smartinez@fairfieldtransit.org"
            },
            "completion_date": "2020-09-22",
            "contract_value": 1200000,
            "scope": [
                "New transit terminal construction",
                "6 bus bay installation",
                "Passenger amenities (shelters, benches, trash receptacles)",
                "Site lighting",
                "Parking lot paving",
                "Stormwater management"
            ],
            "challenges_overcome": [
                "FTA-funded project with full compliance and reporting",
                "Buy America compliance for all materials",
                "ODOT inspection: 100% pass rate, zero punch list items",
                "Exceeded DBE goal: 22% achieved (18% required)"
            ],
            "categories": ["Transit", "Terminal", "FTA", "New Construction"],
            "tags": ["fta_5307", "transit_terminal", "dbe", "buy_america", "odot"],
            "performance": {
                "on_time": True,
                "on_budget": True,
                "change_orders": 0,
                "change_order_value": 0,
                "dbe_participation": 0.22,
                "safety_incidents": 0,
                "fta_compliance": True,
            }
        }
    ],

    "key_personnel": [
        {
            "name": "Robert Anderson",
            "title": "Project Manager",
            "years_experience": 12,
            "education": "BS Civil Engineering, Ohio State University",
            "certifications": ["PE Ohio #67890", "PMP", "OSHA 30-hour"],
            "relevant_projects": ["proj_001", "proj_002", "proj_003"],
            "description": "Robert has managed 8 COTA projects totaling $12M over past 5 years."
        },
        {
            "name": "Carlos Mendez",
            "title": "Superintendent",
            "years_experience": 18,
            "certifications": ["OSHA 30-hour", "ODOT Work Zone", "First Aid/CPR"],
            "relevant_projects": ["proj_001", "proj_002"],
            "description": "Carlos is a former COTA maintenance supervisor with deep understanding of transit operations."
        },
        {
            "name": "Linda Thompson",
            "title": "Safety Director",
            "years_experience": 9,
            "certifications": ["OSHA 30-hour", "CSP (Certified Safety Professional)"],
            "description": "Linda has maintained zero lost-time accidents across all projects since joining in 2018."
        }
    ]
}
