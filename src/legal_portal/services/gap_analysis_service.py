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

logger = logging.getLogger(__name__)


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
            )

            # Use GPT-4.1 for gap detection - faster and more reliable for structured JSON
            # GPT-5.2 with reasoning_effort spends tokens on internal reasoning, not output
            model = self.client.get_preferred_model("gap_analysis", "gpt-4.1")

            logger.info(
                f"[STAGE:3.5:API] Calling OpenAI for gap_analysis | "
                f"model={model} prompt_chars={len(prompt)} max_tokens=4000"
            )

            # Call OpenAI API
            api_start = time.time()
            response_dict = await asyncio.to_thread(
                self.client.create_response,
                model=model,
                instructions=(
                    "You are a critical legal analyst identifying gaps and inconsistencies in case materials. "
                    "Return only valid JSON matching the GapAnalysisResult schema. Do not include any text before or after the JSON."
                ),
                input=prompt,
                max_output_tokens=4000,
                # No reasoning_effort for GPT-4.x - it outputs content directly
            )
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

            raw_response = (response_dict.get("content") or "").strip()

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
            result = self._reconcile_signature_execution_gaps(
                result=result,
                signature_evidence=signature_evidence,
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

        lines: List[str] = []
        for item in rows[:40]:
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

        if len(rows) > 40:
            lines.append(
                f"... {len(rows) - 40} additional signature records omitted for brevity."
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
                -int(row.get("authority_score") or 0),
                str(row.get("document_name") or "").lower(),
            ),
        )
        lines: List[str] = []
        for row in sorted_rows[:50]:
            file_name = row.get("document_name") or "Unknown document"
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

        if len(sorted_rows) > 50:
            lines.append(
                f"... {len(sorted_rows) - 50} additional registry records omitted for brevity."
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
    def _is_identity_or_party_gap_text(blob: str) -> bool:
        """Avoid suppressing genuinely distinct standing/party-identity concerns."""
        markers = (
            "standing",
            "beneficiary",
            "individual vs",
            "entity",
            "investor identity",
            "correct plaintiff",
            "party mismatch",
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
        matched: List[str] = []
        seen = set()

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
    ) -> GapAnalysisResult:
        """Suppress false missing-executed gaps when signed evidence is authoritative."""
        signed_docs = [
            item
            for item in (signature_evidence or [])
            if (item.get("status") or "").lower() == "signed"
        ]
        if not signed_docs:
            return result

        missing_gaps = list(result.gaps_by_category.get(GapCategory.MISSING_DOCUMENT.value, []))
        if not missing_gaps:
            return result

        kept: List[GapItem] = []
        removed: List[GapItem] = []
        matched_doc_names: List[str] = []

        for gap in missing_gaps:
            if not self._is_execution_gap(gap):
                kept.append(gap)
                continue

            gap_blob = " ".join(
                [
                    gap.title or "",
                    gap.description or "",
                    gap.impact_on_case or "",
                    " ".join(gap.recommendations or []),
                ]
            )
            if self._is_identity_or_party_gap_text(gap_blob):
                kept.append(gap)
                continue

            matched = self._find_matching_signed_docs(gap, signed_docs)
            if matched:
                removed.append(gap)
                matched_doc_names.extend(matched)
            else:
                kept.append(gap)

        if not removed:
            return result

        result.gaps_by_category[GapCategory.MISSING_DOCUMENT.value] = kept

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

        note = (
            f"Execution metadata confirms signed documents ({docs_preview}); "
            f"removed {len(removed)} false missing-executed gap(s)."
        )
        notes = list(getattr(result, "reconciliation_notes", []) or [])
        if note not in notes:
            notes.append(note)
        result.reconciliation_notes = notes

        summary = (result.attorney_summary or "").strip()
        if note not in summary:
            result.attorney_summary = f"{summary} {note}".strip() if summary else note

        logger.info(
            "[GAP_SERVICE] Suppressed %s execution gap(s) using signature evidence",
            len(removed),
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
    "category": "<GapCategory enum value>",
    "severity": "<GapSeverity enum value>",
    "title": "<brief description>",
    "description": "<detailed explanation>",
    "affected_issue": "<legal issue name or null>",
    "related_documents": [<document names>],
    "recommendations": [<action items>],
    "impact_on_case": "<explanation>"
}}

Begin your analysis now.
"""

        return prompt

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
