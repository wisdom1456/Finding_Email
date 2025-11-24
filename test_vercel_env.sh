#!/bin/bash

# Test Vercel Environment Variables
# This script helps verify that environment variables are set correctly in Vercel

echo "🔍 Testing Vercel Deployment Environment Variables"
echo "=================================================="
echo ""

# Get the Vercel deployment URL from user
read -p "Enter your Vercel deployment URL (e.g., https://finding-emails-xxx.vercel.app): " VERCEL_URL

# Remove trailing slash if present
VERCEL_URL=${VERCEL_URL%/}

echo ""
echo "Testing: $VERCEL_URL"
echo ""

# Test 1: Basic health check
echo "1️⃣ Testing /api/health endpoint..."
echo ""

HEALTH_RESPONSE=$(curl -s "${VERCEL_URL}/api/health")
echo "Response: $HEALTH_RESPONSE"
echo ""

# Check if response contains "unhealthy"
if echo "$HEALTH_RESPONSE" | grep -q "unhealthy"; then
    echo "❌ Health check failed - environment variables are missing"
    echo ""
    echo "Missing variables:"
    echo "$HEALTH_RESPONSE" | grep -o '"missing_required":\[.*\]' || echo "Unknown"
    echo ""
elif echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo "✅ Health check passed - all required environment variables are set"
    echo ""
else
    echo "⚠️  Could not determine health status"
    echo "This might indicate a more serious problem with the deployment"
    echo ""
fi

# Test 2: Detailed health check
echo "2️⃣ Testing /api/health/detailed endpoint..."
echo ""

DETAILED_RESPONSE=$(curl -s "${VERCEL_URL}/api/health/detailed")
echo "Response: $DETAILED_RESPONSE"
echo ""

if echo "$DETAILED_RESPONSE" | grep -q '"supabase":"healthy"'; then
    echo "✅ Supabase connection is working"
    echo ""
else
    echo "❌ Supabase connection failed"
    echo ""
fi

# Summary
echo "=================================================="
echo "Summary:"
echo ""
echo "To fix environment variable issues:"
echo "1. Go to Vercel Dashboard → Settings → Environment Variables"
echo "2. Add missing variables (see QUICK_FIX_STEPS.md)"
echo "3. Redeploy the application"
echo ""
echo "Required variables:"
echo "  - SUPABASE_URL"
echo "  - SUPABASE_SERVICE_KEY"
echo "  - SUPABASE_ANON_KEY"
echo ""
echo "See QUICK_FIX_STEPS.md for detailed instructions."
echo "=================================================="

