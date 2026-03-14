from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from legal_portal.core.data_models import DocumentGroup, DocumentSummaryStructured, FactMatrix, GroupType, ProcessedDocument

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(
    r"\b("
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"  # MM/DD/YYYY or M-D-YY
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"  # Jan 15, 2025
    r"|\d{4}-\d{2}-\d{2}"  # ISO 2025-01-15
    r")\b",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d{2})?",
)
_STATEMENT_KEYWORDS = re.compile(
    r"\b(statement\s+period|account\s+summary|account\s+ending|"
    r"checking\s+account|savings\s+account)\b",
    re.IGNORECASE,
)
_ACCOUNT_RE = re.compile(r"(?:\*{2,4}|x{2,4}|ending\s+in\s*)(\d{3,6})", re.IGNORECASE)
_INSTITUTION_RE = re.compile(
    r"\b(Chase|Wells\s+Fargo|Bank\s+of\s+America|Citibank|Capital\s+One|"
    r"TD\s+Bank|PNC|US\s+Bank|USAA|Ally|Discover|American\s+Express|"
    r"SunTrust|BB&T|Truist|Regions|Fifth\s+Third|KeyBank|Huntington|"
    r"Citizens|M&T\s+Bank|Comerica|Zions|BMO|HSBC|Barclays|"
    r"Navy\s+Federal)\b",
    re.IGNORECASE,
)


