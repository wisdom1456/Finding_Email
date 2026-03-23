"""Analysis state helpers: retry wrappers, cancellation, progress, preferences, identity.

Extracted from api/routes/_analysis_helpers.py so that service-layer modules
can import these symbols without depending on the route layer.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from legal_portal.api.middleware.retry import retry_sync
from legal_portal.config.default import get_settings
from legal_portal.core.data_models import LetterType
from legal_portal.services.shared.progress_manager import ProgressManager
from legal_portal.utils.type_safety import safe_str, safe_str_required, sanitize_nested_dict

logger = logging.getLogger(__name__)

__all__ = [
    "DBColumnsCache",
    "_db_columns_cache",
    "_GAP_ANALYSIS_INPUT_SCHEMA_VERSION",
    "AnalysisCancelledError",
    "_upsert_with_retry",
    "_update_case_with_retry",
    "_analysis_is_cancelled",
    "_cancel_analysis",
    "_update_analysis_progress",
    "_get_user_ai_preferences",
    "_first_non_empty_text",
    "_resolve_letter_identity_context",
    "_resolve_client_name_for_letter",
]

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class DBColumnsCache:
    """Encapsulates DB column existence checks to avoid repeated probing."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get(self, key: str, default=None):
        return self._cache.get(key, default)

    def __setitem__(self, key: str, value: Any):
        self._cache[key] = value

    def __getitem__(self, key: str):
        return self._cache[key]


_db_columns_cache = DBColumnsCache()
_GAP_ANALYSIS_INPUT_SCHEMA_VERSION = "2026-03-10-map-reduce-v1"

# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------


def _upsert_with_retry(supabase_client, table: str, data: dict, context_id: str, max_attempts: int = 3):
    """Upsert a row with retry on transient Supabase errors."""
    return retry_sync(
        lambda: supabase_client.table(table).upsert(data).execute(),
        max_attempts=max_attempts,
        context_label=f"{table} upsert for {context_id}",
    )


def _update_case_with_retry(supabase_client, case_id: str, update_data: dict, max_attempts: int = 3):
    """Update a case row with retry on transient Supabase errors."""
    return retry_sync(
        lambda: supabase_client.table("cases").update(update_data).eq("id", case_id).execute(),
        max_attempts=max_attempts,
        context_label=f"cases update for {case_id}",
    )


# ---------------------------------------------------------------------------
# Analysis state helpers
# ---------------------------------------------------------------------------


class AnalysisCancelledError(Exception):
    """Raised when an in-progress analysis is cancelled by the user."""


def _analysis_is_cancelled(supabase, analysis_id: str) -> bool:
    """Check whether an analysis has been cancelled.

    We treat either status='cancelled' or status='canceled' as cancelled.
    """
    try:
        resp = supabase.table("analysis_results").select("status").eq("id", analysis_id).limit(1).execute()
        if not resp.data:
            return False
        status_val = (resp.data[0].get("status") or "").lower()
        return status_val in {"cancelled", "canceled"}
    except Exception:
        # Never break processing due to a cancellation check failure
        return False


async def _cancel_analysis(
    *,
    supabase,
    case_id: str,
    analysis_id: str,
    progress_manager: Optional[ProgressManager] = None,
):
    """Cancel an analysis by updating DB state and emitting progress."""
    # Mark analysis as cancelled
    supabase.table("analysis_results").update({"status": "cancelled"}).eq("id", analysis_id).in_("status", ["pending", "processing"]).execute()

    # Un-stick the case so a new analysis can be started
    # (we keep the case and documents; user can retry later)
    supabase.table("cases").update({"status": "pending"}).eq("id", case_id).execute()

    # Best-effort progress update so UI can stop spinning
    payload = {
        "message": "Analysis cancelled by user.",
        "phase": "cancelled",
        "percent": 0,
        "status": "cancelled",
        "timestamp": datetime.utcnow().isoformat(),
    }
    if progress_manager is not None:
        try:
            await progress_manager.publish_progress(channel_id=analysis_id, **payload)
        except Exception:
            pass
    await _update_analysis_progress(supabase, analysis_id, payload)


async def _update_analysis_progress(supabase, analysis_id: str, payload: dict):
    """Update analysis progress in DB with safety check for column existence."""
    if _db_columns_cache.get("has_progress_column") is False:
        return

    try:
        supabase.table("analysis_results").update({"progress": payload}).eq("id", analysis_id).execute()
        _db_columns_cache["has_progress_column"] = True
    except Exception as e:
        if "column analysis_results.progress does not exist" in str(e):
            logger.warning("DB column analysis_results.progress missing. Disabling DB updates.")
            _db_columns_cache["has_progress_column"] = False
        else:
            logger.warning(f"Failed to persist progress to DB: {e}")


async def _get_user_ai_preferences(user_id: str, supabase) -> Optional[Dict[str, str]]:
    """Fetch user's AI model preferences from profile."""
    try:
        response = supabase.table("profiles").select("ai_preferences").eq("id", user_id).single().execute()
        if response.data and response.data.get("ai_preferences"):
            return response.data["ai_preferences"]
    except Exception as e:
        logger.warning(f"Could not fetch user AI preferences: {e}")
    return None


# ---------------------------------------------------------------------------
# Identity resolution helpers
# ---------------------------------------------------------------------------


def _first_non_empty_text(*values: Any) -> Optional[str]:
    """Return the first non-empty string-like value, excluding booleans.

    Delegates to safe_str() for type-safe extraction from untyped data.
    """
    for value in values:
        result = safe_str(value)
        if result:
            return result
    return None


