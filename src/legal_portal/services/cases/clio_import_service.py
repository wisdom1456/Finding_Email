"""Clio import orchestration and case business logic extracted from cases routes.

Contains document import helpers, intake analysis, and background import
processing. Content-hash deduplication has been split into content_dedup.py.
No HTTP or route concerns.
"""

import asyncio
import hashlib
import json as _json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from starlette.concurrency import run_in_threadpool

from legal_portal.api.services.clio_client import ClioAuthError, ClioClient
from legal_portal.api.utils.content_extractor import DocumentProcessor as ContentExtractor
from legal_portal.config.default import get_settings
from legal_portal.core.data_models import DocumentStatus
from legal_portal.core.document_processor import DocumentProcessor, ValidationError
from legal_portal.services.shared.progress_manager import ProgressManager
from legal_portal.utils.blacklist import is_name_blacklisted
from legal_portal.utils.throttled_db_writer import ThrottledDBWriter

# Re-export: run_content_hash_dedup moved to content_dedup.py but still
# imported by cases.py route via this module.
from legal_portal.services.cases.content_dedup import run_content_hash_dedup  # noqa: F401

logger = logging.getLogger(__name__)


async def get_clio_client_for_user(user, supabase) -> ClioClient:
    """Get authenticated Clio client for user with token refresh."""
    try:
        # Get user's tokens
        result = supabase.table("integrations_clio").select("*").eq("user_id", user["id"]).execute()

        if not result.data:
            raise Exception("Clio not connected. Please authorize first.")

        integration = result.data[0]
        access_token = integration["access_token"]
        refresh_token = integration["refresh_token"]
        expires_at_str = integration["expires_at"]

        # Parse the datetime and ensure it's timezone-aware
        if isinstance(expires_at_str, str):
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        else:
            expires_at = expires_at_str

        # Ensure expires_at is timezone-aware (UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Check if token needs refresh
        from legal_portal.api.services.clio_auth_service import ClioAuthService

        now = datetime.now(timezone.utc)
        is_expired = now >= expires_at

        auth_service = ClioAuthService()
        if is_expired:
            # Refresh token
            new_tokens = auth_service.refresh_access_token(refresh_token)

            # Update database
            supabase.table("integrations_clio").update(
                {
                    "access_token": new_tokens["access_token"],
                    "refresh_token": new_tokens["refresh_token"],
                    "expires_at": new_tokens["expires_at"].isoformat(),
                }
            ).eq("user_id", user["id"]).execute()

            access_token = new_tokens["access_token"]

        return ClioClient(access_token)

    except ClioAuthError as e:
        raise Exception(f"Clio authentication failed: {str(e)}") from e
    except Exception:
        raise


