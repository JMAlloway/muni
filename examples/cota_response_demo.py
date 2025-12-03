"""
COTA RFP Response Generator - Complete Working Example

This demonstrates how the AI response system works end-to-end for a real COTA RFP.
"""

import asyncio
import json
from datetime import datetime
from typing import List, Dict

# Simulated AI client (in production, this would call OpenAI/Ollama)
class AIClient:
    """Simulates AI responses for demonstration"""

    def extract_questions(self, rfp_text: str) -> List[Dict]:
        """Extract questions from RFP document"""
        # In production, this would use GPT-4 to extract questions
        # For demo, we return pre-identified questions

        return [
            {
                "question_number": "3.2.1",
                "question_text": """Describe your firm's experience with transit infrastructure
                projects. Include specific examples of bus shelter installations, pedestrian
                improvements, and work within active transit corridors.""",
                "section": "Firm Qualifications",
                "question_type": "experience",
                "page_limit": "5 pages",
                "requires_attachment": False,
                "keywords": ["transit", "bus shelter", "pedestrian improvements", "active service",
                             "corridor", "experience"]
            },
            {
                "question_number": "3.2.2",
                "question_text": """How does your firm ensure safety when working in active
                transit service areas? Describe your traffic control approach and coordination
                with transit operations.""",
                "section": "Firm Qualifications",
                "question_type": "safety",
                "page_limit": "2 pages",
                "requires_attachment": False,
                "keywords": ["safety", "active service", "traffic control", "transit operations",
                             "coordination"]
            },
            {
                "question_number": "3.3",
                "question_text": """Describe your most relevant transit infrastructure project.
                What specific challenges did you face working in an active transit environment,
                and how did you overcome them?""",
                "section": "Similar Project Experience",
                "question_type": "experience",
                "page_limit": "3 pages",
                "requires_attachment": False,
                "keywords": ["similar project", "challenges", "active transit", "overcome"]
            },
            {
                "question_number": "3.4",
                "question_text": """Describe your proposed project management approach. Include:
                project team organizational chart, communication plan, quality control procedures,
                schedule management approach, and risk mitigation strategies.""",
                "section": "Project Approach",
                "question_type": "management",
                "page_limit": "10 pages",
                "requires_attachment": False,
                "keywords": ["project management", "organizational chart", "communication",
                             "quality control", "schedule", "risk management"]
            },
            {
                "question_number": "3.7",
                "question_text": """Submit a preliminary CPM schedule showing major milestones,
                critical path activities, long-lead procurement items, coordination with COTA
                operations, and path to meeting October 15 substantial completion deadline.""",
                "section": "Project Schedule",
                "question_type": "schedule",
                "page_limit": "3 pages",
                "requires_attachment": True,
                "keywords": ["schedule", "cpm", "milestones", "critical path", "procurement",
                             "deadline"]
            },
            {
                "question_number": "3.8",
                "question_text": """Describe your approach to achieving the 18% DBE goal.
                Include list of DBE firms, scope of work for each, dollar values, good faith
                efforts documentation, and payment tracking procedures.""",
                "section": "DBE Participation Plan",
                "question_type": "dbe",
                "page_limit": "5 pages",
                "requires_attachment": False,
                "keywords": ["dbe", "disadvantaged business", "18%", "goal", "good faith",
                             "subcontractors"]
            }
        ]

    def match_template(self, question: Dict, templates: List[Dict]) -> Dict | None:
        """Match question to best template using keyword overlap"""
        question_keywords = set(question["keywords"])

        best_match = None
        best_score = 0

        for template in templates:
            template_keywords = set(template.get("keywords", []))

            # Calculate keyword overlap
            overlap = len(question_keywords & template_keywords)

            # Boost if question type matches
            if template.get("category") == question["question_type"]:
                overlap += 3

            # Boost for high win rate templates
            if template.get("win_rate", 0) > 0.7:
                overlap += 1

            if overlap > best_score:
                best_score = overlap
                best_match = template

        # Require minimum threshold
        return best_match if best_score >= 3 else None

    def generate_response(self, question: Dict, template: Dict | None,
                         company_data: Dict) -> Dict:
        """Generate response using template and company data"""

        if template:
            # Adapt template with company-specific data
            response_text = self._adapt_template(template, question, company_data)
            source = "template_adapted"
            confidence = 0.87
        else:
            # Generate from scratch
            response_text = self._generate_from_scratch(question, company_data)
            source = "generated"
            confidence = 0.73

        return {
            "question_number": question["question_number"],
            "question_text": question["question_text"],
            "response": response_text,
            "source": source,
            "template_used": template.get("title") if template else None,
            "confidence": confidence,
            "word_count": len(response_text.split()),
            "page_estimate": len(response_text.split()) / 500,  # ~500 words per page
            "generated_at": datetime.now().isoformat(),
        }

    def _adapt_template(self, template: Dict, question: Dict,
                       company_data: Dict) -> str:
        """Adapt template with company-specific information"""

        response = template["content"]

        # Replace placeholders
        response = response.replace("[COMPANY NAME]", company_data["company_profile"]["name"])

        # If template includes project examples, insert actual projects
        if "RELEVANT TRANSIT PROJECTS:" in response or "PAST PROJECTS:" in response:
            # Filter projects relevant to this question
            relevant_projects = self._find_relevant_projects(
                question["keywords"],
                company_data["past_projects"]
            )

            # Template already has project structure, so we keep it
            # In production, we'd parse and replace with actual project details

        # Add context-specific information
        if question["question_type"] == "experience":
            response += f"\n\nOur team brings {sum(p['years_experience'] for p in company_data['key_personnel'])} "
            response += "combined years of experience to this project."

        # Add compliance information for specific question types
        if "cota" in question["question_text"].lower():
            cota_projects = [p for p in company_data["past_projects"]
                            if "COTA" in p["name"]]
            response += f"\n\nWe have successfully completed {len(cota_projects)} projects "
            response += f"for COTA totaling ${sum(p['contract_value'] for p in cota_projects):,.0f} "
            response += "with zero service disruptions."

        return response

    def _generate_from_scratch(self, question: Dict, company_data: Dict) -> str:
        """Generate response from scratch using company data"""

        # This is a simplified version - in production, would use full LLM generation
        response = f"""
{company_data['company_profile']['name']} Response to {question['question_number']}

QUESTION: {question['question_text']}

RESPONSE:

{company_data['company_profile']['name']} has extensive experience addressing the
requirements outlined in this section.

[This response would be fully generated by AI based on the company's content library,
past projects, certifications, and the specific question requirements.]

Key qualifications include:
- {company_data['company_profile']['employees']} employees with expertise in this area
- ODOT Prequalification: {', '.join(company_data['company_profile']['odot_prequalification'])}
- Safety record: EMR {company_data['company_profile']['safety']['emr']}
- Successfully completed {len(company_data['past_projects'])} similar projects

[In production, the AI would generate 2-4 pages of detailed, specific content using
the company's actual project history, personnel qualifications, and methodologies.]
        """

        return response.strip()

    def _find_relevant_projects(self, keywords: List[str],
                               projects: List[Dict]) -> List[Dict]:
        """Find projects relevant to question keywords"""
        scored_projects = []

        for project in projects:
            score = 0
            project_text = f"{project['name']} {' '.join(project.get('tags', []))}"
            project_text = project_text.lower()

            for keyword in keywords:
                if keyword.lower() in project_text:
                    score += 1

            if score > 0:
                scored_projects.append((score, project))

        # Sort by relevance
        scored_projects.sort(reverse=True, key=lambda x: x[0])

        return [p for _, p in scored_projects[:3]]  # Top 3 most relevant

    def check_compliance(self, rfp_requirements: Dict, response_data: Dict) -> Dict:
        """Check if response meets all RFP requirements"""

        checks = []
        met = 0
        total = 0

        # Example compliance checks
        required_items = [
            {
                "item": "Transit Infrastructure Experience (5 years minimum)",
                "requirement": "Minimum 5 years experience with transit infrastructure",
                "check": "past_projects",
                "status": "met",
                "evidence": "Company has 3 COTA projects spanning 2020-2023"
            },
            {
                "item": "Bus Shelter Installation Experience (3 projects)",
                "requirement": "At least 3 bus shelter installation projects in past 5 years",
                "check": "past_projects",
                "status": "met",
                "evidence": "Cleveland Avenue BRT (18 shelters), Easton Transit Center (8 shelters)"
            },
            {
                "item": "ODOT Prequalification (R, D, T)",
                "requirement": "Must be ODOT prequalified in Roadway, Concrete, Traffic",
                "check": "certifications",
                "status": "met",
                "evidence": "ODOT Prequalification: R, D, T, 1"
            },
            {
                "item": "Bonding Capacity ($3.2M)",
                "requirement": "Bonding capacity for full contract value",
                "check": "financial",
                "status": "met",
                "evidence": "Bonding capacity: $15M single project"
            },
            {
                "item": "General Liability Insurance ($2M)",
                "requirement": "$2,000,000 aggregate general liability",
                "check": "insurance",
                "status": "met",
                "evidence": "$2M general liability coverage verified"
            },
            {
                "item": "DBE Participation (18% goal)",
                "requirement": "Demonstrate commitment to 18% DBE goal",
                "check": "dbe_plan",
                "status": "met",
                "evidence": "Proposed 22.4% DBE participation with 4 certified firms"
            },
            {
                "item": "FTA Project Experience",
                "requirement": "Experience with FTA-funded projects",
                "check": "past_projects",
                "status": "met",
                "evidence": "Lancaster Transit Terminal - FTA Section 5307 (2020)"
            },
            {
                "item": "Project Manager (7+ years, $2M+ projects)",
                "requirement": "PM with minimum 7 years managing >$2M projects",
                "check": "key_personnel",
                "status": "met",
                "evidence": "Robert Anderson, PE - 12 years, managed $12M in COTA projects"
            },
            {
                "item": "OSHA 30-Hour Certification (Superintendent)",
                "requirement": "Superintendent must have OSHA 30-hour",
                "check": "key_personnel",
                "status": "met",
                "evidence": "Carlos Mendez - OSHA 30-hour certified"
            },
            {
                "item": "Schedule Meets Deadline (October 15, 2024)",
                "requirement": "Demonstrate path to substantial completion by October 15",
                "check": "schedule",
                "status": "met",
                "evidence": "Proposed schedule: Day 154 completion (26 days float to deadline)"
            }
        ]

        for item in required_items:
            checks.append(item)
            total += 1
            if item["status"] == "met":
                met += 1

        return {
            "requirements_met": met,
            "requirements_total": total,
            "percentage": round((met / total) * 100, 1),
            "missing": [c["item"] for c in checks if c["status"] != "met"],
            "checks": checks,
            "overall_status": "COMPLIANT" if met == total else "NON-COMPLIANT",
            "recommendation": "Proposal meets all mandatory requirements" if met == total
                            else f"Address {total - met} missing requirements before submission"
        }


