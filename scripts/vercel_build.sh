#!/bin/bash
set -e

echo ">>> Building frontend with SvelteKit"
cd frontend
npm ci --legacy-peer-deps
npm run build
cd ..

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
