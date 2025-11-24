#!/bin/bash
set -e

echo ">>> VERCEL BUILD DEBUG START"
echo "Current directory: $(pwd)"
ls -la

if [ -d "frontend" ]; then
  echo "Found frontend directory"
  cd frontend
  echo "Changed to frontend directory: $(pwd)"
  ls -la
  
  echo ">>> Installing dependencies..."
  npm install
  
  echo ">>> Building..."
  npm run build
else
  echo "ERROR: frontend directory not found!"
  exit 1
fi

echo ">>> VERCEL BUILD COMPLETE"

