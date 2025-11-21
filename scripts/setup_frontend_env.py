#!/usr/bin/env python3
"""Setup frontend .env file with Supabase credentials from root .env
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load root .env
project_root = Path(__file__).parent.parent
root_env = project_root / ".env"
load_dotenv(root_env)

# Get credentials
supabase_url = os.getenv("SUPABASE_URL")
supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")

if not supabase_url or not supabase_anon_key:
    print("❌ Missing SUPABASE_URL or SUPABASE_ANON_KEY in root .env file")
    exit(1)

# Create frontend .env
frontend_dir = project_root / "frontend"
frontend_env = frontend_dir / ".env"

env_content = f"""# Supabase Configuration (Auto-generated from root .env)
PUBLIC_SUPABASE_URL={supabase_url}
PUBLIC_SUPABASE_ANON_KEY={supabase_anon_key}

# API Configuration
PUBLIC_API_URL=http://localhost:8000
"""

# Write file
frontend_env.write_text(env_content)

print("=" * 60)
print("FRONTEND ENVIRONMENT SETUP")
print("=" * 60)
print(f"✅ Created: {frontend_env}")
print(f"   PUBLIC_SUPABASE_URL: {supabase_url}")
print(f"   PUBLIC_SUPABASE_ANON_KEY: {supabase_anon_key[:20]}...")
print("   PUBLIC_API_URL: http://localhost:8000")
print("\n✅ Frontend is now configured!")
print("\nNext steps:")
print("  cd frontend")
print("  npm run dev")
