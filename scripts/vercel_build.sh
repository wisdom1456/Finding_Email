#!/bin/bash
set -e

echo ">>> Building frontend with SvelteKit"
cd frontend
npm ci --legacy-peer-deps
npm run build
cd ..

echo ">>> Moving SvelteKit build output to root"
if [ -d "frontend/.vercel/output" ]; then
  mkdir -p .vercel
  cp -r frontend/.vercel/output .vercel/
  echo "✅ Build output moved to .vercel/output"
else
  echo "⚠️ WARNING: frontend/.vercel/output not found"
  exit 1
fi

echo ">>> Installing Python dependencies"
if [ -f "api/requirements.txt" ]; then
  cd api
  mkdir -p packages
  python3 -m pip install -r requirements.txt --target packages --upgrade
  echo "✅ Python dependencies installed to api/packages/"
  cd ..
else
  echo "⚠️ WARNING: api/requirements.txt not found"
fi

echo ">>> Verifying critical Python imports for API runtime"
python3 - <<'PY'
import importlib
import sys

sys.path.insert(0, "api/packages")
sys.path.insert(0, "src")
sys.path.insert(0, ".")

# Import the real serverless entrypoint to catch startup-time missing deps.
module = importlib.import_module("api.index")
assert hasattr(module, "app"), "api.index did not expose app"

print("✅ API runtime import smoke check passed")
PY

echo ">>> Verifying environment variables"
echo "Checking required environment variables..."

# Check Supabase variables (required)
if [ -n "$SUPABASE_URL" ]; then
    echo "✅ SUPABASE_URL is set"
else
    echo "❌ SUPABASE_URL is NOT set"
fi

if [ -n "$SUPABASE_SERVICE_KEY" ]; then
    echo "✅ SUPABASE_SERVICE_KEY is set"
else
    echo "❌ SUPABASE_SERVICE_KEY is NOT set"
fi

if [ -n "$SUPABASE_ANON_KEY" ]; then
    echo "✅ SUPABASE_ANON_KEY is set"
else
    echo "❌ SUPABASE_ANON_KEY is NOT set"
fi

# Check optional but important variables
echo "Checking optional environment variables..."

if [ -n "$OPENAI_API_KEY" ]; then
    echo "✅ OPENAI_API_KEY is set"
else
    echo "⚠️ OPENAI_API_KEY is not set (optional but needed for analysis)"
fi

if [ -n "$CLIO_CLIENT_ID" ]; then
    echo "✅ CLIO_CLIENT_ID is set"
else
    echo "⚠️ CLIO_CLIENT_ID is not set (optional but needed for Clio integration)"
fi

if [ -n "$CLIO_CLIENT_SECRET" ]; then
    echo "✅ CLIO_CLIENT_SECRET is set"
else
    echo "⚠️ CLIO_CLIENT_SECRET is not set (optional but needed for Clio integration)"
fi

echo ">>> Environment variable check complete"
echo ">>> Build complete"
