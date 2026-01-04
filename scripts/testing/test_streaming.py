#!/usr/bin/env python3
"""Test the streaming analysis functionality."""
import os
import sys
import asyncio

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
os.environ["LOG_LEVEL"] = "DEBUG"

from dotenv import load_dotenv
load_dotenv()

from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.core.data_models import DocumentSummaryStructured


async def test_streaming():
    """Test the streaming analysis with sample data."""
    print("=" * 60)
    print("STREAMING ANALYSIS TEST")
    print("=" * 60)
    print()
    
    # Sample intake content
    intake_content = """
    Client Information:
    - Name: John Smith
    - Address: 123 Main St, Santa Fe, NM 87501
    - Phone: 505-555-1234
    
    Case Summary:
    Client purchased property at 456 Oak Ave from seller Jane Doe in March 2024.
    After closing, client discovered the property has easement issues not disclosed.
    Seller's survey was inaccurate - neighbor's driveway encroaches 5 feet onto property.
    Client paid $450,000 for the property. Estimated cost to resolve: $25,000-50,000.
    
    Desired Outcome:
    - Recovery of costs to fix easement issue
    - Compensation for diminished property value
    """
    
    # Sample documents
    doc_summaries = [
        DocumentSummaryStructured(
            document_name="Purchase_Agreement.pdf",
            document_type="contract",
            executive_summary="Real estate purchase agreement dated March 2024 for $450,000. Contains standard warranty of title provisions.",
            key_content="Buyer: John Smith. Seller: Jane Doe. Property: 456 Oak Ave, Santa Fe NM. Purchase Price: $450,000.",
        ),
        DocumentSummaryStructured(
            document_name="Title_Survey.pdf",
            document_type="survey",
            executive_summary="Survey showing property boundaries. Does not show neighbor's driveway encroachment.",
            key_content="Survey dated February 2024. Property boundaries marked. No easements shown.",
        ),
        DocumentSummaryStructured(
            document_name="Neighbor_Letter.pdf",
            document_type="correspondence",
            executive_summary="Letter from neighbor claiming driveway easement from 1985 deed.",
            key_content="Neighbor claims prescriptive easement rights. Driveway in use since 1985.",
        ),
    ]
    
    print(f"Testing with {len(doc_summaries)} documents")
    print(f"Intake content: {len(intake_content)} chars")
    print()
    print("Starting streaming analysis...")
    print("-" * 60)
    print()
    
    openai_client = OpenAIClient()
    analyzer = MultiStageAnalyzer(openai_client=openai_client)
    
    token_count = 0
    start_time = asyncio.get_event_loop().time()
    
    try:
        async for token in analyzer.analyze_streaming(
            intake_content=intake_content,
            document_summaries=doc_summaries,
            jurisdiction="New Mexico",
        ):
            print(token, end="", flush=True)
            token_count += 1
    except Exception as e:
        print(f"\n\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    elapsed = asyncio.get_event_loop().time() - start_time
    
    print()
    print()
    print("-" * 60)
    print(f"STREAMING COMPLETE")
    print(f"  Duration: {elapsed:.1f}s")
    print(f"  Tokens received: {token_count}")
    print(f"  Avg tokens/sec: {token_count / elapsed:.1f}")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_streaming())
    sys.exit(0 if success else 1)