async def import_clio_documents_helper(
    matter_id: int,
    case_id: str,
    user: dict,
    clio_client: ClioClient,
    supabase,
    progress_manager=None,
    import_id: str = None,
) -> Dict[str, Any]:
    """Import documents from Clio matter.

    Returns import status with counts and any errors.
    """
    # Import classify_document_type from documents module
    from legal_portal.services.documents.extraction_service import classify_document_type

    # Throttle DB progress writes to reduce disk I/O (SSE remains real-time)
    async def _write_import_progress(progress_payload):
        """Actual DB write for import progress."""
        supabase.table("cases").update({"import_progress": progress_payload}).eq("id", case_id).execute()

    _import_db_writer = ThrottledDBWriter(
        write_fn=_write_import_progress,
        min_interval_seconds=3.0,
    )

    # Helper to persist progress to DB for cross-instance Vercel polling
    async def persist_progress(message: str, phase: str, percent: int, **kwargs):
        """Publish progress to in-memory manager AND persist (throttled) to database."""
        if progress_manager and import_id:
            await progress_manager.publish_progress(
                channel_id=import_id,
                message=message,
                phase=phase,
                percent=percent,
                **kwargs,
            )
        # Persist to DB (throttled) if we have case_id and import_id
        if case_id and import_id:
            try:
                progress_data = {
                    "type": kwargs.get("status", "progress"),
                    "message": message,
                    "phase": phase,
                    "percent": percent,
                }
                import_progress = {
                    "import_id": import_id,
                    "progress": progress_data,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                await _import_db_writer.maybe_write(import_progress)
            except Exception as e:
                logger.warning(f"Failed to persist progress to DB: {e}")

    try:
        # Import communications
        logger.debug("Fetching communications for matter", extra={"matter_id": matter_id})
        await persist_progress("Fetching communications from Clio...", "fetch_communications", 35)
        communications = await run_in_threadpool(clio_client.get_communications, matter_id, limit=100)
        logger.debug("Found communications", extra={"count": len(communications)})

        # Import notes
        logger.debug("Fetching notes for matter", extra={"matter_id": matter_id})
        await persist_progress("Fetching notes from Clio...", "fetch_notes", 38)
        notes = await run_in_threadpool(clio_client.get_notes, matter_id)
        logger.debug("Found notes", extra={"count": len(notes)})

        # Import documents (metadata only)
        logger.debug("Fetching documents for matter", extra={"matter_id": matter_id})
        await persist_progress("Fetching documents from Clio...", "fetch_documents", 40)
        documents = await run_in_threadpool(clio_client.get_documents, matter_id)
        logger.debug("Found documents", extra={"count": len(documents)})

        # Load user blacklist rules once for this import
        blacklist: List[str] = []
        try:
            profile_response = (
                supabase.table("profiles").select("ai_preferences").eq("id", user["id"]).execute()
            )
            if profile_response.data and profile_response.data[0].get("ai_preferences"):
                blacklist = (
                    profile_response.data[0]["ai_preferences"].get("blacklisted_documents", []) or []
                )
            logger.info(
                "Loaded blacklist rules for Clio import",
                extra={"user_id": user["id"], "count": len(blacklist)},
            )
        except Exception as e:
            logger.warning("Failed to load blacklist rules for Clio import", extra={"error": str(e)})

        comm_success = 0
        note_success = 0
        doc_success = 0
        errors = []

        # Track compression statistics
        files_compressed = 0
        total_original_size = 0
        total_compressed_size = 0

        # Save communications as document entries
        total_comms = len(communications)
        for idx, comm in enumerate(communications):
            try:
                subject = comm.subject or "Untitled Communication"
                percent = 42 + int((idx / max(total_comms, 1)) * 5)
                # Persist every 3rd item to avoid DB spam but still show progress
                if idx % 3 == 0:
                    await persist_progress(
                        f"Processing communication {idx + 1} of {total_comms}",
                        "import_communications",
                        percent,
                        sub_step=subject[:50],
                        current_doc={"index": idx + 1, "total": total_comms, "name": subject},
                    )

                if is_name_blacklisted(subject, blacklist):
                    logger.info("Skipping blacklisted communication during Clio import", extra={"subject": subject})
                    continue

                # Create a text document for each communication
                content = f"Subject: {comm.subject}\n"
                content += f"Date: {comm.date}\n"
                content += f"From: {comm.sender.name}\n"
                content += f"Type: {comm.communication_type}\n\n"
                content += comm.body

                # Check if this is an intake form
                is_intake = "intake" in comm.subject.lower() if comm.subject else False

                storage_path = f"clio/{case_id}/comm_{comm.id}.txt"
                try:
                    supabase.storage.from_("documents").upload(
                        storage_path,
                        content.encode("utf-8"),
                        {"content-type": "text/plain"},
                    )
                except Exception as upload_err:
                    logger.warning(f"Failed to upload communication to storage: {upload_err}")

                doc_data = {
                    "case_id": case_id,
                    "file_name": f"Clio Communication - {comm.subject[:50]}.txt",
                    "file_type": "text/plain",
                    "file_size": len(content.encode("utf-8")),
                    "storage_path": storage_path,
                    "status": DocumentStatus.READY,
                    "extracted_text": content,
                    "metadata": {
                        "clio_source": True,
                        "clio_type": "communication",
                        "clio_id": comm.id,
                        "clio_subject": comm.subject,
                        "clio_date": comm.date.isoformat() if comm.date else None,
                        "is_intake_form": is_intake,
                    },
                }
                supabase.table("documents").insert(doc_data).execute()
                comm_success += 1
            except Exception as e:
                errors.append(f"Communication {comm.id}: {str(e)}")

        # Save notes as document entries
        total_notes = len(notes)
        for idx, note in enumerate(notes):
            try:
                note_subject = note.get("subject", "Untitled Note")
                percent = 47 + int((idx / max(total_notes, 1)) * 5)
                # Persist every 3rd item to avoid DB spam
                if idx % 3 == 0:
                    await persist_progress(
                        f"Processing note {idx + 1} of {total_notes}",
                        "import_notes",
                        percent,
                        sub_step=note_subject[:50],
                        current_doc={"index": idx + 1, "total": total_notes, "name": note_subject},
                    )
                note_subject = note.get("subject", "No Subject")

                if is_name_blacklisted(note_subject, blacklist):
                    logger.info("Skipping blacklisted note during Clio import", extra={"subject": note_subject})
                    continue

                note_detail = note.get("detail", "")
                note_date = note.get("date", "")

                # Check if this is an intake form
                is_intake = "intake" in note_subject.lower()

                note_storage_path = f"clio/{case_id}/note_{note['id']}.txt"
                note_content = note_detail or ""
                try:
                    supabase.storage.from_("documents").upload(
                        note_storage_path,
                        note_content.encode("utf-8"),
                        {"content-type": "text/plain"},
                    )
                except Exception as upload_err:
                    logger.warning(f"Failed to upload note to storage: {upload_err}")

                doc_data = {
                    "case_id": case_id,
                    "file_name": f"Clio Note - {note_subject[:50]}.txt",
                    "file_type": "text/plain",
                    "file_size": len(note_content.encode("utf-8")),
                    "storage_path": note_storage_path,
                    "status": DocumentStatus.READY,
                    "extracted_text": note_detail,
                    "metadata": {
                        "clio_source": True,
                        "clio_type": "note",
                        "clio_id": note["id"],
                        "clio_subject": note_subject,
                        "clio_date": note_date,
                        "is_intake_form": is_intake,
                    },
                }
                supabase.table("documents").insert(doc_data).execute()
                note_success += 1
            except Exception as e:
                errors.append(f"Note {note.get('id', 'unknown')}: {str(e)}")

        # Download and process document files
        logger.info("Processing Clio documents", extra={"count": len(documents)})
        total_docs = len(documents)

        # Build duplicate detection set from existing documents in this case
        existing_docs = supabase.table("documents").select("file_name, file_size, metadata").eq("case_id", case_id).execute()
        existing_file_keys = set()
        existing_content_hashes = set()
        existing_clio_ids = set()
        for existing in existing_docs.data or []:
            key = (existing["file_name"], existing.get("file_size", 0))
            existing_file_keys.add(key)
            if existing.get("metadata", {}).get("original_filename"):
                key2 = (existing["metadata"]["original_filename"], existing.get("file_size", 0))
                existing_file_keys.add(key2)
            if existing.get("metadata", {}).get("content_hash"):
                existing_content_hashes.add(existing["metadata"]["content_hash"])
            clio_id = (existing.get("metadata") or {}).get("clio_id")
            if clio_id:
                existing_clio_ids.add(clio_id)

        # Track duplicates seen in THIS import batch
        import_batch_keys = set()
        import_batch_hashes = set()
        duplicates_count = 0
        filtered_small_images_count = 0
        SMALL_IMAGE_THRESHOLD_BYTES = 50 * 1024  # 50KB

        # Cache Clio access token once (instead of fetching per document)
        _clio_access_token = None
        if documents:
            integration = (
                supabase.table("integrations_clio")
                .select("access_token")
                .eq("user_id", user["id"])
                .execute()
            )
            if not integration.data:
                raise Exception("Clio integration not found")
            _clio_access_token = integration.data[0]["access_token"]

        for idx, doc in enumerate(documents):
            try:
                doc_name = doc.get("name", "Untitled Document")
                percent = 52 + int((idx / max(total_docs, 1)) * 40)
                # Persist EVERY document progress since this is the slow part
                await persist_progress(
                    f"Downloading document {idx + 1} of {total_docs}: {doc_name[:30]}",
                    "import_documents",
                    percent,
                    sub_step=doc_name[:50],
                    current_doc={"index": idx + 1, "total": total_docs, "name": doc_name},
                )
                doc_id = doc["id"]
                doc_name = doc.get("name", "Untitled Document")
                doc_size = doc.get("size", 0)

                logger.debug("Processing document", extra={"doc_name": doc_name, "doc_id": doc_id, "size_mb": f"{doc_size / (1024 * 1024):.2f}"})

                if is_name_blacklisted(doc_name, blacklist):
                    logger.info("Skipping blacklisted document during Clio import", extra={"doc_name": doc_name})
                    continue

                # Filter small images (typically email signature logos, social media icons)
                doc_content_type = (doc.get("content_type") or "").lower().strip()
                if (
                    doc_content_type.startswith("image/")
                    and doc_size > 0
                    and doc_size < SMALL_IMAGE_THRESHOLD_BYTES
                ):
                    filtered_small_images_count += 1
                    if doc_id not in existing_clio_ids:
                        logger.info(
                            f"Filtering small image ({doc_size} bytes): {doc_name}",
                            extra={"doc_name": doc_name, "size_bytes": doc_size, "content_type": doc_content_type},
                        )
                        skip_record = {
                            "case_id": case_id,
                            "file_name": doc_name,
                            "file_type": doc_content_type,
                            "file_size": doc_size,
                            "storage_path": "",
                            "status": "skipped_small_image",
                            "extracted_text": None,
                            "metadata": {
                                "clio_source": True,
                                "clio_type": "document",
                                "clio_id": doc_id,
                                "skip_reason": "small_image_filtered",
                                "skip_detail": f"Image under {SMALL_IMAGE_THRESHOLD_BYTES // 1024}KB threshold ({doc_size} bytes)",
                            },
                        }
                        supabase.table("documents").insert(skip_record).execute()
                    else:
                        logger.debug(
                            f"Small image already recorded, skipping re-insert: {doc_name}",
                            extra={"doc_name": doc_name, "clio_id": doc_id},
                        )
                    continue

                # Check file size limits before downloading
                MAX_SIZE_ZIP_MB = 50
                MAX_SIZE_OTHER_MB = 100

                is_zip = doc_name.lower().endswith(".zip")
                size_limit_mb = MAX_SIZE_ZIP_MB if is_zip else MAX_SIZE_OTHER_MB
                size_limit_bytes = size_limit_mb * 1024 * 1024

                if doc_size > size_limit_bytes:
                    file_size_mb = doc_size / (1024 * 1024)
                    logger.warning(
                        f"Skipping large file {doc_name}: "
                        f"{file_size_mb:.1f}MB exceeds {size_limit_mb}MB limit"
                    )
                    errors.append(
                        f"Document {doc_name}: File too large ({file_size_mb:.1f}MB). "
                        f"Maximum size is {size_limit_mb}MB for {'zip files' if is_zip else 'this file type'}."
                    )
                    skip_record = {
                        "case_id": case_id,
                        "file_name": doc_name,
                        "file_type": doc.get("content_type", "application/octet-stream"),
                        "file_size": doc_size,
                        "storage_path": "",
                        "status": "skipped_too_large",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "error": f"File too large ({file_size_mb:.1f}MB). Maximum size is {size_limit_mb}MB.",
                            "error_type": "FILE_TOO_LARGE",
                            "skip_reason": f"Exceeds {size_limit_mb}MB limit for {'zip files' if is_zip else 'documents'}",
                        },
                    }
                    supabase.table("documents").insert(skip_record).execute()
                    continue

                doc_url = f"https://app.clio.com/api/v4/documents/{doc_id}/download.json"
                access_token = _clio_access_token
                DOC_TIMEOUT_SECONDS = 60

                try:
                    file_content, content_type = await asyncio.wait_for(
                        run_in_threadpool(ContentExtractor.download_file, doc_url, access_token),
                        timeout=DOC_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Document download timed out after {DOC_TIMEOUT_SECONDS}s", extra={"doc_name": doc_name})
                    errors.append(f"Document {doc_name}: Download timed out (>60s)")
                    skip_record = {
                        "case_id": case_id,
                        "file_name": doc_name,
                        "file_type": "application/octet-stream",
                        "file_size": 0,
                        "storage_path": "",
                        "status": "download_timeout",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_url": doc_url,
                            "error": f"Download timed out after {DOC_TIMEOUT_SECONDS}s",
                            "error_type": "TIMEOUT",
                        },
                    }
                    supabase.table("documents").insert(skip_record).execute()
                    continue

                original_size = len(file_content)
                logger.debug("Downloaded file", extra={"size_mb": f"{original_size / (1024 * 1024):.2f}"})

                # --- DUPLICATE DETECTION ---
                content_hash = hashlib.sha256(file_content).hexdigest()

                file_key = (doc_name, original_size)
                is_duplicate = False
                duplicate_reason = None

                if content_hash in existing_content_hashes:
                    is_duplicate = True
                    duplicate_reason = "content_hash_match"
                    logger.info(f"Duplicate detected (content hash): {doc_name}")
                elif content_hash in import_batch_hashes:
                    is_duplicate = True
                    duplicate_reason = "content_hash_match_in_batch"
                    logger.info(f"Duplicate detected (content hash in batch): {doc_name}")
                elif file_key in existing_file_keys:
                    is_duplicate = True
                    duplicate_reason = "exists_in_case"
                    logger.info(f"Duplicate detected (exists in case): {doc_name} ({original_size} bytes)")
                elif file_key in import_batch_keys:
                    is_duplicate = True
                    duplicate_reason = "duplicate_in_import"
                    logger.info(f"Duplicate detected (in import batch): {doc_name} ({original_size} bytes)")

                import_batch_keys.add(file_key)
                import_batch_hashes.add(content_hash)

                if is_duplicate:
                    duplicates_count += 1

                is_intake_candidate = "intake" in doc_name.lower()
                processor = DocumentProcessor()

                try:
                    doc_record = await asyncio.wait_for(
                        processor.process_and_upload(
                            file_content=file_content,
                            filename=doc_name,
                            user_id=user["id"],
                            case_id=case_id,
                            supabase_client=supabase,
                            is_intake_form=is_intake_candidate,
                            content_type=content_type,
                            skip_extraction=True,
                            blacklist=blacklist,
                        ),
                        timeout=DOC_TIMEOUT_SECONDS,
                    )

                    if doc_record.get("status") == DocumentStatus.SKIPPED:
                        logger.info(
                            "Skipping blacklisted document after processor check",
                            extra={"doc_name": doc_name},
                        )
                        continue

                    if doc_record.get("metadata", {}).get("compression", {}).get("compressed"):
                        files_compressed += 1
                        comp_meta = doc_record["metadata"]["compression"]
                        total_original_size += comp_meta["original_size"]
                        total_compressed_size += comp_meta["compressed_size"]
                        logger.debug(
                            "File compressed",
                            extra={
                                "original_mb": f"{comp_meta['original_size'] / (1024 * 1024):.2f}",
                                "compressed_mb": f"{comp_meta['compressed_size'] / (1024 * 1024):.2f}",
                            },
                        )

                    classification = classify_document_type(doc_name, content_type or "application/octet-stream")

                    doc_record["metadata"].update(
                        {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_url": doc_url,
                            "clio_filename": doc_name,
                            "is_intake_candidate": is_intake_candidate,
                            "classification": classification,
                            "content_hash": content_hash,
                        }
                    )
                    logger.debug(f"Classified as {classification}: {doc_name}")

                    if is_duplicate:
                        doc_record["metadata"]["is_duplicate"] = True
                        doc_record["metadata"]["duplicate_reason"] = duplicate_reason
                        doc_record["metadata"]["excluded"] = True
                        doc_record["status"] = "duplicate"
                        logger.info(f"Marked as duplicate: {doc_name} (reason: {duplicate_reason})")

                    supabase.table("documents").insert(doc_record).execute()
                    doc_success += 1
                    logger.debug("Successfully imported document", extra={"doc_name": doc_name, "is_duplicate": is_duplicate})

                except ValidationError as e:
                    logger.warning("Validation failed", extra={"error_code": e.error_code, "error": str(e)})
                    raise Exception(f"Validation failed: {str(e)}") from e
                except asyncio.TimeoutError:
                    logger.warning(f"Document processing timed out after {DOC_TIMEOUT_SECONDS}s", extra={"doc_name": doc_name})
                    errors.append(f"Document {doc_name}: Processing timed out (>60s)")
                    skip_record = {
                        "case_id": case_id,
                        "file_name": doc_name,
                        "file_type": content_type or "application/octet-stream",
                        "file_size": original_size,
                        "storage_path": "",
                        "status": "processing_timeout",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_url": doc_url,
                            "error": f"Processing timed out after {DOC_TIMEOUT_SECONDS}s",
                            "error_type": "TIMEOUT",
                        },
                    }
                    supabase.table("documents").insert(skip_record).execute()
                    continue

            except Exception as e:
                error_msg = f"Document {doc.get('id', 'unknown')} ({doc.get('name', 'unknown')}): {str(e)}"
                errors.append(error_msg)
                logger.warning("Error importing document", extra={"doc_id": doc.get("id"), "error": str(e)})

        # Flush any remaining throttled progress before returning
        await _import_db_writer.flush()

        result = {
            "success": len(errors) == 0,
            "communications_count": comm_success,
            "notes_count": note_success,
            "documents_count": doc_success,
            "duplicates_count": duplicates_count,
            "filtered_small_images_count": filtered_small_images_count,
            "total_imported": comm_success + note_success + doc_success,
            "errors": errors if errors else None,
        }

        logger.info(
            "Import summary",
            extra={
                "communications": comm_success,
                "notes": note_success,
                "documents": doc_success,
                "duplicates": duplicates_count,
                "filtered_small_images": filtered_small_images_count,
                "total": comm_success + note_success + doc_success,
                "errors": len(errors) if errors else 0,
            },
        )

        if files_compressed > 0:
            total_saved = total_original_size - total_compressed_size
            avg_reduction = (total_saved / total_original_size) * 100 if total_original_size > 0 else 0
            logger.info(
                "Compression summary",
                extra={
                    "files_compressed": files_compressed,
                    "original_mb": f"{total_original_size / 1024 / 1024:.1f}",
                    "compressed_mb": f"{total_compressed_size / 1024 / 1024:.1f}",
                    "saved_mb": f"{total_saved / 1024 / 1024:.1f}",
                    "reduction_percent": f"{avg_reduction:.1f}",
                },
            )

        # Post-processing: Prioritize intake forms
        logger.debug("Prioritizing intake forms")
        intake_docs = (
            supabase.table("documents")
            .select("id, file_name, file_type, file_size, metadata, status")
            .eq("case_id", case_id)
            .execute()
        )

        if intake_docs.data:
            intake_candidates = [
                doc for doc in intake_docs.data if doc.get("metadata", {}).get("is_intake_candidate") is True
            ]

            if len(intake_candidates) > 1:
                logger.debug("Found intake candidates", extra={"count": len(intake_candidates)})

                scored = []
                for doc in intake_candidates:
                    score = analyze_intake_priority(doc)
                    scored.append((doc, score))
                    logger.debug(
                        "Scored intake candidate",
                        extra={"file_name": doc["file_name"], "score": score, "size": doc.get("file_size", 0)},
                    )

                scored.sort(key=lambda x: x[1], reverse=True)

                best_doc, best_score = scored[0]
                logger.info(
                    "Best intake selected", extra={"file_name": best_doc["file_name"], "score": best_score}
                )

                best_doc["metadata"]["is_intake_form"] = True
                best_doc["metadata"]["is_intake_candidate"] = False
                supabase.table("documents").update({"metadata": best_doc["metadata"]}).eq(
                    "id", best_doc["id"]
                ).execute()

                for doc, score in scored[1:]:
                    doc["metadata"]["is_intake_candidate"] = True
                    doc["metadata"]["is_intake_form"] = False
                    supabase.table("documents").update({"metadata": doc["metadata"]}).eq(
                        "id", doc["id"]
                    ).execute()
                    logger.debug("Marked as alternate", extra={"file_name": doc["file_name"], "score": score})

            elif len(intake_candidates) == 1:
                doc = intake_candidates[0]
                doc["metadata"]["is_intake_form"] = True
                doc["metadata"]["is_intake_candidate"] = False
                supabase.table("documents").update({"metadata": doc["metadata"]}).eq(
                    "id", doc["id"]
                ).execute()
                logger.info("Single intake form identified", extra={"file_name": doc["file_name"]})

        return result

    except Exception as e:
        logger.exception(
            "Exception in import_clio_documents_helper",
            extra={"error": str(e), "error_type": type(e).__name__},
        )

        return {
            "success": False,
            "error": str(e),
            "communications_count": 0,
            "notes_count": 0,
            "documents_count": 0,
            "total_imported": 0,
        }


