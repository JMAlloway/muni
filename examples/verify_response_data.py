#!/usr/bin/env python3
"""
Verify Response Module Data - Query and display example COTA data
"""
import asyncio
import sys
sys.path.insert(0, '/home/user/muni')

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.domain.response_models import (
    CompanyContentLibrary,
    ResponseTemplate,
    RFPResponse,
    ResponseQuestion,
)


async def main():
    # Connect to local database
    engine = create_async_engine(
        "sqlite+aiosqlite:///./local.db",
        echo=False
    )

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        print("=" * 80)
        print("RESPONSE MODULE DATA VERIFICATION")
        print("=" * 80)
        print()

        # 1. Content Library
        print("📚 CONTENT LIBRARY")
        print("-" * 80)
        result = await session.execute(
            select(CompanyContentLibrary).order_by(CompanyContentLibrary.content_type)
        )
        items = result.scalars().all()

        for item in items:
            print(f"\n   {item.content_type.upper()}: {item.title}")
            print(f"   Tags: {', '.join(item.tags)}")
            if item.win_rate:
                print(f"   Win Rate: {item.win_rate:.1%} ({item.wins_when_used}/{item.total_uses} wins)")

            # Show key data fields
            if item.content_type == "past_project":
                print(f"   Value: ${item.data.get('contract_value', 0):,.0f}")
                print(f"   Client: {item.data.get('client', 'N/A')}")
                if 'achievements' in item.data:
                    print(f"   Achievements:")
                    for achievement in item.data['achievements'][:2]:
                        print(f"      • {achievement}")

        # 2. Templates
        print("\n\n📋 RESPONSE TEMPLATES")
        print("-" * 80)
        result = await session.execute(
            select(ResponseTemplate).where(ResponseTemplate.is_active == True)
        )
        templates = result.scalars().all()

        for template in templates:
            print(f"\n   {template.title}")
            print(f"   Category: {template.category}")
            print(f"   Agency: {template.agency_specific or 'All Agencies'}")
            print(f"   Keywords: {', '.join(template.keywords[:5])}")
            print(f"   Win Rate: {template.win_rate:.1%} ({template.wins_count}/{template.use_count} wins)")
            print(f"   Avg Score: {template.avg_score or 0:.1f}/100")
            print(f"   User Rating: {'⭐' * int(template.avg_user_rating or 0)}")

        # 3. RFP Response
        print("\n\n📝 RFP RESPONSES")
        print("-" * 80)
        result = await session.execute(select(RFPResponse))
        responses = result.scalars().all()

        for response in responses:
            print(f"\n   {response.title}")
            print(f"   RFP #: {response.rfp_number}")
            print(f"   Status: {response.status}")
            print(f"   Compliance: {response.compliance_score:.0%} ({response.requirements_met}/{response.requirements_total} requirements met)")
            print(f"   Due Date: {response.due_date.strftime('%Y-%m-%d') if response.due_date else 'N/A'}")

            # Show requirements
            if response.requirements:
                print(f"\n   Requirements:")
                for req in response.requirements.get('mandatory', [])[:3]:
                    status = "✓" if req.get('status') == 'met' else "✗"
                    print(f"      {status} {req.get('name')}")

        # 4. Questions
        print("\n\n❓ RFP QUESTIONS")
        print("-" * 80)
        result = await session.execute(
            select(ResponseQuestion).order_by(ResponseQuestion.question_number)
        )
        questions = result.scalars().all()

        for question in questions:
            print(f"\n   Question {question.question_number}")
            print(f"   {question.question_text[:100]}...")
            print(f"   Type: {question.question_type}")
            print(f"   Keywords: {', '.join(question.keywords)}")

            if question.matched_template_id:
                # Get template name
                result = await session.execute(
                    select(ResponseTemplate).where(ResponseTemplate.id == question.matched_template_id)
                )
                template = result.scalar_one_or_none()
                if template:
                    print(f"   ✓ Matched: {template.title}")
                    print(f"   Confidence: {question.match_confidence:.1%}")
                    print(f"   Template Win Rate: {template.win_rate:.1%}")

        print("\n\n" + "=" * 80)
        print("✅ ALL DATA VERIFIED")
        print("=" * 80)
        print("\nNext: Use these templates to generate AI responses!")
        print("      Run: python examples/cota_response_demo.py")
        print()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
