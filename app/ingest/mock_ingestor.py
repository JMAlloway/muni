from datetime import datetime, timedelta
from .base import RawOpportunity

def fetch() -> list[RawOpportunity]:
    now = datetime.utcnow()
    return [
        RawOpportunity(
            source="mock_city_columbus",
            source_url="https://example.columbus.gov/bids/123",
            title="Columbus — Storm Sewer Rehab 2025",
            summary="Rehab of 1.2 miles of storm sewer",
            category="construction",
            agency_name="City of Columbus",
            location_geo="Franklin County, OH",
            posted_date=now - timedelta(days=2),
            due_date=now + timedelta(days=14),
        ),
        RawOpportunity(
            source="mock_delaware_county",
            source_url="https://example.delawarecountyohio.gov/rfp/abc",
            title="Delaware County — IT Managed Services",
            summary="RFP for managed services provider",
            category="it",
            agency_name="Delaware County",
            location_geo="Delaware County, OH",
            posted_date=now - timedelta(days=1),
            due_date=now + timedelta(days=21),
        ),
    ]
