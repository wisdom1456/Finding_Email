from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from legal_portal.core.data_models import DocumentSummaryStructured, FactMatrix, ProcessedDocument


class DocumentRegistryService:
    """Build an authoritative document registry used across analysis and letters.

    The registry captures document classification, execution status, authority tier,
    and extracted structured anchors (parties, dates, amounts) in a consistent format.
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

    def build_registry(
        self,
        processed_documents: List[ProcessedDocument],
        document_summaries: List[DocumentSummaryStructured],
        fact_matrix: Optional[FactMatrix] = None,
    ) -> List[Dict[str, Any]]:
        """Build registry rows merged from processed docs, summaries, and fact matrix."""
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

            summary = summary_by_name.get(normalized_name, {})
            key_doc = key_docs_by_name.get(normalized_name, {})
            signature = pdoc.signature_detection or {}
            doc_blob = self._compose_instrument_corpus(
                file_name=file_name,
                summary=summary,
                content=(pdoc.content or "")[:24000],
            )
            instrument_hints = self._extract_instrument_hints(doc_blob)
            primary_instrument = instrument_hints[0] if instrument_hints else None

            doc_type = (
                str(summary.get("document_type") or "").strip()
                or self._infer_doc_type_from_name(file_name, instrument_hints)
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
                execution_status=str(signature.get("status") or "unknown"),
                role_in_case=role_in_case,
            )
            authority_score = self._score_authority(
                authority_level=authority_level,
                execution_status=str(signature.get("status") or "unknown"),
                summary=summary,
                key_doc=key_doc,
            )

            parties = self._collect_parties(summary)
            dates = self._collect_dates(summary)
            amounts = self._collect_amounts(summary)

            reliability_notes: List[str] = []
            extraction_quality = (pdoc.extraction_quality or "").lower()
            if extraction_quality in {"low", "medium"}:
                reliability_notes.append(f"Extraction quality is {extraction_quality}.")
            if str(signature.get("status") or "").lower() == "not_detected":
                reliability_notes.append("No signature markers detected in extracted text.")

            registry.append(
                {
                    "document_id": pdoc.document_id,
                    "document_name": file_name,
                    "normalized_name": normalized_name,
                    "file_type": getattr(getattr(pdoc, "file_type", None), "value", None)
                    or str(getattr(pdoc, "file_type", "") or ""),
                    "document_type": doc_type or "Other",
                    "role_in_case": role_in_case,
                    "authority_level": authority_level,
                    "authority_score": authority_score,
                    "authority_reason": authority_reason,
                    "is_key_document": bool(key_doc),
                    "key_document_significance": key_doc.get("significance"),
                    "instrument_hints": instrument_hints,
                    "primary_instrument": primary_instrument,
                    "execution_status": signature.get("status") or "unknown",
                    "execution_confidence": signature.get("confidence") or "none",
                    "execution_source": signature.get("detection_source") or "ingestion",
                    "signing_date": signature.get("signing_date"),
                    "signer_names": self._ensure_list(signature.get("signer_names")),
                    "parties_mentioned": parties,
                    "dates_mentioned": dates,
                    "amounts_mentioned": amounts,
                    "legal_significance": summary.get("legal_significance"),
                    "relevance_to_case": summary.get("relevance_to_case"),
                    "important_details": self._ensure_list(summary.get("important_details"))[:6],
                    "reliability_notes": reliability_notes,
                }
            )

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
            registry.append(
                {
                    "document_id": None,
                    "document_name": file_name,
                    "normalized_name": normalized_name,
                    "file_type": "",
                    "document_type": doc_type or "Other",
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
                    "signing_date": None,
                    "signer_names": [],
                    "parties_mentioned": self._collect_parties(summary),
                    "dates_mentioned": self._collect_dates(summary),
                    "amounts_mentioned": self._collect_amounts(summary),
                    "legal_significance": summary.get("legal_significance"),
                    "relevance_to_case": summary.get("relevance_to_case"),
                    "important_details": self._ensure_list(summary.get("important_details"))[:6],
                    "reliability_notes": [],
                }
            )

        registry.sort(
            key=lambda row: (
                -int(row.get("authority_score") or 0),
                str(row.get("document_name") or "").lower(),
            )
        )
        return registry

    @staticmethod
    def _normalize_name(value: str) -> str:
        text = (value or "").lower().strip()
        text = re.sub(r"\.[a-z0-9]{1,8}$", "", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

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
        blob = " ".join([file_name or "", " ".join(hints)]).lower()
        if any(term in blob for term in ("agreement", "note", "memo terms", "financing")):
            return "Contract"
        if any(term in blob for term in ("email", "correspondence", "update", "message", "clio note")):
            return "Correspondence"
        if any(term in blob for term in ("search", "articles", "official", "secretary of state")):
            return "Notice"
        if any(term in blob for term in ("p&l", "financial", "statement", "breakdown", "packet")):
            return "Evidence"
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
