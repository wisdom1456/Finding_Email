"""Clio integration helpers extracted from clio routes.

Contains redirect URI resolution, import progress persistence,
and sync item categorization. No HTTP or route concerns.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Tuple

logger = logging.getLogger(__name__)


def get_clio_redirect_uri(request) -> str:
    """Get consistent Clio redirect URI.

    Uses CLIO_PRODUCTION_URL if set (recommended for production),
    otherwise falls back to dynamic URL detection.

    This ensures all OAuth flows use the same redirect URI that's
    registered in Clio's developer console.
    """
    # First priority: explicit production URL (recommended)
    production_url = os.getenv("CLIO_PRODUCTION_URL")
    if production_url:
        # Ensure no trailing slash and append callback path
        production_url = production_url.rstrip("/")
        return f"{production_url}/api/clio/callback"

    # Second priority: CLIO_REDIRECT_URI environment variable
    explicit_redirect = os.getenv("CLIO_REDIRECT_URI")
    if explicit_redirect:
        return explicit_redirect

    # Fallback: dynamic detection (may cause issues with preview deployments)
    host = request.headers.get("host", "127.0.0.1:8080")
    if "localhost" in host:
        host = host.replace("localhost", "127.0.0.1")

    protocol = "https" if "vercel" in host or request.headers.get("x-forwarded-proto") == "https" else "http"
    return f"{protocol}://{host}/api/clio/callback"


async def save_import_progress_to_db(
    supabase,
    case_id: str,
    import_id: str,
    progress_data: dict,
) -> None:
    """Save import progress to database for cross-instance polling support on Vercel."""
    try:
        import_progress = {
            "import_id": import_id,
            "progress": progress_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        supabase.table("cases").update({"import_progress": import_progress}).eq("id", case_id).execute()
    except Exception as e:
        # Don't fail the import if progress persistence fails
        logger.warning(f"Failed to persist import progress to DB: {e}")


def categorize_clio_sync_items(
    documents: List[dict],
    communications: List[dict],
    notes: List[dict],
    existing_docs: List[dict],
) -> Tuple[List[dict], List[dict]]:
    """Categorize Clio items as new or updated based on existing documents.

    Args:
        documents: List of documents from Clio API
        communications: List of communications from Clio API
        notes: List of notes from Clio API
        existing_docs: List of existing document records from database

    Returns:
        Tuple of (new_items, updated_items) where each is a list of dicts
        with keys: id, name, type, date

    """
    # Extract existing Clio IDs from metadata
    existing_clio_ids = set()
    for doc in existing_docs:
        metadata = doc.get("metadata", {})
        if metadata.get("clio_source") and metadata.get("clio_id"):
            existing_clio_ids.add(str(metadata["clio_id"]))

    new_items = []
    updated_items = []

    # Process documents
    for doc in documents:
        try:
            doc_id = str(doc.get("id"))
            if not doc_id or doc_id == "None":
                continue
            doc_name = doc.get("name") or "Untitled Document"
            doc_date = doc.get("created_at")

            item = {
                "id": doc_id,
                "name": doc_name,
                "type": "document",
                "date": doc_date,
            }

            if doc_id in existing_clio_ids:
                updated_items.append(item)
            else:
                new_items.append(item)
        except Exception as e:
            logger.warning(f"Failed to process document: {e}")
            continue

    # Process communications
    for comm in communications:
        try:
            comm_id = str(comm.get("id"))
            if not comm_id or comm_id == "None":
                continue
            comm_name = comm.get("subject") or "Untitled Communication"
            comm_date = comm.get("date")

            item = {
                "id": comm_id,
                "name": comm_name,
                "type": "communication",
                "date": comm_date,
            }

            if comm_id in existing_clio_ids:
                updated_items.append(item)
            else:
                new_items.append(item)
        except Exception as e:
            logger.warning(f"Failed to process communication: {e}")
            continue

    # Process notes
    for note in notes:
        try:
            note_id = str(note.get("id"))
            if not note_id or note_id == "None":
                continue
            note_subject = note.get("subject") or "Untitled Note"
            note_date = note.get("created_at")

            item = {
                "id": note_id,
                "name": note_subject,
                "type": "note",
                "date": note_date,
            }

            if note_id in existing_clio_ids:
                updated_items.append(item)
            else:
                new_items.append(item)
        except Exception as e:
            logger.warning(f"Failed to process note: {e}")
            continue

    return new_items, updated_items