def analyze_intake_priority(doc: Dict[str, Any]) -> int:
    """Score intake documents to prioritize filled forms over blank templates.

    Higher scores = better intake form candidates.
    """
    filename = doc.get("file_name", "").lower()
    file_size = doc.get("file_size", 0)

    priority_score = 0

    if "fillable" in filename:
        priority_score -= 100
    if "blank" in filename:
        priority_score -= 100
    if "template" in filename:
        priority_score -= 50
    if "[fillable]" in filename:
        priority_score -= 100
    if "[blank]" in filename:
        priority_score -= 100

    min_content_size = get_settings().min_file_size_for_content
    if file_size > min_content_size:
        priority_score += 50
    elif file_size > min_content_size * 1.4:
        priority_score += 80

    if " - " in filename:
        priority_score += 30
    if "_" in filename and "[fillable]" not in filename:
        priority_score += 10

    if "completed" in filename:
        priority_score += 50
    if "filled" in filename:
        priority_score += 50
    if "final" in filename:
        priority_score += 40

    return priority_score


def analyze_intake_documents(case_id: str, supabase) -> Dict[str, Any]:
    """Analyze documents for intake form candidates.

    Returns analysis with intake document info.
    """
    try:
        docs_result = (
            supabase.table("documents")
            .select("id, file_name, file_type, metadata, status")
            .eq("case_id", case_id)
            .execute()
        )

        documents = docs_result.data

        intake_candidates = [doc for doc in documents if "intake" in doc.get("file_name", "").lower()]
        marked_intake = [doc for doc in documents if doc.get("metadata", {}).get("is_intake_form") is True]

        if len(intake_candidates) == 0:
            message = "⚠️ No intake document found. First document will be used."
            return {
                "intake_candidates_count": 0,
                "marked_intake_count": len(marked_intake),
                "message": message,
                "requires_user_selection": False,
                "best_intake": None,
            }

        scored_candidates = []
        for doc in intake_candidates:
            score = analyze_intake_priority(doc)
            scored_candidates.append(
                {
                    "doc": doc,
                    "score": score,
                    "doc_id": doc["id"],
                    "filename": doc.get("file_name", ""),
                    "size": doc.get("file_size", 0),
                }
            )

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        best_intake = scored_candidates[0] if scored_candidates else None

        if len(marked_intake) == 1:
            message = f"✅ Intake document identified: {marked_intake[0]['file_name']}"
        elif len(intake_candidates) == 1:
            message = f"✅ Intake document identified: {intake_candidates[0]['file_name']}"
        elif best_intake and best_intake["score"] > 0:
            fname = best_intake["filename"]
            score = best_intake["score"]
            message = f"✅ Best intake form auto-selected: {fname} (score: {score})"
        else:
            message = f"⚠️ Multiple intake candidates found ({len(intake_candidates)}). Best match selected."

        return {
            "intake_candidates_count": len(intake_candidates),
            "marked_intake_count": len(marked_intake),
            "message": message,
            "requires_user_selection": False,
            "best_intake": best_intake,
            "scored_candidates": scored_candidates[:5],
        }

    except Exception as e:
        return {"error": str(e), "message": "Failed to analyze intake documents"}


