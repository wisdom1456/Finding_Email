# API Documentation

This document provides reference documentation for the Legal Document Analysis Portal REST API.

## Base URL

- **Development**: `http://localhost:8000`
- **Production**: `https://your-production-domain.com`

## Authentication

All API endpoints require authentication using Supabase JWT tokens. Include the token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

## Endpoints

### Clio Integration

#### POST /api/clio/sync/{case_id}

Sync new and updated documents from Clio into an existing case.

**Authentication:** Required

**Parameters:**
- `case_id` (path, string, required): UUID of the case to sync

**Response:**
```json
{
  "success": true,
  "case_id": "uuid",
  "synced_at": "2026-01-15T14:30:00Z",
  "summary": {
    "new_items": 3,
    "updated_items": 1,
    "total_processed": 4
  },
  "details": {
    "new": [...],
    "updated": [...]
  },
  "needs_reanalysis": true
}
```

**Errors:**
- 404: Case not found or not linked to Clio
- 401: Clio authentication expired
- 500: Sync operation failed

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/clio/sync/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <your-jwt-token>"
```

**Example Success Response:**
```json
{
  "success": true,
  "case_id": "123e4567-e89b-12d3-a456-426614174000",
  "synced_at": "2026-02-04T15:30:00Z",
  "summary": {
    "new_items": 2,
    "updated_items": 1,
    "total_processed": 3
  },
  "details": {
    "new": [
      {
        "id": "doc-1",
        "name": "Medical Records",
        "type": "document"
      },
      {
        "id": "doc-2",
        "name": "Email from Client",
        "type": "communication"
      }
    ],
    "updated": [
      {
        "id": "doc-3",
        "name": "Demand Letter",
        "type": "document"
      }
    ]
  },
  "needs_reanalysis": true
}
```

**Example Error Response (Case Not Found):**
```json
{
  "detail": "Case not found or not linked to Clio"
}
```

**Example Error Response (Clio Auth Expired):**
```json
{
  "detail": "Clio authentication expired. Please reconnect your Clio account."
}
```

---

## Response Format

All API responses follow a consistent format:

### Success Response
```json
{
  "success": true,
  "data": { ... }
}
```

### Error Response
```json
{
  "detail": "Error message describing what went wrong"
}
```

## Rate Limiting

API endpoints may be rate-limited to prevent abuse. Rate limit headers are included in responses:

- `X-RateLimit-Limit`: Maximum requests per time window
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Time when the rate limit resets (Unix timestamp)

## Versioning

The API is currently at version 1.0. Future breaking changes will be introduced in new API versions with appropriate deprecation notices.

## Support

For API issues or questions:
1. Check the [troubleshooting guide](README.md)
2. Review the [developer documentation](developer/developer-guide.md)
3. Open an issue in the GitHub repository
