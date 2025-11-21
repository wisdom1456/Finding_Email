# Testing Guide - Legal Document Analysis Portal

## ✅ All Issues Resolved

This guide documents the testing process for the refactored application.

## Current Status

- ✅ Backend running on `http://localhost:8000`
- ✅ Frontend running on `http://localhost:5173`
- ✅ Supabase connected with RLS enabled
- ✅ Tailwind CSS working correctly
- ✅ Authentication flow functional
- ✅ Case creation working with RLS policies

## Quick Test Checklist

### 1. Backend Health Check

```bash
curl http://localhost:8000/health
```

**Expected:** `{"status":"healthy","database":"connected"}`

### 2. Frontend Access

Open browser to: `http://localhost:5173`

**Expected:**
- Redirects to `/login` if not authenticated
- Shows styled login form with Tailwind CSS

### 3. User Registration

1. Navigate to registration page
2. Fill in:
   - Email: `test@example.com`
   - Password: `SecurePass123!`
   - Full Name: `Test User`
3. Click "Sign Up"

**Expected:**
- Success message
- Redirect to login or dashboard

### 4. User Login

1. Navigate to `/login`
2. Enter credentials
3. Click "Sign In"

**Expected:**
- Redirect to `/app` dashboard
- User menu shows email

### 5. Case Creation

1. Navigate to "Cases" in sidebar
2. Click "New Case"
3. Fill in:
   - Client Name: `Test Client`
   - Reference Number: `TC-001`
   - Description: `Test case description`
   - Status: `Pending`
4. Click "Create Case"

**Expected:**
- Success message
- Case appears in case list
- **NO RLS POLICY ERROR** ✅

### 6. Document Upload

1. Open a case detail page
2. Click "Upload Document"
3. Select a PDF file
4. Add title and description
5. Click "Upload"

**Expected:**
- Upload progress shown
- Document appears in document list
- File stored in Supabase Storage

### 7. Analysis Trigger

1. On case detail page
2. Click "Start Analysis"
3. Select provider (if multiple)

**Expected:**
- Analysis status: "Processing"
- Background task initiated
- Status updates in UI

## Automated Test Scripts

### Test Supabase Connection

```bash
python3 scripts/test_supabase_connection.py
```

**Verifies:**
- Database connectivity
- Schema existence
- RLS policies

### Test Case Creation (Programmatic)

```bash
python3 scripts/debug_create_case.py
```

**Verifies:**
- User creation
- Profile creation
- Case creation via API
- RLS policy compliance

### Test Client Authentication

```bash
python3 scripts/test_client_auth.py
```

**Verifies:**
- Authorization header setting
- Token propagation to PostgREST

## API Endpoint Tests

### Health Check

```bash
curl http://localhost:8000/health
```

### Create Case (with auth)

```bash
# Get token first (from login)
TOKEN="eyJ..."

curl -X POST http://localhost:8000/api/cases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "API Test Client",
    "reference_number": "API-001",
    "description": "Created via API",
    "status": "pending"
  }'
```

**Expected:** Status 201, case JSON returned

### List Cases

```bash
curl http://localhost:8000/api/cases \
  -H "Authorization: Bearer $TOKEN"
```

**Expected:** Array of user's cases

### Upload Document

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.pdf" \
  -F "case_id=<case-uuid>" \
  -F "title=Test Document" \
  -F "description=Test upload"
```

**Expected:** Status 201, document JSON returned

## Common Issues & Solutions

### Issue: "Row level security policy violation"

**Solution:** ✅ FIXED
- Ensure backend uses `get_user_supabase_client` for user operations
- Verify `Authorization` header is set correctly
- See `RLS_FIX_SUMMARY.md` for details

### Issue: Frontend shows "Welcome to SvelteKit"

**Solution:** ✅ FIXED
- `+page.server.ts` now handles redirection
- Root page redirects based on auth state

### Issue: Tailwind CSS not working

**Solution:** ✅ FIXED
- Installed `@tailwindcss/postcss`
- Updated `postcss.config.js` to use new plugin
- Updated `app.css` to use `@import "tailwindcss"`

### Issue: 500 Internal Server Error on frontend

**Solution:**
1. Check terminal logs for PostCSS/build errors
2. Restart frontend: `cd frontend && npm run dev`
3. Clear browser cache
4. Check `.env` variables are set

### Issue: Database connection failed

**Solution:**
1. Verify `.env` has correct Supabase credentials
2. Check Supabase project is active (not paused)
3. Run `python3 scripts/test_supabase_connection.py`

## Regression Test Suite

Run the full Python test suite:

```bash
# From project root
pytest tests/ -v

