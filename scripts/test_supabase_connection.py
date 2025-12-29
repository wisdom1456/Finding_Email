#!/usr/bin/env python3
"""Test Supabase connection and verify schema is applied.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from supabase import create_client

# Load .env from project root
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)


def test_connection():
    """Test connection to Supabase and check schema."""
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    anon_key = os.getenv("SUPABASE_ANON_KEY")

    print("=" * 60)
    print("SUPABASE CONNECTION TEST")
    print("=" * 60)

    # Check environment variables
    if not url:
        print("❌ SUPABASE_URL not found in .env file")
        return False

    if not service_key:
        print("❌ SUPABASE_SERVICE_KEY not found in .env file")
        return False

    if not anon_key:
        print("⚠️  SUPABASE_ANON_KEY not found in .env file")
        print("   (Required for frontend authentication)")

    print("✅ Environment variables loaded")
    print(f"   URL: {url}")
    print(f"   Service Key: {service_key[:20]}...")
    if anon_key:
        print(f"   Anon Key: {anon_key[:20]}...")

    print("\n" + "=" * 60)
    print("Testing connection...")
    print("=" * 60)

    try:
        # Create client
        client = create_client(url, service_key)
        print("✅ Supabase client created successfully")

        # Test each table
        tables_to_check = ["profiles", "cases", "documents", "analysis_results"]
        existing_tables = []
        missing_tables = []

        print("\nChecking tables...")
        for table_name in tables_to_check:
            try:
                client.table(table_name).select("count", count="exact").limit(0).execute()
                existing_tables.append(table_name)
                print(f"   ✅ {table_name} - exists")
            except Exception as e:
                if "relation" in str(e).lower() and "does not exist" in str(e).lower():
                    missing_tables.append(table_name)
                    print(f"   ❌ {table_name} - not found")
                else:
                    print(f"   ⚠️  {table_name} - error: {str(e)}")

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        if len(existing_tables) == len(tables_to_check):
            print("✅ All tables exist - schema is properly applied!")
            return True
        elif len(existing_tables) > 0:
            print(f"⚠️  Partial schema: {len(existing_tables)}/{len(tables_to_check)} tables exist")
            print(f"   Existing: {', '.join(existing_tables)}")
            print(f"   Missing: {', '.join(missing_tables)}")
            return False
        else:
            print("❌ No tables found - schema needs to be applied")
            print("\n📋 Next steps:")
            print("   1. Go to https://app.supabase.com")
            print("   2. Select your project")
            print("   3. Go to SQL Editor")
            print("   4. Copy and execute: supabase/schema.sql")
            return False

    except Exception as e:
        print(f"❌ Connection failed: {str(e)}")
        return False


if __name__ == "__main__":
    success = test_connection()
    exit(0 if success else 1)
