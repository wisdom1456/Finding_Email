# Row Level Security (RLS) Authentication Fix

## Problem

When creating a case through the frontend, users encountered this error:

```
new row violates row-level security policy for table "cases"
```

This occurred despite:
- Valid JWT tokens being sent from the frontend
- The user being authenticated
- The backend receiving the correct `user_id`

## Root Cause

The backend was using `SUPABASE_SERVICE_KEY` for **all** database operations, including user-initiated actions. While the service key has administrative privileges and can bypass RLS, it doesn't set the `auth.uid()` context that RLS policies depend on.

Our RLS policy for case creation was:

```sql
CREATE POLICY "Users can create own cases"
    ON cases FOR INSERT
    WITH CHECK (auth.uid() = user_id);
```

When using the service key:
- `auth.uid()` returns `NULL`
- The policy check `NULL = user_id` fails
- Insert is rejected

## Solution

### 1. Created User-Scoped Supabase Client

Added `get_user_supabase_client()` dependency in `src/legal_portal/api/dependencies.py`:

```python
def get_user_supabase_client(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get Supabase client authenticated as the current user.
    This ensures RLS policies work correctly because auth.uid() will be set.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")  # Use ANON key, not SERVICE key
    
    client = create_client(supabase_url, supabase_key)
    
    # Authenticate with the user's token
    client.postgrest.auth(credentials.credentials)
    
    # Explicitly set the header to ensure it overrides the API key
    # This fixes an issue where .auth() might not override the key-based header
    client.postgrest.session.headers["Authorization"] = f"Bearer {credentials.credentials}"
    
    return client
```

**Key points:**
- Uses `SUPABASE_ANON_KEY` (not service key)
- Accepts user's JWT token from `Authorization` header
- Explicitly sets `Authorization: Bearer <user_token>` for PostgREST
- Creates fresh client per request (not cached) for user-specific auth state

### 2. Updated Route Dependencies

Changed all user-initiated endpoints to use `get_user_supabase_client`:

**Cases (`src/legal_portal/api/routes/cases.py`):**
```python
@router.post("", response_model=CaseResponse)
async def create_case(
    case_data: CaseCreate,
    user = Depends(get_current_user),
    supabase = Depends(get_user_supabase_client)  # Changed from get_supabase_client
):
    # Now auth.uid() is correctly set to the user's ID
    response = supabase.table("cases").insert({
        "user_id": user.user.id,
        "client_name": case_data.client_name,
        # ...
    }).execute()
```

**Documents (`src/legal_portal/api/routes/documents.py`):**
- `upload_document`
- `list_documents_for_case`
- `get_document`
- `delete_document`

All now use `Depends(get_user_supabase_client)`.

**Analysis (`src/legal_portal/api/routes/analysis.py`):**
```python
@router.post("/start")
async def start_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    user = Depends(get_current_user),
    user_supabase = Depends(get_user_supabase_client),     # For initial RLS checks
    service_supabase = Depends(get_supabase_client)        # For background tasks
):
    # Use user_supabase for initial validation
    # Pass service_supabase to background task for stable permissions
```

### 3. Service Key Still Used For

The original `get_supabase_client()` (using service key) is still used for:
- Admin operations
- Background tasks (passed explicitly)
- User authentication validation in `get_current_user()`

## How RLS Works Now

1. **Frontend** sends request with `Authorization: Bearer <jwt_token>`
2. **Backend** extracts token in `get_user_supabase_client()`
3. **Supabase client** is created with ANON key + user token
4. **PostgREST** receives requests with user's token in `Authorization` header
5. **PostgreSQL** validates JWT and sets `auth.uid()` for the session
6. **RLS policies** can now correctly check `auth.uid() = user_id`
7. **Operation succeeds** ✅

## Verification

Tested with `scripts/debug_create_case.py`:

```bash
$ python3 scripts/debug_create_case.py
Status: 201
Response: {
  "id": "63ca1a57-0224-4b56-a3b1-f5a9dcc0826d",
  "user_id": "2b790096-fb2e-418b-a7a2-e3e1a3e0836e",
  "client_name": "Debug Client",
  "status": "pending"
}
```

## Key Takeaways

1. **Service Role Key bypasses RLS** - Don't use it for user operations
2. **ANON Key + User JWT** enables RLS - This is the correct pattern
3. **`auth.uid()` requires user context** - Set via JWT in Authorization header
4. **Explicit header setting may be needed** - Some client versions need manual override
5. **Background tasks need stable permissions** - Pass service client explicitly

## Files Modified

- `src/legal_portal/api/dependencies.py` - Added `get_user_supabase_client`
- `src/legal_portal/api/routes/cases.py` - Updated all endpoints
- `src/legal_portal/api/routes/documents.py` - Updated all endpoints
- `src/legal_portal/api/routes/analysis.py` - Updated with dual client approach
- `scripts/test_client_auth.py` - Test script to verify header behavior

## Environment Variables Required

```bash
# .env (root and frontend/.env)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...      # Public, safe for frontend
SUPABASE_SERVICE_KEY=eyJ...    # Private, admin access
```

## Testing RLS Policies

To verify RLS is working:

```bash
# 1. Create a user and get token
python3 scripts/debug_create_case.py

# 2. Try to access another user's data (should fail)
# Modify script to use different user_id in request vs. token

# 3. Check Supabase logs for policy violations
```

## Further Reading

- [Supabase RLS Documentation](https://supabase.com/docs/guides/auth/row-level-security)
- [PostgREST JWT Authentication](https://postgrest.org/en/stable/auth.html)
- [Service Role vs ANON Key](https://supabase.com/docs/guides/api/api-keys)

---

**Status:** ✅ **FIXED** - Case creation now works correctly with RLS policies enforced.

