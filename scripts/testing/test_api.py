#!/usr/bin/env python3
"""Test OpenAI API with exact parameters used in fact extraction."""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from dotenv import load_dotenv
load_dotenv()

from legal_portal.utils.openai_client import OpenAIClient


def test_create_response():
    """Test create_response with same params as fact extraction.
    
    This uses the exact same parameters that the multi_stage_analyzer
    uses when calling the OpenAI API for fact extraction.
    """
    client = OpenAIClient()
    
    print("="*60)
    print("Testing OpenAI create_response (fact extraction params)")
    print("="*60)
    print("Model: gpt-5.2")
    print("reasoning_effort: medium")
    print("verbosity: high")
    print("max_output_tokens: 8192")
    print("-"*60)
    
    # Test prompt similar to what fact extraction uses
    test_prompt = """
    Extract key facts from this legal case:
    
    CLIENT INFORMATION:
    - Name: Mary Ann Rivera
    - Location: Santa Fe County, New Mexico
    
    CASE SUMMARY:
    - Issue: Real estate transaction dispute involving property boundaries
    - Documents reviewed: Survey documents, warranty deed, tax records
    - Key dates: Property purchased 2024, dispute arose 2025
    
    TASK:
    Extract and return a JSON object with the following structure:
    {
        "parties": [{"name": "...", "role": "...", "contact": "..."}],
        "timeline": [{"date": "...", "event": "...", "significance": "..."}],
        "financial_data": [{"description": "...", "amount": "...", "date": "..."}],
        "preliminary_issues": ["issue1", "issue2"],
        "jurisdiction_notes": "..."
    }
    """
    
    instructions = """You are a legal analyst extracting structured facts from case documents.
    Return ONLY valid JSON matching the requested structure.
    Be thorough but concise."""
    
    print("\nMaking API call...")
    
    try:
        result = client.create_response(
            model="gpt-5.2",
            input=test_prompt,
            instructions=instructions,
            reasoning_effort="medium",
            verbosity="high",
            max_output_tokens=8192,
        )
        
        content = result.get("content", "")
        usage = result.get("usage", {})
        
        print(f"\n{'='*60}")
        print("RESULT")
        print("="*60)
        print(f"Content length: {len(content)} chars")
        print(f"Finish reason: {result.get('finish_reason')}")
        print(f"Prompt tokens: {usage.get('prompt_tokens', 'N/A')}")
        print(f"Completion tokens: {usage.get('completion_tokens', 'N/A')}")
        print(f"Total tokens: {usage.get('total_tokens', 'N/A')}")
        
        if content:
            print(f"\nResponse preview (first 1000 chars):")
            print("-"*60)
            print(content[:1000])
            if len(content) > 1000:
                print("...")
            
            # Try to parse as JSON
            try:
                parsed = json.loads(content)
                print(f"\n✓ Valid JSON response")
                print(f"  Parties: {len(parsed.get('parties', []))}")
                print(f"  Timeline: {len(parsed.get('timeline', []))}")
                print(f"  Financial: {len(parsed.get('financial_data', []))}")
            except json.JSONDecodeError:
                print(f"\n⚠ Response is not valid JSON (may need extraction)")
            
            return True
        else:
            print(f"\n{'='*60}")
            print("*** EMPTY RESPONSE - THIS IS THE BUG ***")
            print("="*60)
            print("The API returned no content. This is what causes the")
            print("'GPT API returned an empty response for fact extraction' error.")
            print("\nCheck:")
            print("  1. reasoning_effort parameter placement")
            print("  2. max_completion_tokens vs max_tokens")
            print("  3. API response finish_reason")
            return False
            
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"ERROR: {type(e).__name__}")
        print("="*60)
        print(str(e))
        import traceback
        traceback.print_exc()
        return False


def test_simple_call():
    """Test a simple API call to verify connectivity."""
    client = OpenAIClient()
    
    print("="*60)
    print("Testing basic API connectivity")
    print("="*60)
    
    try:
        result = client.create_chat_completion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'API working' in 3 words or less"}],
            max_tokens=10,
        )
        print(f"Response: {result.get('content', 'No content')}")
        print("✓ Basic API connectivity works")
        return True
    except Exception as e:
        print(f"✗ API connectivity failed: {e}")
        return False


if __name__ == "__main__":
    # First test basic connectivity
    if not test_simple_call():
        print("\nBasic API test failed. Check your OPENAI_API_KEY.")
        sys.exit(1)
    
    print("\n")
    
    # Then test the full fact extraction call
    success = test_create_response()
    sys.exit(0 if success else 1)

