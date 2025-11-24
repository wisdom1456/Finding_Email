#!/bin/bash
set -e

echo ">>> VERCEL BUILD DEBUG START"
echo "Current directory: $(pwd)"
node -v
npm -v
ls -la

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
else
  echo "ERROR: frontend directory not found!"
  exit 1
fi

echo ">>> VERCEL BUILD COMPLETE"

