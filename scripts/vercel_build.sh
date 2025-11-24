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

echo ">>> Build complete"
