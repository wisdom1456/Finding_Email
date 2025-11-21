import asyncio
import os

import requests
from dotenv import load_dotenv

from supabase import create_client

# Load env
load_dotenv()
url = os.getenv("SUPABASE_URL")
service_key = os.getenv("SUPABASE_SERVICE_KEY")


async def test_create_case():
    print("--- Authenticating (Admin) ---")
    # Use service key to create/get user
    admin_client = create_client(url, service_key)

    email = "auto_test@example.com"
    password = "password123"

    user_id = None

    # 1. Create user if not exists
    try:
        # Check if user exists (hard to list, just try sign up)
        print("Creating user...")
        # admin.create_user auto-confirms email usually
        response = admin_client.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        user_id = response.user.id
        print(f"User created: {user_id}")
    except Exception as e:
        print(f"Create user failed (maybe exists): {e}")
        # Try to sign in to get ID
        try:
            resp = admin_client.auth.sign_in_with_password({"email": email, "password": password})
            user_id = resp.user.id
            token = resp.session.access_token
        except Exception as e2:
            print(f"Sign in failed: {e2}")
            return

    # 2. Ensure profile exists
    try:
        print("Ensuring profile...")
        admin_client.table("profiles").upsert(
            {"id": user_id, "email": email, "full_name": "Auto Test"}
        ).execute()
    except Exception as e:
        print(f"Profile upsert failed: {e}")

    # 3. Sign in as user to get fresh token (if we didn't get it above)
    # We need a token to call the API
    client = create_client(url, os.getenv("SUPABASE_ANON_KEY"))
    try:
        resp = client.auth.sign_in_with_password({"email": email, "password": password})
        token = resp.session.access_token
        print(f"--- Got Token: {token[:10]}... ---")
    except Exception as e:
        print(f"Client sign in failed: {e}")
        return

    # Now call the backend API
    api_url = "http://localhost:8000/api/cases"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"client_name": "Debug Client", "reference_number": "DBG-001", "description": "Debug case"}

    print(f"--- Calling API: {api_url} ---")
    response = requests.post(api_url, json=data, headers=headers)

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")


if __name__ == "__main__":
    asyncio.run(test_create_case())
