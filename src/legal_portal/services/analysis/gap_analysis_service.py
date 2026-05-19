"""Gap Analysis Service - Identifies missing documents, contradictions, and weaknesses.

This service performs AI-powered analysis to identify gaps and inconsistencies in case materials,
providing attorneys with critical feedback about case completeness.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set

from legal_portal.core.data_models import (
    BatchEvidence,
    BatchFinding,
    BatchGapReport,
    CaseRecommendation,
    CaseRecommendationCategory,
    ConfidenceLevel,
    DeepAnalysis,
    DocumentSummaryStructured,
    FactMatrix,
    GapAnalysisResult,
    GapCategory,
    GapItem,
    GapSeverity,
    LegalIssueMap,
    RecommendedLetterType,
)
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.type_safety import safe_str_required

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _normalize_title(title: str) -> str:
    """Normalize a finding title for deduplication comparison."""
    return re.sub(r"[^\w\s]", "", title.lower()).strip()


def _deduplicate_findings(findings: List[BatchFinding]) -> List[BatchFinding]:
    """Deterministic deduplication for mechanical merge fallback.

    Two findings are considered duplicates if ALL of:
    1. Normalized titles match (lowercase, strip whitespace, remove punctuation)
    2. Same category
    3. Overlapping document_ids (intersection >= 1)

    When duplicates are found:
    - Keep the finding with the higher severity (critical > high > medium > low)
    - On severity tie, keep the one with more document_ids
    - On further tie, keep the first encountered (stable sort)
    - Merge document_ids from both into the kept finding (union)
    """
    if not findings:
        return []

    # Group by (normalized_title, category)
    groups: Dict[tuple, List[BatchFinding]] = {}
    for finding in findings:
        key = (_normalize_title(finding.title), finding.category.lower())
        groups.setdefault(key, []).append(finding)

    result: List[BatchFinding] = []
    for _key, group in sorted(groups.items()):
        if len(group) == 1:
            result.append(group[0])
            continue

        # Check for overlapping document_ids within the group
        # Merge findings that share at least one document_id
        merged: List[BatchFinding] = []
        for finding in group:
            found_merge = False
            finding_ids = set(finding.document_ids)
            for i, existing in enumerate(merged):
                existing_ids = set(existing.document_ids)
                if finding_ids & existing_ids:  # intersection >= 1
                    # Keep the higher-severity finding, merge doc IDs
                    existing_rank = _SEVERITY_RANK.get(existing.severity.lower(), 0)
                    finding_rank = _SEVERITY_RANK.get(finding.severity.lower(), 0)

                    winner = finding if (
                        finding_rank > existing_rank
                        or (finding_rank == existing_rank
                            and len(finding.document_ids) > len(existing.document_ids))
                    ) else existing

                    merged[i] = BatchFinding(
                        category=winner.category,
                        severity=winner.severity,
                        title=winner.title,
                        description=winner.description,
                        document_ids=list(existing_ids | finding_ids),
                        affected_issue=winner.affected_issue,
                        cross_batch_uncertain=False,
                    )
                    found_merge = True
                    break

            if not found_merge:
                merged.append(finding)

        result.extend(merged)

    return result


class GapAnalysisService:
    """Service for analyzing case completeness and identifying gaps."""

    def __init__(self, openai_client: OpenAIClient):
        """Initialize the gap analysis service.

        Args:
            openai_client: OpenAI client for GPT model calls

        """
        self.client = openai_client

    async def analyze_gaps(
        self,
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        deep_analysis: DeepAnalysis,
        document_summaries: List[DocumentSummaryStructured],
        intake_content: Optional[str] = None,
        resolution_context: Optional[str] = None,
        prior_gap_analysis: Optional[GapAnalysisResult] = None,
        signature_evidence: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        truncation_context: Optional[Dict[str, Any]] = None,
    ) -> GapAnalysisResult:
        """Analyze case for gaps, contradictions, and weaknesses.

        This performs Stage 3.5 analysis - critical review of case completeness.

        Args:
            fact_matrix: Extracted facts from Stage 1
            issue_map: Legal issues from Stage 2
            deep_analysis: Deep analysis from Stage 3
            document_summaries: Summaries of all documents
            intake_content: Original intake form content
            resolution_context: Optional user-provided resolution context
            prior_gap_analysis: Optional prior gap analysis for selective refresh
            signature_evidence: Optional authoritative signature metadata per case document
            document_registry: Optional authoritative document registry rows

        Returns:
            GapAnalysisResult with identified gaps and completeness assessment

        """
        logger.info("[GAP_SERVICE] Starting gap analysis (Stage 3.5)")
        signed_count = sum(
            1
            for item in (signature_evidence or [])
            if (item.get("status") or "").lower() == "signed"
        )
        logger.info(
            "[GAP_SERVICE] Inputs - fact_matrix parties: %s, issues: %s, docs: %s, "
            "signature_records: %s, signed_docs: %s",
            len(fact_matrix.parties),
            len(issue_map.primary_issues),
            len(document_summaries),
            len(signature_evidence or []),
            signed_count,
        )

        try:
            # Build the analysis prompt
            prompt = self._build_gap_analysis_prompt(
                fact_matrix=fact_matrix,
                issue_map=issue_map,
                deep_analysis=deep_analysis,
                document_summaries=document_summaries,
                intake_content=intake_content,
                resolution_context=resolution_context,
                prior_gap_analysis=prior_gap_analysis,
                signature_evidence=signature_evidence,
                document_registry=document_registry,
                truncation_context=truncation_context,
            )

            prompt_chars = len(prompt)
            logger.info(f"[GAP:PROMPT] prompt_size={prompt_chars} chars (~{prompt_chars // 4} tokens)")

            # Use GPT-4.1 for gap detection - faster and more reliable for structured JSON
            # GPT-5.2 with reasoning_effort spends tokens on internal reasoning, not output
            model = self.client.get_preferred_model("gap_analysis", "gpt-5.5")

            logger.info(
                f"[STAGE:3.5:API] Calling OpenAI for gap_analysis | "
                f"model={model} prompt_chars={len(prompt)} max_tokens=12000"
            )

            # Call OpenAI API with timeout guard
            from legal_portal.config.default import get_settings
            _gap_settings = get_settings()

            api_start = time.time()
            try:
                response_dict = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.create_response,
                        model=model,
                        instructions=(
                            "You are a critical legal analyst identifying gaps and inconsistencies in case materials. "
                            "Return only valid JSON matching the GapAnalysisResult schema. Do not include any text before or after the JSON."
                        ),
                        input=prompt,
                        max_output_tokens=12000,
                        reasoning_effort="low" if self.client._is_gpt5_model(model) else None,
                    ),
                    timeout=_gap_settings.gap_analysis_budget_seconds,
                )
            except asyncio.TimeoutError:
                api_duration = time.time() - api_start
                logger.error(
                    f"[STAGE:3.5:TIMEOUT] Gap analysis AI call timed out after {api_duration:.1f}s "
                    f"(budget={_gap_settings.gap_analysis_budget_seconds}s)"
                )
                fallback = self._create_fallback_result(error=f"Gap analysis timed out after {api_duration:.0f}s")
                fallback.recommendation = self._generate_recommendation(
                    gap_analysis=fallback,
                    deep_analysis=deep_analysis,
                )
                return fallback
            api_duration = time.time() - api_start

            finish_reason = response_dict.get("finish_reason", "unknown")
            logger.info(
                f"[STAGE:3.5:API] OpenAI response received | "
                f"duration={api_duration:.1f}s finish_reason={finish_reason} "
                f"prompt_tokens={response_dict.get('usage', {}).get('prompt_tokens', 0)} "
                f"completion_tokens={response_dict.get('usage', {}).get('completion_tokens', 0)}"
            )

            # Check for API error
            if response_dict.get("success") is False:
                error_msg = response_dict.get("error", "Unknown API error")
                logger.error(f"[STAGE:3.5:ERROR] API returned error: {error_msg}")
                fallback = self._create_fallback_result(error=error_msg)
                fallback.recommendation = self._generate_recommendation(
                    gap_analysis=fallback,
                    deep_analysis=deep_analysis,
                )
                return fallback

            raw_response = safe_str_required(response_dict.get("content"), "")

            if not raw_response:
                logger.warning("Gap analysis returned empty response")
                fallback = self._create_fallback_result()
                fallback.recommendation = self._generate_recommendation(
                    gap_analysis=fallback,
                    deep_analysis=deep_analysis,
                )
                return fallback

            # Parse JSON response
            response_json = json.loads(raw_response)
            result = GapAnalysisResult(**response_json)
            overflow_doc_ids = set(truncation_context.get("overflow_doc_ids", [])) if truncation_context else None
            overflow_doc_names = set(truncation_context.get("overflow_doc_names", [])) if truncation_context else None
            result = self._reconcile_signature_execution_gaps(
                result=result,
                signature_evidence=signature_evidence,
                overflow_doc_ids=overflow_doc_ids,
                overflow_doc_names=overflow_doc_names,
            )

            # Generate case recommendation based on gap analysis and deep analysis
            recommendation = self._generate_recommendation(
                gap_analysis=result,
                deep_analysis=deep_analysis,
            )
            result.recommendation = recommendation

            logger.info(
                f"Gap analysis completed: {result.total_gaps} gaps found "
                f"({result.critical_count} critical, {result.high_count} high), "
                f"recommendation: {recommendation.category.value}"
            )

            return result

        except Exception as e:
            logger.error(f"Gap analysis failed: {e}", exc_info=True)
            fallback = self._create_fallback_result(error=str(e))
            fallback.recommendation = self._generate_recommendation(
                gap_analysis=fallback,
                deep_analysis=deep_analysis,
            )
            return fallback

    @staticmethod
    def _truncate_text(value: Optional[str], limit: int) -> str:
        """Trim text for prompt context blocks without dropping key signal."""
        text = (value or "").strip()
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def _build_document_evidence_summary(
        self,
        document_summaries: List[DocumentSummaryStructured],
    ) -> str:
        """Create compact per-document evidence context from structured summaries."""
        if not document_summaries:
            return "No structured document summaries were provided."

        lines: List[str] = []
        for doc in document_summaries[:30]:
            lines.append(f"- {doc.document_name} ({doc.document_type})")
            overview = self._truncate_text(doc.executive_summary, 260)
            if not overview:
                overview = self._truncate_text(doc.key_content, 260)
            if overview:
                lines.append(f"  overview: {overview}")
            if doc.legal_significance:
                lines.append(
                    f"  legal_significance: {self._truncate_text(doc.legal_significance, 220)}"
                )
            if doc.important_details:
                details = "; ".join(
                    self._truncate_text(detail, 120)
                    for detail in doc.important_details[:3]
                    if (detail or "").strip()
                )
                if details:
                    lines.append(f"  details: {details}")

        if len(document_summaries) > 30:
            lines.append(
                f"... {len(document_summaries) - 30} additional document summaries omitted for brevity."
            )

        return "\n".join(lines)

    def _build_signature_evidence_summary(
        self,
        signature_evidence: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Format authoritative signature metadata for the prompt."""
        rows = signature_evidence or []
        if not rows:
            return "No signature metadata was provided."

        display_limit = min(len(rows), 60)
        lines: List[str] = []
        for item in rows[:display_limit]:
            file_name = item.get("file_name") or "Unknown document"
            status = (item.get("status") or "unknown").lower()
            confidence = item.get("confidence") or "unknown"
            digital = bool(item.get("has_digital_signature"))
            signing_date = item.get("signing_date")
            source = item.get("detection_source")
            instrument_hints = item.get("instrument_hints") or []

            line = (
                f"- {file_name}: status={status}, confidence={confidence}, "
                f"digital={digital}"
            )
            if signing_date:
                line += f", signing_date={signing_date}"
            if source:
                line += f", source={source}"
            if instrument_hints:
                preview = ", ".join(str(h) for h in instrument_hints[:3])
                line += f", hints={preview}"
            lines.append(line)

        if len(rows) > display_limit:
            lines.append(
                f"... {len(rows) - display_limit} additional signature records omitted for brevity."
            )

        return "\n".join(lines)

    def _build_document_registry_summary(
        self,
        document_registry: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Format document registry rows for gap-analysis grounding."""
        rows = [row for row in (document_registry or []) if isinstance(row, dict)]
        if not rows:
            return "No document registry was provided."

        sorted_rows = sorted(
            rows,
            key=lambda row: (
                1 if row.get("authority_score") is None else 0,
                -int(row.get("authority_score") or 0),
                str(row.get("document_name") or "").lower(),
            ),
        )
        display_limit = min(len(sorted_rows), 75)
        lines: List[str] = []
        for row in sorted_rows[:display_limit]:
            file_name = row.get("document_name") or "Unknown document"
            eval_status = row.get("evaluation_status")
            if eval_status == "metadata_only":
                lines.append(
                    f"- {file_name}: evaluation_status=metadata_only (full text not analyzed)"
                )
                continue
            doc_type = row.get("document_type") or "Unknown"
            authority = row.get("authority_level") or "supporting_evidence"
            authority_reason = row.get("authority_reason") or ""
            execution_status = row.get("execution_status") or "unknown"
            execution_confidence = row.get("execution_confidence") or "none"
            primary_instrument = row.get("primary_instrument") or "n/a"
            is_key_doc = bool(row.get("is_key_document"))
            role = row.get("role_in_case") or "general case support"
            signature_expected = bool(row.get("signature_expected"))
            signature_review = bool(row.get("signature_review_recommended"))
            line = (
                f"- {file_name}: type={doc_type}, authority={authority}, key_doc={is_key_doc}, "
                f"execution={execution_status}({execution_confidence}), instrument={primary_instrument}, "
                f"role={role}, signature_expected={signature_expected}, signature_review={signature_review}"
            )
            if authority_reason:
                line += f", authority_reason={self._truncate_text(str(authority_reason), 140)}"
            lines.append(line)

        if len(sorted_rows) > display_limit:
            lines.append(
                f"... {len(sorted_rows) - display_limit} additional registry records omitted for brevity."
            )
        return "\n".join(lines)

    @staticmethod
    def _tokenize_for_match(value: str) -> Set[str]:
        """Tokenize text for lightweight fuzzy document-name matching."""
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "from",
            "that",
            "this",
            "document",
            "missing",
            "terms",
            "copy",
            "final",
            "draft",
            "pdf",
        }
        normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
        tokens: Set[str] = set()
        for raw in normalized.split():
            if len(raw) < 3:
                continue
            token = raw
            if token.endswith("s") and len(token) >= 5 and not token.endswith("ss"):
                token = token[:-1]
            if token in stopwords:
                continue
            tokens.add(token)
            # Map common legal-document synonyms so "contract" and "agreement" overlap.
            if token in {"agreement", "contract"}:
                tokens.update({"agreement", "contract"})
            elif token in {"subscription", "investor", "investment"}:
                tokens.add("investment")
            elif token in {"unit", "units", "membership"}:
                tokens.add("membership")
        return tokens

    @staticmethod
    def _is_execution_gap(gap: GapItem) -> bool:
        """Heuristic: identify missing-document gaps specifically about execution/signature."""
        blob = " ".join(
            [
                gap.title or "",
                gap.description or "",
                gap.impact_on_case or "",
                " ".join(gap.recommendations or []),
            ]
        ).lower()
        execution_terms = ("executed", "signed", "signature", "execution")
        instrument_terms = (
            "agreement",
            "contract",
            "subscription",
            "investment",
            "financing",
            "purchase",
            "note",
        )
        missing_terms = (
            "missing",
            "absence",
            "lack of",
            "not provided",
            "not produced",
            "unsigned",
            "no executed",
            "no clear evidence",
            "unable to confirm",
            "cannot confirm",
            "low confidence",
            "low-confidence",
            "signature review not completed",
            "review not completed",
            "countersignature review",
            "counter-signature review",
            "non-digital",
            "manual signatures",
            "missing signature date",
            "missing execution date",
            "date conformity",
        )
        no_provided_pattern = re.compile(r"\bno\b.{0,45}\bprovided\b")

        return (
            gap.category == GapCategory.MISSING_DOCUMENT
            and any(term in blob for term in execution_terms)
            and any(term in blob for term in instrument_terms)
            and (
                any(term in blob for term in missing_terms)
                or bool(no_provided_pattern.search(blob))
            )
        )

    @staticmethod
    def _is_signature_followup_gap(gap: GapItem) -> bool:
        """Detect non-blocking signature-quality/date follow-up concerns tied to signed agreements."""
        if gap.category not in {
            GapCategory.MISSING_DOCUMENT,
            GapCategory.TIMELINE_GAP,
            GapCategory.INCOMPLETE_INFO,
        }:
            return False

        blob = " ".join(
            [
                gap.title or "",
                gap.description or "",
                gap.impact_on_case or "",
                " ".join(gap.related_documents or []),
                " ".join(gap.recommendations or []),
            ]
        ).lower()

        signature_terms = (
            "executed",
            "signed",
            "signature",
            "execution",
            "counter-signature",
            "countersignature",
            "signatory",
        )
        instrument_terms = (
            "operating agreement",
            "subscription agreement",
            "investment agreement",
            "purchase agreement",
            "financing",
            "contract",
            "agreement",
        )
        followup_terms = (
            "low confidence",
            "low-confidence",
            "non-digital",
            "manual signature",
            "signature review not completed",
            "review not completed",
            "missing signature",
            "missing execution",
            "signature date",
            "execution date",
            "dated",
            "date conformity",
            "party-signed",
            "all members",
            "all relevant parties",
            "all required parties",
            "countersignature review",
        )

        return (
            any(term in blob for term in signature_terms)
            and any(term in blob for term in instrument_terms)
            and any(term in blob for term in followup_terms)
        )

    @staticmethod
    def _is_identity_or_party_gap_text(blob: str) -> bool:
        """Avoid suppressing genuinely distinct standing/party-identity concerns."""
        markers = (
            "standing",
            "beneficiary",
            "individual vs",
            "entity",
            "investor identity",
            "both investors",
            "correct plaintiff",
            "party mismatch",
            "party alignment",
            "all relevant parties",
            "all required parties",
            "all members",
            "all signatures",
            "countersignature",
            "counter-signature",
            "signatory authority",
            "assignee",
        )
        text = (blob or "").lower()
        return any(marker in text for marker in markers)

    def _find_matching_signed_docs(
        self,
        gap: GapItem,
        signed_docs: List[Dict[str, Any]],
    ) -> List[str]:
        """Match an execution gap to signed docs using name and token overlap."""
        matched: List[str] = []
        seen = set()

        # PRIORITY 1: Check if gap.related_documents contains exact file name matches
        # This is more reliable than fuzzy token matching since the AI already identified the docs
        related_docs_lower = {(doc or "").lower() for doc in (gap.related_documents or [])}

        if related_docs_lower:
            for doc in signed_docs:
                file_name = doc.get("file_name") or ""
                file_name_lower = file_name.lower()

                # Exact match or base name match (without extension)
                base_name = file_name_lower.rsplit(".", 1)[0]

                if file_name_lower in related_docs_lower or base_name in related_docs_lower:
                    key = file_name_lower
                    if key not in seen:
                        seen.add(key)
                        matched.append(file_name)
                        logger.info(
                            "[GAP_RECONCILE] Exact match via related_documents | gap_title=%s doc=%s",
                            gap.title[:50] if gap.title else "No title",
                            file_name
                        )

        # If we found exact matches, return them (more reliable than fuzzy matching)
        if matched:
            return matched

        # FALLBACK: Use fuzzy token-based matching if no exact matches
        blob = " ".join(
            [
                gap.title or "",
                gap.description or "",
                gap.impact_on_case or "",
                " ".join(gap.related_documents or []),
                " ".join(gap.recommendations or []),
            ]
        ).lower()
        gap_tokens = self._tokenize_for_match(blob)

        for doc in signed_docs:
            file_name = doc.get("file_name") or ""
            file_name_lc = file_name.lower()
            base_name = file_name_lc.rsplit(".", 1)[0]
            hint_phrases = [
                str(h).strip().lower()
                for h in (doc.get("instrument_hints") or [])
                if str(h).strip()
            ]
            signer_names = [
                str(name).strip()
                for name in (doc.get("signer_names") or [])
                if str(name).strip()
            ]
            matching_blob = " ".join([base_name, " ".join(hint_phrases), " ".join(signer_names)]).strip()
            doc_tokens = self._tokenize_for_match(matching_blob)
            overlap = gap_tokens & doc_tokens
            hint_phrase_match = any(
                phrase in blob
                for phrase in hint_phrases
                if len(phrase) >= 6
            )

            strong_match = file_name_lc in blob or base_name in blob
            fuzzy_match = len(overlap) >= 2
            semantic_overlap = {
                "agreement",
                "subscription",
                "contract",
                "investment",
                "purchase",
                "financing",
                "promissory",
                "note",
                "membership",
                "units",
            } & overlap
            semantic_match = len(semantic_overlap) >= 1
            thematic_match = (
                len(overlap) >= 1
                and any(
                    kw in matching_blob
                    for kw in ("agreement", "contract", "subscription", "investment", "financing")
                )
                and any(
                    kw in blob
                    for kw in ("agreement", "contract", "subscription", "investment", "financing")
                )
            )

            if strong_match or hint_phrase_match or fuzzy_match or semantic_match or thematic_match:
                key = file_name_lc or str(doc.get("document_id"))
                if key in seen:
                    continue
                seen.add(key)
                matched.append(file_name or "Unknown document")

        return matched

    def _reconcile_signature_execution_gaps(
        self,
        result: GapAnalysisResult,
        signature_evidence: Optional[List[Dict[str, Any]]],
        overflow_doc_ids: Optional[Set[str]] = None,
        overflow_doc_names: Optional[Set[str]] = None,
    ) -> GapAnalysisResult:
        """Suppress execution/signature follow-up gaps when signed evidence is present.

        When overflow_doc_ids/overflow_doc_names are provided, also reclassify
        missing_document gaps that reference overflow-present docs to incomplete_info
        instead of removing them entirely.
        """
        logger.info(
            "[GAP_RECONCILE] Starting reconciliation | signature_evidence_count=%s",
            len(signature_evidence or [])
        )
        signed_docs = [
            item
            for item in (signature_evidence or [])
            if (item.get("status") or "").lower() == "signed"
        ]
        logger.info(
            "[GAP_RECONCILE] Filtered to signed docs | signed_count=%s",
            len(signed_docs)
        )
        if signed_docs:
            logger.info(
                "[GAP_RECONCILE] Signed doc examples: %s",
                [doc.get("file_name") for doc in signed_docs[:3]]
            )
        has_overflow = bool(overflow_doc_ids or overflow_doc_names)
        if not signed_docs and not has_overflow:
            logger.info("[GAP_RECONCILE] No signed docs and no overflow, skipping reconciliation")
            return result

        candidate_categories = (
            GapCategory.MISSING_DOCUMENT.value,
            GapCategory.TIMELINE_GAP.value,
            GapCategory.INCOMPLETE_INFO.value,
        )
        if not any(result.gaps_by_category.get(category) for category in candidate_categories):
            logger.info("[GAP_RECONCILE] No gaps in candidate categories, skipping")
            return result

        logger.info(
            "[GAP_RECONCILE] Found gaps in candidate categories | missing_doc=%s timeline=%s incomplete=%s",
            len(result.gaps_by_category.get(GapCategory.MISSING_DOCUMENT.value, [])),
            len(result.gaps_by_category.get(GapCategory.TIMELINE_GAP.value, [])),
            len(result.gaps_by_category.get(GapCategory.INCOMPLETE_INFO.value, []))
        )

        kept_by_category = {
            category: [] for category in candidate_categories
        }
        removed: List[GapItem] = []
        non_blocking_identity_hits = 0
        matched_doc_names: List[str] = []

        if signed_docs:
            # Signature-based reconciliation: suppress execution gaps matched to signed docs
            for category in candidate_categories:
                gaps_in_category = list(result.gaps_by_category.get(category, []))
                logger.info(
                    "[GAP_RECONCILE] Processing %s gaps in category: %s",
                    len(gaps_in_category),
                    category
                )
                for gap in gaps_in_category:
                    is_exec = self._is_execution_gap(gap)
                    is_followup = self._is_signature_followup_gap(gap)

                    if not (is_exec or is_followup):
                        logger.info(
                            "[GAP_RECONCILE] Gap not execution-related, keeping | title=%s is_exec=%s is_followup=%s",
                            gap.title[:60] if gap.title else "No title",
                            is_exec,
                            is_followup
                        )
                        kept_by_category[category].append(gap)
                        continue

                    logger.info(
                        "[GAP_RECONCILE] Gap IS execution-related | title=%s is_exec=%s is_followup=%s",
                        gap.title[:60] if gap.title else "No title",
                        is_exec,
                        is_followup
                    )

                    gap_blob = " ".join(
                        [
                            gap.title or "",
                            gap.description or "",
                            gap.impact_on_case or "",
                            " ".join(gap.recommendations or []),
                        ]
                    )
                    matched = self._find_matching_signed_docs(gap, signed_docs)
                    logger.info(
                        "[GAP_RECONCILE] Matching result | gap_title=%s matched_count=%s matched_docs=%s",
                        gap.title[:60] if gap.title else "No title",
                        len(matched),
                        matched[:3] if matched else []
                    )
                    if matched:
                        matched_doc_names.extend(matched)
                        if self._is_identity_or_party_gap_text(gap_blob):
                            non_blocking_identity_hits += 1
                        logger.info(
                            "[GAP_RECONCILE] REMOVING gap | title=%s matched_docs=%s",
                            gap.title[:60] if gap.title else "No title",
                            matched[:2]
                        )
                        removed.append(gap)
                    else:
                        logger.info(
                            "[GAP_RECONCILE] No matches found, keeping gap | title=%s",
                            gap.title[:60] if gap.title else "No title"
                        )
                        kept_by_category[category].append(gap)
        else:
            # No signed docs — copy all gaps to kept_by_category for overflow pass
            for category in candidate_categories:
                kept_by_category[category] = list(result.gaps_by_category.get(category, []))

        # Overflow-aware reclassification: reclassify missing_document gaps
        # whose referenced documents all exist in the overflow set
        overflow_reclassified = 0
        if overflow_doc_ids or overflow_doc_names:
            _norm_overflow_names = {
                (n or "").strip().lower() for n in (overflow_doc_names or set()) if n
            }
            _overflow_ids = overflow_doc_ids or set()
            missing_kept = kept_by_category.get(GapCategory.MISSING_DOCUMENT.value, [])
            still_missing = []
            for gap in missing_kept:
                related = gap.related_documents or []
                if not related:
                    still_missing.append(gap)
                    continue

                # Check if ALL referenced docs are in the overflow set
                # Match by ID first (if gap has document_id refs), then by name
                all_in_overflow = True
                any_in_overflow = False
                for doc_ref in related:
                    doc_ref_str = (doc_ref or "").strip()
                    # Try ID match first, then normalized name match
                    in_overflow = (
                        (doc_ref_str in _overflow_ids)
                        or (doc_ref_str.lower() in _norm_overflow_names)
                    )
                    if in_overflow:
                        any_in_overflow = True
                    else:
                        all_in_overflow = False

                if all_in_overflow and any_in_overflow:
                    # All referenced docs exist in overflow — reclassify to incomplete_info
                    gap.category = GapCategory.INCOMPLETE_INFO
                    if gap.severity in (GapSeverity.CRITICAL, GapSeverity.HIGH):
                        gap.severity = GapSeverity.MEDIUM
                    gap.description = (
                        (gap.description or "")
                        + " [Note: Referenced document(s) exist in the case file but were "
                        "outside the full analysis window. Reclassified from missing_document.]"
                    )
                    kept_by_category.setdefault(GapCategory.INCOMPLETE_INFO.value, []).append(gap)
                    overflow_reclassified += 1
                    logger.info(
                        "[GAP_RECONCILE] Reclassified overflow gap to incomplete_info | title=%s",
                        gap.title[:60] if gap.title else "No title"
                    )
                elif any_in_overflow and not all_in_overflow:
                    # Mix of overflow and genuinely missing — keep but annotate
                    gap.description = (
                        (gap.description or "")
                        + " [Note: Some referenced documents exist in the case file but were "
                        "outside the full analysis window.]"
                    )
                    still_missing.append(gap)
                else:
                    still_missing.append(gap)

            kept_by_category[GapCategory.MISSING_DOCUMENT.value] = still_missing
            if overflow_reclassified:
                logger.info(
                    "[GAP_RECONCILE] Overflow reclassification | reclassified=%s",
                    overflow_reclassified,
                )

        if not removed and not overflow_reclassified:
            logger.info("[GAP_RECONCILE] No gaps were removed or reclassified during reconciliation")
            return result

        logger.info(
            "[GAP_RECONCILE] Reconciliation complete | removed=%s non_blocking_identity=%s overflow_reclassified=%s",
            len(removed),
            non_blocking_identity_hits,
            overflow_reclassified,
        )

        for category in candidate_categories:
            result.gaps_by_category[category] = kept_by_category[category]

        all_gaps = [g for gaps in result.gaps_by_category.values() for g in gaps]
        result.total_gaps = len(all_gaps)
        result.critical_count = sum(1 for g in all_gaps if g.severity == GapSeverity.CRITICAL)
        result.high_count = sum(1 for g in all_gaps if g.severity == GapSeverity.HIGH)
        result.medium_count = sum(1 for g in all_gaps if g.severity == GapSeverity.MEDIUM)
        result.low_count = sum(1 for g in all_gaps if g.severity == GapSeverity.LOW)

        severity_bonus = {
            GapSeverity.CRITICAL: 9.0,
            GapSeverity.HIGH: 6.0,
            GapSeverity.MEDIUM: 3.0,
            GapSeverity.LOW: 1.0,
        }
        bonus = sum(severity_bonus.get(g.severity, 0.0) for g in removed)
        if bonus > 0:
            result.overall_completeness_score = min(
                100.0,
                round(float(result.overall_completeness_score) + bonus, 1),
            )

        unique_docs = sorted({name for name in matched_doc_names if name})
        if unique_docs:
            docs_preview = ", ".join(unique_docs[:3])
            if len(unique_docs) > 3:
                docs_preview += f", +{len(unique_docs) - 3} more"
        else:
            docs_preview = "signed case documents"

        action_text = f"removed {len(removed)} execution/signature coverage gap(s) treated as non-blocking"
        if non_blocking_identity_hits:
            action_text += (
                f" and treated {non_blocking_identity_hits} party/standing signature-coverage concern(s) "
                "as non-blocking because signed agreements are present"
            )
        note = (
            f"Execution metadata confirms signed documents ({docs_preview}); "
            f"{action_text}."
        )
        notes = list(getattr(result, "reconciliation_notes", []) or [])
        if note not in notes:
            notes.append(note)
        result.reconciliation_notes = notes

        summary = (result.attorney_summary or "").strip()
        if note not in summary:
            result.attorney_summary = f"{summary} {note}".strip() if summary else note

        logger.info(
            "[GAP_SERVICE] Signature reconciliation adjusted gaps | removed=%s non_blocking_identity=%s",
            len(removed),
            non_blocking_identity_hits,
        )
        return result

    def _build_gap_analysis_prompt(
        self,
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        deep_analysis: DeepAnalysis,
        document_summaries: List[DocumentSummaryStructured],
        intake_content: Optional[str],
        resolution_context: Optional[str] = None,
        prior_gap_analysis: Optional[GapAnalysisResult] = None,
        signature_evidence: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        truncation_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the AI prompt for gap detection.

        Args:
            fact_matrix: Extracted facts
            issue_map: Legal issues
            deep_analysis: Deep analysis
            document_summaries: Document summaries
            intake_content: Intake form content
            resolution_context: Optional user-supplied context to resolve gaps
            prior_gap_analysis: Optional prior gap analysis to reconcile
            signature_evidence: Optional authoritative signature metadata
            document_registry: Optional authoritative document registry rows

        Returns:
            Formatted prompt for GPT-5.2

        """
        # Prepare document list
        doc_list = "\n".join([f"- {doc.document_name}" for doc in document_summaries]) or "None provided"
        doc_evidence_summary = self._build_document_evidence_summary(document_summaries)
        signature_evidence_summary = self._build_signature_evidence_summary(signature_evidence)
        document_registry_summary = self._build_document_registry_summary(document_registry)

        # Prepare parties
        parties_list = "\n".join([f"- {p.name} ({p.role})" for p in fact_matrix.parties])

        # Prepare timeline events
        timeline_list = "\n".join(
            [
                f"- {event.date if event.date else 'Unknown date'}: {event.description}"
                for event in fact_matrix.timeline[:10]  # Limit to 10 most important
            ]
        )

        # Prepare legal issues
        issues_list = "\n".join(
            [f"- {issue.issue_name} (confidence: {issue.confidence})" for issue in issue_map.primary_issues]
        )

        # Evidence gaps from deep analysis
        evidence_gaps = "\n".join(deep_analysis.risk_assessment.evidence_gaps) if deep_analysis.risk_assessment.evidence_gaps else "None identified"

        prior_gaps_summary = "None provided"
        if prior_gap_analysis:
            prior_lines = []
            for category, gaps in prior_gap_analysis.gaps_by_category.items():
                for gap in gaps[:12]:
                    prior_lines.append(
                        f"- [{gap.gap_id}] ({gap.severity}) {gap.title} | category={category}"
                    )
            if prior_lines:
                prior_gaps_summary = "\n".join(prior_lines[:80])

        resolution_section = resolution_context.strip() if resolution_context else "None provided"

        # Build truncation disclosure section
        truncation_section = ""
        if truncation_context and truncation_context.get("overflow_count", 0) > 0:
            total = truncation_context["total_documents"]
            window = truncation_context["evidence_window"]
            overflow_count = truncation_context["overflow_count"]
            overflow_names = truncation_context.get("overflow_doc_names", [])
            capped_names = overflow_names[:20]
            bullet_list = "\n".join(f"  - {name}" for name in capped_names)
            more_text = f"\n  ... and {overflow_count - 20} more" if overflow_count > 20 else ""
            truncation_section = f"""
**Document Coverage Notice:**
This case contains {total} documents. {window} documents had full text analysis;
{overflow_count} additional documents have metadata-only coverage (marked
"not_evaluated" / "metadata_only" in the registry and signature evidence).

Documents outside full analysis window (showing first {min(20, overflow_count)}):
{bullet_list}{more_text}

CRITICAL: Do NOT flag any document with evaluation_status="metadata_only" as
"missing." These documents EXIST in the case file but were not fully analyzed.
If you have concerns about their content, classify as "incomplete_info" with a
recommendation to review, NOT as "missing_document."

"""

        prompt = f"""You are a critical legal analyst reviewing a case file for completeness and consistency.
Your role is to identify weaknesses, gaps, and concerns that an attorney should address BEFORE proceeding.

CONTEXT:

**Documents Provided:**
{doc_list}

**Document Evidence (Structured Summaries):**
{doc_evidence_summary}

**Execution/Signature Evidence (Authoritative Metadata):**
{signature_evidence_summary}

**Document Registry (Authority/Role Classification):**
{document_registry_summary}

**Parties Involved:**
{parties_list}

**Timeline (Key Events):**
{timeline_list}

**Legal Issues Identified:**
{issues_list}

**Known Evidence Gaps:**
{evidence_gaps}

**Prior Gap Analysis (if any):**
{prior_gaps_summary}

**User Resolution Inputs (if any):**
{resolution_section}

**Case Viability Assessment:**
- Overall Strength: {deep_analysis.overall_case_strength}
- Is Viable: {deep_analysis.is_viable}
- Reasoning: {deep_analysis.viability_reasoning or 'Not provided'}

**Intake Information:**
{intake_content[:2000] if intake_content else 'No intake form provided'}
{truncation_section}
---

TASK: Identify gaps and inconsistencies in 5 categories:

1. **MISSING DOCUMENTS**
   - Documents referenced in other documents but not provided
   - Expected documents based on case type (e.g., lease agreement, contract, notice, invoices)
   - Critical evidence gaps that weaken the case

2. **FACTUAL CONTRADICTIONS**
   - Conflicting information across documents (e.g., different amounts, dates, terms)
   - Intake form vs. document discrepancies
   - Party name conflicts or inconsistencies

3. **TIMELINE GAPS**
   - Missing critical dates (e.g., when notice was sent, when contract was signed)
   - Out-of-sequence events that don't make logical sense
   - Statute of limitations concerns based on missing dates

4. **UNVERIFIABLE CLAIMS**
   - Assertions made in intake or analysis without supporting evidence
   - Claims that appear in one document but aren't corroborated by others
   - Assumptions that need verification

5. **HALLUCINATION RISKS** (CRITICAL FOR LETTER QUALITY)
   - Facts stated in the analysis that lack document support
   - Legal conclusions drawn without explicit statutory basis
   - Implied information that should be stated explicitly
   - Calculations or derived dates/amounts that could be wrong
   - Assumptions about opposing party's position or knowledge
   - Contract terms or clauses referenced but not quoted from documents
   - Any statement that would require "making something up" to include in a letter

---

INSTRUCTIONS:

For each gap you identify:
- Assign severity: "critical" (case-breaking), "high" (significant impact), "medium" (notable concern), or "low" (minor issue)
- Provide a brief title (under 100 chars)
- Write a detailed description explaining the gap
- Explain the impact on the case
- Provide 1-3 specific recommendations to address the gap
- List related documents (if any)
- Identify which legal issue is affected (if applicable)

Be thorough but balanced:
- Don't invent problems that don't exist
- Focus on material gaps that actually affect case viability
- Consider whether the gap is truly critical or just "nice to have"

If prior gaps and user resolutions are provided:
- Reconcile each prior gap against the user input and supporting excerpts.
- Reuse existing `gap_id` when the same underlying issue remains open.
- If an issue appears fully resolved, omit it from `gaps_by_category`.
- If partially resolved, keep it with reduced severity when justified.
- Create new gap IDs only for genuinely new issues.

Execution guardrails:
- Treat the "Execution/Signature Evidence" block as authoritative metadata.
- If a document is marked `status=signed`, do NOT claim that same document is missing execution/signature.
- If signatures exist but party/standing alignment is unclear, classify that as contradiction/incomplete info, not missing executed documents.
- Treat the "Document Registry" block as authoritative for document role/authority tier.
- High-authority documents (controlling instruments and official records) should anchor your gap severity decisions.
- Do not call a document "missing" if the same or equivalent instrument is present in the registry.
- If `signature_expected=true` and `signature_review=true`, treat it as a review/verification gap (execution unclear), not a missing-document gap.

Calculate an overall completeness score (0-100):
- 90-100: Excellent documentation, minor gaps only
- 75-89: Good documentation, some notable gaps
- 60-74: Adequate documentation, significant gaps exist
- 40-59: Poor documentation, major gaps throughout
- 0-39: Critical documentation failures

Provide an attorney summary (2-3 sentences) about overall case completeness and most critical action items.

Return your analysis as structured JSON matching the GapAnalysisResult schema:
{{
    "total_gaps": <int>,
    "critical_count": <int>,
    "high_count": <int>,
    "medium_count": <int>,
    "low_count": <int>,
    "gaps_by_category": {{
        "missing_document": [<GapItem objects>],
        "factual_contradiction": [<GapItem objects>],
        "timeline_gap": [<GapItem objects>],
        "unverifiable_claim": [<GapItem objects>],
        "hallucination_risk": [<GapItem objects>],
        "incomplete_info": [<GapItem objects>]
    }},
    "overall_completeness_score": <float 0-100>,
    "attorney_summary": "<string>"
}}

Each GapItem should have:
{{
    "gap_id": "<unique_id>",
    "category": "<category_enum>",
    "severity": "<severity_enum>",
    "title": "<brief description>",
    "description": "<detailed explanation>",
    "affected_issue": "<legal issue name or null>",
    "related_documents": [<document names>],
    "recommendations": [<action items>],
    "impact_on_case": "<explanation>"
}}

Valid category values (category_enum): missing_document, factual_contradiction, timeline_gap, unverifiable_claim, hallucination_risk, incomplete_info
Valid severity values (severity_enum): critical, high, medium, low

Begin your analysis now.
"""

        return prompt

    # ──────────────────────────────────────────────────────────────────
    # Map-Reduce Gap Analysis (for cases with >50 docs)
    # ──────────────────────────────────────────────────────────────────

    async def analyze_gaps_map_reduce(
        self,
        batches: List[Any],  # List[GapBatch] from analysis.py
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        deep_analysis: DeepAnalysis,
        intake_content: Optional[str] = None,
        signature_evidence: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        resolution_context: Optional[str] = None,
        prior_gap_analysis: Optional[GapAnalysisResult] = None,
        truncation_context: Optional[Dict[str, Any]] = None,
    ) -> GapAnalysisResult:
        """Run map-reduce gap analysis across multiple document batches.

        Map phase: parallel batch analysis with gpt-5-mini
        Reduce phase: merge batch reports with gpt-5.4

        The existing single-pass path uses gpt-5.2 because it does straightforward
        structured extraction on <=50 pre-summarized docs. The map-reduce path
        uses reasoning models because map batches must detect cross-document
        contradictions and infer missing evidence from partial views, and the
        reduce phase must merge conflicting signals across batches.
        """
        pipeline_start = time.time()
        total_docs = sum(len(b.document_summaries) for b in batches)
        logger.info(
            f"[GAP:MAP_REDUCE] Starting | batches={len(batches)} "
            f"total_docs={total_docs}"
        )

        # ── Map phase ──
        parse_stats = {
            "first_attempt_success": 0,
            "repair_prompt_success": 0,
            "fallback_model_success": 0,
            "total_failures": 0,
        }
        map_tasks = [
            self._run_map_batch(
                batch, fact_matrix, issue_map, batches, parse_stats,
                truncation_context=truncation_context,
            )
            for batch in batches
        ]
        batch_results = await asyncio.gather(*map_tasks, return_exceptions=True)

        successful: List[BatchGapReport] = []
        failed_batches: List[Dict[str, Any]] = []
        batch_metadata: List[Dict[str, Any]] = []

        for i, result in enumerate(batch_results):
            if isinstance(result, tuple) and len(result) == 2:
                report, meta = result
                successful.append(report)
                batch_metadata.append(meta)
            elif isinstance(result, Exception):
                failed_batches.append({
                    "batch_id": batches[i].batch_id,
                    "batch_label": batches[i].batch_label,
                    "error": str(result),
                })
                logger.error(
                    f"[GAP:MAP:{batches[i].batch_id}] FAILED | error={result}"
                )

        total_attempted = len(batches)
        parse_failure_pct = (
            (parse_stats["total_failures"] / total_attempted * 100)
            if total_attempted > 0
            else 0.0
        )

        logger.info(
            f"[GAP:MAP:PARSE_STATS] total_batches={total_attempted} "
            f"first_attempt_success={parse_stats['first_attempt_success']} "
            f"repair_success={parse_stats['repair_prompt_success']} "
            f"fallback_success={parse_stats['fallback_model_success']} "
            f"total_failures={parse_stats['total_failures']} "
            f"parse_failure_rate={parse_failure_pct:.1f}%"
        )

        if parse_failure_pct > 40:
            logger.warning(
                "[GAP:MAP:VIABILITY_WARNING] gpt-5-mini parse failure rate "
                f"exceeds 40% ({parse_failure_pct:.1f}%) — consider switching "
                "default map model"
            )

        parse_stats["parse_failure_rate_pct"] = round(parse_failure_pct, 1)

        # ── Determine quality and route to reduce or fallback ──
        if not successful:
            # All map batches failed → fall back to single-pass
            logger.warning(
                "[GAP:MAP_REDUCE] All map batches failed — falling back to single-pass"
            )
            all_summaries = [
                s for batch in batches for s in batch.document_summaries
            ]
            # Build fallback truncation context from omitted summaries
            fallback_truncation = truncation_context
            if len(all_summaries) > 50 and not fallback_truncation:
                omitted = all_summaries[50:]
                fallback_truncation = {
                    "total_documents": len(all_summaries),
                    "evidence_window": 50,
                    "overflow_count": len(omitted),
                    "overflow_doc_ids": set(),
                    "overflow_doc_names": [
                        getattr(s, "document_name", "Unknown") for s in omitted
                    ],
                }
            # Use only first 50 docs for single-pass fallback
            result = await self.analyze_gaps(
                fact_matrix=fact_matrix,
                issue_map=issue_map,
                deep_analysis=deep_analysis,
                document_summaries=all_summaries[:50],
                intake_content=intake_content,
                resolution_context=resolution_context,
                prior_gap_analysis=prior_gap_analysis,
                signature_evidence=signature_evidence,
                document_registry=document_registry,
                truncation_context=fallback_truncation,
            )
            result.analysis_quality = "fallback_single_pass"
            result.map_reduce_metadata = {
                "pipeline": "fallback_single_pass",
                "total_documents_analyzed": min(50, total_docs),
                "failed_batches": failed_batches,
                "parse_stats": parse_stats,
                "overflow_doc_names": (
                    fallback_truncation.get("overflow_doc_names", [])
                    if fallback_truncation
                    else []
                ),
            }
            return result

        # ── Reduce phase ──
        analysis_quality = "full" if not failed_batches else "degraded_partial"
        reduce_start = time.time()

        try:
            result = await self._run_reduce(
                successful_reports=successful,
                failed_batches=failed_batches,
                fact_matrix=fact_matrix,
                issue_map=issue_map,
                deep_analysis=deep_analysis,
                intake_content=intake_content,
                signature_evidence=signature_evidence,
                document_registry=document_registry,
                resolution_context=resolution_context,
                prior_gap_analysis=prior_gap_analysis,
                truncation_context=truncation_context,
            )
        except Exception as reduce_err:
            logger.error(f"[GAP:REDUCE] FAILED | error={reduce_err}", exc_info=True)
            result = self._mechanical_merge(successful)
            analysis_quality = "degraded_merge"

        reduce_duration = time.time() - reduce_start

        # ── Post-processing (same as single-pass) ──
        overflow_doc_ids = set(truncation_context.get("overflow_doc_ids", [])) if truncation_context else None
        overflow_doc_names = set(truncation_context.get("overflow_doc_names", [])) if truncation_context else None
        result = self._reconcile_signature_execution_gaps(
            result, signature_evidence,
            overflow_doc_ids=overflow_doc_ids,
            overflow_doc_names=overflow_doc_names,
        )
        result.recommendation = self._generate_recommendation(
            result, deep_analysis=deep_analysis
        )

        # Add INCOMPLETE_INFO gap if some batches failed
        if failed_batches:
            incomplete_item = GapItem(
                gap_id="gap_map_reduce_incomplete",
                title="Incomplete Analysis - Some Document Batches Failed",
                description=(
                    f"{len(failed_batches)} of {total_attempted} document batches "
                    f"could not be analyzed. Results may be incomplete."
                ),
                severity=GapSeverity.MEDIUM,
                category=GapCategory.INCOMPLETE_INFO,
                impact_on_case=(
                    f"Analysis covers only {total_attempted - len(failed_batches)} of "
                    f"{total_attempted} document batches. Some gaps may be undetected."
                ),
            )
            result.gaps_by_category.setdefault("incomplete_info", []).append(
                incomplete_item
            )

        # ── Attach provenance metadata ──
        map_total_findings = sum(len(r.findings) for r in successful)
        result.analysis_quality = analysis_quality
        result.map_reduce_metadata = {
            "pipeline": "map_reduce",
            "total_documents_analyzed": total_docs,
            "map_model": self.client.get_preferred_model(
                "gap_analysis_map", "gpt-5.4-mini"
            ),
            "reduce_model": self.client.get_preferred_model(
                "gap_analysis_reduce", "gpt-5.5"
            ),
            "batches": batch_metadata,
            "failed_batches": failed_batches,
            "reduce_duration_s": round(reduce_duration, 1),
            "map_total_findings": map_total_findings,
            "reduce_final_gaps": result.total_gaps,
            "parse_stats": parse_stats,
            "total_duration_s": round(time.time() - pipeline_start, 1),
        }

        logger.info(
            f"[GAP:MAP_REDUCE] Complete | quality={analysis_quality} "
            f"gaps={result.total_gaps} score={result.overall_completeness_score} "
            f"duration={result.map_reduce_metadata['total_duration_s']}s"
        )

        return result

    async def _run_map_batch(
        self,
        batch: Any,  # GapBatch
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        all_batches: List[Any],
        parse_stats: Dict[str, int],
        truncation_context: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """Run gap analysis on a single batch with tiered retry.

        Returns (BatchGapReport, metadata_dict) on success, raises on failure.
        """
        batch_start = time.time()
        map_model = self.client.get_preferred_model("gap_analysis_map", "gpt-5.4-mini")

        logger.info(
            f"[GAP:MAP:{batch.batch_id}] Starting | docs={len(batch.document_summaries)} "
            f"label={batch.batch_label} model={map_model}"
        )

        prompt = self._build_map_prompt(
            batch, fact_matrix, issue_map, all_batches,
            truncation_context=truncation_context,
        )
        prompt_chars = len(prompt)
        logger.info(
            f"[GAP:PROMPT] batch={batch.batch_id} prompt_size={prompt_chars} chars "
            f"(~{prompt_chars // 4} tokens)"
        )
        instructions = (
            "You are a critical legal analyst reviewing a batch of case documents. "
            "Return only valid JSON matching the BatchGapReport schema. "
            "Do not include any text before or after the JSON."
        )

        def _build_batch_meta(
            report: BatchGapReport, model: str, retry_count: int,
        ) -> Dict[str, Any]:
            return {
                "batch_id": batch.batch_id,
                "batch_label": batch.batch_label,
                "doc_count": len(batch.document_summaries),
                "evidence_count": len(report.evidence),
                "findings_count": len(report.findings),
                "duration_s": round(time.time() - batch_start, 1),
                "model_used": model,
                "retry_count": retry_count,
            }

        # Attempt 1: primary model
        raw_response = None
        try:
            response_dict = await asyncio.to_thread(
                self.client.create_response,
                model=map_model,
                instructions=instructions,
                input=prompt,
                max_output_tokens=3000,
                reasoning_effort="low" if self.client._is_gpt5_model(map_model) else None,
            )
            raw_response = (response_dict.get("content") or "").strip()
            report = self._parse_batch_report(raw_response, batch)
            parse_stats["first_attempt_success"] += 1
            logger.info(
                f"[GAP:MAP:{batch.batch_id}] Complete | "
                f"duration={time.time() - batch_start:.1f}s "
                f"evidence={len(report.evidence)} findings={len(report.findings)}"
            )
            return report, _build_batch_meta(report, map_model, 0)
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning(
                f"[GAP:MAP:{batch.batch_id}] Parse failed (attempt 1) | "
                f"model={map_model}"
            )

        # Attempt 2: same model, repair prompt
        try:
            repair_prompt = (
                "The previous output had invalid JSON. Here is the malformed output:\n\n"
                f"{(raw_response or '')[:2000]}\n\n"
                "Return ONLY the corrected JSON object matching the BatchGapReport schema. "
                "No markdown, no explanation. The schema requires: "
                "batch_id (str), batch_label (str), document_count (int), "
                "evidence (list of objects with category, document_ids, status, severity, detail), "
                "findings (list of objects with category, severity, title, description, document_ids), "
                "cross_batch_flags (list of strings)."
            )
            response_dict = await asyncio.to_thread(
                self.client.create_response,
                model=map_model,
                instructions="Return ONLY valid JSON. No markdown, no explanation.",
                input=repair_prompt,
                max_output_tokens=2000,
                reasoning_effort="low" if self.client._is_gpt5_model(map_model) else None,
            )
            raw_response = (response_dict.get("content") or "").strip()
            report = self._parse_batch_report(raw_response, batch)
            parse_stats["repair_prompt_success"] += 1
            logger.info(
                f"[GAP:MAP:{batch.batch_id}] Complete (repair) | "
                f"duration={time.time() - batch_start:.1f}s "
                f"evidence={len(report.evidence)} findings={len(report.findings)}"
            )
            return report, _build_batch_meta(report, map_model, 1)
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning(
                f"[GAP:MAP:{batch.batch_id}] Parse failed (attempt 2 repair) | "
                f"model={map_model}"
            )

        # Attempt 3: fallback to gpt-5.2
        fallback_model = "gpt-5.5"
        try:
            response_dict = await asyncio.to_thread(
                self.client.create_response,
                model=fallback_model,
                instructions=instructions,
                input=prompt,
                max_output_tokens=3000,
            )
            raw_response = (response_dict.get("content") or "").strip()
            report = self._parse_batch_report(raw_response, batch)
            parse_stats["fallback_model_success"] += 1
            logger.info(
                f"[GAP:MAP:{batch.batch_id}] Complete (fallback) | "
                f"duration={time.time() - batch_start:.1f}s model={fallback_model} "
                f"evidence={len(report.evidence)} findings={len(report.findings)}"
            )
            return report, _build_batch_meta(report, fallback_model, 2)
        except Exception as e:
            parse_stats["total_failures"] += 1
            logger.error(
                f"[GAP:MAP:{batch.batch_id}] FAILED | all 3 attempts exhausted | "
                f"error={e}"
            )
            raise RuntimeError(
                f"Map batch {batch.batch_id} failed after 3 attempts: {e}"
            ) from e

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Remove markdown code fences (```json ... ```) from LLM output."""
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)
        return text

    def _parse_batch_report(self, raw: str, batch: Any) -> BatchGapReport:
        """Parse raw JSON into BatchGapReport, raising on failure."""
        cleaned = self._strip_markdown_fences(raw)
        data = json.loads(cleaned)
        # Ensure batch_id/batch_label match what we sent
        data["batch_id"] = batch.batch_id
        data["batch_label"] = batch.batch_label
        data["document_count"] = len(batch.document_summaries)
        return BatchGapReport(**data)

    def _build_map_prompt(
        self,
        batch: Any,  # GapBatch
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        all_batches: List[Any],
        truncation_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the prompt for a single map-phase batch."""
        # Document ID mapping table
        id_table = "\n".join(
            f"  {s.document_id or 'NO_ID'} → {s.document_name}"
            for s in batch.document_summaries
        )

        # Other batch labels for context
        other_labels = [
            f"{b.batch_label} ({len(b.document_summaries)} docs)"
            for b in all_batches
            if b.batch_id != batch.batch_id
        ]

        doc_evidence = self._build_document_evidence_summary(batch.document_summaries)
        sig_evidence = self._build_signature_evidence_summary(batch.signature_evidence)
        reg_summary = self._build_document_registry_summary(batch.registry_entries)

        # Condensed shared context
        parties_text = ", ".join(
            p.name for p in (fact_matrix.parties or [])[:10]
        ) or "None identified"
        timeline_text = self._truncate_text(
            json.dumps(
                [e.model_dump() for e in (fact_matrix.timeline or [])[:10]],
                default=str,
            )
            if fact_matrix.timeline
            else "",
            2000,
        )
        issues_text = "\n".join(
            f"- {iss.issue_name} ({iss.category})"
            for iss in (issue_map.primary_issues or [])[:10]
        ) or "None identified"

        # Lightweight truncation notice for map batches
        map_truncation_note = ""
        if truncation_context and truncation_context.get("overflow_count", 0) > 0:
            map_truncation_note = (
                f"\n**Note:** This case has {truncation_context['total_documents']} total documents. "
                f"Some documents have metadata-only coverage (evaluation_status='metadata_only'). "
                "Do NOT flag metadata_only documents as 'missing.'\n"
            )

        prompt = f"""## Gap Analysis — Batch: {batch.batch_label}

You are analyzing batch "{batch.batch_label}" ({len(batch.document_summaries)} documents)
as part of a multi-batch gap analysis.

### Document ID Mapping
{id_table}

### Other Batches Being Analyzed Separately
{chr(10).join(f"- {lbl}" for lbl in other_labels) if other_labels else "This is the only batch."}

**Important:** If you suspect evidence might exist in another batch, set
`cross_batch_uncertain: true` on that finding and add a flag to `cross_batch_flags`
using format: `CHECK_BATCH:{{batch_label}} FOR:{{category}}`. Maximum 5 flags.

### Case Context

**Parties:** {parties_text}

**Timeline:**
{timeline_text}

**Primary Issues:**
{issues_text}

### Document Evidence (This Batch Only)
{doc_evidence}

### Signature Evidence (This Batch Only)
{sig_evidence}

### Document Registry (This Batch Only)
{reg_summary}
{map_truncation_note}
### Your Task

Analyze ONLY the documents in this batch. For each:
1. Identify evidence categories that are present, missing, or incomplete
2. Identify gaps, contradictions, and concerns
3. Flag items that may be resolved by documents in other batches

Return a JSON object matching this schema:
{{
  "batch_id": "{batch.batch_id}",
  "batch_label": "{batch.batch_label}",
  "document_count": {len(batch.document_summaries)},
  "evidence": [
    {{"category": "string", "document_ids": ["uuid"], "status": "present|missing|incomplete",
      "severity": "critical|high|medium|low or null", "detail": "1-2 sentences"}}
  ],
  "findings": [
    {{"category": "string", "severity": "critical|high|medium|low", "title": "string",
      "description": "string", "document_ids": ["uuid"],
      "affected_issue": "string or null", "cross_batch_uncertain": false}}
  ],
  "cross_batch_flags": ["CHECK_BATCH:label FOR:category"]
}}

Use document_ids (UUIDs) from the mapping table above, not document names.
Return ONLY valid JSON. No markdown, no explanation.
"""
        return prompt

    # Category keyword heuristics for normalizing freeform LLM category strings
    _CATEGORY_KEYWORDS: Dict[str, List[str]] = {
        "missing_document": [
            "missing", "absent", "lack", "unavailable", "not provided", "proof", "no ",
        ],
        "factual_contradiction": [
            "contradict", "inconsisten", "conflict", "discrepan",
        ],
        "timeline_gap": [
            "timeline", "date", "chronolog", "sequence", "delay",
        ],
        "unverifiable_claim": [
            "unverif", "cannot confirm", "no evidence", "unsupported",
        ],
        "hallucination_risk": [
            "hallucin", "fabricat", "invented",
        ],
        "incomplete_info": [
            "incomplete", "partial", "insufficient", "unclear", "vague",
            "communication", "identity", "damage", "valuation", "execution",
            "contract", "repair",
        ],
    }

    _VALID_CATEGORIES = {
        "missing_document", "factual_contradiction", "timeline_gap",
        "unverifiable_claim", "hallucination_risk", "incomplete_info",
    }

    def _map_category_key(self, raw_key: str) -> str:
        """Map a freeform category string to a valid GapCategory enum value."""
        normalized = raw_key.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in self._VALID_CATEGORIES:
            return normalized
        # Keyword heuristic search
        for cat, keywords in self._CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in normalized or kw in raw_key.lower():
                    return cat
        return "incomplete_info"

    def _normalize_reduce_output(self, data: dict) -> dict:
        """Defense-in-depth normalizer for reduce-phase LLM output.

        Handles common LLM deviations from the GapItem schema:
        - Freeform category keys → valid enum values
        - Missing gap_id → auto-generated
        - Missing impact_on_case → filled from description
        - affected_issues (list) → affected_issue (str)
        - suggested_action → recommendations (list)
        - supporting_documents → related_documents
        - Missing reconciliation_notes → []
        - Severity counts recalculated from actual items
        """
        # --- Normalize gaps_by_category keys ---
        raw_gaps = data.get("gaps_by_category", {})
        normalized_gaps: Dict[str, list] = {}
        for raw_key, items in raw_gaps.items():
            mapped_key = self._map_category_key(raw_key)
            if mapped_key not in normalized_gaps:
                normalized_gaps[mapped_key] = []
            if isinstance(items, list):
                normalized_gaps[mapped_key].extend(items)

        # --- Per-item fixes ---
        gap_counter = 0
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for cat_key, items in normalized_gaps.items():
            for item in items:
                if not isinstance(item, dict):
                    continue

                # Auto-generate gap_id if missing
                if not item.get("gap_id"):
                    item["gap_id"] = f"gap_reduce_{gap_counter}"
                gap_counter += 1

                # Normalize category field on the item itself
                if "category" in item:
                    item["category"] = self._map_category_key(str(item["category"]))
                else:
                    item["category"] = cat_key

                # affected_issues (list) → affected_issue (str)
                if "affected_issues" in item and "affected_issue" not in item:
                    ai = item.pop("affected_issues")
                    item["affected_issue"] = ai[0] if isinstance(ai, list) and ai else None

                # suggested_action → recommendations (wrap in list)
                if "suggested_action" in item and "recommendations" not in item:
                    sa = item.pop("suggested_action")
                    item["recommendations"] = [sa] if sa else []

                # supporting_documents → related_documents
                if "supporting_documents" in item and "related_documents" not in item:
                    item["related_documents"] = item.pop("supporting_documents")

                # Missing impact_on_case → fill from description or suggested_action
                if not item.get("impact_on_case"):
                    item["impact_on_case"] = (
                        item.get("description")
                        or item.get("suggested_action")
                        or "Impact not specified"
                    )

                # Count severity
                sev = str(item.get("severity", "medium")).lower()
                if sev in severity_counts:
                    severity_counts[sev] += 1

        data["gaps_by_category"] = normalized_gaps

        # --- Top-level fixes ---
        if "reconciliation_notes" not in data:
            data["reconciliation_notes"] = []

        # Recalculate severity counts from actual items
        data["critical_count"] = severity_counts["critical"]
        data["high_count"] = severity_counts["high"]
        data["medium_count"] = severity_counts["medium"]
        data["low_count"] = severity_counts["low"]
        data["total_gaps"] = sum(severity_counts.values())

        return data

    async def _run_reduce(
        self,
        successful_reports: List[BatchGapReport],
        failed_batches: List[Dict[str, Any]],
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        deep_analysis: DeepAnalysis,
        intake_content: Optional[str] = None,
        signature_evidence: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        resolution_context: Optional[str] = None,
        prior_gap_analysis: Optional[GapAnalysisResult] = None,
        truncation_context: Optional[Dict[str, Any]] = None,
    ) -> GapAnalysisResult:
        """Merge batch reports into a single GapAnalysisResult."""
        reduce_model = self.client.get_preferred_model(
            "gap_analysis_reduce", "gpt-5.5"
        )
        total_findings = sum(len(r.findings) for r in successful_reports)

        logger.info(
            f"[GAP:REDUCE] Starting | batches_ok={len(successful_reports)} "
            f"batches_failed={len(failed_batches)} total_findings={total_findings} "
            f"model={reduce_model}"
        )

        prompt = self._build_reduce_prompt(
            successful_reports=successful_reports,
            failed_batches=failed_batches,
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            intake_content=intake_content,
            signature_evidence=signature_evidence,
            document_registry=document_registry,
            resolution_context=resolution_context,
            prior_gap_analysis=prior_gap_analysis,
            truncation_context=truncation_context,
        )

        prompt_chars = len(prompt)
        logger.info(f"[GAP:PROMPT] prompt_size={prompt_chars} chars (~{prompt_chars // 4} tokens)")

        from legal_portal.config.default import get_settings
        _gap_settings = get_settings()

        try:
            response_dict = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.create_response,
                    model=reduce_model,
                    instructions=(
                        "You are a senior legal analyst merging batch gap analysis reports "
                        "into a unified assessment. Return only valid JSON matching the "
                        "GapAnalysisResult schema. Do not include any text before or after the JSON."
                    ),
                    input=prompt,
                    max_output_tokens=8000,
                    reasoning_effort="low" if self.client._is_gpt5_model(reduce_model) else None,
                ),
                timeout=_gap_settings.gap_analysis_budget_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"[GAP:REDUCE:TIMEOUT] Reduce phase timed out "
                f"(budget={_gap_settings.gap_analysis_budget_seconds}s)"
            )
            raise

        raw = (response_dict.get("content") or "").strip()
        if not raw:
            raise ValueError("Reduce phase returned empty response")

        data = json.loads(self._strip_markdown_fences(raw))
        data = self._normalize_reduce_output(data)
        result = GapAnalysisResult(**data)

        logger.info(
            f"[GAP:REDUCE] Complete | final_gaps={result.total_gaps} "
            f"score={result.overall_completeness_score}"
        )
        return result

    def _build_reduce_prompt(
        self,
        successful_reports: List[BatchGapReport],
        failed_batches: List[Dict[str, Any]],
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        deep_analysis: DeepAnalysis,
        intake_content: Optional[str] = None,
        signature_evidence: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        resolution_context: Optional[str] = None,
        prior_gap_analysis: Optional[GapAnalysisResult] = None,
        truncation_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the prompt for the reduce phase."""
        # Serialize batch reports
        batch_reports_json = json.dumps(
            [r.model_dump() for r in successful_reports],
            indent=2,
            default=str,
        )

        # Full context blocks
        sig_summary = self._build_signature_evidence_summary(signature_evidence)
        reg_summary = self._build_document_registry_summary(document_registry)
        intake_text = self._truncate_text(intake_content, 2000)

        # Deep analysis summary
        deep_text = ""
        if deep_analysis:
            deep_text = self._truncate_text(
                json.dumps(deep_analysis.model_dump(), default=str), 4000
            )

        # Issues
        issues_text = "\n".join(
            f"- {iss.issue_name} ({iss.category})"
            for iss in (issue_map.primary_issues or [])[:15]
        ) or "None identified"

        # Prior analysis context
        prior_text = ""
        if prior_gap_analysis:
            prior_text = f"\n### Prior Gap Analysis\n{self._truncate_text(json.dumps(prior_gap_analysis.model_dump(), default=str), 3000)}"
        resolution_text = ""
        if resolution_context:
            resolution_text = f"\n### Resolution Context\n{self._truncate_text(resolution_context, 2000)}"

        failed_text = ""
        if failed_batches:
            failed_text = (
                "\n### Failed Batches (Not Analyzed)\n"
                + "\n".join(
                    f"- {fb['batch_label']}: {fb['error']}"
                    for fb in failed_batches
                )
                + "\nNote: Documents in failed batches were not analyzed. "
                "Flag any gaps that might be affected by this missing coverage."
            )

        # Build truncation disclosure for reduce prompt
        truncation_text = ""
        if truncation_context and truncation_context.get("overflow_count", 0) > 0:
            total = truncation_context["total_documents"]
            window = truncation_context["evidence_window"]
            overflow_count = truncation_context["overflow_count"]
            overflow_names = truncation_context.get("overflow_doc_names", [])
            capped_names = overflow_names[:20]
            bullet_list = "\n".join(f"  - {name}" for name in capped_names)
            more_text = f"\n  ... and {overflow_count - 20} more" if overflow_count > 20 else ""
            truncation_text = f"""
### Document Coverage Notice
This case contains {total} documents. {window} documents had full text analysis;
{overflow_count} additional documents have metadata-only coverage (marked
"metadata_only" in the registry and signature evidence).

Documents outside full analysis window (showing first {min(20, overflow_count)}):
{bullet_list}{more_text}

CRITICAL: Do NOT flag any document with evaluation_status="metadata_only" as
"missing." These documents EXIST in the case file but were not fully analyzed.
If you have concerns about their content, classify as "incomplete_info" with a
recommendation to review, NOT as "missing_document."
"""

        prompt = f"""## Gap Analysis — Reduce Phase (Merge Batch Reports)

You are merging {len(successful_reports)} batch gap analysis reports into a single
unified gap analysis result.

### Batch Reports
{batch_reports_json}
{failed_text}

### Full Case Context

**Primary Issues:**
{issues_text}

**Full Signature Evidence:**
{sig_summary}

**Full Document Registry:**
{reg_summary}

**Deep Analysis:**
{deep_text}

**Intake Content:**
{intake_text}
{prior_text}
{resolution_text}
{truncation_text}
### Merge Instructions

1. **Cross-reference evidence:** If Batch A flags "missing contract" but Batch B's
   evidence shows status="present" for that category, REMOVE the gap.
2. **Resolve cross_batch_uncertain:** Items with cross_batch_uncertain=true require
   cross-batch verification. Check cross_batch_flags against other batches' evidence.
   Only include the gap if no other batch has the evidence.
3. **Identify cross-batch gaps:** Look for gaps only visible when combining all batches
   (e.g., timeline inconsistencies across documents in different batches).
4. **Deduplicate:** Merge overlapping findings across batches. Keep the higher severity.
5. **Recalibrate severity:** With full case context, adjust severity levels.
6. **Calculate overall_completeness_score:** Single score 0-100 for the entire case.

### Output Schema

Return a JSON object with these fields:
{{
  "total_gaps": int,
  "critical_count": int,
  "high_count": int,
  "medium_count": int,
  "low_count": int,
  "gaps_by_category": {{
    "<category_enum>": [
      {{
        "gap_id": "gap_1",
        "category": "<category_enum>",
        "severity": "critical|high|medium|low",
        "title": "Brief description of the gap",
        "description": "Detailed explanation",
        "impact_on_case": "How this gap affects case viability or strategy",
        "affected_issue": "Which legal issue is affected",
        "related_documents": ["doc names..."],
        "recommendations": ["Suggested actions..."]
      }}
    ]
  }},
  "overall_completeness_score": float (0-100),
  "attorney_summary": "Executive summary string",
  "reconciliation_notes": ["Notes about cross-batch reconciliation..."]
}}

IMPORTANT — category_enum MUST be one of these exact values (use as BOTH dictionary keys AND each item's "category" field):
- missing_document
- factual_contradiction
- timeline_gap
- unverifiable_claim
- hallucination_risk
- incomplete_info

Return ONLY valid JSON. No markdown, no explanation.
"""
        return prompt

    def _mechanical_merge(
        self,
        successful_reports: List[BatchGapReport],
    ) -> GapAnalysisResult:
        """Deterministic fallback when the reduce phase fails.

        Concatenates batch findings, deduplicates, and constructs a
        GapAnalysisResult without an LLM call.
        """
        logger.info(
            f"[GAP:REDUCE:MECHANICAL] Merging {len(successful_reports)} batch reports"
        )

        all_findings = []
        for report in successful_reports:
            all_findings.extend(report.findings)

        deduped = _deduplicate_findings(all_findings)

        # Build gaps_by_category from deduplicated findings
        gaps_by_category: Dict[str, List[GapItem]] = {}
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        _valid_categories = {cat.value for cat in GapCategory}

        for idx, finding in enumerate(deduped):
            severity_str = finding.severity.lower()
            severity_counts[severity_str] = severity_counts.get(severity_str, 0) + 1

            category = (
                GapCategory(finding.category)
                if finding.category in _valid_categories
                else GapCategory.INCOMPLETE_INFO
            )
            gap_item = GapItem(
                gap_id=f"gap_merge_{idx}",
                title=finding.title,
                description=finding.description,
                severity=GapSeverity(severity_str),
                category=category,
                impact_on_case=finding.description,
                related_documents=[str(did) for did in finding.document_ids],
            )
            cat_key = category.value
            gaps_by_category.setdefault(cat_key, []).append(gap_item)

        total = len(deduped)
        # Estimate completeness from severity distribution
        penalty = (
            severity_counts["critical"] * 15
            + severity_counts["high"] * 8
            + severity_counts["medium"] * 3
            + severity_counts["low"] * 1
        )
        score = max(0.0, min(100.0, 100.0 - penalty))

        return GapAnalysisResult(
            total_gaps=total,
            critical_count=severity_counts["critical"],
            high_count=severity_counts["high"],
            medium_count=severity_counts["medium"],
            low_count=severity_counts["low"],
            gaps_by_category=gaps_by_category,
            overall_completeness_score=score,
            attorney_summary=(
                f"Mechanical merge of {len(successful_reports)} batch reports. "
                f"{total} gaps identified ({severity_counts['critical']} critical, "
                f"{severity_counts['high']} high). AI-powered merge was unavailable."
            ),
            reconciliation_notes=[
                "Result produced by mechanical merge fallback (reduce phase failed)."
            ],
        )

    def _create_fallback_result(self, error: Optional[str] = None) -> GapAnalysisResult:
        """Create a fallback result when gap analysis fails.

        Args:
            error: Optional error message

        Returns:
            Basic GapAnalysisResult indicating analysis could not be performed

        """
        fallback_gaps: Dict[str, List[GapItem]] = {
            category.value: [] for category in GapCategory
        }

        if error:
            # Add a single gap indicating the analysis failed
            fallback_gaps[GapCategory.INCOMPLETE_INFO.value] = [
                GapItem(
                    gap_id="gap_analysis_error",
                    category=GapCategory.INCOMPLETE_INFO,
                    severity=GapSeverity.HIGH,
                    title="Gap Analysis Could Not Be Completed",
                    description=f"The automated gap analysis encountered an error: {error}",
                    affected_issue=None,
                    related_documents=[],
                    recommendations=[
                        "Manually review case materials for completeness",
                        "Verify all referenced documents are included",
                        "Check for factual inconsistencies across documents",
                    ],
                    impact_on_case="Unable to provide automated completeness assessment. Manual review recommended.",
                )
            ]

        return GapAnalysisResult(
            total_gaps=1 if error else 0,
            critical_count=0,
            high_count=1 if error else 0,
            medium_count=0,
            low_count=0,
            gaps_by_category=fallback_gaps,
            overall_completeness_score=50.0 if error else 100.0,
            attorney_summary=(
                "Gap analysis could not be completed due to a system error. Manual review recommended."
                if error
                else "No automated gap analysis was performed."
            ),
        )

    def _generate_recommendation(
        self,
        gap_analysis: GapAnalysisResult,
        deep_analysis: Optional[DeepAnalysis] = None,
    ) -> CaseRecommendation:
        """Generate a case recommendation based on gap analysis and deep analysis results.

        Decision logic:
        | Condition | Category | Color | Letter Type |
        |-----------|----------|-------|-------------|
        | !is_viable OR score < 30 OR critical >= 3 | NOT_VIABLE | red | DECLINATION |
        | score < 60 OR (critical >= 1 AND high >= 2) | NEEDS_DOCUMENTATION | yellow | REQUEST_DOCUMENTS |
        | case_strength == "weak" OR (high >= 3 AND score < 75) | SETTLEMENT_RECOMMENDED | orange | SETTLEMENT_ADVISORY |
        | Otherwise | STRONG_CASE | green | PROCEED |

        Args:
            gap_analysis: The completed gap analysis result
            deep_analysis: Optional deep analysis for viability and strength info

        Returns:
            CaseRecommendation with category, reasoning, and suggested next steps

        """
        score = gap_analysis.overall_completeness_score
        critical = gap_analysis.critical_count
        high = gap_analysis.high_count

        # Extract viability and strength from deep analysis if available
        is_viable = deep_analysis.is_viable if deep_analysis else True
        case_strength = deep_analysis.overall_case_strength if deep_analysis else "moderate"
        viability_reasoning = deep_analysis.viability_reasoning if deep_analysis else None

        # Decision logic
        if not is_viable or score < 30 or critical >= 3:
            category = CaseRecommendationCategory.NOT_VIABLE
            confidence = ConfidenceLevel.HIGH if not is_viable else ConfidenceLevel.MEDIUM
            color = "red"
            letter_type = RecommendedLetterType.DECLINATION
            display_name = "Not Viable"

            if not is_viable:
                reasoning = viability_reasoning or (
                    "The case does not appear to have sufficient legal merit to pursue. "
                    "Critical deficiencies in the evidence or legal basis make success unlikely."
                )
            elif critical >= 3:
                reasoning = (
                    f"The case has {critical} critical gaps that must be resolved before proceeding. "
                    "These deficiencies represent fundamental weaknesses that could undermine any legal action."
                )
            else:
                reasoning = (
                    f"The documentation completeness score ({score:.0f}%) is too low to proceed. "
                    "Essential information is missing that would be required to build a viable case."
                )

            next_steps = [
                "Send a declination letter explaining why the case cannot be pursued",
                "Provide statute of limitations warning if applicable",
                "Offer referral resources if appropriate",
            ]

        elif score < 60 or (critical >= 1 and high >= 2):
            category = CaseRecommendationCategory.NEEDS_DOCUMENTATION
            confidence = ConfidenceLevel.HIGH if score < 45 else ConfidenceLevel.MEDIUM
            color = "yellow"
            letter_type = RecommendedLetterType.REQUEST_DOCUMENTS
            display_name = "Needs Documentation"

            gap_summary = []
            if critical >= 1:
                gap_summary.append(f"{critical} critical")
            if high >= 1:
                gap_summary.append(f"{high} high-priority")
            gap_text = " and ".join(gap_summary) + " gap(s)" if gap_summary else "gaps"

            reasoning = (
                f"The case has {gap_text} that need to be addressed before proceeding. "
                f"Current documentation completeness is {score:.0f}%. "
                "Request the missing documents from the client to strengthen the case."
            )

            next_steps = [
                "Send a document request letter listing specific needed items",
                "Set a 14 business day deadline for client response",
                "Schedule follow-up review once documents are received",
            ]

        elif case_strength == "weak" or (high >= 3 and score < 75):
            category = CaseRecommendationCategory.SETTLEMENT_RECOMMENDED
            confidence = ConfidenceLevel.MEDIUM
            color = "orange"
            letter_type = RecommendedLetterType.SETTLEMENT_ADVISORY
            display_name = "Settlement Recommended"

            if case_strength == "weak":
                reasoning = (
                    "While the case can proceed, the overall strength assessment is weak. "
                    "Settlement negotiations may be more cost-effective than litigation. "
                    "Consider the client's risk tolerance and financial situation."
                )
            else:
                reasoning = (
                    f"The case has {high} high-priority gaps and a completeness score of {score:.0f}%. "
                    "This may make full litigation risky. "
                    "Settlement could achieve client goals while managing downside exposure."
                )

            next_steps = [
                "Send a settlement advisory letter outlining options",
                "Discuss litigation vs. settlement trade-offs with client",
                "Prepare initial settlement demand range if client agrees",
            ]

        else:
            category = CaseRecommendationCategory.STRONG_CASE
            confidence = ConfidenceLevel.HIGH if score >= 80 else ConfidenceLevel.MEDIUM
            color = "green"
            letter_type = RecommendedLetterType.PROCEED
            display_name = "Strong Case"

            strength_desc = "strong" if case_strength == "strong" else "well-supported"
            reasoning = (
                f"This appears to be a {strength_desc} case with {score:.0f}% documentation completeness. "
                "The evidence supports proceeding with a demand letter or other legal action. "
                "Minor gaps identified should be addressed but do not prevent moving forward."
            )

            next_steps = [
                "Send an engagement letter confirming representation",
                "Proceed with drafting a demand letter",
                "Establish case timeline and next milestones",
            ]

        return CaseRecommendation(
            category=category,
            confidence=confidence,
            reasoning=reasoning,
            next_steps=next_steps,
            suggested_letter_type=letter_type,
            category_display_name=display_name,
            category_color=color,
        )
