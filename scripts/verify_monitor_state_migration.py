#!/usr/bin/env python3
"""Verify that the monitor_state migration has been applied correctly.

Usage:
    python3 scripts/verify_monitor_state_migration.py

Expected output if successful:
    ✅ monitor_state table exists
    ✅ Seed row exists: {'key': 'last_restart_at', 'value': None, ...}
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Load .env from project root
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)


def verify_migration():
    """Verify monitor_state table and seed data."""
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not url or not service_key:
        print("❌ SUPABASE_URL or SUPABASE_SERVICE_KEY not in .env")
        return False

    try:
        # Create client
        client = create_client(url, service_key)
        print("✅ Supabase client created")

        # Check if table exists and has seed data
        result = client.table("monitor_state").select("*").execute()
        print("✅ monitor_state table exists")

        # Verify seed data
        data = result.data
        if len(data) < 1:
            print("❌ No seed data found in monitor_state")
            return False

        seed_row = None
        for row in data:
            if row.get("key") == "last_restart_at":
                seed_row = row
                break

        if seed_row is None:
            print("❌ Seed row 'last_restart_at' not found")
            print(f"   Found rows: {[r.get('key') for r in data]}")
            return False

        print(f"✅ Seed row exists: {seed_row}")

        # Verify structure
        required_fields = {"key", "value", "updated_at"}
        actual_fields = set(seed_row.keys())
        if not required_fields.issubset(actual_fields):
            print(f"❌ Missing fields: {required_fields - actual_fields}")
            return False

        print("✅ All required fields present")

        # Verify seed value is NULL
        if seed_row.get("value") is not None:
            print(f"⚠️  Seed value is {seed_row.get('value')}, expected None")
            return False

        print("✅ Seed value is None (as expected)")

        print()
        print("=" * 60)
        print("✅ MIGRATION VERIFICATION SUCCESSFUL")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"❌ Verification failed: {str(e)}")
        if "does not exist" in str(e).lower() or "PGRST205" in str(e):
            print()
            print("The monitor_state table has not been created yet.")
            print()
            print("To apply the migration:")
            print("  1. Visit: https://app.supabase.com/project/nqjepycmhddfekeufcle/sql/new")
            print("  2. Open: supabase/migrations/20260419000000_add_monitor_state.sql")
            print("  3. Copy and paste the SQL, then click Run")
        return False


if __name__ == "__main__":
    success = verify_migration()
    sys.exit(0 if success else 1)
