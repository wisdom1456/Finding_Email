#!/usr/bin/env python3
"""
Test script to validate the PromptAndApiService constructor fix.
This script attempts to instantiate EmailGeneratorV2 which should no longer throw the TypeError.
"""

import sys
import traceback
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_email_generator_initialization():
    """Test that EmailGeneratorV2 can be initialized without TypeError."""
    try:
        print("🧪 Testing EmailGeneratorV2 initialization...")
        
        # Import the class that was causing the TypeError
        from backend_logic.email_generator import EmailGeneratorV2
        
        print("✅ Import successful")
        
        # Create a mock client (the required parameter)
        class MockClient:
            pass
        
        mock_client = MockClient()
        
        # Try to initialize it (this previously caused the PromptAndApiService TypeError)
        email_gen = EmailGeneratorV2(client=mock_client)
        
        print("✅ EmailGeneratorV2 initialization successful!")
        print("🎉 PromptAndApiService TypeError has been resolved!")
        
        return True
        
    except TypeError as e:
        print(f"❌ TypeError still exists: {e}")
        print("📍 Stack trace:")
        traceback.print_exc()
        return False
        
    except Exception as e:
        print(f"⚠️  Other error occurred (but not the target TypeError): {e}")
        print("📍 Stack trace:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🐛 TESTING PROMPTANDAPISERVICE CONSTRUCTOR FIX")
    print("=" * 60)
    
    success = test_email_generator_initialization()
    
    print("=" * 60)
    if success:
        print("✅ TEST PASSED: Constructor fix is working!")
    else:
        print("❌ TEST FAILED: Constructor issue persists")
    print("=" * 60)
    
    sys.exit(0 if success else 1)