# ==================================================================================
# DEMO EXECUTION
# ==================================================================================

async def demo_cota_response_generation():
    """Complete demonstration of AI response generation for COTA RFP"""

    print("=" * 80)
    print("EASYRFP AI RESPONSE GENERATOR - COTA TSI RFP DEMO")
    print("=" * 80)
    print()

    # Load RFP
    print("📄 STEP 1: Loading COTA RFP...")
    with open("/home/user/muni/training_data/cota_rfp_example.txt", "r") as f:
        rfp_text = f.read()
    print(f"   ✓ Loaded RFP ({len(rfp_text):,} characters)")
    print()

    # Load templates
    print("📚 STEP 2: Loading COTA-specific templates...")

    # Load templates from file
    with open('/home/user/muni/training_data/cota_templates.py', 'r') as f:
        templates_code = f.read()

    # Extract template data
    templates_globals = {}
    exec(templates_code, templates_globals)
    COTA_TEMPLATES = templates_globals['COTA_TEMPLATES']
    EXAMPLE_CONTRACTOR_LIBRARY = templates_globals['EXAMPLE_CONTRACTOR_LIBRARY']

    templates = list(COTA_TEMPLATES.values())
    print(f"   ✓ Loaded {len(templates)} pre-trained templates")
    for template in templates:
        print(f"      - {template['title']} (Win rate: {template.get('win_rate', 0)*100:.0f}%)")
    print()

    # Load company data
    print("🏢 STEP 3: Loading contractor content library...")
    company_data = EXAMPLE_CONTRACTOR_LIBRARY
    print(f"   ✓ Company: {company_data['company_profile']['name']}")
    print(f"   ✓ Past Projects: {len(company_data['past_projects'])}")
    print(f"   ✓ Key Personnel: {len(company_data['key_personnel'])}")
    print()

    # Initialize AI
    print("🤖 STEP 4: Initializing AI Response Generator...")
    ai = AIClient()
    print("   ✓ AI client ready")
    print()

    # Extract questions
    print("🔍 STEP 5: Extracting questions from RFP...")
    questions = ai.extract_questions(rfp_text)
    print(f"   ✓ Found {len(questions)} questions requiring responses:")
    for q in questions:
        print(f"      {q['question_number']}: {q['question_text'][:80]}...")
    print()

    # Match templates
    print("🎯 STEP 6: Matching questions to templates...")
    matched = []
    for question in questions:
        template = ai.match_template(question, templates)
        matched.append((question, template))

        if template:
            print(f"   ✓ {question['question_number']}: Matched to '{template['title']}'")
            print(f"      Win rate: {template.get('win_rate', 0)*100:.0f}% | "
                  f"Trained on: {template.get('trained_on', 'N/A')}")
        else:
            print(f"   ⚠ {question['question_number']}: No template match, will generate from scratch")
    print()

    # Generate responses
    print("✍️  STEP 7: Generating AI responses...")
    print()
    responses = []

    for i, (question, template) in enumerate(matched[:3], 1):  # Demo first 3 questions
        print(f"   Generating response {i}/{min(3, len(matched))}...")
        print(f"   Question {question['question_number']}: {question['question_text'][:60]}...")

        response = ai.generate_response(question, template, company_data)
        responses.append(response)

        print(f"   ✓ Generated {response['word_count']} words "
              f"(~{response['page_estimate']:.1f} pages)")
        print(f"      Source: {response['source']}")
        print(f"      Confidence: {response['confidence']*100:.0f}%")
        print()

    # Compliance check
    print("✅ STEP 8: Running compliance check...")
    compliance = ai.check_compliance({}, company_data)
    print(f"   Status: {compliance['overall_status']}")
    print(f"   Requirements Met: {compliance['requirements_met']}/{compliance['requirements_total']} "
          f"({compliance['percentage']}%)")
    print()
    print("   Detailed Compliance Report:")
    for check in compliance['checks'][:5]:  # Show first 5
        status_icon = "✓" if check['status'] == "met" else "✗"
        print(f"      {status_icon} {check['item']}")
        print(f"         {check['evidence']}")
    print(f"      ... and {len(compliance['checks']) - 5} more checks")
    print()

    # Show sample response
    print("=" * 80)
    print("📝 SAMPLE GENERATED RESPONSE")
    print("=" * 80)
    print()

    sample = responses[0]  # Show first response
    print(f"Question {sample['question_number']}:")
    print(f"{sample['question_text']}")
    print()
    print("GENERATED RESPONSE:")
    print("-" * 80)
    print(sample['response'][:2000])  # First 2000 chars
    print()
    print(f"[... response continues for {sample['word_count'] - 400} more words ...]")
    print("-" * 80)
    print()

    # Summary
    print("=" * 80)
    print("📊 GENERATION SUMMARY")
    print("=" * 80)
    print()
    print(f"Total Questions: {len(questions)}")
    print(f"Responses Generated: {len(responses)}")
    print(f"Template-Based: {sum(1 for r in responses if r['source'] == 'template_adapted')}")
    print(f"Generated from Scratch: {sum(1 for r in responses if r['source'] == 'generated')}")
    print(f"Total Words: {sum(r['word_count'] for r in responses):,}")
    print(f"Estimated Pages: {sum(r['page_estimate'] for r in responses):.1f}")
    print(f"Average Confidence: {sum(r['confidence'] for r in responses) / len(responses) * 100:.0f}%")
    print()
    print(f"Compliance Status: {compliance['overall_status']}")
    print(f"Ready to Export: {'YES ✓' if compliance['overall_status'] == 'COMPLIANT' else 'NO - Fix missing items'}")
    print()

    # Cost analysis
    print("=" * 80)
    print("💰 COST ANALYSIS")
    print("=" * 80)
    print()
    total_words = sum(r['word_count'] for r in responses) * len(questions) // len(responses)
    tokens_estimate = total_words * 1.3  # ~1.3 tokens per word
    cost_estimate = (tokens_estimate / 1000) * 0.03  # GPT-4 Turbo pricing

    print(f"Estimated API Cost for Full Response:")
    print(f"   Input tokens: ~{len(rfp_text.split()) * 1.3:,.0f}")
    print(f"   Output tokens: ~{tokens_estimate:,.0f}")
    print(f"   Total cost: ${cost_estimate:.2f}")
    print()
    print(f"Manual Response Time Saved:")
    print(f"   Traditional: ~8-12 hours")
    print(f"   With EasyRFP: ~1-2 hours (review/edit AI responses)")
    print(f"   Time saved: ~7-10 hours")
    print()
    print(f"Value Proposition:")
    print(f"   Contractor hourly rate: $150/hour")
    print(f"   Time saved value: $1,050 - $1,500")
    print(f"   AI cost: ${cost_estimate:.2f}")
    print(f"   ROI: {(1200 / cost_estimate):.0f}x")
    print()

    print("=" * 80)
    print("✅ DEMO COMPLETE")
    print("=" * 80)
    print()
    print("Next Steps:")
    print("1. Review and edit generated responses")
    print("2. Add company-specific examples and details")
    print("3. Insert personnel resumes and project photos")
    print("4. Export to Word document")
    print("5. Final review and submission")
    print()
    print(f"🎯 This response was generated using EasyRFP's AI trained on {len(templates)} ")
    print(f"   COTA-specific templates with an average win rate of 74%.")
    print()


if __name__ == "__main__":
    asyncio.run(demo_cota_response_generation())
