from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

import markdown2
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from legal_portal.core.data_models import ProcessingError
from legal_portal.services.letter_strategy_service import LetterStrategyService
from legal_portal.utils.diagnostic_logger import DiagnosticLogger
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.markdown_utils import clean_markdown_response
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


class JsonProcessingService:
    """Handles interaction with OpenAI for processing structured data."""

    def __init__(self, client: OpenAIClient, config: dict):
        """Initialize the service.

        Args:
        ----
            client: An instance of the custom OpenAIClient wrapper.
            config: Configuration dictionary.

        """
        self.client = client
        self.config = config

    def _get_letter_generation_model(self, fallback: str = "gpt-5.2") -> str:
        """Resolve preferred model for letter generation."""
        try:
            return self.client.get_preferred_model("letter_generation", fallback)
        except Exception:
            return fallback

    async def repair_letter_constraints(
        self,
        draft_markdown: str,
        violations: List[Dict[str, Any]],
        *,
        mode: str = "default",
        model: str = "gpt-5-mini",
        critic_feedback: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Apply constrained repair only for listed quality violations."""
        if not draft_markdown.strip():
            return draft_markdown

        critic_sections = []
        if critic_feedback and isinstance(critic_feedback, dict):
            failed_sections = critic_feedback.get("failed_sections") or []
            if isinstance(failed_sections, list):
                critic_sections = [item for item in failed_sections if isinstance(item, dict)]

        if not violations and not critic_sections:
            return draft_markdown

        violation_lines: List[str] = []
        for idx, violation in enumerate(violations[:20], start=1):
            rule = str(violation.get("rule", "unknown"))
            message = str(violation.get("message", ""))
            severity = str(violation.get("severity", "warning"))
            violation_lines.append(f"{idx}. [{severity}] {rule}: {message}")

        critic_lines: List[str] = []
        for idx, section in enumerate(critic_sections[:12], start=1):
            section_name = str(section.get("section_name", "unknown section"))
            issue_type = str(section.get("issue_type", "quality_issue"))
            required_fix = str(section.get("required_fix", ""))
            do_not_change = str(section.get("do_not_change", "All other sections and facts"))
            priority = str(section.get("priority", "medium"))
            critic_lines.append(
                (
                    f"{idx}. [{priority}] {section_name} ({issue_type})\n"
                    f"   required_fix: {required_fix}\n"
                    f"   do_not_change: {do_not_change}"
                )
            )

        prompt = (
            "Revise the letter using ONLY the required fixes below.\n"
            "Do not introduce new facts, dates, names, or legal claims.\n"
            "Do not remove valid factual content.\n"
            "Do not rewrite the full document.\n"
            "Preserve unchanged sections verbatim as much as possible.\n"
            f"Mode: {mode}\n\n"
            "Violations to fix:\n"
            f"{chr(10).join(violation_lines) if violation_lines else 'None'}\n\n"
            "Critic section fixes:\n"
            f"{chr(10).join(critic_lines) if critic_lines else 'None'}\n\n"
            "Letter draft:\n"
            f"{draft_markdown}\n"
        )

        loop = asyncio.get_running_loop()
        repaired = await loop.run_in_executor(
            None,
            self._make_openai_request_responses_api,
            prompt,
            model,
            "low",
            "low",
            4000,
            (
                "You are a legal writing editor. Fix only the listed violations. "
                "Return the revised letter in markdown with no commentary."
            ),
        )

        return (repaired or "").strip() or draft_markdown

    async def build_findings_strategy(
        self,
        *,
        fact_matrix,
        deep_analysis,
        gap_analysis=None,
        timeout_seconds: int = 15,
        model: str = "gpt-5-mini",
        allow_model: bool = True,
    ) -> Dict[str, Any]:
        """Build strategy object for findings drafting."""
        strategy_service = LetterStrategyService(self.client)
        return await strategy_service.build_findings_strategy(
            fact_matrix=fact_matrix,
            deep_analysis=deep_analysis,
            gap_analysis=gap_analysis,
            allow_model=allow_model,
            timeout_seconds=timeout_seconds,
            model=model,
        )

    async def run_quality_critic(
        self,
        *,
        draft_markdown: str,
        letter_type: str,
        lint_violations: List[Dict[str, Any]],
        quality_report_v2: Optional[Dict[str, Any]] = None,
        model: str = "gpt-5-mini",
        timeout_seconds: int = 20,
    ) -> Dict[str, Any]:
        """Run section-level quality critic and return machine-readable fixes."""
        if not draft_markdown.strip():
            return {"failed_sections": []}

        prompt_name = (
            "demand_quality_critic_prompt.txt"
            if letter_type == "demand"
            else "findings_quality_critic_prompt.txt"
        )
        try:
            template = self._load_prompt_asset(prompt_name)
        except Exception as exc:
            logger.warning("Critic prompt missing (%s): %s", prompt_name, exc)
            return {"failed_sections": []}

        replacements = {
            "lint_violations_json": json.dumps(lint_violations or [], default=str, indent=2),
            "quality_v2_json": json.dumps(quality_report_v2 or {}, default=str, indent=2),
            "draft_markdown": draft_markdown,
        }
        prompt = template
        for key, value in replacements.items():
            prompt = prompt.replace(f"{{{key}}}", value)

        loop = asyncio.get_running_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                self._make_openai_request_responses_api,
                prompt,
                model,
                "low",
                "low",
                1800,
                (
                    "You are a legal writing quality critic. Return valid JSON only with failed sections "
                    "and minimal required fixes."
                ),
            ),
            timeout=max(1, int(timeout_seconds)),
        )

        parsed = self._parse_json_block(response or "")
        if not parsed or not isinstance(parsed, dict):
            return {"failed_sections": []}
        failed_sections = parsed.get("failed_sections")
        if not isinstance(failed_sections, list):
            return {"failed_sections": []}
        parsed["failed_sections"] = [item for item in failed_sections if isinstance(item, dict)]
        return parsed

    def _load_prompt_asset(self, file_name: str) -> str:
        """Load prompt template from the prompts directory."""
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", file_name)
        with open(prompt_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _parse_json_block(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON that may be wrapped in markdown fences."""
        payload = (text or "").strip()
        if payload.startswith("```"):
            payload = re.sub(r"^```(?:json)?\s*", "", payload)
            payload = re.sub(r"\s*```$", "", payload).strip()
        try:
            parsed = json.loads(payload)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    async def process_documents_to_json(self, prompt: str) -> Tuple[Optional[str], List[ProcessingError]]:
        """Process a prompt to get a JSON response from OpenAI asynchronously.

        Args:
        ----
            prompt: The prompt to send to the OpenAI API.

        Returns:
        -------
            A tuple containing the JSON response string and a list of any processing errors.

        """
        try:
            model = self.client.get_preferred_model("document_analysis", "gpt-5.2")
            max_output_tokens = int(self.config.get("openai_max_tokens", 12000)) if isinstance(self.config, dict) else 12000

            response_content = await asyncio.to_thread(
                self._make_openai_request_responses_api,
                prompt=prompt,
                model=model,
                reasoning_effort="minimal",
                verbosity="low",
                max_output_tokens=max_output_tokens,
                instructions=(
                    "You are a precise legal document analyst. "
                    "Return valid JSON only with no markdown, code fences, or explanatory text."
                ),
            )

            if response_content:
                # Successfully received content, return it with no errors
                return response_content, []
            else:
                # OpenAI returned an empty response
                error_message = "OpenAI returned an empty or null response."
                logger.error(error_message)
                error = ProcessingError(
                    source="JsonProcessingService",
                    error_type="APIError",
                    error_message=error_message,
                )
                return None, [error]

        except Exception as e:
            logger.exception(f"An unexpected error occurred in process_documents_to_json: {e}")
            error = ProcessingError(
                source="JsonProcessingService",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return None, [error]

    JURISDICTION_CONFIG = {
        "Florida": {
            "name": "Florida",
            "name_upper": "FLORIDA",
            "statute_example": "Fla. Stat. § 718.116",
            "statute_citation_prefix": "Florida Statute §",
            "statute_citation_short_prefix": "Fla. Stat. §",
            "guidance_file": "florida_guidance.md",
        },
        "New Mexico": {
            "name": "New Mexico",
            "name_upper": "NEW MEXICO",
            "statute_example": "N.M. Stat. Ann. § 57-12-2",
            "statute_citation_prefix": "N.M. Stat. Ann. §",
            "statute_citation_short_prefix": "NMSA 1978 §",
            "guidance_file": "new_mexico_guidance.md",
        },
    }

    _DOCUMENT_INSTRUMENT_HINT_PATTERNS = [
        ("subscription agreement", re.compile(r"\bsubscription\s+agreement\b", re.IGNORECASE)),
        ("operating agreement", re.compile(r"\boperating\s+agreement\b", re.IGNORECASE)),
        ("promissory note", re.compile(r"\bpromissory\s+note\b", re.IGNORECASE)),
        ("membership certificate", re.compile(r"\bmembership\s+certificate\b", re.IGNORECASE)),
        ("side letter", re.compile(r"\bside\s+letter\b", re.IGNORECASE)),
        ("investment agreement", re.compile(r"\binvestment\s+agreement\b", re.IGNORECASE)),
        ("purchase agreement", re.compile(r"\b(?:unit\s+)?purchase\s+agreement\b", re.IGNORECASE)),
        ("loan agreement", re.compile(r"\bloan\s+agreement\b", re.IGNORECASE)),
        ("financing agreement", re.compile(r"\bfinancing\s+agreement\b", re.IGNORECASE)),
        ("text messages", re.compile(r"\btext\s+messages?\b", re.IGNORECASE)),
        ("emails", re.compile(r"\bemails?\b", re.IGNORECASE)),
    ]
    _DOCUMENT_MATCH_STOPWORDS = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "missing",
        "document",
        "documents",
        "file",
        "files",
        "copy",
        "final",
        "draft",
        "provided",
        "provide",
        "agreement",
        "contract",
        "executed",
        "signed",
        "signature",
        "pdf",
        "doc",
        "docx",
        "txt",
        "eml",
    }
    _MAX_RAW_DOCS_FOR_PROMPT = 12
    _MAX_RAW_DOC_CHARS_PER_DOC = 6000
    _MAX_RAW_DOC_TOTAL_CHARS = 50000
    _MAX_FINDINGS_PROMPT_CHARS = 220000

    @staticmethod
    def _gap_get(gap: Any, field: str, default: str = "") -> str:
        """Read fields from GapItem-like objects or dictionaries."""
        if isinstance(gap, dict):
            value = gap.get(field, default)
        else:
            value = getattr(gap, field, default)
        return value if isinstance(value, str) else str(value or default)

    @staticmethod
    def _normalize_doc_name(value: str) -> str:
        """Normalize file names/titles for rough matching."""
        text = (value or "").lower().strip()
        text = re.sub(r"\.[a-z0-9]{1,8}$", "", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        """Trim long strings for prompt-friendly register lines."""
        text = (value or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + "..."

    def _extract_document_hints(self, value: str) -> Set[str]:
        """Extract known instrument/message hints from text."""
        hints: Set[str] = set()
        text = re.sub(r"[_\-]+", " ", (value or ""))
        for label, pattern in self._DOCUMENT_INSTRUMENT_HINT_PATTERNS:
            if pattern.search(text):
                hints.add(label)
        return hints

    def _tokenize_for_doc_match(self, value: str) -> Set[str]:
        """Tokenize text for conservative present-document matching."""
        normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
        return {
            token
            for token in normalized.split()
            if len(token) >= 3 and token not in self._DOCUMENT_MATCH_STOPWORDS
        }

    def _infer_document_role(self, name: str, doc_type: str, narrative: str) -> str:
        """Infer a case role for a document using generic lexical signals."""
        blob = " ".join([name or "", doc_type or "", narrative or ""]).lower()
        role_patterns = [
            ("deal terms and investor rights", r"\b(subscription|purchase|investment|promissory|note|memo\s+terms|financing)\b"),
            ("entity governance and control", r"\b(operating\s+agreement|articles|organization|bylaws|member|manager)\b"),
            ("communications and representations", r"\b(email|correspondence|update|message|communication|clio\s+note)\b"),
            ("payment and damages evidence", r"\b(payment|wire|receipt|down\s+payment|bank|invoice|amount)\b"),
            ("financial performance evidence", r"\b(p&l|profit|loss|financial|statement|unaudited)\b"),
            ("public-facing marketing or offering", r"\b(crowdfunding|listing|offering|investor\s+packet|brochure)\b"),
            ("regulatory or entity records", r"\b(secretary\s+of\s+state|business\s+search|official|filing)\b"),
            ("visual evidence", r"\b(jpeg|jpg|png|image|photo|scan)\b"),
            ("client intake and background", r"\b(intake|questionnaire|client\s+form)\b"),
        ]
        for role, pattern in role_patterns:
            if re.search(pattern, blob, re.IGNORECASE):
                return role
        return "general case evidence"

    @staticmethod
    def _is_execution_or_signature_gap_text(blob: str) -> bool:
        """Detect missing-gap text that specifically asks for executed/signed versions."""
        text = (blob or "").lower()
        return any(
            term in text
            for term in (
                "executed",
                "signed",
                "signature",
                "execution copy",
                "counterpart signature",
                "not signed",
            )
        )

    def _build_document_register_context(
        self,
        fact_matrix,
        original_documents: Optional[Dict[str, str]],
        document_summaries: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, Set[str], Set[str]]:
        """Build an authoritative list of present documents for prompt grounding."""
        lines: List[str] = []
        present_names: Set[str] = set()
        present_hints: Set[str] = set()
        seen_names: Set[str] = set()

        has_header = False
        summary_map: Dict[str, Dict[str, Any]] = {}
        for entry in document_summaries or []:
            if not isinstance(entry, dict):
                continue
            doc_name = (entry.get("document_name") or "").strip()
            if not doc_name:
                continue
            summary_map[self._normalize_doc_name(doc_name)] = entry

        def _ensure_header() -> None:
            nonlocal has_header
            if has_header:
                return
            lines.append("--- DOCUMENT REGISTER (AUTHORITATIVE LIST OF PROVIDED FILES) ---")
            has_header = True

        for entry in document_registry or []:
            if not isinstance(entry, dict):
                continue
            doc_name = (entry.get("document_name") or "").strip()
            if not doc_name:
                continue
            normalized_name = self._normalize_doc_name(doc_name)
            if normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)
            _ensure_header()

            doc_type = (entry.get("document_type") or "Unknown").strip()
            role = (entry.get("role_in_case") or "general case evidence").strip()
            authority = (entry.get("authority_level") or "supporting_evidence").strip()
            execution = (entry.get("execution_status") or "unknown").strip()
            instrument = (entry.get("primary_instrument") or "n/a").strip()
            signature_expected = bool(entry.get("signature_expected"))
            signature_review = bool(entry.get("signature_review_recommended"))
            significance = (
                entry.get("legal_significance")
                or entry.get("relevance_to_case")
                or entry.get("authority_reason")
                or "Supports core case narrative."
            )
            significance = self._truncate(str(significance), 150)
            lines.append(
                f"- {doc_name} | type={doc_type} | role={role} | "
                f"authority={authority} | execution={execution} | instrument={instrument} | "
                f"signature_expected={signature_expected} | signature_review={signature_review} | "
                f"case_place={significance}"
            )

            present_names.add(normalized_name)
            present_hints.update(self._extract_document_hints(doc_name))
            raw_hints = entry.get("instrument_hints")
            if isinstance(raw_hints, list):
                for hint in raw_hints:
                    present_hints.update(self._extract_document_hints(str(hint)))
            elif raw_hints:
                present_hints.update(self._extract_document_hints(str(raw_hints)))
            present_hints.update(self._extract_document_hints(significance))

        key_documents = list(getattr(fact_matrix, "key_documents", []) or [])
        for doc in key_documents:
            doc_name = (getattr(doc, "document_name", "") or "").strip()
            if not doc_name:
                continue
            normalized_name = self._normalize_doc_name(doc_name)
            if normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)
            _ensure_header()

            summary_entry = summary_map.get(normalized_name, {})
            doc_type = (
                (summary_entry.get("document_type") if isinstance(summary_entry, dict) else "")
                or (getattr(doc, "document_type", "") or "Unknown")
            ).strip()
            significance = (
                (summary_entry.get("legal_significance") if isinstance(summary_entry, dict) else "")
                or (summary_entry.get("relevance_to_case") if isinstance(summary_entry, dict) else "")
                or (getattr(doc, "significance", "") or "Supports core case narrative.")
            ).strip()
            role = self._infer_document_role(doc_name, doc_type, significance)
            lines.append(
                f"- {doc_name} | type={doc_type} | role={role} | case_place={self._truncate(significance, 150)}"
            )
            present_names.add(normalized_name)
            present_hints.update(self._extract_document_hints(doc_name))
            present_hints.update(self._extract_document_hints(significance))

        for normalized_name, summary_entry in summary_map.items():
            if normalized_name in seen_names:
                continue
            doc_name = (summary_entry.get("document_name") or "").strip()
            if not doc_name:
                continue
            seen_names.add(normalized_name)
            _ensure_header()

            doc_type = (summary_entry.get("document_type") or "Unknown").strip()
            significance = (
                summary_entry.get("legal_significance")
                or summary_entry.get("relevance_to_case")
                or summary_entry.get("executive_summary")
                or "Supports core case narrative."
            )
            significance = self._truncate(significance, 150)
            role = self._infer_document_role(doc_name, doc_type, significance)
            lines.append(
                f"- {doc_name} | type={doc_type} | role={role} | case_place={significance}"
            )
            present_names.add(normalized_name)
            present_hints.update(self._extract_document_hints(doc_name))
            present_hints.update(self._extract_document_hints(significance))

        if original_documents:
            _ensure_header()
            for filename, content in original_documents.items():
                normalized_name = self._normalize_doc_name(filename)
                if not normalized_name or normalized_name in seen_names:
                    continue
                seen_names.add(normalized_name)
                role = self._infer_document_role(filename, "Case Document", "")
                lines.append(
                    f"- {filename} | type=Case Document | role={role} | case_place=Primary source text included for review."
                )
                present_names.add(normalized_name)
                present_hints.update(self._extract_document_hints(filename))
                present_hints.update(self._extract_document_hints((content or "")[:5000]))

        if lines:
            lines.append(
                "Use the register above as authoritative proof of what is already in the case file."
            )
            lines.append(
                "Do not request a document as 'missing' when that same instrument appears in this register."
            )
            return "\n".join(lines) + "\n\n", present_names, present_hints

        return "", present_names, present_hints

    def _gap_refs_present_doc(
        self,
        gap: Any,
        present_names: Set[str],
        present_hints: Set[str],
    ) -> bool:
        """True when a missing-document gap appears to describe docs already present."""
        if isinstance(gap, dict):
            related_documents = gap.get("related_documents", [])
            recommendations = gap.get("recommendations", [])
        else:
            related_documents = getattr(gap, "related_documents", [])
            recommendations = getattr(gap, "recommendations", [])

        gap_blob = " ".join(
            [
                self._gap_get(gap, "title"),
                self._gap_get(gap, "description"),
                self._gap_get(gap, "impact_on_case"),
                " ".join(str(item) for item in (related_documents or [])),
                " ".join(str(item) for item in (recommendations or [])),
            ]
        ).lower()

        # Preserve true execution/signature gaps unless upstream reconciliation removed them.
        if self._is_execution_or_signature_gap_text(gap_blob):
            return False

        gap_hints = self._extract_document_hints(gap_blob)
        if gap_hints and gap_hints.intersection(present_hints):
            return True

        gap_tokens = self._tokenize_for_doc_match(gap_blob)
        for name in present_names:
            name_tokens = self._tokenize_for_doc_match(name)
            if not name_tokens:
                continue
            overlap = gap_tokens & name_tokens
            if len(overlap) >= 2:
                return True
            if len(name_tokens) == 1:
                token = next(iter(name_tokens))
                if len(token) >= 8 and token in gap_tokens:
                    return True
            if len(name) >= 18 and name in gap_blob:
                return True

        return False

    def _score_raw_document_for_prompt(self, filename: str, content: str) -> int:
        """Prioritize high-value legal instruments when prompt space is limited."""
        blob = " ".join([filename or "", (content or "")[:1500]]).lower()
        score = 0

        high_value_patterns = (
            r"\bsubscription\s+agreement\b",
            r"\boperating\s+agreement\b",
            r"\bpromissory\s+note\b",
            r"\bmemo\s+terms\b",
            r"\bterms\s+for\s+financing\b",
            r"\binvestment\s+agreement\b",
            r"\bwire\b",
            r"\bpayment\b",
            r"\breceipt\b",
        )
        medium_value_patterns = (
            r"\bcorrespondence\b",
            r"\bemail\b",
            r"\bupdate\b",
            r"\bintake\b",
            r"\binvestor\s+packet\b",
            r"\bcrowdfunding\b",
            r"\bp&l\b",
            r"\bprofit\b",
            r"\bloss\b",
        )

        for pattern in high_value_patterns:
            if re.search(pattern, blob, re.IGNORECASE):
                score += 3
        for pattern in medium_value_patterns:
            if re.search(pattern, blob, re.IGNORECASE):
                score += 1
        return score

    def _select_raw_documents_for_prompt(
        self,
        original_documents: Dict[str, str],
    ) -> Tuple[List[Tuple[str, str, int, int]], int]:
        """Select a bounded set of raw documents for prompt grounding."""
        ranked: List[Tuple[int, int, str, str]] = []
        for index, (filename, content) in enumerate(original_documents.items()):
            text = content or ""
            ranked.append(
                (
                    self._score_raw_document_for_prompt(filename, text),
                    index,
                    filename,
                    text,
                )
            )

        ranked.sort(key=lambda row: (-row[0], row[1]))

        selected: List[Tuple[str, str, int, int]] = []
        total_chars = 0

        for _score, _index, filename, text in ranked:
            if len(selected) >= self._MAX_RAW_DOCS_FOR_PROMPT:
                break

            full_len = len(text)
            clipped = text[: self._MAX_RAW_DOC_CHARS_PER_DOC]
            clip_len = len(clipped)

            if clip_len == 0:
                continue

            projected_total = total_chars + clip_len
            if projected_total > self._MAX_RAW_DOC_TOTAL_CHARS:
                if not selected:
                    clip_len = min(self._MAX_RAW_DOC_TOTAL_CHARS, clip_len)
                    clipped = clipped[:clip_len]
                    projected_total = clip_len
                else:
                    continue

            selected.append((filename, clipped, full_len, clip_len))
            total_chars = projected_total

        omitted_count = max(0, len(original_documents) - len(selected))
        return selected, omitted_count

    def _build_adaptive_findings_prompt(
        self,
        *,
        intake_content: str,
        fact_matrix,
        legal_analysis,
        structure_guidance,
        verified_statutes: list,
        quality_context: str,
        statute_context: str,
        attorney_name: str,
        firm_name: str,
        contact_phone: str,
        contact_email: str,
        clio_matter_context: str,
        qa_context: str,
        jurisdiction: str,
        original_documents: Optional[Dict[str, str]],
        document_summaries_for_context: Optional[List[Dict[str, Any]]],
        document_registry: Optional[List[Dict[str, Any]]],
        gap_analysis,
        strategy_object: Optional[Dict[str, Any]] = None,
        prefer_compact: bool = False,
    ) -> Tuple[str, bool]:
        """Build adaptive findings prompt and indicate whether raw docs are included."""
        include_raw_documents = bool(original_documents) and not prefer_compact
        structured_context = self._format_multi_stage_context(
            fact_matrix,
            legal_analysis,
            structure_guidance,
            verified_statutes,
            original_documents=original_documents,
            document_summaries=document_summaries_for_context,
            document_registry=document_registry,
            gap_analysis=gap_analysis,
            include_raw_documents=include_raw_documents,
        )

        prompt = self._build_findings_prompt(
            jurisdiction=jurisdiction,
            intake_content=intake_content,
            document_summaries=structured_context,
            quality_context=quality_context,
            statute_context=statute_context,
            attorney_name=attorney_name,
            firm_name=firm_name,
            contact_phone=contact_phone,
            contact_email=contact_email,
            clio_matter_context=clio_matter_context,
            qa_context=qa_context,
            structure_guidance=structure_guidance,
            strategy_object=strategy_object,
        )

        if include_raw_documents and len(prompt) > self._MAX_FINDINGS_PROMPT_CHARS:
            logger.warning(
                "Findings prompt exceeds size guardrail (%s chars); retrying without raw document text",
                len(prompt),
            )
            structured_context = self._format_multi_stage_context(
                fact_matrix,
                legal_analysis,
                structure_guidance,
                verified_statutes,
                original_documents=original_documents,
                document_summaries=document_summaries_for_context,
                document_registry=document_registry,
                gap_analysis=gap_analysis,
                include_raw_documents=False,
            )
            prompt = self._build_findings_prompt(
                jurisdiction=jurisdiction,
                intake_content=intake_content,
                document_summaries=structured_context,
                quality_context=quality_context,
                statute_context=statute_context,
                attorney_name=attorney_name,
                firm_name=firm_name,
                contact_phone=contact_phone,
                contact_email=contact_email,
                clio_matter_context=clio_matter_context,
                qa_context=qa_context,
                structure_guidance=structure_guidance,
                strategy_object=strategy_object,
            )
            include_raw_documents = False

        return prompt, include_raw_documents

    def _load_prompt_template(self, jurisdiction: str = "Florida") -> str:
        """Load the prompt template from a file and inject jurisdiction-specific guidance."""
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "findings_letter_prompt.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()

            # Dynamically load jurisdiction-specific guidance
            guidance_file_name = self.JURISDICTION_CONFIG.get(jurisdiction, {}).get("guidance_file")
            jurisdiction_specific_guidance = ""
            if guidance_file_name:
                guidance_path = os.path.join(
                    os.path.dirname(__file__), "..", "prompts", "jurisdiction_guidance", guidance_file_name
                )
                if os.path.exists(guidance_path):
                    with open(guidance_path, "r", encoding="utf-8") as f_guidance:
                        jurisdiction_specific_guidance = f_guidance.read()
                else:
                    logger.warning(f"Jurisdiction-specific guidance file not found: {guidance_path}")
            else:
                logger.warning(f"No guidance file configured for jurisdiction: {jurisdiction}")

            # Get jurisdiction-specific citation prefixes for prompt formatting
            juris_config = self.JURISDICTION_CONFIG.get(jurisdiction, self.JURISDICTION_CONFIG["Florida"])
            jurisdiction_name = juris_config["name"]
            jurisdiction_name_upper = juris_config["name_upper"]
            statute_citation_prefix = juris_config["statute_citation_prefix"]
            statute_citation_short_prefix = juris_config["statute_citation_short_prefix"]
            statute_example = juris_config["statute_example"]

            # Format the template with dynamic values
            # We use double braces for placeholders that should remain for the second formatting pass
            return template.format(
                jurisdiction=jurisdiction,
                jurisdiction_name=jurisdiction_name,
                jurisdiction_name_upper=jurisdiction_name_upper,
                jurisdiction_statute_citation_prefix=statute_citation_prefix,
                jurisdiction_statute_citation_short_prefix=statute_citation_short_prefix,
                jurisdiction_statute_example=statute_example,
                jurisdiction_specific_guidance=jurisdiction_specific_guidance,
                # Other placeholders will be filled by the calling function
                qa_context="{qa_context}",
                intake_data="{intake_data}",
                document_summaries="{document_summaries}",
                quality_context="{quality_context}",
                statute_context="{statute_context}",
                attorney_name="{attorney_name}",
                attorney_title="{attorney_title}",
                firm_name="{firm_name}",
                contact_phone="{contact_phone}",
                contact_email="{contact_email}",
                clio_matter_context="{clio_matter_context}",
            )
        except FileNotFoundError as e:
            logger.error(f"Prompt template file not found at: {prompt_path}")
            raise ValueError(f"Findings email prompt template not found at {prompt_path}") from e

    def generate_html_letter(
        self, intake_data: str, document_summaries: str, jurisdiction: str = "Florida"
    ) -> str:
        """Generate HTML letter content using the single master prompt."""
        logger.info(f"Starting HTML letter generation for {jurisdiction} using master prompt")
        try:
            prompt_template = self._load_prompt_template(jurisdiction=jurisdiction)

            formatted_prompt = prompt_template.format(
                intake_data=intake_data,
                document_summaries=document_summaries,
                # Provide empty values for other placeholders to avoid KeyError
                qa_context="",
                quality_context="",
                statute_context="",
                attorney_name="Attorney",
                attorney_title="Partner",
                firm_name="",
                contact_phone="",
                contact_email="",
                clio_matter_context="",
            )

            logger.info(f"Making OpenAI request with master prompt for {jurisdiction} using gpt-5.2.")
            markdown_response = self._make_openai_request_responses_api(
                formatted_prompt,
                model="gpt-5.2",
                reasoning_effort="low",
                verbosity="high"
            )

            if not markdown_response or not markdown_response.strip():
                error_msg = "OpenAI returned empty response for Markdown generation"
                logger.error(error_msg)
                raise ValueError(error_msg)

            logger.info("Converting Markdown response to HTML")
            html_content = self._convert_markdown_to_html(markdown_response)

            logger.info(
                "Successfully generated HTML letter",
                extra={"html_length": len(html_content)},
            )
            return html_content

        except Exception as e:
            logger.exception("Unexpected error in HTML letter generation")
            raise e

    def _format_confirmed_qa_context(self, confirmed_qa_pairs: Optional[list]) -> Tuple[str, int]:
        """Format confirmed intake Q&A pairs for prompt insertion."""
        if not confirmed_qa_pairs:
            return "No user-confirmed Q&A pairs available.", 0

        if isinstance(confirmed_qa_pairs, str):
            cleaned_context = confirmed_qa_pairs.strip()
            if cleaned_context:
                return cleaned_context, 0
            return "No user-confirmed Q&A pairs available.", 0

        if not isinstance(confirmed_qa_pairs, list):
            return str(confirmed_qa_pairs), 0

        formatted_pairs = []
        for i, qa in enumerate(confirmed_qa_pairs, 1):
            if isinstance(qa, dict):
                question = qa.get("question", "N/A")
                answer = qa.get("answer", "N/A")
            else:
                question = str(qa)
                answer = "N/A"
            formatted_pairs.append(f"{i}. Q: {question}\n   A: {answer}")

        if not formatted_pairs:
            return "No user-confirmed Q&A pairs available.", 0

        qa_context = "USER-CONFIRMED INTAKE QUESTIONS & ANSWERS:\n\n"
        qa_context += "\n\n".join(formatted_pairs)
        qa_context += "\n\n"
        return qa_context, len(formatted_pairs)

    def _resolve_attorney_and_firm_names(
        self,
        intake_content: str,
        attorney_name: Optional[str],
        firm_name: Optional[str],
    ) -> Tuple[str, str]:
        """Resolve attorney and firm names from explicit args or intake content."""
        resolved_attorney_name = attorney_name
        if not resolved_attorney_name:
            attorney_match = re.search(
                r'"attorney_name":\s*"([^"]+)"',
                intake_content or "",
                re.IGNORECASE,
            )
            if not attorney_match:
                attorney_match = re.search(r'"attorneyName":\s*"([^"]+)"', intake_content or "")
            resolved_attorney_name = attorney_match.group(1) if attorney_match else "Senior Partner"

        resolved_firm_name = firm_name
        if not resolved_firm_name:
            firm_match = re.search(r'"firm_name":\s*"([^"]+)"', intake_content or "", re.IGNORECASE)
            resolved_firm_name = firm_match.group(1) if firm_match else ""

        return resolved_attorney_name, resolved_firm_name

    def _resolve_contact_details(
        self,
        jurisdiction: str,
        contact_phone: Optional[str],
        contact_email: Optional[str],
    ) -> Tuple[str, str]:
        """Resolve contact phone/email values with jurisdiction-specific defaults."""
        default_phone = "(727) 275-9575" if jurisdiction == "Florida" else "(505) 555-0199"
        resolved_contact_phone = contact_phone if contact_phone else default_phone
        resolved_contact_email = contact_email if contact_email else ""
        return resolved_contact_phone, resolved_contact_email

    def _build_verified_statute_context(self, verified_statutes: list, jurisdiction: str) -> str:
        """Build prompt context for verified statutes from the legal corpus."""
        if not verified_statutes:
            return ""

        statute_prefix = "FLORIDA" if jurisdiction == "Florida" else "NEW MEXICO"
        statute_context = f"\n\nVERIFIED {statute_prefix} STATUTES:\n\n"
        for statute in verified_statutes:
            citation = statute.get("citation", "Unknown Citation")
            title = statute.get("title", "")
            summary = statute.get("summary", "")
            relevance = statute.get("relevance_reason", statute.get("relevance", ""))

            statute_context += f"{citation}: {title}\n"
            statute_context += f"Summary: {summary}\n"
            if relevance:
                statute_context += f"Relevance: {relevance}\n"
            statute_context += "\n"

        return statute_context

    def _build_findings_prompt(
        self,
        jurisdiction: str,
        intake_content: str,
        document_summaries: str,
        quality_context: str,
        statute_context: str,
        attorney_name: str,
        firm_name: str,
        contact_phone: str,
        contact_email: str,
        clio_matter_context: str,
        qa_context: str,
        structure_guidance=None,  # LetterStructure for adaptive generation
        strategy_object: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the findings prompt for JSON, adaptive, and streaming generation."""
        prompt_template = self._load_prompt_template(jurisdiction=jurisdiction)
        prompt = prompt_template.format(
            qa_context=qa_context,
            intake_data=(intake_content or "")[:5000],
            document_summaries=document_summaries,
            quality_context=quality_context or "",
            statute_context=statute_context or "",
            attorney_name=attorney_name,
            attorney_title="Senior Partner",
            firm_name=firm_name or "",
            contact_phone=contact_phone,
            contact_email=contact_email,
            clio_matter_context=clio_matter_context or "",
        )

        if structure_guidance is not None:
            structure_instruction = self._create_structure_instruction(structure_guidance)
            prompt = f"{prompt}\n\n{structure_instruction}"

        prompt = f"{prompt}\n\n{self._build_balanced_client_strategy_directives(strategy_object)}"

        return prompt

    async def generate_findings_letter_from_json(
        self,
        intake_content: str,
        document_summaries_json: str,
        quality_context: str = "",
        attorney_name: str = None,
        firm_name: str = None,
        confirmed_qa_pairs: list = None,
        contact_phone: str = None,
        contact_email: str = None,
        statute_context: str = "",
        clio_matter_context: str = "",
        jurisdiction: str = "Florida",  # Added jurisdiction parameter
    ) -> str:
        """Generate findings email from structured JSON summaries.

        Args:
        ----
            intake_content: Extracted text from intake form
            document_summaries_json: JSON string of structured DocumentSummaryStructured objects
            quality_context: Formatted quality assessment results
            attorney_name: Attorney name for signature (optional, will extract from intake if not provided)
            firm_name: Firm name for signature (optional, will extract from intake if not provided)
            confirmed_qa_pairs: User-confirmed question-answer pairs from intake form review
            contact_phone: Contact phone for letter footer (optional, uses placeholder if not provided)
            contact_email: Contact email for letter footer
                (optional, uses placeholder if not provided)
            statute_context: Context about relevant statutes for the case
            clio_matter_context: Rich context from CLIO matter including timeline,
                party relationships, communication patterns
            jurisdiction: State jurisdiction (e.g., "Florida", "New Mexico")

        Returns:
        -------
            HTML letter content

        """
        logger.info(f"Generating letter for {jurisdiction} from structured JSON input")

        qa_context, qa_pair_count = self._format_confirmed_qa_context(confirmed_qa_pairs)
        if qa_pair_count > 0:
            logger.info(f"Including {qa_pair_count} user-confirmed Q&A pairs in letter generation")
        else:
            logger.info("No confirmed Q&A pairs provided for letter generation")

        attorney_name, firm_name = self._resolve_attorney_and_firm_names(
            intake_content=intake_content,
            attorney_name=attorney_name,
            firm_name=firm_name,
        )
        contact_phone, contact_email_value = self._resolve_contact_details(
            jurisdiction=jurisdiction,
            contact_phone=contact_phone,
            contact_email=contact_email,
        )

        if clio_matter_context:
            logger.info("Including CLIO matter context in dedicated prompt section")

        prompt = self._build_findings_prompt(
            jurisdiction=jurisdiction,
            intake_content=intake_content,
            document_summaries=document_summaries_json,
            quality_context=quality_context,
            statute_context=statute_context,
            attorney_name=attorney_name,
            firm_name=firm_name,
            contact_phone=contact_phone,
            contact_email=contact_email_value,
            clio_matter_context=clio_matter_context,
            qa_context=qa_context,
        )

        logger.info("Making OpenAI request for letter generation from JSON")

        loop = asyncio.get_running_loop()
        markdown_response = await loop.run_in_executor(
            None,  # Use the default thread pool executor
            self._make_openai_request_responses_api,
            prompt,
            "gpt-5.2",  # model
            "medium",  # reasoning_effort
            "high",  # verbosity
            12000,  # max_output_tokens
            (  # instructions
                "You are a senior legal writing assistant helping to draft professional "
                "client findings emails. Follow the template structure exactly and "
                "provide comprehensive, well-reasoned legal analysis."
            ),
        )

        if not markdown_response or not markdown_response.strip():
            raise ValueError("OpenAI returned empty response for letter generation")

        # Convert to HTML
        html_content = self._convert_markdown_to_html(markdown_response)

        logger.info("Successfully generated letter from JSON", extra={"html_length": len(html_content)})

        return html_content

    async def generate_findings_letter_adaptive(
        self,
        intake_content: str,
        fact_matrix,  # FactMatrix
        legal_analysis,  # DeepAnalysis
        structure_guidance,  # LetterStructure
        verified_statutes: list,
        attorney_name: str = None,
        firm_name: str = None,
        confirmed_qa_pairs: list = None,
        contact_phone: str = None,
        contact_email: str = None,
        quality_context: str = "",
        clio_matter_context: str = "",
        jurisdiction: str = "Florida",  # Added jurisdiction parameter
        diag_logger: Optional[DiagnosticLogger] = None,
        original_documents: Optional[Dict[str, str]] = None,  # Explicit raw content
        document_summaries_for_context: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        strategy_object: Optional[Dict[str, Any]] = None,
        gap_analysis=None,  # GapAnalysisResult for guardrails
    ) -> str:
        """Generate findings email using multi-stage analysis results.

        This method uses structured analysis from MultiStageAnalyzer to generate
        an attorney-quality letter with adaptive structure based on case complexity.

        Args:
        ----
            intake_content: Extracted text from intake form
            fact_matrix: FactMatrix with structured facts from Stage 1
            legal_analysis: DeepAnalysis with comprehensive analysis from Stage 3
            structure_guidance: LetterStructure determining format from Stage 4
            verified_statutes: List of verified statutes from corpus
            attorney_name: Attorney name for signature
            firm_name: Firm name for signature
            confirmed_qa_pairs: User-confirmed Q&A pairs
            contact_phone: Contact phone number
            contact_email: Contact email
            quality_context: Quality assessment context
            clio_matter_context: CLIO matter context
            jurisdiction: State jurisdiction (e.g., "Florida", "New Mexico")
            diag_logger: Optional diagnostic logger for stage-by-stage artifacts
            original_documents: Optional raw source document content for precision/citations
            gap_analysis: Optional gap analysis result used for anti-hallucination guardrails

        Returns:
        -------
            HTML letter content

        """
        # All cases now use natural_flow format - no structure override needed
        # The analyzer always returns natural_flow regardless of complexity
        num_issues = len(legal_analysis.issue_analyses)
        logger.info(
            f"Generating natural flow letter for {jurisdiction} with {num_issues} issues",
            extra={"structure": "natural_flow", "issues": num_issues, "jurisdiction": jurisdiction},
        )

        qa_context, qa_pair_count = self._format_confirmed_qa_context(confirmed_qa_pairs)
        if qa_pair_count > 0:
            logger.info(f"Including {qa_pair_count} confirmed Q&A pairs")

        attorney_name, firm_name = self._resolve_attorney_and_firm_names(
            intake_content=intake_content,
            attorney_name=attorney_name,
            firm_name=firm_name,
        )
        contact_phone, contact_email_value = self._resolve_contact_details(
            jurisdiction=jurisdiction,
            contact_phone=contact_phone,
            contact_email=contact_email,
        )

        statute_context = self._build_verified_statute_context(
            verified_statutes=verified_statutes,
            jurisdiction=jurisdiction,
        )
        prompt, prompt_includes_raw_docs = self._build_adaptive_findings_prompt(
            intake_content=intake_content,
            fact_matrix=fact_matrix,
            legal_analysis=legal_analysis,
            structure_guidance=structure_guidance,
            verified_statutes=verified_statutes,
            quality_context=quality_context,
            statute_context=statute_context,
            attorney_name=attorney_name,
            firm_name=firm_name,
            contact_phone=contact_phone,
            contact_email=contact_email_value,
            clio_matter_context=clio_matter_context,
            qa_context=qa_context,
            original_documents=original_documents,
            document_summaries_for_context=document_summaries_for_context,
            document_registry=document_registry,
            strategy_object=strategy_object,
            gap_analysis=gap_analysis,
            jurisdiction=jurisdiction,
        )

        logger.info("Making OpenAI request for adaptive letter generation")

        model = self._get_letter_generation_model("gpt-5.2")
        loop = asyncio.get_running_loop()
        markdown_response = await loop.run_in_executor(
            None,
            self._make_openai_request_responses_api,
            prompt,
            model,
            "medium",
            "high",
            12000,
            (
                "You are a senior legal writing assistant. Generate an attorney-quality "
                "findings email following the adaptive structure guidance provided."
            ),
        )

        if (not markdown_response or not markdown_response.strip()) and prompt_includes_raw_docs:
            logger.warning(
                "Adaptive findings generation returned empty response; retrying with compact context"
            )
            compact_prompt, _ = self._build_adaptive_findings_prompt(
                intake_content=intake_content,
                fact_matrix=fact_matrix,
                legal_analysis=legal_analysis,
                structure_guidance=structure_guidance,
                verified_statutes=verified_statutes,
                quality_context=quality_context,
                statute_context=statute_context,
                attorney_name=attorney_name,
                firm_name=firm_name,
                contact_phone=contact_phone,
                contact_email=contact_email_value,
                clio_matter_context=clio_matter_context,
                qa_context=qa_context,
                original_documents=original_documents,
                document_summaries_for_context=document_summaries_for_context,
                document_registry=document_registry,
                strategy_object=strategy_object,
                gap_analysis=gap_analysis,
                jurisdiction=jurisdiction,
                prefer_compact=True,
            )
            markdown_response = await loop.run_in_executor(
                None,
                self._make_openai_request_responses_api,
                compact_prompt,
                model,
                "medium",
                "high",
                12000,
                (
                    "You are a senior legal writing assistant. Generate an attorney-quality "
                    "findings email following the adaptive structure guidance provided."
                ),
            )

        if not markdown_response or not markdown_response.strip():
            raise ValueError("OpenAI returned empty response for adaptive letter generation")

        # --- FORMATTING POLISH PASS (Second AI Call) ---
        # Apply consistent formatting and layout
        logger.info("Applying formatting polish pass for consistency")
        try:
            # Try relative import first, then absolute
            try:
                from src.legal_portal.utils.letter_polish import LetterPolisher
            except ImportError:
                from legal_portal.utils.letter_polish import LetterPolisher

            polisher = LetterPolisher(self.client)
            polish_result = polisher.polish_letter(markdown_response)

            if polish_result["success"]:
                markdown_response = polish_result["polished_letter"]
                logger.info(
                    f"Formatting polish applied successfully. Changes: {len(polish_result['changes_made'])}",
                    extra={"changes": polish_result["changes_made"]},
                )
            else:
                logger.warning(
                    f"Formatting polish failed: {polish_result.get('error', 'Unknown')}. Using original."
                )
        except Exception as e:
            logger.warning(f"Formatting polish pass failed: {e}. Using original letter.")
        # --- END POLISH PASS ---

        # Convert to HTML
        html_content = self._convert_markdown_to_html(markdown_response)

        # Stage 5: Log Final Letter
        if diag_logger:
            diag_logger.log_stage("stage5_final_letter", html_content, {
                "jurisdiction": jurisdiction,
                "num_issues": num_issues,
                "attorney_name": attorney_name
            })

        logger.info(
            "Successfully generated natural flow letter",
            extra={"html_length": len(html_content), "structure": "natural_flow"},
        )

        return html_content

    async def stream_findings_letter_adaptive(
        self,
        intake_content: str,
        fact_matrix,  # FactMatrix
        legal_analysis,  # DeepAnalysis
        structure_guidance,  # LetterStructure
        verified_statutes: list,
        attorney_name: str = None,
        firm_name: str = None,
        confirmed_qa_pairs: list = None,
        contact_phone: str = None,
        contact_email: str = None,
        quality_context: str = "",
        clio_matter_context: str = "",
        jurisdiction: str = "Florida",
        original_documents: Optional[Dict[str, str]] = None,
        document_summaries_for_context: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        strategy_object: Optional[Dict[str, Any]] = None,
        gap_analysis=None,  # GapAnalysisResult for guardrails
    ) -> AsyncGenerator[str, None]:
        """Stream adaptive findings email generation.

        Note: This bypasses the formatting polish pass for real-time delivery.
        """
        qa_context, qa_pair_count = self._format_confirmed_qa_context(confirmed_qa_pairs)
        if qa_pair_count > 0:
            logger.info(f"Including {qa_pair_count} confirmed Q&A pairs in streaming generation")

        # Signature details
        attorney_name = attorney_name or "Senior Partner"
        contact_phone, contact_email_value = self._resolve_contact_details(
            jurisdiction=jurisdiction,
            contact_phone=contact_phone,
            contact_email=contact_email,
        )

        statute_context = self._build_verified_statute_context(
            verified_statutes=verified_statutes,
            jurisdiction=jurisdiction,
        )
        prompt, prompt_includes_raw_docs = self._build_adaptive_findings_prompt(
            intake_content=intake_content,
            fact_matrix=fact_matrix,
            legal_analysis=legal_analysis,
            structure_guidance=structure_guidance,
            verified_statutes=verified_statutes,
            quality_context=quality_context,
            statute_context=statute_context,
            attorney_name=attorney_name,
            firm_name=firm_name or "",
            contact_phone=contact_phone,
            contact_email=contact_email_value,
            clio_matter_context=clio_matter_context,
            qa_context=qa_context,
            original_documents=original_documents,
            document_summaries_for_context=document_summaries_for_context,
            document_registry=document_registry,
            strategy_object=strategy_object,
            gap_analysis=gap_analysis,
            jurisdiction=jurisdiction,
        )

        logger.info(f"Streaming adaptive findings email for {jurisdiction}")
        model = self._get_letter_generation_model("gpt-5.2")
        stream_started = False
        try:
            async for token in self.client.create_response_stream(
                model=model,
                instructions=(
                    "You are a senior legal writing assistant. Generate an attorney-quality "
                    "findings email following the adaptive structure guidance provided."
                ),
                input=prompt,
                reasoning_effort="low",
                verbosity="high",
            ):
                stream_started = True
                yield token
        except Exception:
            if not prompt_includes_raw_docs or stream_started:
                raise

            logger.warning(
                "Streaming findings failed before first token; retrying with compact context"
            )
            compact_prompt, _ = self._build_adaptive_findings_prompt(
                intake_content=intake_content,
                fact_matrix=fact_matrix,
                legal_analysis=legal_analysis,
                structure_guidance=structure_guidance,
                verified_statutes=verified_statutes,
                quality_context=quality_context,
                statute_context=statute_context,
                attorney_name=attorney_name,
                firm_name=firm_name or "",
                contact_phone=contact_phone,
                contact_email=contact_email_value,
                clio_matter_context=clio_matter_context,
                qa_context=qa_context,
                original_documents=original_documents,
                document_summaries_for_context=document_summaries_for_context,
                document_registry=document_registry,
                strategy_object=strategy_object,
                gap_analysis=gap_analysis,
                jurisdiction=jurisdiction,
                prefer_compact=True,
            )
            async for token in self.client.create_response_stream(
                model=model,
                instructions=(
                    "You are a senior legal writing assistant. Generate an attorney-quality "
                    "findings email following the adaptive structure guidance provided."
                ),
                input=compact_prompt,
                reasoning_effort="low",
                verbosity="high",
            ):
                yield token

    def _format_multi_stage_context(
        self, fact_matrix, legal_analysis, structure_guidance, verified_statutes,
        original_documents: Optional[Dict[str, str]] = None,
        document_summaries: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        gap_analysis=None,  # GapAnalysisResult for guardrails
        include_raw_documents: bool = True,
    ) -> str:
        """Format multi-stage analysis results for letter generation prompt."""
        import json

        context = "MULTI-STAGE ANALYSIS RESULTS:\n\n"

        # Facts
        context += "FACT MATRIX:\n"
        context += (
            f"Parties: {json.dumps([p.model_dump() for p in fact_matrix.parties], default=str, indent=2)}\n"
        )
        context += (
            f"Timeline: {json.dumps([e.model_dump() for e in fact_matrix.timeline], default=str, indent=2)}\n"
        )
        context += (
            f"Financial Data: "
            f"{json.dumps([f.model_dump() for f in fact_matrix.financial_data], default=str, indent=2)}\n\n"
        )

        register_context, present_doc_names, present_doc_hints = self._build_document_register_context(
            fact_matrix=fact_matrix,
            original_documents=original_documents,
            document_summaries=document_summaries,
            document_registry=document_registry,
        )
        if register_context:
            context += register_context

        # Original Documents (bounded to avoid prompt overrun in large case files)
        if original_documents and include_raw_documents:
            selected_docs, omitted_count = self._select_raw_documents_for_prompt(original_documents)
            if selected_docs:
                context += "--- FULL DOCUMENT CONTENT (for precision and citations) ---\n"
                for filename, clipped_content, full_len, clip_len in selected_docs:
                    context += f"\nDOCUMENT: {filename}\n"
                    context += f"{clipped_content}\n"
                    if full_len > clip_len:
                        context += (
                            f"... [truncated: showing {clip_len} of {full_len} characters]\n"
                        )
                if omitted_count > 0:
                    context += (
                        f"\n... [{omitted_count} additional document(s) omitted from full text context "
                        "to preserve model context budget]\n"
                    )
                context += "--- END DOCUMENT CONTENT ---\n\n"

        # Legal Analysis
        context += "LEGAL ANALYSIS:\n"
        for analysis in legal_analysis.issue_analyses:
            context += f"\nISSUE: {analysis.issue_name}\n"
            context += f"Legal Standard: {analysis.legal_standard}\n"
            context += f"Application: {analysis.fact_application}\n"
            context += f"Remedies: {', '.join(analysis.remedies_available)}\n"
            if analysis.procedural_requirements:
                context += f"Procedural Requirements: {analysis.procedural_requirements}\n"
            context += f"Confidence: {analysis.confidence_level}\n"

        # Overall Assessment
        context += f"\nOVERALL CASE STRENGTH: {legal_analysis.overall_case_strength}\n"
        context += f"Key Strengths: {', '.join(legal_analysis.key_strengths)}\n"
        context += f"Key Challenges: {', '.join(legal_analysis.key_challenges)}\n"

        # Case Viability Assessment
        context += "\n--- CASE VIABILITY ASSESSMENT ---\n"
        context += f"IS_VIABLE: {legal_analysis.is_viable}\n"
        context += f"RECOMMEND_DEMAND_LETTER: {legal_analysis.recommend_demand_letter}\n"
        if legal_analysis.viability_reasoning:
            context += f"VIABILITY_REASONING: {legal_analysis.viability_reasoning}\n"

        # Gap Analysis for Guardrails (if available)
        if gap_analysis:
            context += "\n--- GAP ANALYSIS (CRITICAL - READ BEFORE DRAFTING) ---\n"
            context += f"COMPLETENESS_SCORE: {gap_analysis.overall_completeness_score}/100\n"
            context += f"TOTAL_GAPS: {gap_analysis.total_gaps}\n"
            context += f"CRITICAL_GAPS: {gap_analysis.critical_count}\n"
            context += f"HIGH_SEVERITY_GAPS: {gap_analysis.high_count}\n"
            context += f"ATTORNEY_SUMMARY: {gap_analysis.attorney_summary}\n"

            # List critical and high gaps explicitly
            if gap_analysis.critical_count > 0 or gap_analysis.high_count > 0:
                context += "\n**CRITICAL/HIGH SEVERITY GAPS (MUST ADDRESS IN LETTER):**\n"
                for _category, gaps in gap_analysis.gaps_by_category.items():
                    for gap in gaps:
                        if hasattr(gap, 'severity') and gap.severity in ['critical', 'high']:
                            context += f"- [{gap.severity.upper()}] {gap.title}: {gap.description}\n"
                            context += f"  Impact: {gap.impact_on_case}\n"

            # Missing documents that affect credibility
            missing_docs = gap_analysis.gaps_by_category.get('missing_document', [])
            if missing_docs:
                actionable_missing_docs = []
                present_but_flagged = []
                for gap in missing_docs:
                    if self._gap_refs_present_doc(gap, present_doc_names, present_doc_hints):
                        present_but_flagged.append(gap)
                    else:
                        actionable_missing_docs.append(gap)

                if actionable_missing_docs:
                    context += "\n**MISSING DOCUMENTS (do not assume contents):**\n"
                    for gap in actionable_missing_docs:
                        context += f"- {self._gap_get(gap, 'title')}\n"

                if present_but_flagged:
                    context += "\n**DOCUMENTS ALREADY PRESENT (do NOT request again):**\n"
                    for gap in present_but_flagged:
                        context += f"- {self._gap_get(gap, 'title')}\n"
                    context += (
                        "These items were flagged in gap analysis but appear in the provided document register; "
                        "treat them as present unless there is a specific execution/signature deficiency.\n"
                    )

            # Unverifiable claims (prevent hallucination)
            unverifiable = gap_analysis.gaps_by_category.get('unverifiable_claim', [])
            if unverifiable:
                context += "\n**UNVERIFIABLE CLAIMS (use hedging language):**\n"
                for gap in unverifiable:
                    context += f"- {gap.title}: {gap.description}\n"

            # Factual contradictions
            contradictions = gap_analysis.gaps_by_category.get('factual_contradiction', [])
            if contradictions:
                context += "\n**FACTUAL CONTRADICTIONS (acknowledge uncertainty):**\n"
                for gap in contradictions:
                    context += f"- {gap.title}: {gap.description}\n"

        return context

    def _create_structure_instruction(self, structure_guidance) -> str:
        """Create structure instruction based on letter structure guidance."""
        instructions = "\n\nSTRUCTURE GUIDANCE:\n\n"

        # All cases now use natural flow format - no formal section headers
        instructions += """Use NATURAL FLOW format (REQUIRED):

**CRITICAL - The letter should read like professional correspondence, NOT a legal memo.**

**STRUCTURE:**
1. Warm greeting: "Good afternoon [Name]," or "Good morning [Name],"
2. Opening: Documents reviewed + property address + primary concern in plain English
3. Factual narrative: 2-3 paragraphs describing what happened (NO formal "FACTUAL SUMMARY" header)
4. Transition: "Here are the key points of our analysis:"
5. Legal points as flowing bullet paragraphs (each bullet is a complete paragraph, NO bold headers)
6. Recommendations paragraph: "Based on the above, a negotiated resolution..."
7. Protective checklist if client needs to take action (with explanations)
8. Call to action: "Please let us know if you would like us to proceed..."
9. Signature and disclaimer

**PROHIBITED:**
- Do NOT use formal section headers like "FACTUAL SUMMARY" or "RECOMMENDED ACTION"
- Do NOT use bold issue titles in bullets (like "**Implied Warranty**:")
- Do NOT use "Key Findings" intro
- Do NOT use numbered sections for legal issues (2., 3., 4.)

**REQUIRED - PLAIN LANGUAGE:**
- Every legal term must be explained in plain English
- Use "What this means for you:" or similar to explain practical impact
- Use analogies clients understand ("like a hold on your property")

**REQUIRED structure example:**
```
Good afternoon Mr. Devlin and Ms. Bell,

I hope you are doing well. I wanted to follow up with a summary of our
findings after reviewing [documents], regarding your property at [address].

As discussed, the primary concern is [plain English statement of issue].

Based on our review, we understand that [2-3 paragraphs of facts without formal headers]...

Here are the key points of our analysis:

- Under Florida law, there's a protection called an "implied warranty" -- this
means contractors are legally required to do competent work, even if your
contract doesn't say so. In your case, [application]. What this means for
you: [practical impact].

- Before you can sue a contractor in Florida, you must follow a process under
Chapter 558. Think of it as a required 'cool-down period.' [explanation].
For you, this means [practical impact].

- You received a Notice to Owner -- this is a warning that [explanation in
plain English]. Here's why this matters: [consequence chain]. This is
preventable if we act now.

Based on the above, a negotiated resolution would likely be your most
efficient path forward. [Specific recommendations with timeline].

If you decide to [action], here's what you need to do:
- [Step with explanation of why]
- [Step with explanation of why]

Please let us know if you would like us to proceed with [action], or whether
you would prefer that we first set a phone call to discuss.

Thank you,
[Signature]

[Disclaimer]
```
"""

        instructions += f"\n\nAdditional context: {structure_guidance.reasoning}\n"

        return instructions

    def _build_balanced_client_strategy_directives(self, strategy_object: Optional[Dict[str, Any]]) -> str:
        """Append late-binding drafting directives for balanced client strategy style."""
        strategy_json = json.dumps(strategy_object or {}, default=str, indent=2)
        return (
            "BALANCED CLIENT STRATEGY DIRECTIVES (LATEST - OVERRIDE EARLIER CONFLICTS):\n"
            "- Write for an intelligent client. Keep tone confident, practical, and measured.\n"
            "- Use concise paragraphs and avoid internal-lawyer phrasing.\n"
            "- Do not output explicit section labels/headings such as "
            "'Opening review', 'Facts', 'Core issue', 'Legal theories', 'Timing risk', "
            "'Strategy', or 'Action items'.\n"
            "- Use natural transition lines instead (for example: "
            "'As discussed, the primary concern is ...', 'Based on the records ...', "
            "'Here are the key points of our analysis:', 'Based on the above, we recommend ...').\n"
            "- Findings section depth targets:\n"
            "  facts summary: 120-180 words.\n"
            "  each core theory paragraph: 70-120 words.\n"
            "  recommendation strategy section: 100-150 words.\n"
            "- Follow the exact order in strategy_object.ranked_theories when presenting legal theories.\n"
            "- Keep the first two theory paragraphs focused on the highest-priority ranked theories.\n"
            "- First-use legal term micro-explainer: explain each legal term once in plain language.\n"
            "- For each major claim paragraph, include at least one evidence anchor "
            "(date, amount, source document, or communication).\n"
            "- Do not use internal labels like 'micro-explainer' or snake_case legal tokens "
            "(for example, unjust_enrichment).\n"
            "- Avoid stacking citation-style parentheticals; keep references readable in prose.\n"
            "- Include one practical client-impact sentence in each major section.\n"
            "- Avoid unsupported hard accusations and avoid overstatement.\n"
            "- Keep legal doctrine explanations brief and strategic.\n"
            "- Preserve controlled urgency without hard-coded today-date math.\n\n"
            "STRATEGY OBJECT (USE AS FACT/CLAIM MAP):\n"
            f"{strategy_json}\n"
        )

    def _convert_markdown_to_html(self, markdown_content: str) -> str:
        """Convert Markdown content to clean HTML.

        Args:
        ----
            markdown_content: Markdown text from OpenAI response

        Returns:
        -------
            Well-formatted HTML content

        """
        if not markdown_content:
            return ""

        # Clean the markdown content first - remove any code fences or extra formatting
        cleaned_markdown = self._clean_markdown_response(markdown_content)

        # Configure markdown2 with appropriate extras for legal documents
        extras = [
            "fenced-code-blocks",
            "tables",
            "break-on-newline",
            "cuddled-lists",
            "metadata",
            "smarty-pants",
        ]

        try:
            # Convert markdown to HTML
            html_content = markdown2.markdown(cleaned_markdown, extras=extras)

            # Wrap in a legal-letter container div for styling consistency
            wrapped_html = f'<div class="legal-letter">\\n{html_content}\\n</div>'

            # Ensure proper HTML structure
            if not wrapped_html.startswith("<html"):
                wrapped_html = f"<html>\\n<body>\\n{wrapped_html}\\n</body>\\n</html>"

            logger.debug(
                "Successfully converted Markdown to HTML",
                extra={
                    "markdown_length": len(cleaned_markdown),
                    "html_length": len(wrapped_html),
                    "method": "_convert_markdown_to_html",
                },
            )

            return wrapped_html

        except Exception as e:
            logger.error(
                "Failed to convert Markdown to HTML",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "markdown_preview": cleaned_markdown[:200] if cleaned_markdown else None,
                    "method": "_convert_markdown_to_html",
                },
            )
            # Return a fallback HTML structure if conversion fails
            return "<html><body><p>Error converting document to HTML.</p></body></html>"

    def _clean_markdown_response(self, response_text: str) -> str:
        """Clean OpenAI response to extract valid Markdown.

        Args:
        ----
            response_text: Raw OpenAI response

        Returns:
        -------
            Cleaned Markdown content

        """
        return clean_markdown_response(response_text)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type(
            (
                RateLimitError,
                APIError,
                APITimeoutError,
                APIConnectionError,
                InternalServerError,
            )
        ),
    )
    def _make_openai_request(
        self,
        prompt: str,
        model: Optional[str] = "gpt-5.2",
        temperature: float = 0.3,
        max_tokens: int = 12000,
        system_message: str = None,
    ) -> Optional[str]:
        """Make OpenAI API request with comprehensive error handling (legacy Chat Completions API)."""
        # Default system message for JSON output (document analysis)
        if system_message is None:
            system_message = "You are a helpful assistant designed to output JSON."

        logger.info(
            "Making OpenAI request",
            extra={
                "method": "_make_openai_request",
                "hypothesis_id": "openai_api_failure",
                "model": model,
                "prompt_length": len(prompt),
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

        try:
            response_dict = self.client.create_chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response_dict["content"]
        except Exception as e:
            logger.exception(f"An error occurred during the OpenAI request: {e}")
            # Depending on desired behavior, you might want to return None or re-raise
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type(
            (
                RateLimitError,
                APIError,
                APITimeoutError,
                APIConnectionError,
                InternalServerError,
            )
        ),
    )
    def _make_openai_request_responses_api(
        self,
        prompt: str,
        model: Optional[str] = "gpt-5.2",
        reasoning_effort: Optional[str] = "low",
        verbosity: Optional[str] = "high",
        max_output_tokens: int = 12000,
        instructions: str = None,
    ) -> Optional[str]:
        """Make OpenAI API request using Responses API with reasoning and verbosity controls."""
        # Default instructions
        if instructions is None:
            instructions = "You are a helpful assistant designed to output JSON."

        logger.info(
            "Making Responses API request",
            extra={
                "method": "_make_openai_request_responses_api",
                "model": model,
                "prompt_length": len(prompt),
                "reasoning_effort": reasoning_effort,
                "verbosity": verbosity,
                "max_output_tokens": max_output_tokens,
            },
        )

        try:
            response_dict = self.client.create_response(
                model=model,
                input=prompt,
                instructions=instructions,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
                max_output_tokens=max_output_tokens,
            )
            return response_dict["content"]
        except Exception as e:
            logger.exception(f"An error occurred during the Responses API request: {e}")
            # Depending on desired behavior, you might want to return None or re-raise
            return None
