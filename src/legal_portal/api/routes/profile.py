"""Profile management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from legal_portal.api.dependencies import get_current_user, get_user_supabase_client
from legal_portal.core.data_models import ProfileResponse, ProfileUpdate
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse)
async def get_profile(
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Get current user's profile information."""
    try:
        user_id = user["id"]
        user_email = user.get("email", "")

        # Fetch profile from database
        response = supabase.table("profiles").select("*").eq("id", user_id).execute()

        if not response.data:
            # Profile doesn't exist, create a basic one
            logger.info(f"Profile not found for user {user_id}, creating one")
            create_data = {
                "id": user_id,
                "email": user_email,
                "full_name": user.get("user_metadata", {}).get("full_name", ""),
            }
            create_response = supabase.table("profiles").insert(create_data).execute()

            if not create_response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create profile"
                )

            profile_data = create_response.data[0]
        else:
            profile_data = response.data[0]

        logger.info(f"Retrieved profile for user {user_id}")
        return ProfileResponse(**profile_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching profile: {str(e)}"
        ) from e


@router.put("", response_model=ProfileResponse)
async def update_profile(
    profile_update: ProfileUpdate,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Update current user's profile information."""
    try:
        user_id = user["id"]
        user_email = user.get("email", "")

        # Build update dictionary, excluding None values
        update_data = profile_update.model_dump(exclude_none=True)

        # ai_preferences is already a dict from the model, no conversion needed

        if not update_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

        # First, check if profile exists
        check_response = supabase.table("profiles").select("id").eq("id", user_id).execute()

        if not check_response.data:
            # Profile doesn't exist, create it with the update data
            logger.info(f"Creating new profile for user {user_id}")
            create_data = {"id": user_id, "email": user_email, **update_data}
            response = supabase.table("profiles").insert(create_data).execute()

            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create profile"
                )

            logger.info(f"Created profile for user {user_id}")
            return ProfileResponse(**response.data[0])

        # Profile exists, update it
        response = supabase.table("profiles").update(update_data).eq("id", user_id).execute()

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

        logger.info(f"Updated profile for user {user_id}: {list(update_data.keys())}")
        return ProfileResponse(**response.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error updating profile: {str(e)}"
        ) from e
