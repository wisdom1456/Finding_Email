"""Chunk Service for Token-Based Document Batching

Implements First Fit Decreasing (FFD) bin packing algorithm to create
balanced chunks of documents based on token counts.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_MAX_TOKENS_PER_CHUNK = 50000
MIN_TOKENS_PER_CHUNK = 25000
MAX_TOKENS_PER_CHUNK = 100000


@dataclass
class DocumentInfo:
    """Document metadata for chunking."""

    id: str
    name: str
    token_count: int
    content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tokens": self.token_count,
        }


@dataclass
class Chunk:
    """A chunk of documents to process together."""

    index: int
    doc_ids: List[str] = field(default_factory=list)
    total_tokens: int = 0
    status: str = "pending"  # pending, processing, completed, partial_failure

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "doc_ids": self.doc_ids,
            "tokens": self.total_tokens,
            "status": self.status,
        }


@dataclass
class ChunkPlan:
    """Complete chunk plan for an analysis."""

    chunks: List[Chunk]
    total_documents: int
    total_tokens: int
    max_tokens_per_chunk: int
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": {
                "max_tokens_per_chunk": self.max_tokens_per_chunk,
                "created_at": self.created_at,
            },
            "chunks": [c.to_dict() for c in self.chunks],
            "total_documents": self.total_documents,
            "total_tokens": self.total_tokens,
        }


class ChunkService:
    """Service for creating and managing document chunks."""

    def __init__(self, max_tokens_per_chunk: int = DEFAULT_MAX_TOKENS_PER_CHUNK):
        """Initialize chunk service.
        
        Args:
            max_tokens_per_chunk: Maximum tokens allowed per chunk (default 50,000)

        """
        # Clamp to valid range
        self.max_tokens_per_chunk = max(
            MIN_TOKENS_PER_CHUNK,
            min(max_tokens_per_chunk, MAX_TOKENS_PER_CHUNK)
        )

    def create_balanced_chunks(
        self,
        documents: List[Any],
        token_field: str = "token_count"
    ) -> ChunkPlan:
        """Create token-balanced chunks using First Fit Decreasing algorithm.
        
        This algorithm:
        1. Sorts documents by token count (largest first)
        2. Places each document in the first chunk that has room
        3. Creates a new chunk if no existing chunk has room
        
        Args:
            documents: List of document objects with token_count attribute/field
            token_field: Name of the token count field (default: "token_count")
            
        Returns:
            ChunkPlan with balanced chunks

        """
        if not documents:
            return ChunkPlan(
                chunks=[],
                total_documents=0,
                total_tokens=0,
                max_tokens_per_chunk=self.max_tokens_per_chunk,
            )

        # Extract document info
        doc_infos = []
        for doc in documents:
            doc_id = getattr(doc, 'id', None) or str(uuid4())
            doc_name = getattr(doc, 'file_name', None) or getattr(doc, 'name', 'Unknown')

            # Get token count - try attribute first, then dict access
            if hasattr(doc, token_field):
                tokens = getattr(doc, token_field) or 0
            elif isinstance(doc, dict) and token_field in doc:
                tokens = doc[token_field] or 0
            else:
                # Estimate tokens from content if available
                content = getattr(doc, 'content', '') or ''
                tokens = len(content) // 4  # Rough estimate: 4 chars per token

            doc_infos.append(DocumentInfo(
                id=doc_id,
                name=doc_name,
                token_count=tokens,
            ))

        # Sort by token count descending (First Fit Decreasing)
        sorted_docs = sorted(doc_infos, key=lambda d: d.token_count, reverse=True)

        # Apply FFD bin packing
        chunks: List[Chunk] = []

        for doc in sorted_docs:
            placed = False

            # Try to fit in existing chunk
            for chunk in chunks:
                if chunk.total_tokens + doc.token_count <= self.max_tokens_per_chunk:
                    chunk.doc_ids.append(doc.id)
                    chunk.total_tokens += doc.token_count
                    placed = True
                    break

            # Create new chunk if needed
            if not placed:
                new_chunk = Chunk(
                    index=len(chunks),
                    doc_ids=[doc.id],
                    total_tokens=doc.token_count,
                )
                chunks.append(new_chunk)

        total_tokens = sum(c.total_tokens for c in chunks)

        logger.info(
            f"[CHUNKING] Created {len(chunks)} chunks for {len(documents)} documents "
            f"(total: {total_tokens:,} tokens, max/chunk: {self.max_tokens_per_chunk:,})"
        )

        for i, chunk in enumerate(chunks):
            logger.debug(
                f"  Chunk {i}: {len(chunk.doc_ids)} docs, {chunk.total_tokens:,} tokens"
            )

        return ChunkPlan(
            chunks=chunks,
            total_documents=len(documents),
            total_tokens=total_tokens,
            max_tokens_per_chunk=self.max_tokens_per_chunk,
        )

    def estimate_chunk_time(self, chunk: Chunk) -> float:
        """Estimate processing time for a chunk in seconds.
        
        Based on empirical data:
        - ~8 seconds per 10,000 tokens for GPT processing
        - Plus overhead for API calls and database writes
        
        Args:
            chunk: The chunk to estimate
            
        Returns:
            Estimated time in seconds

        """
        base_time = (chunk.total_tokens / 10000) * 8  # 8 seconds per 10K tokens
        overhead = len(chunk.doc_ids) * 2  # 2 seconds overhead per document
        return base_time + overhead

    def estimate_total_time(self, plan: ChunkPlan) -> float:
        """Estimate total processing time for entire plan.
        
        Args:
            plan: The chunk plan
            
        Returns:
            Estimated time in seconds

        """
        chunk_time = sum(self.estimate_chunk_time(c) for c in plan.chunks)
        synthesis_time = 60  # Case synthesis
        multistage_time = 90  # Multi-stage analysis
        handoff_overhead = len(plan.chunks) * 2  # Chunk handoff time

        return chunk_time + synthesis_time + multistage_time + handoff_overhead

    def get_documents_for_chunk(
        self,
        documents: List[Any],
        chunk: Chunk
    ) -> List[Any]:
        """Get the actual document objects for a chunk.
        
        Args:
            documents: Full list of documents
            chunk: The chunk to get documents for
            
        Returns:
            List of documents in the chunk

        """
        doc_map = {
            (getattr(d, 'id', None) or str(i)): d
            for i, d in enumerate(documents)
        }
        return [doc_map[doc_id] for doc_id in chunk.doc_ids if doc_id in doc_map]


def create_chunk_state(
    documents: List[Any],
    max_tokens_per_chunk: int = DEFAULT_MAX_TOKENS_PER_CHUNK
) -> Dict[str, Any]:
    """Create initial chunk_state for database storage.
    
    Args:
        documents: List of documents to process
        max_tokens_per_chunk: Maximum tokens per chunk
        
    Returns:
        chunk_state dict ready for database storage

    """
    service = ChunkService(max_tokens_per_chunk)
    plan = service.create_balanced_chunks(documents)

    # Build document status dict
    doc_status = {}
    for doc in documents:
        doc_id = getattr(doc, 'id', None) or str(uuid4())
        doc_name = getattr(doc, 'file_name', None) or getattr(doc, 'name', 'Unknown')
        tokens = getattr(doc, 'token_count', 0) or 0

        # Find which chunk this doc is in
        chunk_index = None
        for chunk in plan.chunks:
            if doc_id in chunk.doc_ids:
                chunk_index = chunk.index
                break

        doc_status[doc_id] = {
            "name": doc_name,
            "status": "pending",
            "tokens": tokens,
            "chunk": chunk_index,
        }

    return {
        **plan.to_dict(),
        "current_chunk": 0,
        "phase": "document_analysis",
        "documents": doc_status,
        "summaries": {},
        "lock": None,
    }


def get_pending_documents(chunk_state: Dict[str, Any]) -> List[str]:
    """Get list of document IDs that are still pending."""
    return [
        doc_id for doc_id, info in chunk_state.get("documents", {}).items()
        if info.get("status") == "pending"
    ]


def get_failed_documents(chunk_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get list of failed documents with their error info."""
    return [
        {"id": doc_id, **info}
        for doc_id, info in chunk_state.get("documents", {}).items()
        if info.get("status") == "failed"
    ]


def get_chunk_summary(chunk_state: Dict[str, Any]) -> Dict[str, int]:
    """Get summary counts of document statuses."""
    documents = chunk_state.get("documents", {})
    statuses = [info.get("status", "pending") for info in documents.values()]

    return {
        "total": len(documents),
        "pending": statuses.count("pending"),
        "processing": statuses.count("processing"),
        "completed": statuses.count("completed"),
        "failed": statuses.count("failed"),
        "skipped": statuses.count("skipped"),
    }


def can_proceed_to_synthesis(chunk_state: Dict[str, Any]) -> bool:
    """Check if all documents are addressed (completed or skipped)."""
    summary = get_chunk_summary(chunk_state)
    return summary["pending"] == 0 and summary["processing"] == 0 and summary["failed"] == 0

