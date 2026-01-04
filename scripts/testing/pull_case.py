#!/usr/bin/env python3
"""Pull case data from Supabase for local testing."""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client


def pull_case(case_id: str = None, client_name: str = None):
    """Fetch case and documents from Supabase.
    
    Args:
        case_id: Direct case ID to fetch
        client_name: Client name to search for (partial match)
    
    Returns:
        Tuple of (case, documents) or None if not found
    """
    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_KEY")
    )
    
    # Find case by ID or client name
    if client_name:
        result = supabase.table("cases").select("*").ilike("client_name", f"%{client_name}%").execute()
    else:
        result = supabase.table("cases").select("*").eq("id", case_id).execute()
    
    if not result.data:
        print(f"No case found for: {client_name or case_id}")
        return None
    
    case = result.data[0]
    print(f"Found case: {case['client_name']} (ID: {case['id']})")
    print(f"  Matter: {case.get('matter_description', 'N/A')}")
    print(f"  Created: {case.get('created_at', 'N/A')}")
    
    # Fetch documents
    docs = supabase.table("documents").select("*").eq("case_id", case["id"]).execute()
    print(f"Found {len(docs.data)} documents")
    
    # List documents
    for doc in docs.data:
        text_len = len(doc.get("extracted_text", "") or "")
        print(f"  - {doc.get('file_name', 'unknown')} ({text_len} chars)")
    
    # Create snapshot directory
    safe_name = case['client_name'].lower().replace(' ', '_').replace("'", "")
    snapshot_dir = os.path.join(os.path.dirname(__file__), '..', 'snapshots', safe_name)
    os.makedirs(snapshot_dir, exist_ok=True)
    
    # Save snapshot
    snapshot_path = os.path.join(snapshot_dir, "case.json")
    with open(snapshot_path, "w") as f:
        json.dump({
            "case": case,
            "documents": docs.data,
            "pulled_at": str(__import__('datetime').datetime.now())
        }, f, indent=2, default=str)
    
    print(f"\nSaved to {snapshot_path}")
    return case, docs.data


def list_cases():
    """List all available cases."""
    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_KEY")
    )
    
    result = supabase.table("cases").select("id, client_name, matter_description, created_at").order("created_at", desc=True).limit(20).execute()
    
    print("Recent cases:")
    print("-" * 60)
    for case in result.data:
        print(f"  {case['client_name']}")
        print(f"    ID: {case['id']}")
        print(f"    Matter: {case.get('matter_description', 'N/A')[:50]}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            list_cases()
        else:
            # Argument is client name
            pull_case(client_name=" ".join(sys.argv[1:]))
    else:
        # Default to Mary Ann Rivera
        pull_case(client_name="Mary Ann Rivera")

