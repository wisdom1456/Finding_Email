"""Temporary debug endpoint for gap analysis."""

from fastapi import APIRouter, Depends
from legal_portal.api.dependencies import get_user_supabase_client

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/gap-analysis/{case_id}")
async def debug_gap_analysis(
    case_id: str,
    supabase=Depends(get_user_supabase_client),
):
    """Debug endpoint to check gap analysis data for a case."""

    # Get latest analysis
    response = (
        supabase.table("analysis_results")
        .select("id, created_at, status, result")
        .eq("case_id", case_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        return {"error": "No analysis found", "case_id": case_id}

    analysis = response.data[0]
    result = analysis.get("result", {})
    multi_stage = result.get("multi_stage_result")

    debug_info = {
        "analysis_id": analysis["id"],
        "created_at": analysis["created_at"],
        "status": analysis["status"],
        "has_result": result is not None,
        "has_multi_stage_result": multi_stage is not None,
        "has_gap_analysis": multi_stage.get("gap_analysis") is not None if multi_stage else False,
    }

    if multi_stage:
        debug_info["multi_stage_keys"] = list(multi_stage.keys())

        gap_analysis = multi_stage.get("gap_analysis")
        if gap_analysis:
            debug_info["gap_analysis"] = {
                "total_gaps": gap_analysis.get("total_gaps"),
                "critical_count": gap_analysis.get("critical_count"),
                "high_count": gap_analysis.get("high_count"),
                "medium_count": gap_analysis.get("medium_count"),
                "low_count": gap_analysis.get("low_count"),
                "completeness_score": gap_analysis.get("overall_completeness_score"),
            }
        else:
            debug_info["gap_analysis_null_reason"] = "Field exists but is null/undefined"

    return debug_info
