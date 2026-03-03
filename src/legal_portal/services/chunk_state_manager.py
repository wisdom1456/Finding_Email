"""Chunk State Manager - Database Operations for Chunked Processing

Handles persistence of chunk_state to Supabase for recovery and status tracking.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from supabase import Client

logger = logging.getLogger(__name__)


class ChunkStateManager:
    """Manages chunk_state persistence in the database."""

    def __init__(self, supabase: Client, analysis_id: str, batch_size: int = 5):
        """Initialize chunk state manager.
        
        Args:
            supabase: Supabase client instance
            analysis_id: The analysis ID to manage state for
            batch_size: Number of updates to batch before writing to DB

        """
        self.supabase = supabase
        self.analysis_id = analysis_id
        self._instance_id = str(uuid4())[:8]  # Short unique ID for this instance
        self._pending_updates = []
        self._batch_size = batch_size
        self._dirty_state = None

    async def initialize_chunk_state(
        self,
        documents: List[Any],
        max_tokens_per_chunk: int = 50000
    ) -> Dict[str, Any]:
        """Initialize chunk_state for a new analysis.
        
        Args:
            documents: List of documents to process
            max_tokens_per_chunk: Maximum tokens per chunk
            
        Returns:
            The initialized chunk_state

        """
        from legal_portal.services.chunk_service import create_chunk_state

        chunk_state = create_chunk_state(documents, max_tokens_per_chunk)

        # Save to database
        try:
            self.supabase.table("analysis_results").update({
                "chunk_state": chunk_state
            }).eq("id", self.analysis_id).execute()

            logger.info(
                f"[CHUNK_STATE] Initialized for {self.analysis_id}: "
                f"{len(chunk_state.get('chunks', []))} chunks, "
                f"{len(chunk_state.get('documents', {}))} documents"
            )
        except Exception as e:
            logger.error(f"[CHUNK_STATE] Failed to initialize: {e}")
            raise

        return chunk_state

    async def get_chunk_state(self) -> Optional[Dict[str, Any]]:
        """Get current chunk_state from database."""
        try:
            response = self.supabase.table("analysis_results").select(
                "chunk_state"
            ).eq("id", self.analysis_id).single().execute()

            return response.data.get("chunk_state") if response.data else None
        except Exception as e:
            logger.error(f"[CHUNK_STATE] Failed to get state: {e}")
            return None

    async def acquire_lock(self, timeout_seconds: int = 330) -> bool:
        """Acquire processing lock to prevent concurrent processing.
        
        Args:
            timeout_seconds: Lock timeout (should be slightly longer than Vercel timeout)
            
        Returns:
            True if lock acquired, False if already locked

        """
        try:
            response = self.supabase.rpc("acquire_analysis_lock", {
                "p_analysis_id": self.analysis_id,
                "p_instance_id": self._instance_id,
                "p_timeout_seconds": timeout_seconds
            }).execute()

            result = response.data
            acquired = result.get("acquired", False)

            if not acquired:
                logger.warning(
                    f"[CHUNK_STATE] Lock not acquired for {self.analysis_id}: "
                    f"{result.get('reason', 'unknown')}"
                )
            else:
                logger.info(f"[CHUNK_STATE] Lock acquired for {self.analysis_id}")

            return acquired
        except Exception as e:
            logger.error(f"[CHUNK_STATE] Failed to acquire lock: {e}")
            # If RPC fails (e.g., function doesn't exist), proceed anyway
            return True

    async def release_lock(self) -> bool:
        """Release processing lock."""
        try:
            response = self.supabase.rpc("release_analysis_lock", {
                "p_analysis_id": self.analysis_id,
                "p_instance_id": self._instance_id
            }).execute()

            result = response.data
            return result.get("released", False)
        except Exception as e:
            logger.warning(f"[CHUNK_STATE] Failed to release lock: {e}")
            return False

    async def update_document_status(
        self,
        doc_id: str,
        status: str,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
        summary: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update the status of a single document.
        
        Args:
            doc_id: Document ID
            status: New status (pending, processing, completed, failed, skipped)
            error: Error message if failed
            error_type: Error type code if failed
            summary: Summary data if completed

        """
        try:
            # Get current state
            current_state = await self.get_chunk_state()
            if not current_state:
                logger.warning(f"[CHUNK_STATE] No state found for {self.analysis_id}")
                return

            documents = current_state.get("documents", {})
            summaries = current_state.get("summaries", {})

            if doc_id not in documents:
                logger.warning(f"[CHUNK_STATE] Document {doc_id} not found in state")
                return

            # Update document status
            doc_info = documents[doc_id]
            doc_info["status"] = status

            if status == "completed":
                doc_info["completed_at"] = datetime.utcnow().isoformat()
                if summary:
                    summary_key = f"sum_{doc_id}"
                    summaries[summary_key] = summary
                    doc_info["summary_key"] = summary_key
            elif status == "failed":
                doc_info["failed_at"] = datetime.utcnow().isoformat()
                doc_info["error"] = error or "Unknown error"
                doc_info["error_type"] = error_type or "UNKNOWN"
                doc_info["retry_count"] = doc_info.get("retry_count", 0) + 1
            elif status == "processing":
                doc_info["started_at"] = datetime.utcnow().isoformat()
            elif status == "skipped":
                doc_info["skipped_at"] = datetime.utcnow().isoformat()

            # Update in-memory state
            current_state["documents"] = documents
            current_state["summaries"] = summaries
            self._dirty_state = current_state
            self._pending_updates.append(doc_id)

            # Batch writes: only write to DB every N updates or on completion
            should_flush = (
                len(self._pending_updates) >= self._batch_size or
                status in ["completed", "failed"]  # Always flush on terminal states
            )

            if should_flush:
                await self._flush_updates()

        except Exception as e:
            logger.error(f"[CHUNK_STATE] Failed to update document status: {e}")

    async def update_chunk_status(
        self,
        chunk_index: int,
        status: str
    ) -> None:
        """Update the status of a chunk.
        
        Args:
            chunk_index: Index of the chunk
            status: New status (pending, processing, completed, partial_failure)

        """
        try:
            current_state = await self.get_chunk_state()
            if not current_state:
                return

            chunks = current_state.get("chunks", [])
            if chunk_index < len(chunks):
                chunks[chunk_index]["status"] = status
                current_state["chunks"] = chunks
                current_state["current_chunk"] = chunk_index

                # Batch this update too
                self._dirty_state = current_state
                self._pending_updates.append(f"chunk_{chunk_index}")

                # Flush on chunk completion
                if status in ["completed", "partial_failure"]:
                    await self._flush_updates()

        except Exception as e:
            logger.error(f"[CHUNK_STATE] Failed to update chunk status: {e}")

    async def update_phase(self, phase: str) -> None:
        """Update the processing phase.
        
        Args:
            phase: New phase (document_analysis, synthesis, multi_stage, completed, failed)

        """
        try:
            current_state = await self.get_chunk_state()
            if not current_state:
                return

            current_state["phase"] = phase

            # Always flush phase changes immediately (they're rare and important)
            self.supabase.table("analysis_results").update({
                "chunk_state": current_state
            }).eq("id", self.analysis_id).execute()

            logger.info(f"[CHUNK_STATE] Phase updated to: {phase}")

        except Exception as e:
            logger.error(f"[CHUNK_STATE] Failed to update phase: {e}")

    async def get_failed_documents(self) -> List[Dict[str, Any]]:
        """Get list of failed documents with error info."""
        state = await self.get_chunk_state()
        if not state:
            return []

        return [
            {"id": doc_id, **info}
            for doc_id, info in state.get("documents", {}).items()
            if info.get("status") == "failed"
        ]

    async def get_document_summary(self) -> Dict[str, int]:
        """Get summary counts of document statuses."""
        state = await self.get_chunk_state()
        if not state:
            return {"total": 0, "pending": 0, "processing": 0, "completed": 0, "failed": 0, "skipped": 0}

        documents = state.get("documents", {})
        statuses = [info.get("status", "pending") for info in documents.values()]

        return {
            "total": len(documents),
            "pending": statuses.count("pending"),
            "processing": statuses.count("processing"),
            "completed": statuses.count("completed"),
            "failed": statuses.count("failed"),
            "skipped": statuses.count("skipped"),
        }

    async def can_proceed_to_synthesis(self) -> bool:
        """Check if all documents are addressed (completed or skipped)."""
        summary = await self.get_document_summary()
        return summary["pending"] == 0 and summary["processing"] == 0 and summary["failed"] == 0

    async def mark_documents_skipped(self, doc_ids: List[str]) -> int:
        """Mark multiple documents as skipped.
        
        Args:
            doc_ids: List of document IDs to skip
            
        Returns:
            Number of documents marked as skipped

        """
        count = 0
        for doc_id in doc_ids:
            await self.update_document_status(doc_id, "skipped")
            count += 1
        return count

    async def reset_documents_for_retry(self, doc_ids: List[str]) -> int:
        """Reset documents to pending status for retry.
        
        Args:
            doc_ids: List of document IDs to retry
            
        Returns:
            Number of documents reset

        """
        try:
            current_state = await self.get_chunk_state()
            if not current_state:
                return 0

            documents = current_state.get("documents", {})
            count = 0

            for doc_id in doc_ids:
                if doc_id in documents:
                    documents[doc_id]["status"] = "pending"
                    documents[doc_id]["error"] = None
                    documents[doc_id]["error_type"] = None
                    count += 1

            current_state["documents"] = documents

            self.supabase.table("analysis_results").update({
                "chunk_state": current_state
            }).eq("id", self.analysis_id).execute()

            return count
        except Exception as e:
            logger.error(f"[CHUNK_STATE] Failed to reset documents: {e}")
            return 0

    async def get_all_summaries(self) -> List[Dict[str, Any]]:
        """Get all completed document summaries."""
        state = await self.get_chunk_state()
        if not state:
            return []

        summaries = state.get("summaries", {})
        return list(summaries.values())

    async def finalize(self) -> None:
        """Flush any pending updates before closing. Call this at the end of processing."""
        if self._pending_updates:
            logger.info(f"[CHUNK_STATE] Finalizing with {len(self._pending_updates)} pending updates")
            await self._flush_updates()

    async def _flush_updates(self) -> None:
        """Flush pending updates to database."""
        if not self._dirty_state:
            return

        try:
            self.supabase.table("analysis_results").update({
                "chunk_state": self._dirty_state
            }).eq("id", self.analysis_id).execute()

            logger.info(
                f"[CHUNK_STATE] Flushed {len(self._pending_updates)} updates to DB"
            )
            self._pending_updates.clear()
            self._dirty_state = None

        except Exception as e:
            logger.error(f"[CHUNK_STATE] Failed to flush updates: {e}")
            raise

    async def save_summary(self, doc_id: str, summary: Dict[str, Any]) -> None:
        """Save a document summary to chunk_state.
        
        Args:
            doc_id: Document ID
            summary: Summary data

        """
        try:
            current_state = await self.get_chunk_state()
            if not current_state:
                return

            summaries = current_state.get("summaries", {})
            summary_key = f"sum_{doc_id}"
            summaries[summary_key] = summary

            # Also update the document record
            documents = current_state.get("documents", {})
            if doc_id in documents:
                documents[doc_id]["summary_key"] = summary_key

            current_state["summaries"] = summaries
            current_state["documents"] = documents

            self.supabase.table("analysis_results").update({
                "chunk_state": current_state
            }).eq("id", self.analysis_id).execute()

        except Exception as e:
            logger.error(f"[CHUNK_STATE] Failed to save summary: {e}")

