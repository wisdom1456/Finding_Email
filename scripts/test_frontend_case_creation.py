#!/usr/bin/env python3
"""Test case creation as if coming from the frontend.
This simulates the actual frontend request flow.
"""

import os

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
API_URL = "http://localhost:8000"


def main():
    print("=== Testing Frontend Case Creation Flow ===\n")

    # Step 1: Login with existing user
    print("Step 1: Attempting login...")
    login_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"

    login_data = {"email": "testuser123@gmail.com", "password": "TestPassword123!"}

    headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}

    try:
        response = requests.post(login_url, json=login_data, headers=headers)
        print(f"Login status: {response.status_code}")

        if response.status_code != 200:
            print(f"Login failed: {response.text}")
            return

        auth_data = response.json()
        token = auth_data.get("access_token")
        user_id = auth_data.get("user", {}).get("id")

        print("✅ Login successful")
        print(f"   User ID: {user_id}")
        print(f"   Token (first 30 chars): {token[:30]}...")

    except Exception as e:
        print(f"❌ Login error: {e}")
        return

    # Step 2: Create case via API
    print("\nStep 2: Creating case via API...")
    print(f"   URL: {API_URL}/api/cases")

    case_data = {
        "client_name": "Frontend Test Client",
        "reference_number": "FE-TEST-001",
        "description": "Testing from frontend simulation",
        "status": "pending",
    }

    api_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"   Headers: Authorization: Bearer {token[:30]}...")
    print(f"   Body: {case_data}")

    try:
        response = requests.post(f"{API_URL}/api/cases", json=case_data, headers=api_headers)

        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📊 Response Body: {response.text}")

        if response.status_code == 201:
            print("\n✅ SUCCESS: Case created successfully!")
            case = response.json()
            print(f"   Case ID: {case['id']}")
            print(f"   Client Name: {case['client_name']}")
        else:
            print(f"\n❌ FAILED: Status {response.status_code}")
            print(f"   Error: {response.text}")

    except Exception as e:
        print(f"\n❌ API call error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