class DocumentRegistryService:
    """Build an authoritative document registry used across analysis and letters.

    The registry captures document classification, execution status, authority tier,
    and extracted structured anchors (parties, dates, amounts) in a consistent format.

    Supports staged enrichment:
      Stage 1 (extraction): build_initial_registry() — heuristics only, no AI
      Stage 2 (cross-doc):  enrich_cross_document()  — relationship detection
      Stage 3 (attorney):   managed by verify endpoint
      Stage 4 (AI):         enrich_with_ai()          — merges AI summary data
    """

    _INSTRUMENT_PATTERNS = [
        ("subscription agreement", re.compile(r"\bsubscription\s+agreement\b", re.IGNORECASE)),
        ("operating agreement", re.compile(r"\boperating\s+agreement\b", re.IGNORECASE)),
        ("promissory note", re.compile(r"\bpromissory\s+note\b", re.IGNORECASE)),
        ("investment agreement", re.compile(r"\binvestment\s+agreement\b", re.IGNORECASE)),
        ("purchase agreement", re.compile(r"\b(?:unit\s+)?purchase\s+agreement\b", re.IGNORECASE)),
        ("loan agreement", re.compile(r"\bloan\s+agreement\b", re.IGNORECASE)),
        ("financing memo", re.compile(r"\b(memo\s+terms|terms\s+for\s+financing)\b", re.IGNORECASE)),
        ("membership certificate", re.compile(r"\bmembership\s+certificate\b", re.IGNORECASE)),
        ("articles of organization", re.compile(r"\barticles?\s+of\s+(organization|incorporation)\b", re.IGNORECASE)),
        ("business search", re.compile(r"\bbusiness\s+search\b", re.IGNORECASE)),
        ("offering materials", re.compile(r"\b(form\s*c|offering|crowdfunding|investor\s+packet)\b", re.IGNORECASE)),
        ("financial statements", re.compile(r"\b(p&l|profit\s+and\s+loss|balance\s+sheet|financial)\b", re.IGNORECASE)),
        ("correspondence", re.compile(r"\b(email|correspondence|message|update|text)\b", re.IGNORECASE)),
    ]

    # ------------------------------------------------------------------ #
    #  Stage 1: Post-extraction (called per-document during upload)
    # ------------------------------------------------------------------ #

    def build_initial_registry(self, processed_doc: ProcessedDocument) -> Dict[str, Any]:
        """Build a single registry record from extraction data only.

        Uses filename, file_type, extracted text snippet, and signature_detection.
        No AI calls. Sets enrichment_stage='extraction'.
        """
        file_name = (processed_doc.file_name or "").strip()
        normalized_name = self._normalize_name(file_name)
        signature = processed_doc.signature_detection or {}
        enrichment = processed_doc.attorney_enrichment or {}
        content_snippet = (processed_doc.content or "")[:3000]

        doc_blob = self._compose_instrument_corpus(
            file_name=file_name,
            summary={},
            content=content_snippet,
        )
        instrument_hints = self._extract_instrument_hints(doc_blob)
        primary_instrument = instrument_hints[0] if instrument_hints else None

        doc_type = self._infer_doc_type_from_name(file_name, instrument_hints)
        doc_type_confidence = "medium" if doc_type != "Other" else "low"

        role_in_case = self._infer_role_in_case(
            file_name=file_name,
            doc_type=doc_type,
            instrument_hints=instrument_hints,
            legal_significance="",
        )
        authority_level, authority_reason = self._infer_authority(
            doc_type=doc_type,
            instrument_hints=instrument_hints,
            execution_status=str(signature.get("status") or "unknown"),
            role_in_case=role_in_case,
        )
        authority_score = self._score_authority(
            authority_level=authority_level,
            execution_status=str(signature.get("status") or "unknown"),
            summary={},
            key_doc={},
        )
        signature_expected, signature_expectation_reason = self._infer_signature_expectation(
            file_name=file_name,
            doc_type=doc_type,
            instrument_hints=instrument_hints,
        )

        quick_facts = self._extract_quick_facts(content_snippet)
        system_summary = self._generate_system_summary(
            processed_doc.content or "", doc_type, normalized_name
        )

        reliability_notes: List[str] = []
        extraction_quality = (processed_doc.extraction_quality or "").lower()
        if extraction_quality in {"low", "medium"}:
            reliability_notes.append(f"Extraction quality is {extraction_quality}.")
        if str(signature.get("status") or "").lower() == "not_detected":
            reliability_notes.append("No signature markers detected in extracted text.")
        signature_review_recommended = (
            bool(signature_expected)
            and str(signature.get("status") or "unknown").lower() not in {"signed"}
            and str(signature.get("confidence") or "").lower() != "verified"
        )
        if signature_review_recommended:
            reliability_notes.append(
                "Document type is typically executed; attorney signature verification recommended."
            )

        return {
            "document_id": processed_doc.document_id,
            "document_name": file_name,
            "normalized_name": normalized_name,
            "file_type": getattr(getattr(processed_doc, "file_type", None), "value", None)
            or str(getattr(processed_doc, "file_type", "") or ""),
            "document_type": doc_type or "Other",
            "document_type_confidence": doc_type_confidence,
            "document_type_source": "extraction",
            "role_in_case": role_in_case,
            "authority_level": authority_level,
            "authority_score": authority_score,
            "authority_reason": authority_reason,
            "is_key_document": False,
            "key_document_significance": None,
            "instrument_hints": instrument_hints,
            "primary_instrument": primary_instrument,
            "execution_status": signature.get("status") or "unknown",
            "execution_confidence": signature.get("confidence") or "none",
            "execution_source": signature.get("detection_source") or "ingestion",
            "signature_expected": signature_expected,
            "signature_expectation_reason": signature_expectation_reason,
            "signature_review_recommended": signature_review_recommended,
            "signing_date": signature.get("signing_date"),
            "signer_names": self._ensure_list(signature.get("signer_names")),
            "parties_mentioned": [],
            "dates_mentioned": quick_facts.get("dates", []),
            "amounts_mentioned": quick_facts.get("amounts", []),
            "system_summary": system_summary,
            # Fact source separation: quick_facts_raw is regex-extracted at upload time.
            # quick_facts_ai is populated later by AI enrichment (Stage 4).
            # attorney_enrichment.key_facts is set by attorney (Stage 3).
            # Resolution order: attorney > ai > raw
            "quick_facts_raw": quick_facts,
            "quick_facts_ai": None,
            "legal_significance": None,
            "relevance_to_case": None,
            "important_details": [],
            "reliability_notes": reliability_notes,
            "document_type_override": enrichment.get("document_type_override"),
            "relevance_level": enrichment.get("relevance_level"),
            "key_facts": enrichment.get("key_facts"),
            "attorney_notes": enrichment.get("attorney_notes"),
            "document_relationships": enrichment.get("document_relationships"),
            "enrichment_stage": "extraction",
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #
    #  Stage 2: Cross-document (after all uploads for a case)
    # ------------------------------------------------------------------ #

    def enrich_cross_document(
        self,
        registries: List[Dict[str, Any]],
        processed_docs: List[ProcessedDocument],
    ) -> List[Dict[str, Any]]:
        """Add cross-document relationships: email thread grouping, filename similarity.

        Sets enrichment_stage='cross_doc' for updated records.
        """
        # Build lookup of file_name -> registry index
        name_to_idx: Dict[str, int] = {}
        for i, reg in enumerate(registries):
            name_to_idx[reg.get("document_name", "")] = i

        # --- Email thread grouping ---
        email_groups: Dict[str, List[str]] = {}
        for pdoc in processed_docs or []:
            fn = (pdoc.file_name or "").strip()
            if not fn:
                continue
            idx = name_to_idx.get(fn)
            if idx is None:
                continue
            reg = registries[idx]
            if reg.get("document_type") not in ("Correspondence", "Email"):
                continue
            # Extract subject from email content
            subject = self._extract_email_subject(pdoc.content or "")
            if subject:
                email_groups.setdefault(subject, []).append(fn)

        # Apply email thread relationships
        for subject, group_names in email_groups.items():
            if len(group_names) < 2:
                continue
            for fn in group_names:
                idx = name_to_idx.get(fn)
                if idx is None:
                    continue
                reg = registries[idx]
                related = [n for n in group_names if n != fn]
                existing = reg.get("suggested_relationships") or []
                existing.append({
                    "type": "email_thread",
                    "subject": subject,
                    "related_documents": related,
                })
                reg["suggested_relationships"] = existing
                reg["enrichment_stage"] = "cross_doc"
                reg["enriched_at"] = datetime.now(timezone.utc).isoformat()

        # --- Sequential photo detection ---
        photo_docs = []
        for reg in registries:
            fn = reg.get("document_name", "")
            if reg.get("document_type") == "Photo/Media" or any(
                fn.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".heic")
            ):
                photo_docs.append(reg)

        if len(photo_docs) >= 2:
            # Sort by filename and detect sequential numbering
            photo_docs.sort(key=lambda r: r.get("document_name", ""))
            seq_re = re.compile(r"(\d+)\.[a-z]+$", re.IGNORECASE)
            for i in range(len(photo_docs) - 1):
                m1 = seq_re.search(photo_docs[i].get("document_name", ""))
                m2 = seq_re.search(photo_docs[i + 1].get("document_name", ""))
                if m1 and m2 and abs(int(m1.group(1)) - int(m2.group(1))) <= 2:
                    for reg in (photo_docs[i], photo_docs[i + 1]):
                        existing = reg.get("suggested_relationships") or []
                        peer = photo_docs[i + 1] if reg is photo_docs[i] else photo_docs[i]
                        existing.append({
                            "type": "sequential_photo",
                            "related_documents": [peer.get("document_name", "")],
                        })
                        reg["suggested_relationships"] = existing
                        if reg.get("enrichment_stage") != "cross_doc":
                            reg["enrichment_stage"] = "cross_doc"
                            reg["enriched_at"] = datetime.now(timezone.utc).isoformat()

        # --- Contract family detection ---
        # Detect base+addendum/amendment/exhibit/schedule/attachment patterns.
        _FAMILY_SUFFIXES = re.compile(
            r"[_\s\-]+(addendum|amendment|exhibit|schedule|attachment|supplement|rider|appendix)"
            r"[\s_\-]*[a-z0-9]*$",
            re.IGNORECASE,
        )
        # Group registries by a "family stem" derived from the normalized name
        family_stems: Dict[str, List[Dict[str, Any]]] = {}
        for reg in registries:
            norm = reg.get("normalized_name", "")
            if not norm:
                continue
            stem = _FAMILY_SUFFIXES.sub("", norm).strip()
            if stem and stem != norm:
                # This doc has a family suffix — group under the stem
                family_stems.setdefault(stem, []).append(reg)
            else:
                # Could be a base document — only include if other docs share its stem
                family_stems.setdefault(norm, []).append(reg)

        for stem, members in family_stems.items():
            if len(members) < 2:
                continue
            member_names = [m.get("document_name", "") for m in members]
            for reg in members:
                related = [n for n in member_names if n != reg.get("document_name", "")]
                if not related:
                    continue
                existing = reg.get("suggested_relationships") or []
                # Avoid duplicate family entries
                if any(r.get("type") == "contract_family" for r in existing):
                    continue
                existing.append({
                    "type": "contract_family",
                    "stem": stem,
                    "related_documents": related,
                })
                reg["suggested_relationships"] = existing
                if reg.get("enrichment_stage") != "cross_doc":
                    reg["enrichment_stage"] = "cross_doc"
                    reg["enriched_at"] = datetime.now(timezone.utc).isoformat()

        return registries

    # ------------------------------------------------------------------ #
    #  Stage 4: AI enrichment (called during analysis)
    # ------------------------------------------------------------------ #

    def enrich_with_ai(
        self,
        registry: Dict[str, Any],
        summary: Dict[str, Any],
        key_doc: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Enrich existing registry record with AI analysis results.

        Document type replacement rules:
          - attorney_enrichment.document_type_override exists → NEVER replace
          - current confidence == "high" → store AI suggestion only (no replace)
          - current confidence == "medium" → store AI suggestion only (no replace)
          - current confidence == "low" AND no attorney override → auto-replace

        NEVER overwrites attorney-set values.
        Sets enrichment_stage='ai_analysis'.
        """
        key_doc = key_doc or {}
        has_attorney_type_override = bool(registry.get("document_type_override"))

        # --- Document type classification with strict replacement rules ---
        ai_doc_type = str(summary.get("document_type") or "").strip()
        if ai_doc_type:
            # Always store the AI suggestion for transparency
            registry["ai_suggested_document_type"] = ai_doc_type
            registry["ai_document_type_confidence"] = "high"

            if not has_attorney_type_override:
                current_confidence = registry.get("document_type_confidence", "low")
                if current_confidence == "low":
                    # Only auto-replace when current confidence is low
                    registry["document_type"] = ai_doc_type
                    registry["document_type_confidence"] = "high"
                    registry["document_type_source"] = "ai"
                # medium and high: AI suggestion stored above but type NOT replaced

        # Add AI-only fields (these are always null before AI runs)
        registry["legal_significance"] = summary.get("legal_significance")
        registry["relevance_to_case"] = summary.get("relevance_to_case")
        registry["important_details"] = self._ensure_list(summary.get("important_details"))[:6]

        # --- Fact source separation ---
        # AI-extracted facts go into quick_facts_ai, NOT merged into quick_facts_raw.
        # Resolution order: attorney_enrichment.key_facts > quick_facts_ai > quick_facts_raw
        ai_parties = self._collect_parties(summary)
        ai_dates = self._collect_dates(summary)
        ai_amounts = self._collect_amounts(summary)
        registry["quick_facts_ai"] = {
            "parties": ai_parties,
            "dates": ai_dates,
            "amounts": ai_amounts,
        }

        # Update top-level mention fields with best available data (AI > regex)
        if ai_parties:
            registry["parties_mentioned"] = ai_parties
        if ai_dates:
            registry["dates_mentioned"] = ai_dates
        if ai_amounts:
            registry["amounts_mentioned"] = ai_amounts

        # Key document status from FactMatrix
        if key_doc:
            registry["is_key_document"] = True
            registry["key_document_significance"] = key_doc.get("significance")

        # Recalculate role and authority with AI context
        file_name = registry.get("document_name", "")
        instrument_hints = registry.get("instrument_hints", [])

        # Re-compose instrument corpus with AI summary data for better hints
        doc_blob = self._compose_instrument_corpus(
            file_name=file_name,
            summary=summary,
            content="",
        )
        ai_hints = self._extract_instrument_hints(doc_blob)
        # Merge new hints (AI may find instruments in full text that extraction missed)
        existing_hint_set = {h.lower() for h in instrument_hints}
        for hint in ai_hints:
            if hint.lower() not in existing_hint_set:
                instrument_hints.append(hint)
                existing_hint_set.add(hint.lower())
        registry["instrument_hints"] = instrument_hints[:8]
        if instrument_hints and not registry.get("primary_instrument"):
            registry["primary_instrument"] = instrument_hints[0]

        role_in_case = self._infer_role_in_case(
            file_name=file_name,
            doc_type=registry.get("document_type", "Other"),
            instrument_hints=instrument_hints,
            legal_significance=str(summary.get("legal_significance") or ""),
        )
        registry["role_in_case"] = role_in_case

        authority_level, authority_reason = self._infer_authority(
            doc_type=registry.get("document_type", "Other"),
            instrument_hints=instrument_hints,
            execution_status=registry.get("execution_status", "unknown"),
            role_in_case=role_in_case,
        )
        registry["authority_level"] = authority_level
        registry["authority_reason"] = authority_reason
        registry["authority_score"] = self._score_authority(
            authority_level=authority_level,
            execution_status=registry.get("execution_status", "unknown"),
            summary=summary,
            key_doc=key_doc,
        )

        # Update system_summary with AI executive summary if available
        ai_summary_text = str(summary.get("executive_summary") or "").strip()
        if ai_summary_text:
            registry["system_summary"] = ai_summary_text[:500]

        registry["enrichment_stage"] = "ai_analysis"
        registry["enriched_at"] = datetime.now(timezone.utc).isoformat()
        return registry

    # ------------------------------------------------------------------ #
    #  Persistence helper
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    #  Value Resolution
    # ------------------------------------------------------------------ #
    #
    #  Document type hierarchy (first non-empty wins):
    #    1. document_type_override  — attorney explicitly set this (ALWAYS WINS)
    #    2. document_type           — base type (heuristic at upload, or AI-upgraded)
    #    3. "Other"                 — fallback when both are empty
    #
    #  The effective value is written to the `document_type_label` column.
    #  The `ai_suggested_document_type` field stores the AI's suggestion
    #  even when it was not auto-applied (for transparency / audit).
    #
    #  Confidence tracks the base type source:
    #    "low"    — filename keyword only
    #    "medium" — extraction heuristic with instrument hints
    #    "high"   — AI classification
    #
    #  Frontend reads:
    #    doc.document_type_label           — effective display value
    #    doc.metadata.attorney_enrichment.document_type_override — for "override" styling
    #    doc.metadata.registry.ai_suggested_document_type        — AI's suggestion (if different)
    # ------------------------------------------------------------------ #

    @staticmethod
    def resolve_effective_type(registry: Dict[str, Any]) -> str:
        """Return the effective document type: override > base > 'Other'."""
        return (
            registry.get("document_type_override")
            or registry.get("document_type")
            or "Other"
        )

    @staticmethod
    def resolve_denormalized_columns(registry: Dict[str, Any]) -> Dict[str, Any]:
        """Compute denormalized column values from a registry dict.

        Returns a dict with the column values that should be written to the
        documents table alongside the registry. Used by persist_to_document()
        and the verify endpoint to keep columns in sync.
        """
        effective_type = DocumentRegistryService.resolve_effective_type(registry)
        return {
            "document_type_label": effective_type,
            "document_type_confidence": registry.get("document_type_confidence", "low"),
            "signed_status": registry.get("execution_status") or "unknown",
            "signature_expected": bool(registry.get("signature_expected", False)),
            "system_summary": registry.get("system_summary"),
            "enrichment_stage": registry.get("enrichment_stage", "extraction"),
        }

    @staticmethod
    def persist_to_document(
        document_id: str,
        registry: Dict[str, Any],
        supabase_client: Any,
    ) -> None:
        """Write registry to metadata.registry and update denormalized columns.

        THIS IS THE ONLY ALLOWED WRITE PATH for registry-backed document fields:
        document_type_label, document_type_confidence, signed_status,
        signature_expected, system_summary, enrichment_stage, metadata.registry.

        The verify endpoint is the one exception: it updates attorney_enrichment
        in the same transaction and uses resolve_denormalized_columns() to keep
        the denormalized columns in sync.
        """
        # Fetch current metadata to merge registry into it
        result = (
            supabase_client.table("documents")
            .select("metadata")
            .eq("id", document_id)
            .single()
            .execute()
        )
        metadata = (result.data or {}).get("metadata") or {}
        metadata["registry"] = registry

        # Try with denormalized columns; fall back to metadata-only if columns
        # don't exist yet (migration pending).
        update_payload = DocumentRegistryService.resolve_denormalized_columns(registry)
        update_payload["metadata"] = metadata

        try:
            supabase_client.table("documents").update(update_payload).eq("id", document_id).execute()
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "persist_to_document: denormalized columns not available, writing metadata only"
            )
            supabase_client.table("documents").update(
                {"metadata": metadata}
            ).eq("id", document_id).execute()

    # ------------------------------------------------------------------ #
    #  Diagnostic
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_registry_integrity(document: Dict[str, Any]) -> List[str]:
        """Check that a document's denormalized columns match its registry.

        Returns a list of mismatch descriptions. Empty list = healthy.
        Accepts a document row dict with top-level columns and metadata.registry.
        """
        issues: List[str] = []
        registry = (document.get("metadata") or {}).get("registry")
        if registry is None:
            issues.append("metadata.registry is missing")
            return issues

        expected = DocumentRegistryService.resolve_denormalized_columns(registry)
        for col, expected_val in expected.items():
            actual_val = document.get(col)
            if actual_val != expected_val:
                issues.append(
                    f"column '{col}' mismatch: expected {expected_val!r}, got {actual_val!r}"
                )

        # Check enrichment_stage is a known value
        stage = registry.get("enrichment_stage")
        valid_stages = {"none", "extraction", "cross_doc", "ai_analysis", "migration"}
        if stage not in valid_stages:
            issues.append(f"unknown enrichment_stage: {stage!r}")

        # Check fact source separation
        if registry.get("quick_facts_raw") is not None and not isinstance(
            registry.get("quick_facts_raw"), dict
        ):
            issues.append("quick_facts_raw should be a dict or None")
        if registry.get("quick_facts_ai") is not None and not isinstance(
            registry.get("quick_facts_ai"), dict
        ):
            issues.append("quick_facts_ai should be a dict or None")

        # Check for AI-derived fields present but stage != ai_analysis
        if stage != "ai_analysis":
            ai_fields = (
                "legal_significance",
                "relevance_to_case",
                "important_details",
                "quick_facts_ai",
            )
            present = [f for f in ai_fields if registry.get(f)]
            if present:
                issues.append(
                    f"inconsistent_enrichment_stage: ai fields {present} "
                    f"present but stage={stage!r} (expected 'ai_analysis')"
                )

        return issues

    # ------------------------------------------------------------------ #
    #  Legacy wrapper (backward compatibility)
    # ------------------------------------------------------------------ #

    def build_registry(
        self,
        processed_documents: List[ProcessedDocument],
        document_summaries: List[DocumentSummaryStructured],
        fact_matrix: Optional[FactMatrix] = None,
    ) -> List[Dict[str, Any]]:
        """Build registry rows merged from processed docs, summaries, and fact matrix.

        Legacy wrapper that calls build_initial_registry + enrich_with_ai for each doc.
        """
        summary_by_name = {
            self._normalize_name(item.document_name): item.model_dump(mode="json")
            for item in (document_summaries or [])
            if (item.document_name or "").strip()
        }
        key_docs_by_name = {
            self._normalize_name(k.document_name): k.model_dump(mode="json")
            for k in ((fact_matrix.key_documents if fact_matrix else []) or [])
            if (k.document_name or "").strip()
        }

        registry: List[Dict[str, Any]] = []
        seen_names = set()

        for pdoc in processed_documents or []:
            file_name = (pdoc.file_name or "").strip()
            if not file_name:
                continue
            normalized_name = self._normalize_name(file_name)
            if normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)

            # Stage 1: build initial registry from extraction data
            entry = self.build_initial_registry(pdoc)

            # Stage 4: enrich with AI data if available
            summary = summary_by_name.get(normalized_name, {})
            key_doc = key_docs_by_name.get(normalized_name, {})
            if summary:
                entry = self.enrich_with_ai(entry, summary, key_doc)
            elif key_doc:
                entry["is_key_document"] = True
                entry["key_document_significance"] = key_doc.get("significance")

            registry.append(entry)

        # Include summaries not present in processed docs map (defensive for legacy rows).
        for normalized_name, summary in summary_by_name.items():
            if normalized_name in seen_names:
                continue
            file_name = str(summary.get("document_name") or "Unknown Document").strip()
            key_doc = key_docs_by_name.get(normalized_name, {})
            doc_blob = self._compose_instrument_corpus(
                file_name=file_name,
                summary=summary,
                content="",
            )
            instrument_hints = self._extract_instrument_hints(doc_blob)
            doc_type = str(summary.get("document_type") or "").strip() or self._infer_doc_type_from_name(
                file_name, instrument_hints
            )
            role_in_case = self._infer_role_in_case(
                file_name=file_name,
                doc_type=doc_type,
                instrument_hints=instrument_hints,
                legal_significance=str(summary.get("legal_significance") or ""),
            )
            authority_level, authority_reason = self._infer_authority(
                doc_type=doc_type,
                instrument_hints=instrument_hints,
                execution_status="unknown",
                role_in_case=role_in_case,
            )
            signature_expected, signature_expectation_reason = self._infer_signature_expectation(
                file_name=file_name,
                doc_type=doc_type,
                instrument_hints=instrument_hints,
            )
            signature_review_recommended = bool(signature_expected)
            registry.append(
                {
                    "document_id": None,
                    "document_name": file_name,
                    "normalized_name": normalized_name,
                    "file_type": "",
                    "document_type": doc_type or "Other",
                    "document_type_confidence": "high" if summary.get("document_type") else "low",
                    "document_type_source": "ai" if summary.get("document_type") else "filename",
                    "role_in_case": role_in_case,
                    "authority_level": authority_level,
                    "authority_score": self._score_authority(
                        authority_level=authority_level,
                        execution_status="unknown",
                        summary=summary,
                        key_doc=key_doc,
                    ),
                    "authority_reason": authority_reason,
                    "is_key_document": bool(key_doc),
                    "key_document_significance": key_doc.get("significance"),
                    "instrument_hints": instrument_hints,
                    "primary_instrument": instrument_hints[0] if instrument_hints else None,
                    "execution_status": "unknown",
                    "execution_confidence": "none",
                    "execution_source": "none",
                    "signature_expected": signature_expected,
                    "signature_expectation_reason": signature_expectation_reason,
                    "signature_review_recommended": signature_review_recommended,
                    "signing_date": None,
                    "signer_names": [],
                    "parties_mentioned": self._collect_parties(summary),
                    "dates_mentioned": self._collect_dates(summary),
                    "amounts_mentioned": self._collect_amounts(summary),
                    "system_summary": str(summary.get("executive_summary") or "")[:500] or None,
                    "quick_facts_raw": {},
                    "quick_facts_ai": {
                        "parties": self._collect_parties(summary),
                        "dates": self._collect_dates(summary),
                        "amounts": self._collect_amounts(summary),
                    },
                    "legal_significance": summary.get("legal_significance"),
                    "relevance_to_case": summary.get("relevance_to_case"),
                    "important_details": self._ensure_list(summary.get("important_details"))[:6],
                    "reliability_notes": [],
                    "enrichment_stage": "ai_analysis" if summary else "none",
                    "enriched_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        registry.sort(
            key=lambda row: (
                -int(row.get("authority_score") or 0),
                str(row.get("document_name") or "").lower(),
            )
        )
        return registry

    # ------------------------------------------------------------------ #
    #  New helper methods
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_quick_facts(text: str) -> Dict[str, List[str]]:
        """Regex extraction of dates and dollar amounts from first 3000 chars."""
        snippet = (text or "")[:3000]
        dates = list(dict.fromkeys(m.group(0) for m in _DATE_RE.finditer(snippet)))[:8]
        amounts = list(dict.fromkeys(m.group(0) for m in _AMOUNT_RE.finditer(snippet)))[:8]
        return {"dates": dates, "amounts": amounts}

    @staticmethod
    def _generate_system_summary(
        text: str, doc_type: str, normalized_name: str = ""
    ) -> Optional[str]:
        """First meaningful sentence from extracted text, capped at 200 chars.

        Protects against OCR garbage, email header blocks, and other noise.
        Falls back to a safe descriptor built from normalized_name + doc_type.
        """

        def _is_ocr_garbage(s: str) -> bool:
            """Detect OCR noise: excessive punctuation or non-alpha ratio."""
            if not s:
                return True
            alpha = sum(1 for c in s if c.isalpha())
            return alpha / len(s) < 0.4

        def _is_email_header(s: str) -> bool:
            lower = s.lower()
            return any(
                lower.startswith(p)
                for p in ("from:", "to:", "cc:", "bcc:", "date:", "subject:", "sent:")
            )

        def _safe_fallback() -> Optional[str]:
            """Build a neutral summary from filename + doc type."""
            label = (normalized_name or "").strip()
            dtype = (doc_type or "").strip()
            if label and dtype:
                return f"{label.replace(' ', '_')} — {dtype} document."
            if label:
                return f"{label.replace(' ', '_')} document."
            if dtype:
                return f"{dtype} document."
            return None

        if not text:
            return _safe_fallback()

        lines = text.strip().splitlines()
        for line in lines:
            stripped = line.strip()
            if len(stripped) < 20:
                continue
            if stripped.upper() == stripped and len(stripped) < 60:
                continue  # All-caps header
            if _is_email_header(stripped):
                continue
            if _is_ocr_garbage(stripped):
                continue
            # Take first meaningful line, truncate to 200 chars
            if len(stripped) > 200:
                dot_pos = stripped.rfind(".", 0, 200)
                if dot_pos > 80:
                    return stripped[: dot_pos + 1]
                return stripped[:197] + "..."
            return stripped

        # No usable line found — fall back to filename-based summary
        return _safe_fallback()

    @staticmethod
    def _extract_email_subject(content: str) -> Optional[str]:
        """Extract normalized email subject from content for thread grouping."""
        if not content:
            return None
        for line in content.splitlines()[:30]:
            if line.lower().startswith("subject:"):
                raw = line[8:].strip()
                # Normalize: strip Re:/Fwd: prefixes
                normalized = re.sub(r"^(?:re|fwd?|fw)\s*:\s*", "", raw, flags=re.IGNORECASE).strip()
                return normalized.lower() if normalized else None
        return None

    # ------------------------------------------------------------------ #
    #  Existing private helpers (unchanged)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_name(value: str) -> str:
        text = (value or "").lower().strip()
        text = re.sub(r"\.[a-z0-9]{1,8}$", "", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    # ------------------------------------------------------------------ #
    #  Document Group Detection (Phase A)
    # ------------------------------------------------------------------ #

    def detect_document_groups(
        self,
        documents: List[Dict[str, Any]],
    ) -> List[DocumentGroup]:
        """Detect groups of related documents. Deterministic — no AI calls.

        First rollout: only high-confidence group types (email threads,
        contract families, sequential photos, bank statements with
        institution + account + statement pattern).

        Returns list of DocumentGroup. Documents not in any group are excluded.
        A document can appear in at most one group.
        """
        import uuid

        groups: List[DocumentGroup] = []

        # 1. Email thread grouping
        groups.extend(self._detect_email_thread_groups(documents))

        # 2. Contract family grouping
        groups.extend(self._detect_contract_family_groups(documents))

        # 3. Sequential photo grouping
        groups.extend(self._detect_photo_sequence_groups(documents))

        # 4. Bank statement grouping (high-confidence: all 3 signals required)
        groups.extend(self._detect_bank_statement_groups(documents))

        # Enforce: each document in at most one group (first-detected wins)
        seen_doc_ids: set = set()
        final_groups: List[DocumentGroup] = []
        for group in groups:
            remaining_ids = [did for did in group.member_document_ids if did not in seen_doc_ids]
            remaining_names = [
                group.member_document_names[i]
                for i, did in enumerate(group.member_document_ids)
                if did not in seen_doc_ids
            ]
            if len(remaining_ids) >= 2:
                group = DocumentGroup(
                    group_id=group.group_id,
                    group_type=group.group_type,
                    label=group.label,
                    member_document_ids=remaining_ids,
                    member_document_names=remaining_names,
                    group_metadata=group.group_metadata,
                    authority_score=group.authority_score,
                    canonical_document_id=group.canonical_document_id,
                )
                final_groups.append(group)
                seen_doc_ids.update(remaining_ids)

        logger.info(
            f"[GROUPING] Detected {len(final_groups)} groups "
            f"covering {len(seen_doc_ids)}/{len(documents)} documents"
        )
        return final_groups

    def _detect_email_thread_groups(self, documents: List[Dict[str, Any]]) -> List[DocumentGroup]:
        """Group .eml files by normalized email subject."""
        import uuid

        threads: Dict[str, List[Dict[str, Any]]] = {}
        for doc in documents:
            name = (doc.get("file_name") or "").lower()
            if not (name.endswith(".eml") or "email" in name):
                continue
            subject = self._extract_email_subject(doc.get("extracted_text") or "")
            if not subject:
                continue
            # _extract_email_subject already strips one layer of Re:/Fwd:
            # and lowercases; strip any remaining nested prefixes
            norm = re.sub(r"^(re|fwd?|fw)\s*:\s*", "", subject, flags=re.IGNORECASE)
            while re.match(r"^(re|fwd?|fw)\s*:", norm, re.IGNORECASE):
                norm = re.sub(r"^(re|fwd?|fw)\s*:\s*", "", norm, flags=re.IGNORECASE)
            norm = norm.strip().lower()
            if norm:
                threads.setdefault(norm, []).append(doc)

        groups = []
        for subject, members in threads.items():
            if len(members) < 2:
                continue
            scores = [
                (m.get("metadata") or {}).get("registry", {}).get("authority_score")
                for m in members
            ]
            valid_scores = [s for s in scores if s is not None]
            groups.append(DocumentGroup(
                group_id=f"grp_{uuid.uuid4().hex[:12]}",
                group_type=GroupType.EMAIL_THREAD,
                label=f"Thread: {subject[:60]}",
                member_document_ids=[m["id"] for m in members],
                member_document_names=[m.get("file_name", "") for m in members],
                group_metadata={"subject": subject},
                authority_score=max(valid_scores) if valid_scores else None,
            ))
        return groups

    def _detect_contract_family_groups(self, documents: List[Dict[str, Any]]) -> List[DocumentGroup]:
        """Group documents with base contract + amendment/exhibit naming pattern."""
        import uuid

        suffix_re = re.compile(
            r"[_\s\-]+(addendum|amendment|exhibit|schedule|attachment|"
            r"supplement|rider|appendix|annex|side\s*letter)[\s_\-]*[a-z0-9]*",
            re.IGNORECASE,
        )
        families: Dict[str, List[tuple]] = {}  # stem -> [(doc, is_base)]
        for doc in documents:
            norm = self._normalize_name(doc.get("file_name") or "")
            match = suffix_re.search(norm)
            if match:
                stem = norm[:match.start()].strip()
                if stem:
                    families.setdefault(stem, []).append((doc, False))
            else:
                families.setdefault(norm, []).append((doc, True))

        groups = []
        for stem, members_flags in families.items():
            if len(members_flags) < 2:
                continue
            if not any(not is_base for _, is_base in members_flags):
                continue  # No amendments/exhibits — not a family
            members = [m for m, _ in members_flags]
            base_docs = [m for m, is_base in members_flags if is_base]
            canonical_id = base_docs[0]["id"] if base_docs else members[0]["id"]
            scores = [
                (m.get("metadata") or {}).get("registry", {}).get("authority_score")
                for m in members
            ]
            valid_scores = [s for s in scores if s is not None]
            groups.append(DocumentGroup(
                group_id=f"grp_{uuid.uuid4().hex[:12]}",
                group_type=GroupType.CONTRACT_FAMILY,
                label=f"Contract: {stem.replace('_', ' ').title()} ({len(members)} docs)",
                member_document_ids=[m["id"] for m in members],
                member_document_names=[m.get("file_name", "") for m in members],
                group_metadata={"stem": stem},
                authority_score=max(valid_scores) if valid_scores else None,
                canonical_document_id=canonical_id,
            ))
        return groups

    def _detect_photo_sequence_groups(self, documents: List[Dict[str, Any]]) -> List[DocumentGroup]:
        """Group image files with sequential numbering in filenames."""
        import uuid

        photo_exts = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".bmp", ".gif"}
        numbered = []
        for doc in documents:
            name = doc.get("file_name") or ""
            ext = os.path.splitext(name)[1].lower()
            if ext not in photo_exts:
                continue
            match = re.search(r"(\d+)\.[a-z]+$", name.lower())
            if match:
                numbered.append((int(match.group(1)), doc))

        if len(numbered) < 2:
            return []

        numbered.sort(key=lambda x: x[0])
        sequences: List[List[Dict[str, Any]]] = [[numbered[0][1]]]
        for i in range(1, len(numbered)):
            if numbered[i][0] - numbered[i - 1][0] <= 2:
                sequences[-1].append(numbered[i][1])
            else:
                sequences.append([numbered[i][1]])

        groups = []
        for seq in sequences:
            if len(seq) < 2:
                continue
            scores = [
                (m.get("metadata") or {}).get("registry", {}).get("authority_score")
                for m in seq
            ]
            valid_scores = [s for s in scores if s is not None]
            groups.append(DocumentGroup(
                group_id=f"grp_{uuid.uuid4().hex[:12]}",
                group_type=GroupType.PHOTO_SEQUENCE,
                label=f"Photos ({len(seq)} images)",
                member_document_ids=[m["id"] for m in seq],
                member_document_names=[m.get("file_name", "") for m in seq],
                authority_score=max(valid_scores) if valid_scores else 50,
            ))
        return groups

    def _detect_bank_statement_groups(self, documents: List[Dict[str, Any]]) -> List[DocumentGroup]:
        """Group bank statements when ALL 3 signals match: institution + account + statement."""
        import uuid

        candidates = []
        for doc in documents:
            content = (doc.get("extracted_text") or "")[:3000]
            name_lower = (doc.get("file_name") or "").lower()

            # Signal 1: statement pattern (filename or content)
            has_statement = bool(_STATEMENT_KEYWORDS.search(content)) or "statement" in name_lower
            if not has_statement:
                continue

            # Signal 2: institution
            inst_match = _INSTITUTION_RE.search(content)
            if not inst_match:
                continue
            institution = inst_match.group(0).strip().lower()

            # Signal 3: account hint
            acct_match = _ACCOUNT_RE.search(content)
            if not acct_match:
                continue
            account = acct_match.group(1)

            key = f"{institution}|{account}"
            candidates.append((key, doc, institution))

        clusters: Dict[str, tuple] = {}
        for key, doc, inst in candidates:
            if key not in clusters:
                clusters[key] = ([], inst)
            clusters[key][0].append(doc)

        groups = []
        for key, (members, institution) in clusters.items():
            if len(members) < 2:
                continue
            account = key.split("|")[1]
            dates = []
            for m in members:
                for d in re.findall(
                    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*[\s_-]*\d{4})",
                    (m.get("file_name") or "").lower(),
                ):
                    dates.append(d.strip())
            date_range = f"{dates[0]} to {dates[-1]}" if len(dates) >= 2 else ""
            scores = [
                (m.get("metadata") or {}).get("registry", {}).get("authority_score")
                for m in members
            ]
            valid_scores = [s for s in scores if s is not None]
            groups.append(DocumentGroup(
                group_id=f"grp_{uuid.uuid4().hex[:12]}",
                group_type=GroupType.BANK_STATEMENTS,
                label=f"{institution.title()} Statements"
                      + (f" ({date_range})" if date_range else f" ({len(members)} docs)"),
                member_document_ids=[m["id"] for m in members],
                member_document_names=[m.get("file_name", "") for m in members],
                group_metadata={
                    "institution": institution.title(),
                    "account_hint": f"****{account}",
                    "date_range": date_range or None,
                },
                authority_score=max(valid_scores) if valid_scores else 68,
            ))
        return groups

    @staticmethod
    def _ensure_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [value]

    def _compose_instrument_corpus(
        self,
        *,
        file_name: str,
        summary: Dict[str, Any],
        content: str,
    ) -> str:
        return "\n".join(
            [
                file_name or "",
                str(summary.get("document_type") or ""),
                str(summary.get("executive_summary") or ""),
                str(summary.get("key_content") or ""),
                str(summary.get("legal_significance") or ""),
                content or "",
            ]
        )

    def _extract_instrument_hints(self, text: str) -> List[str]:
        hints: List[str] = []
        seen = set()
        for label, pattern in self._INSTRUMENT_PATTERNS:
            if not pattern.search(text or ""):
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            hints.append(label)
            if len(hints) >= 8:
                break
        return hints

    def _infer_doc_type_from_name(self, file_name: str, hints: List[str]) -> str:
        fn = (file_name or "").lower()
        blob = " ".join([fn, " ".join(hints)]).lower()

        # Detect Clio Notes and Communications first (before "note" matches Contract)
        if fn.startswith("clio note") or fn.startswith("clio communication"):
            return "Correspondence"
        # Detect emails from extension
        if fn.endswith(".eml"):
            return "Correspondence"
        # Detect photos/images from filename extension
        if re.search(r"\.(jpe?g|png|heic|gif|tiff?|bmp|webp)$", fn):
            return "Photo/Media"
        # Detect intake forms
        if "intake" in blob and ("form" in blob or fn.endswith(".pdf")):
            return "Intake Form"
        # Contracts — use "agreement" and specific "note" terms, not bare "note"
        if any(term in blob for term in ("agreement", "promissory note", "memo terms", "financing")):
            return "Contract"
        if any(term in blob for term in ("email", "correspondence", "update", "message")):
            return "Correspondence"
        if any(term in blob for term in ("search", "articles", "official", "secretary of state")):
            return "Notice"
        if any(term in blob for term in ("p&l", "financial", "statement", "breakdown", "packet")):
            return "Evidence"
        # Small text files (Clio notes, chat logs) — classify as notes
        if fn.endswith(".txt") or fn.endswith(".csv"):
            return "Note"
        if fn == "chat.doc":
            return "Correspondence"
        return "Other"

    def _infer_role_in_case(
        self,
        *,
        file_name: str,
        doc_type: str,
        instrument_hints: List[str],
        legal_significance: str,
    ) -> str:
        blob = " ".join(
            [file_name or "", doc_type or "", " ".join(instrument_hints), legal_significance or ""]
        ).lower()
        if any(term in blob for term in ("subscription agreement", "promissory note", "investment agreement", "purchase agreement", "loan agreement", "financing memo")):
            return "deal terms and investor rights"
        if any(term in blob for term in ("operating agreement", "articles of organization", "business search")):
            return "entity governance and authority chain"
        if any(term in blob for term in ("email", "correspondence", "update", "message", "clio note")):
            return "communications and representations"
        if any(term in blob for term in ("p&l", "financial", "breakdown", "payment", "receipt", "wire")):
            return "financial performance and damages"
        if any(term in blob for term in ("crowdfunding", "offering", "investor packet", "form c")):
            return "offering and solicitation context"
        if any(term in blob for term in ("intake", "questionnaire")):
            return "client intake and background"
        return "general case support"

    def _infer_signature_expectation(
        self,
        *,
        file_name: str,
        doc_type: str,
        instrument_hints: List[str],
    ) -> tuple[bool, str]:
        """Infer whether the document is typically expected to be executed/signed."""
        # Emails, photos, notes, text files are never expected to be signed
        no_sig_types = {"correspondence", "photo/media", "email", "note", "communication"}
        if (doc_type or "").lower() in no_sig_types:
            return False, "Document type does not require signatures."
        fn_lower = (file_name or "").lower()
        if re.search(r"\.(eml|jpe?g|png|heic|gif|tiff?|bmp|webp|txt|csv)$", fn_lower):
            return False, "File type does not require signatures."
        if fn_lower.startswith("clio note") or fn_lower.startswith("clio communication"):
            return False, "Clio notes and communications do not require signatures."

        hint_set = {h.lower() for h in instrument_hints}
        typically_signed_hints = {
            "subscription agreement",
            "operating agreement",
            "promissory note",
            "investment agreement",
            "purchase agreement",
            "loan agreement",
            "financing memo",
            "membership certificate",
        }
        if hint_set.intersection(typically_signed_hints):
            return True, "Instrument type is typically executed by one or more parties."

        blob = " ".join([file_name or "", doc_type or ""]).lower()
        if any(
            term in blob
            for term in (
                "agreement",
                "contract",
                "promissory note",
                "amendment",
                "addendum",
                "release",
                "consent",
                "authorization",
                "affidavit",
                "declaration",
                "stipulation",
                "guaranty",
                "power of attorney",
                "poa",
            )
        ):
            return True, "Filename/type indicates a document that is normally signed."

        return False, "Document is not typically executed or signature requirement is unclear."

    def _infer_authority(
        self,
        *,
        doc_type: str,
        instrument_hints: List[str],
        execution_status: str,
        role_in_case: str,
    ) -> tuple[str, str]:
        exec_lc = (execution_status or "").lower()
        hint_set = {h.lower() for h in instrument_hints}
        controlling_hints = {
            "subscription agreement",
            "operating agreement",
            "promissory note",
            "investment agreement",
            "purchase agreement",
            "loan agreement",
            "financing memo",
            "membership certificate",
        }
        official_hints = {"articles of organization", "business search"}

        if exec_lc == "signed" and hint_set.intersection(controlling_hints):
            return (
                "controlling_signed_instrument",
                "Signed controlling instrument detected (agreement/note/governance record).",
            )
        if hint_set.intersection(controlling_hints) or (doc_type or "").lower() == "contract":
            return (
                "controlling_instrument",
                "Primary contractual/governance terms appear in this document.",
            )
        if hint_set.intersection(official_hints):
            return (
                "official_record",
                "Government/entity filing or status record.",
            )
        if "communications" in role_in_case:
            return (
                "party_communication",
                "Contains representations, updates, or admissions between parties.",
            )
        if "financial" in role_in_case:
            return (
                "financial_record",
                "Supports damages tracing, payment history, or performance metrics.",
            )
        if "offering" in role_in_case:
            return (
                "offering_material",
                "Public/investor-facing solicitation context.",
            )
        if "intake" in role_in_case:
            return (
                "client_background",
                "Client-supplied intake context.",
            )
        return ("supporting_evidence", "General supporting record.")

    def _score_authority(
        self,
        *,
        authority_level: str,
        execution_status: str,
        summary: Dict[str, Any],
        key_doc: Dict[str, Any],
    ) -> int:
        base = {
            "controlling_signed_instrument": 95,
            "controlling_instrument": 82,
            "official_record": 74,
            "financial_record": 68,
            "party_communication": 64,
            "offering_material": 60,
            "client_background": 40,
            "supporting_evidence": 50,
        }.get(authority_level, 45)

        if (execution_status or "").lower() == "signed":
            base += 3
        if key_doc:
            base += 4
        if summary.get("legal_significance"):
            base += 2
        if self._ensure_list(summary.get("important_details")):
            base += 1
        return min(100, max(1, base))

    def _collect_parties(self, summary: Dict[str, Any]) -> List[str]:
        parties = self._ensure_list(summary.get("parties"))
        structured = summary.get("structured_data") or {}
        parties.extend(self._ensure_list(structured.get("parties")))
        deduped: List[str] = []
        seen = set()
        for value in parties:
            candidate = str(value).strip()
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
            if len(deduped) >= 12:
                break
        return deduped

    def _collect_dates(self, summary: Dict[str, Any]) -> List[str]:
        dates: List[str] = []
        for item in self._ensure_list(summary.get("key_dates")):
            if isinstance(item, dict):
                value = item.get("date") or item.get("event")
            else:
                value = str(item)
            text = str(value or "").strip()
            if text:
                dates.append(text)
        structured = summary.get("structured_data") or {}
        for item in self._ensure_list(structured.get("dates")):
            if isinstance(item, dict):
                value = item.get("date") or item.get("event")
            else:
                value = str(item)
            text = str(value or "").strip()
            if text:
                dates.append(text)
        return self._dedupe_strings(dates, limit=12)

    def _collect_amounts(self, summary: Dict[str, Any]) -> List[str]:
        amounts: List[str] = []
        for item in self._ensure_list(summary.get("key_amounts")):
            if isinstance(item, dict):
                value = item.get("amount") or item.get("description")
            else:
                value = str(item)
            text = str(value or "").strip()
            if text:
                amounts.append(text)
        structured = summary.get("structured_data") or {}
        for item in self._ensure_list(structured.get("amounts")):
            if isinstance(item, dict):
                value = item.get("amount") or item.get("description")
            else:
                value = str(item)
            text = str(value or "").strip()
            if text:
                amounts.append(text)
        return self._dedupe_strings(amounts, limit=12)

    @staticmethod
    def _dedupe_strings(values: List[str], limit: int) -> List[str]:
        out: List[str] = []
        seen = set()
        for value in values:
            candidate = (value or "").strip()
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(candidate)
            if len(out) >= limit:
                break
        return out