async def process_clio_import_background(
    matter_id: int,
    case_id: str,
    user: dict,
    clio_client: ClioClient,
    supabase,
    progress_manager: ProgressManager,
    import_id: str,
    case_clio_data: dict,
):
    """Background task to handle Clio import process."""
    # #region agent log
    def _debug_log_bg(msg, data, hyp):
        logger.info(f"[DEBUG] {msg} | hyp={hyp} | data={_json.dumps(data)}")
    _debug_log_bg("bg_task_start", {"import_id": import_id, "case_id": case_id, "matter_id": matter_id}, "H2,H4")
    # #endregion

    async def save_progress_to_db(progress_data: dict):
        # #region agent log
        _debug_log_bg("save_progress_to_db_called", {"progress_data": progress_data}, "H2")
        # #endregion
        try:
            import_progress = {
                "import_id": import_id,
                "progress": progress_data,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            supabase.table("cases").update({"import_progress": import_progress}).eq("id", case_id).execute()
            # #region agent log
            _debug_log_bg("save_progress_to_db_success", {"case_id": case_id}, "H2")
            # #endregion
        except Exception as e:
            # #region agent log
            _debug_log_bg("save_progress_to_db_error", {"error": str(e)}, "H1,H2")
            # #endregion
            logger.warning(f"Failed to persist import progress to DB: {e}")

    try:
        progress_data = {"type": "progress", "message": "Starting document import from Clio...", "phase": "import_start", "percent": 30}
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Starting document import from Clio...",
            phase="import_start",
            percent=30,
            sub_step="initialization",
        )
        await save_progress_to_db(progress_data)

        logger.debug("Starting document import (background)")
        import_result = await import_clio_documents_helper(
            matter_id, case_id, user, clio_client, supabase, progress_manager, import_id
        )
        logger.info("Import completed", extra={"total_imported": import_result.get("total_imported", 0)})

        await run_in_threadpool(
            lambda: supabase.table("cases")
            .update(
                {
                    "clio_matter_data": {
                        **case_clio_data,
                        "communications_count": import_result.get("communications_count", 0),
                        "notes_count": import_result.get("notes_count", 0),
                        "documents_count": import_result.get("documents_count", 0),
                    }
                }
            )
            .eq("id", case_id)
            .execute()
        )

        fatal_import_error = import_result.get("error")
        if fatal_import_error:
            progress_data = {
                "type": "error",
                "message": f"Import failed: {fatal_import_error}",
                "phase": "error",
                "percent": 40,
                "status": "error",
                "error": str(fatal_import_error),
                "data": {"import_status": import_result, "success": False},
            }
            await progress_manager.publish_progress(
                channel_id=import_id,
                message=f"Import failed: {fatal_import_error}",
                phase="error",
                percent=40,
                status="error",
                error=str(fatal_import_error),
                data={"import_status": import_result, "success": False},
            )
            await save_progress_to_db(progress_data)
            _debug_log_bg("bg_task_error", {"import_id": import_id, "error": str(fatal_import_error)}, "H4")
            return

        progress_data = {"type": "progress", "message": "Analyzing intake documents...", "phase": "analyze_intake", "percent": 90}
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Analyzing intake documents...",
            phase="analyze_intake",
            percent=90,
            sub_step="identification",
        )
        await save_progress_to_db(progress_data)
        logger.debug("Analyzing intake documents")
        intake_analysis = await run_in_threadpool(analyze_intake_documents, case_id, supabase)
        logger.debug("Intake analysis complete", extra={"message": intake_analysis.get("message", "N/A")})

        progress_data = {"type": "completed", "message": "Case creation completed successfully!", "phase": "complete", "percent": 100, "status": "completed"}
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Case creation completed successfully!",
            phase="complete",
            percent=100,
            sub_step="done",
            status="completed",
            data={
                "import_status": import_result,
                "intake_analysis": intake_analysis,
                "success": bool(import_result.get("success", True)),
            },
        )
        await save_progress_to_db(progress_data)
        # #region agent log
        _debug_log_bg("bg_task_complete", {"import_id": import_id, "case_id": case_id}, "H2,H4")
        # #endregion

    except Exception as e:
        logger.exception("Error in background import", extra={"error": str(e)})
        progress_data = {"type": "error", "message": f"Import failed: {str(e)}", "phase": "error", "percent": 0, "status": "error"}
        await progress_manager.publish_progress(
            channel_id=import_id,
            message=f"Import failed: {str(e)}",
            phase="error",
            percent=0,
            status="error",
            error=str(e),
        )
        await save_progress_to_db(progress_data)
        # #region agent log
        _debug_log_bg("bg_task_error", {"import_id": import_id, "error": str(e)}, "H4")
        # #endregion
