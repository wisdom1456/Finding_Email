#!/bin/bash
set -e

echo ">>> VERCEL BUILD DEBUG START"
echo "Current directory: $(pwd)"
node -v
npm -v
ls -la

echo ">>> Checking Environment Variables..."
if [ -z "$PUBLIC_SUPABASE_URL" ]; then
  echo "WARNING: PUBLIC_SUPABASE_URL is not set!"
else
  echo "PUBLIC_SUPABASE_URL is set."
fi

if [ -z "$PUBLIC_SUPABASE_ANON_KEY" ]; then
  echo "WARNING: PUBLIC_SUPABASE_ANON_KEY is not set!"
else
  echo "PUBLIC_SUPABASE_ANON_KEY is set."
fi

if [ -d "frontend" ]; then
  echo "Found frontend directory"
  cd frontend
  echo "Changed to frontend directory: $(pwd)"
  ls -la
  
  echo ">>> Installing dependencies (npm ci)..."
  # Use --ignore-scripts to prevent any recursive hooks from firing
  npm ci --ignore-scripts --legacy-peer-deps
  
  # Run svelte-kit sync manually since we ignored scripts
  echo ">>> Running svelte-kit sync..."
  npx svelte-kit sync
  
  echo ">>> Building..."
  npm run build
  
  echo ">>> Moving build output to root..."
  cd ..
  mkdir -p .vercel
  # Clean up any existing output to avoid copy issues
  rm -rf .vercel/output
  
  # Copy the output directory from frontend to root
  if [ -d "frontend/.vercel/output" ]; then
      cp -r frontend/.vercel/output .vercel/
      echo "Build output moved to root .vercel/output"
      ls -la .vercel/output
  else
      echo "ERROR: frontend/.vercel/output not found! Adapter might not have run correctly."
      ls -la frontend/.vercel || echo "frontend/.vercel does not exist"
      exit 1
  fi
else
  echo "ERROR: frontend directory not found!"
  exit 1
fi

echo ">>> Installing Python dependencies for serverless functions..."
if [ -f "api/requirements.txt" ]; then
  echo "Found api/requirements.txt"
  cd api
  pip install -r requirements.txt --target .
  cd ..
  echo "Python dependencies installed"
else
  echo "WARNING: api/requirements.txt not found"
fi

echo ">>> VERCEL BUILD COMPLETE"