def _resolve_letter_identity_context(
    *,
    supabase,
    case_id: str,
    artifacts: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    """Resolve attorney/firm/contact/client identity context with robust fallbacks."""
    artifacts_map = artifacts if isinstance(artifacts, dict) else {}
    overrides_map = overrides if isinstance(overrides, dict) else {}

    case_data: Dict[str, Any] = {}
    profile_data: Dict[str, Any] = {}

    try:
        case_resp = supabase.table("cases").select("*").eq("id", case_id).limit(1).execute()
        if case_resp.data:
            case_data = case_resp.data[0] or {}
    except Exception as case_err:
        logger.warning(f"[LETTER] Failed to load case identity context for {case_id}: {case_err}")

    case_metadata = case_data.get("metadata")
    if not isinstance(case_metadata, dict):
        case_metadata = {}
    else:
        case_metadata = sanitize_nested_dict(case_metadata)

    clio_matter_data = case_data.get("clio_matter_data")
    if not isinstance(clio_matter_data, dict):
        clio_matter_data = {}
    else:
        clio_matter_data = sanitize_nested_dict(clio_matter_data)

    user_id = case_data.get("user_id")
    if user_id:
        try:
            profile_resp = (
                supabase.table("profiles")
                .select("full_name,firm_name,phone,email")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if profile_resp.data:
                profile_data = profile_resp.data[0] or {}
        except Exception as profile_err:
            logger.warning(
                "[LETTER] Failed to load profile identity context for %s: %s",
                case_id,
                profile_err,
            )

    attorney_name = _first_non_empty_text(
        overrides_map.get("attorney_name"),
        overrides_map.get("attorneyName"),
        overrides_map.get("name"),
        artifacts_map.get("attorney_name"),
        artifacts_map.get("attorneyName"),
        case_data.get("attorney_name"),
        case_data.get("attorneyName"),
        case_metadata.get("attorney_name"),
        case_metadata.get("attorneyName"),
        clio_matter_data.get("responsible_attorney"),
        clio_matter_data.get("responsibleAttorney"),
        profile_data.get("full_name"),
    )
    firm_name = _first_non_empty_text(
        overrides_map.get("firm_name"),
        overrides_map.get("firmName"),
        overrides_map.get("firm"),
        artifacts_map.get("firm_name"),
        artifacts_map.get("firmName"),
        case_data.get("firm_name"),
        case_data.get("firmName"),
        case_metadata.get("firm_name"),
        case_metadata.get("firmName"),
        clio_matter_data.get("firm_name"),
        clio_matter_data.get("firmName"),
        clio_matter_data.get("law_firm_name"),
        clio_matter_data.get("lawFirmName"),
        profile_data.get("firm_name"),
    )
    contact_phone = _first_non_empty_text(
        overrides_map.get("contact_phone"),
        overrides_map.get("contactPhone"),
        overrides_map.get("phone"),
        artifacts_map.get("contact_phone"),
        artifacts_map.get("contactPhone"),
        case_data.get("contact_phone"),
        case_data.get("contactPhone"),
        case_metadata.get("contact_phone"),
        case_metadata.get("contactPhone"),
        clio_matter_data.get("contact_phone"),
        clio_matter_data.get("contactPhone"),
        profile_data.get("phone"),
    )
    contact_email = _first_non_empty_text(
        overrides_map.get("contact_email"),
        overrides_map.get("contactEmail"),
        overrides_map.get("email"),
        artifacts_map.get("contact_email"),
        artifacts_map.get("contactEmail"),
        case_data.get("contact_email"),
        case_data.get("contactEmail"),
        case_metadata.get("contact_email"),
        case_metadata.get("contactEmail"),
        clio_matter_data.get("contact_email"),
        clio_matter_data.get("contactEmail"),
        profile_data.get("email"),
    )
    client_name = _first_non_empty_text(
        overrides_map.get("client_name"),
        overrides_map.get("clientName"),
        artifacts_map.get("client_name"),
        artifacts_map.get("clientName"),
        case_data.get("client_name"),
        case_data.get("clientName"),
        case_metadata.get("client_name"),
        case_metadata.get("clientName"),
        clio_matter_data.get("client_name"),
        clio_matter_data.get("clientName"),
    )

    return {
        "attorney_name": attorney_name,
        "firm_name": firm_name,
        "contact_phone": contact_phone,
        "contact_email": contact_email,
        "client_name": client_name,
    }


def _resolve_client_name_for_letter(
    *,
    resolved_identity: Optional[Dict[str, Any]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    fact_matrix: Optional[Any] = None,
) -> str:
    """Resolve client name from identity context with fact-matrix fallback."""
    client_name = _first_non_empty_text(
        (resolved_identity or {}).get("client_name"),
        (artifacts or {}).get("client_name"),
        (artifacts or {}).get("clientName"),
    )

    if not client_name and fact_matrix is not None:
        parties: List[Any] = []
        if isinstance(fact_matrix, dict):
            parties = fact_matrix.get("parties", []) or []
        else:
            parties = getattr(fact_matrix, "parties", []) or []

        for party in parties:
            role = ""
            name = ""
            if isinstance(party, dict):
                role = safe_str(party.get("role")) or ""
                name = safe_str(party.get("name")) or ""
            else:
                role = safe_str(getattr(party, "role", None)) or ""
                name = safe_str(getattr(party, "name", None)) or ""

            if role.lower() in {"client", "plaintiff", "claimant"} and name.strip():
                client_name = name.strip()
                break

    return client_name or "Client"