# Run specific test file
pytest tests/api/test_cases.py -v

# Run with coverage
pytest tests/ --cov=src/legal_portal --cov-report=html
```

## Browser Testing Checklist

Test in multiple browsers:
- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari

Test responsive design:
- [ ] Mobile (375px)
- [ ] Tablet (768px)
- [ ] Desktop (1024px+)

## Security Testing

### RLS Policy Verification

1. Create two users (User A, User B)
2. User A creates a case
3. Try to access User A's case with User B's token

**Expected:** 
- User B cannot see User A's cases
- API returns empty array or 403

### Authentication Testing

1. Try API endpoints without token

**Expected:** 401 Unauthorized

2. Try with expired token

**Expected:** 401 Unauthorized

3. Try with invalid token

**Expected:** 401 Unauthorized

## Performance Testing

### Load Test Cases Endpoint

```bash
# Install hey: brew install hey

# 100 requests with 10 concurrent
hey -n 100 -c 10 \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/cases
```

**Expected:**
- All requests succeed
- Response time < 200ms average

### Document Upload Test

```bash
# Upload 10MB file
dd if=/dev/zero of=test_10mb.pdf bs=1m count=10

time curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_10mb.pdf" \
  -F "case_id=<case-uuid>" \
  -F "title=Large File Test"
```

**Expected:**
- Upload completes successfully
- Time < 30 seconds

## Database Testing

### Verify Schema

```bash
python3 scripts/test_supabase_connection.py
```

### Check RLS Policies

```sql
-- Run in Supabase SQL Editor
SELECT 
  tablename, 
  policyname, 
  permissive, 
  roles, 
  cmd
FROM pg_policies 
WHERE schemaname = 'public'
ORDER BY tablename, policyname;
```

### Verify Triggers

```sql
SELECT 
  trigger_name, 
  event_manipulation, 
  event_object_table
FROM information_schema.triggers
WHERE trigger_schema = 'public'
ORDER BY event_object_table;
```

## Monitoring

### Backend Logs

```bash
# Follow backend logs
tail -f logs/backend.log  # If logging to file

# Or monitor terminal where backend is running
```

### Frontend Logs

Open browser DevTools:
- Console for JavaScript errors
- Network tab for API calls
- Application tab for Supabase auth state

### Supabase Dashboard

Monitor in Supabase dashboard:
- Database -> Table Editor: View data
- Storage: View uploaded files
- Logs: Database queries and errors
- Auth: User list and sessions

## Test Data Cleanup

### Delete Test Cases

```bash
# Via API (deletes user's cases only)
for case_id in $(curl -s http://localhost:8000/api/cases \
  -H "Authorization: Bearer $TOKEN" | jq -r '.[].id')
do
  curl -X DELETE http://localhost:8000/api/cases/$case_id \
    -H "Authorization: Bearer $TOKEN"
done
```

### Delete Test Users (Supabase Dashboard)

1. Go to Authentication -> Users
2. Select test users
3. Click "Delete users"

### Clear Storage Bucket

1. Go to Storage
2. Select bucket
3. Delete test files

## Success Criteria

All tests pass when:
- ✅ Backend health check returns 200
- ✅ Frontend loads with Tailwind styling
- ✅ Users can register and login
- ✅ Users can create cases (no RLS errors)
- ✅ Users can upload documents
- ✅ Analysis can be triggered
- ✅ RLS policies prevent cross-user access
- ✅ API returns proper error codes
- ✅ No console errors in browser
- ✅ Responsive design works on all screen sizes

## Next Steps After Testing

Once all tests pass:
1. Deploy backend to production (e.g., Vercel, Railway)
2. Deploy frontend to Vercel
3. Update environment variables for production
4. Configure production Supabase project
5. Set up monitoring and logging
6. Enable HTTPS only
7. Configure CORS for production domains

---

**Last Updated:** 2025-11-20  
**Status:** ✅ All core functionality tested and working

