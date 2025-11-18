# Authentication Architecture

## Overview

The Legal Document Analysis Portal currently uses **PIN-based authentication** for access control. Two enterprise authentication modules exist in the codebase but are not currently integrated.

## Current Implementation: PIN Authentication

### How It Works

The application uses a simple PIN-based authentication system implemented in `src/legal_portal/ui/main.py`:

1. **Configuration**: PIN is set via environment variable `APP_ACCESS_PIN` (default: "0101")
2. **Session Management**: Authentication state stored in Streamlit session (`st.session_state.authenticated`)
3. **Access Control**: All pages require authentication check via `check_authentication()` function
4. **User Experience**: Simple PIN entry form with unlock button

### Implementation Details

```python
# Environment Configuration
APP_PIN = os.getenv("APP_ACCESS_PIN", "0101")

# Authentication Check
def check_authentication():
    """Check if user is authenticated with PIN."""
    if not st.session_state.authenticated:
        # Show PIN entry form
        # Validate against APP_PIN
        # Set st.session_state.authenticated = True on success
```

### Security Considerations

**Current PIN approach:**
- ✅ Simple and fast for single-user/small team scenarios
- ✅ No external dependencies
- ⚠️ No user tracking or audit trail
- ⚠️ Shared credential (one PIN for all users)
- ⚠️ No password reset mechanism
- ⚠️ Not suitable for multi-user enterprise environments

## Available But Not Integrated: Enterprise Auth

### 1. Enterprise Authentication Module (`core/auth.py`)

A comprehensive authentication system with:

**Features:**
- User roles (Admin, User, Viewer, Auditor)
- Granular permissions system
- YAML-based user configuration
- BCrypt password hashing
- JWT token generation
- Session management
- Role-based access control (RBAC)

**Capabilities:**
- `streamlit-authenticator` integration
- Password hashing with bcrypt
- JWT token management
- Role-permission mapping
- Session timeout handling

**Configuration:** Uses `config/auth_config.yaml` for user definitions

### 2. OAuth/SSO Module (`core/oauth.py`)

Enterprise Single Sign-On integration supporting:

**Providers:**
- Google OAuth 2.0
- Microsoft Azure AD
- Okta
- Auth0

**Features:**
- OAuth 2.0 / OIDC flow
- Token management
- User profile retrieval
- State parameter for CSRF protection
- Environment-based configuration

**Configuration:** Requires environment variables:
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`
- `OKTA_DOMAIN`, `OKTA_CLIENT_ID`, `OKTA_CLIENT_SECRET`
- `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`

## Why Enterprise Auth Not Currently Used

The enterprise authentication modules (`auth.py` and `oauth.py`) exist but are not imported or used in the application. Reasons may include:

1. **Simplicity**: PIN auth is sufficient for current use case
2. **Development Phase**: Enterprise features planned for future releases
3. **Deployment Context**: Application may be running in controlled environment
4. **Configuration Overhead**: OAuth requires external provider setup

## Migration Path to Enterprise Auth

If you need to implement enterprise authentication:

### Option A: Streamlit Authenticator (YAML-based)

1. Import authentication module:
   ```python
   from legal_portal.core.auth import AuthManager, UserRole
   ```

2. Initialize authenticator in `main.py`:
   ```python
   auth_manager = AuthManager()
   authenticator = auth_manager.get_authenticator()
   ```

3. Replace PIN check with:
   ```python
   name, authentication_status, username = authenticator.login('Login', 'main')
   ```

4. Configure users in `config/auth_config.yaml`

### Option B: OAuth/SSO Integration

1. Import OAuth module:
   ```python
   from legal_portal.core.oauth import OAuthProvider
   ```

2. Initialize OAuth provider:
   ```python
   oauth = OAuthProvider(provider="google")  # or "azure", "okta", "auth0"
   ```

3. Implement OAuth flow:
   ```python
   auth_url = oauth.get_authorization_url()
   # Handle callback and token exchange
   user_info = oauth.get_user_info(token)
   ```

4. Set up environment variables for chosen provider

5. Configure callback URL in provider dashboard

## Recommendations

### For Production Deployment

**Use Enterprise Auth if you need:**
- Multiple users with individual accounts
- Audit trail of who performed actions
- Role-based permissions (different access levels)
- Integration with company SSO (Google Workspace, Azure AD, etc.)
- Password management and reset capabilities

**Keep PIN Auth if:**
- Single user or small trusted team
- Simple internal tool
- Quick deployment needed
- No compliance requirements for user tracking

### Security Best Practices

1. **Change Default PIN**: Always set `APP_ACCESS_PIN` environment variable in production
2. **Use HTTPS**: Ensure application runs over HTTPS in production
3. **Session Timeout**: Consider adding session timeout for PIN auth
4. **Audit Logging**: Implement user action logging even with PIN auth
5. **Environment Variables**: Never commit PINs or OAuth credentials to git

## Files Reference

- **Current Auth**: `src/legal_portal/ui/main.py` (check_authentication function)
- **Enterprise Auth**: `src/legal_portal/core/auth.py`
- **OAuth Module**: `src/legal_portal/core/oauth.py`
- **Config Template**: `config/auth_config.yaml`
- **PIN Config**: `.env` file (`APP_ACCESS_PIN` variable)

## Summary

| Feature | PIN Auth (Current) | Enterprise Auth | OAuth/SSO |
|---------|-------------------|-----------------|-----------|
| **Status** | ✅ Active | 📦 Available | 📦 Available |
| **Users** | Single shared PIN | Multiple users | SSO integration |
| **Audit Trail** | ❌ No | ✅ Yes | ✅ Yes |
| **Roles/Permissions** | ❌ No | ✅ Yes | ✅ Yes |
| **Setup Complexity** | Low | Medium | High |
| **Best For** | Internal/dev use | Multi-user teams | Enterprise deployment |

---

**Last Updated**: November 17, 2025  
**Current Implementation**: PIN-based authentication (simple, single-user)  
**Available Options**: Enterprise auth and OAuth/SSO modules ready for integration when needed

