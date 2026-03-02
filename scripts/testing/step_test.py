#!/usr/bin/env python3
"""Run analysis step-by-step to isolate failures."""
import os
import sys
import json
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
os.environ["LOG_LEVEL"] = "DEBUG"

from dotenv import load_dotenv
load_dotenv()

from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.core.data_models import DocumentSummaryStructured

# Initialize shared client
openai_client = OpenAIClient()


async def test_step_by_step(snapshot_path: str):
    """Run each analysis stage separately to isolate failures.
    
    Args:
        snapshot_path: Path to the case.json snapshot file
    """
    with open(snapshot_path) as f:
        data = json.load(f)
    
    case = data["case"]
    documents = data["documents"]
    
    print(f"\n{'='*60}")
    print(f"Step-by-Step Analysis: {case['client_name']}")
    print(f"Documents: {len(documents)}")
    print(f"{'='*60}\n")
    
    # Build document summaries from extracted text
    doc_summaries = []
    intake_content = ""
    
    for doc in documents:
        file_name = doc.get("file_name", "unknown")
        extracted_text = doc.get("extracted_text", "") or ""
        
        if extracted_text:
            # Derive doc_type from metadata or file_type
            metadata = doc.get("metadata") or {}
            doc_type = (
                metadata.get("classification")
                or metadata.get("attorney_enrichment", {}).get("document_type_override")
                or doc.get("file_type", "document")
            )
            
            # Create DocumentSummaryStructured object
            doc_summary = DocumentSummaryStructured(
                document_name=file_name,
                document_type=doc_type,
                executive_summary=extracted_text[:500],
                key_content=extracted_text[:5000],  # First 5000 chars
            )
            doc_summaries.append(doc_summary)
            
            # Find intake form
            if "intake" in file_name.lower():
                intake_content = extracted_text
                print(f"  Found intake form: {file_name} ({len(extracted_text)} chars)")
    
    print(f"  Processed {len(doc_summaries)} documents with text")
    
    if not intake_content:
        print("\n  WARNING: No intake form found, using first document")
        if doc_summaries:
            intake_content = doc_summaries[0].key_content or ""
    
    # Determine jurisdiction from case data
    jurisdiction = case.get("jurisdiction", "New Mexico")
    print(f"  Jurisdiction: {jurisdiction}")
    
    # Create analyzer with OpenAI client
    analyzer = MultiStageAnalyzer(openai_client=openai_client)
    
    # ============================================================
    # STEP 1: Test fact extraction (THIS IS WHERE THE ERROR OCCURS)
    # ============================================================
    print(f"\n{'='*60}")
    print("STEP 1: Fact Matrix Extraction")
    print("This is where 'GPT API returned an empty response' occurs")
    print("="*60)
    
    try:
        fact_matrix = await analyzer._extract_fact_matrix(
            intake_content=intake_content,
            document_summaries=doc_summaries,
            jurisdiction=jurisdiction
        )
        
        print(f"\n  SUCCESS: Fact matrix extracted!")
        print(f"  - Parties: {len(fact_matrix.parties)}")
        print(f"  - Timeline events: {len(fact_matrix.timeline)}")
        print(f"  - Financial items: {len(fact_matrix.financial_data)}")
        print(f"  - Preliminary issues: {fact_matrix.preliminary_issues}")
        
    except ValueError as e:
        print(f"\n  FAILED: {e}")
        print("\n  This is the exact error we're debugging!")
        print("  Check the logs above for [OPENAI:REQUEST] and [OPENAI:RESPONSE]")
        return None
        
    except Exception as e:
        print(f"\n  ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # ============================================================
    # STEP 2: Issue mapping (only if step 1 succeeded)
    # ============================================================
    print(f"\n{'='*60}")
    print("STEP 2: Issue Mapping")
    print("="*60)
    
    try:
        # Use preliminary issues from fact matrix as case type hint
        case_type = "contract_dispute"  # Default - could be enhanced
        if fact_matrix.preliminary_issues:
            issues_text = " ".join(fact_matrix.preliminary_issues).lower()
            if "real estate" in issues_text:
                case_type = "real_estate"
            elif "employment" in issues_text:
                case_type = "employment"
        print(f"  Case type: {case_type}")
        
        issue_map = await analyzer._map_legal_issues(
            fact_matrix=fact_matrix,
            intake_content=intake_content,
            case_type=case_type,
            legal_issues_hint=fact_matrix.preliminary_issues,
            jurisdiction=jurisdiction
        )
        
        print(f"\n  SUCCESS: Issues mapped!")
        print(f"  - Primary issues: {len(issue_map.primary_issues)}")
        for issue in issue_map.primary_issues[:3]:
            print(f"    - {issue.issue_name}: {issue.category}")
            
    except Exception as e:
        print(f"\n  ERROR in step 2: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return fact_matrix
    
    print(f"\n{'='*60}")
    print("All steps completed successfully!")
    print("="*60)
    
    return fact_matrix


def find_snapshot(name: str = None) -> str:
    """Find snapshot path by name or use default."""
    snapshots_dir = os.path.join(os.path.dirname(__file__), '..', 'snapshots')
    
    if name:
        safe_name = name.lower().replace(' ', '_').replace("'", "")
        path = os.path.join(snapshots_dir, safe_name, "case.json")
        if os.path.exists(path):
            return path
        if os.path.exists(name):
            return name
    
    default_path = os.path.join(snapshots_dir, "mary_ann_rivera", "case.json")
    if os.path.exists(default_path):
        return default_path
    
    print("No snapshot found. Run 'make pull-case' first.")
    return None


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else None
    snapshot = find_snapshot(name)
    
    if snapshot:
        print(f"Using snapshot: {snapshot}")
        asyncio.run(test_step_by_step(snapshot))
    else:
        sys.exit(1)

