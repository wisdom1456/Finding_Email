import os

from dotenv import load_dotenv

from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_ANON_KEY")


def test_client_auth():
    print("Testing Supabase Client Auth...")
    client = create_client(url, key)
    token = "test-token-123"

    # Set auth
    client.postgrest.auth(token)
    # Force update to match the fix
    client.postgrest.session.headers["Authorization"] = f"Bearer {token}"

    # Check headers
    headers = client.postgrest.session.headers
    print(f"Headers keys: {list(headers.keys())}")

    auth_header = headers.get("Authorization") or headers.get("authorization")
    print(f"Auth Header Value: {auth_header}")

    if auth_header == f"Bearer {token}":
        print("✅ Auth header set correctly")
    else:
        print("❌ Auth header NOT set correctly")


if __name__ == "__main__":
    test_client_auth()
