"""Health check endpoints."""

import os

from fastapi import APIRouter, Depends

from legal_portal.api.dependencies import get_supabase_client

router = APIRouter()


@router.get("/health")
async def health_check():
    """Check health and verify environment variables are set.

    Returns
    -------
        Health status including environment variable check

    """
    # Check for required environment variables
    required_vars = {
        "SUPABASE_URL": bool(os.getenv("SUPABASE_URL")),
        "SUPABASE_SERVICE_KEY": bool(os.getenv("SUPABASE_SERVICE_KEY")),
        "SUPABASE_ANON_KEY": bool(os.getenv("SUPABASE_ANON_KEY")),
    }

    optional_vars = {
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "CLIO_CLIENT_ID": bool(os.getenv("CLIO_CLIENT_ID")),
        "CLIO_CLIENT_SECRET": bool(os.getenv("CLIO_CLIENT_SECRET")),
    }

    missing_required = [k for k, v in required_vars.items() if not v]
    missing_optional = [k for k, v in optional_vars.items() if not v]

    status = "healthy" if not missing_required else "unhealthy"

    response = {
        "status": status,
        "service": "Legal Document Analysis API",
        "version": "1.0.0",
        "environment": {
            "required_vars_set": all(required_vars.values()),
            "missing_required": missing_required if missing_required else None,
            "missing_optional": missing_optional if missing_optional else None,
        },
    }

    return response


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

    # Check OCR service
    from legal_portal.config.default import get_settings
    settings = get_settings()
    ocr_status = "disabled"
    if settings.ocr_remote_enabled:
        try:
            from legal_portal.utils.ocr_service_client import get_ocr_client
            ocr_health = await get_ocr_client().health_check()
            ocr_status = ocr_health.get("status", "unknown")
        except Exception as e:
            ocr_status = f"unreachable: {e}"

    checks["ocr_service"] = {
        "status": ocr_status,
        "remote_enabled": settings.ocr_remote_enabled,
        "remote_required": settings.ocr_remote_required,
    }

    overall_status = "healthy" if checks["supabase"] == "healthy" else "degraded"

    return {"status": overall_status, "checks": checks}
