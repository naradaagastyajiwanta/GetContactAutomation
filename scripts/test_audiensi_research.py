"""
Test script for audiensi research using Gemini AI.
Run: python scripts/test_audiensi_research.py
"""

import sys
import os
import asyncio
import json

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


async def test_gemini_research():
    """Test Gemini AI research for a sample university."""
    from orchestrator.audiensi_research import (
        research_university_background,
        format_research_wa_message,
    )

    print("=" * 60)
    print("Testing Gemini AI Audiensi Research")
    print("=" * 60)

    # Test with a well-known university
    university = "Universitas Muhammadiyah Jakarta"
    city = "Jakarta Selatan"
    schedule_date = "2025-06-15"

    print(f"\nResearching: {university}")
    print(f"City: {city}")
    print(f"Date: {schedule_date}")
    print("-" * 60)

    result = await research_university_background(
        university_name=university,
        university_city=city,
        schedule_date=schedule_date,
    )

    print("\n📊 Research Result (JSON):")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Format as WA message
    print("\n" + "=" * 60)
    print("📱 WhatsApp Message Preview:")
    print("=" * 60)
    wa_msg = format_research_wa_message(
        university_name=university,
        schedule_date=schedule_date,
        schedule_time="10:00",
        research=result,
    )
    print(wa_msg)

    # Check for errors
    if "error" in result:
        print(f"\n⚠️ Error in result: {result['error']}")
    else:
        print("\n✅ Research completed successfully!")

    return result


if __name__ == "__main__":
    result = asyncio.run(test_gemini_research())
