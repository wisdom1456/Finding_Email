"""Health check endpoints."""

import os

from fastapi import APIRouter, Depends
from legal_portal.api.dependencies import get_supabase_client

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check endpoint.

    Returns
    -------
        Health status

    """
    return {"status": "healthy", "service": "Legal Document Analysis API", "version": "1.0.0"}


@router.get("/health/detailed")
async def detailed_health_check(supabase=Depends(get_supabase_client)):
    """Detailed health check with dependency verification.

    Returns
    -------
        Detailed health status including service dependencies

    """
    checks = {"api": "healthy", "supabase": "unknown", "openai": "unknown"}

    # Check Supabase connection
    try:
        # Simple query to verify connection
        supabase.table("profiles").select("count", count="exact").limit(0).execute()
        checks["supabase"] = "healthy"
    except Exception as e:
        checks["supabase"] = f"unhealthy: {str(e)}"

    # Check OpenAI API key
    if os.getenv("OPENAI_API_KEY"):
        checks["openai"] = "configured"
    else:
        checks["openai"] = "not configured"

    overall_status = "healthy" if checks["supabase"] == "healthy" else "degraded"

    return {"status": overall_status, "checks": checks}
