"""Pre-draft strategy builder for findings and demand letters."""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

from legal_portal.core.data_models import (
    ClaimPlanV1,
    DemandSpecV1,
    EvidenceAnchorV1,
    LetterStrategyV1,
)
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


class LetterStrategyService:
    """Build a structured strategy object that guides drafting."""

    _MAX_TIMELINE_ITEMS = 6
    _MAX_ANCHORS_PER_THEORY = 4
    _MAX_THEORIES = 4

    def __init__(self, client: Optional[OpenAIClient] = None) -> None:
        self.client = client
        self.prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")

    async def build_findings_strategy(
        self,
        *,
        fact_matrix,
        deep_analysis,
        gap_analysis=None,
        allow_model: bool = True,
        timeout_seconds: int = 15,
        model: str = "gpt-5-mini",
    ) -> Dict[str, Any]:
        """Build findings strategy object with model-first, deterministic fallback."""
        fallback = self._build_findings_strategy_fallback(
            fact_matrix=fact_matrix,
            deep_analysis=deep_analysis,
            gap_analysis=gap_analysis,
        )

        if not allow_model or not self.client:
            return fallback.model_dump(mode="json")

        try:
            context_json = json.dumps(
                self._build_context_payload(
                    fact_matrix=fact_matrix,
                    deep_analysis=deep_analysis,
                    gap_analysis=gap_analysis,
                ),
                default=str,
            )
            prompt = self._load_prompt("findings_strategy_prompt.txt").replace(
                "{context_json}",
                context_json,
            )
            parsed = await self._request_strategy_json(
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                model=model,
            )
            if not parsed:
                return fallback.model_dump(mode="json")

            strategy = LetterStrategyV1(**self._merge_dict(parsed, fallback.model_dump(mode="json")))
            return strategy.model_dump(mode="json")
        except Exception as exc:
            logger.warning("Findings strategy model step failed, falling back: %s", exc)
            return fallback.model_dump(mode="json")

    async def build_demand_strategy(
        self,
        *,
        fact_matrix,
        deep_analysis,
        target_party_name: str,
        demand_amount: Optional[float],
        demand_deadline: str,
        specific_demands: Optional[List[str]],
        client_name: str,
        gap_analysis=None,
        allow_model: bool = True,
        timeout_seconds: int = 15,
        model: str = "gpt-5-mini",
    ) -> Dict[str, Any]:
        """Build demand strategy object with model-first, deterministic fallback."""
        fallback = self._build_demand_strategy_fallback(
            fact_matrix=fact_matrix,
            deep_analysis=deep_analysis,
            gap_analysis=gap_analysis,
            target_party_name=target_party_name,
            demand_amount=demand_amount,
            demand_deadline=demand_deadline,
            specific_demands=specific_demands or [],
            client_name=client_name,
        )

        if not allow_model or not self.client:
            return fallback.model_dump(mode="json")

        try:
            prompt = self._load_prompt("demand_strategy_prompt.txt")
            replacements = {
                "target_party_name": target_party_name,
                "demand_deadline": demand_deadline,
                "demand_amount": f"{demand_amount:.2f}" if demand_amount is not None else "TBD",
                "context_json": json.dumps(
                    self._build_context_payload(
                        fact_matrix=fact_matrix,
                        deep_analysis=deep_analysis,
                        gap_analysis=gap_analysis,
                    ),
                    default=str,
                ),
            }
            for key, value in replacements.items():
                prompt = prompt.replace(f"{{{key}}}", value)

            parsed = await self._request_strategy_json(
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                model=model,
            )
            if not parsed:
                return fallback.model_dump(mode="json")

            strategy = LetterStrategyV1(**self._merge_dict(parsed, fallback.model_dump(mode="json")))
            if strategy.demand_spec is None:
                strategy.demand_spec = fallback.demand_spec
            return strategy.model_dump(mode="json")
        except Exception as exc:
            logger.warning("Demand strategy model step failed, falling back: %s", exc)
            return fallback.model_dump(mode="json")

    async def _request_strategy_json(
        self,
        *,
        prompt: str,
        timeout_seconds: int,
        model: str,
    ) -> Optional[Dict[str, Any]]:
        """Request JSON strategy from model and parse safely."""
        if not self.client:
            return None

        loop = asyncio.get_running_loop()

        def _run_request() -> Dict[str, Any]:
            return self.client.create_response(
                model=model,
                instructions=(
                    "You are a legal strategy planner. Return valid JSON only. "
                    "Do not include markdown, comments, or explanations."
                ),
                input=prompt,
                reasoning_effort="low",
                verbosity="low",
                max_output_tokens=1800,
            )

        response = await asyncio.wait_for(
            loop.run_in_executor(None, _run_request),
            timeout=max(1, int(timeout_seconds)),
        )
        content = str((response or {}).get("content") or "").strip()
        if not content:
            return None
        return self._parse_json_like(content)

    def _build_findings_strategy_fallback(
        self,
        *,
        fact_matrix,
        deep_analysis,
        gap_analysis=None,
    ) -> LetterStrategyV1:
        """Build deterministic findings strategy fallback."""
        claim_plans = self._build_claim_plans(fact_matrix=fact_matrix, deep_analysis=deep_analysis)
        timeline = self._build_timeline_highlights(fact_matrix)
        risk_flags = self._build_risk_flags(deep_analysis=deep_analysis, gap_analysis=gap_analysis)
        uncertainty_items = self._build_uncertainty_items(deep_analysis=deep_analysis, gap_analysis=gap_analysis)

        overall_strength = getattr(deep_analysis, "overall_case_strength", "moderate")
        case_summary = (
            "Primary objective is recovery or documented make-whole performance through the "
            "strongest contract-based path, with secondary leverage theories preserved."
        )
        if overall_strength == "weak":
            case_summary = (
                "Recovery path remains possible but depends on tightening documentation and "
                "targeting responsible parties before making demands."
            )

        return LetterStrategyV1(
            case_summary=case_summary,
            ranked_theories=claim_plans,
            timeline_highlights=timeline,
            risk_flags=risk_flags,
            uncertainty_items=uncertainty_items,
            recommended_sequence=[
                "Confirm payment proof and documentary anchors.",
                "Send targeted demand letter with specific response deadline.",
                "Use secondary fraud/securities theories as negotiation leverage where supported.",
                "Prepare filing strategy if no meaningful response.",
            ],
        )

    def _build_demand_strategy_fallback(
        self,
        *,
        fact_matrix,
        deep_analysis,
        gap_analysis,
        target_party_name: str,
        demand_amount: Optional[float],
        demand_deadline: str,
        specific_demands: List[str],
        client_name: str,
    ) -> LetterStrategyV1:
        """Build deterministic demand strategy fallback."""
        base = self._build_findings_strategy_fallback(
            fact_matrix=fact_matrix,
            deep_analysis=deep_analysis,
            gap_analysis=gap_analysis,
        )
        demand_spec = DemandSpecV1(
            targets=[target_party_name],
            amount_mode="fixed" if demand_amount is not None else "tbd",
            deadline=demand_deadline or "10 business days",
            accounting_request=(
                "Provide a written accounting of all funds received from the client and how those funds were used."
            ),
            cure_ladder=(
                specific_demands
                if specific_demands
                else [
                    "Provide written confirmation of obligation and repayment path.",
                    "Provide complete accounting and supporting records.",
                    "Cure defaults within the demand deadline or face litigation.",
                ]
            ),
            preservation_language=(
                f"Preserve all records and communications relating to {client_name}'s investment and fund flow."
            ),
        )
        base.case_summary = (
            "Demand should prioritize enforceable repayment/accounting obligations, name the responsible party, "
            "and set a clear cure deadline before litigation."
        )
        base.demand_spec = demand_spec
        return base

    def _build_context_payload(
        self,
        *,
        fact_matrix,
        deep_analysis,
        gap_analysis=None,
    ) -> Dict[str, Any]:
        """Create compact context for strategy generation."""
        parties = [
            {"name": p.name, "role": p.role}
            for p in getattr(fact_matrix, "parties", [])[:10]
        ]
        timeline = [
            {
                "date": str(getattr(e, "date", "")),
                "description": getattr(e, "description", ""),
                "source_document": getattr(e, "source_document", ""),
            }
            for e in getattr(fact_matrix, "timeline", [])[:12]
        ]
        financial = [
            {
                "amount": getattr(item, "amount", None),
                "description": getattr(item, "description", ""),
                "date": str(getattr(item, "date", "")),
                "source_document": getattr(item, "source_document", ""),
            }
            for item in getattr(fact_matrix, "financial_data", [])[:12]
        ]
        issues = [
            {
                "issue_name": getattr(issue, "issue_name", ""),
                "confidence_level": getattr(issue, "confidence_level", "moderate"),
                "supporting_evidence": getattr(issue, "supporting_evidence", [])[:6],
                "remedies_available": getattr(issue, "remedies_available", [])[:4],
            }
            for issue in getattr(deep_analysis, "issue_analyses", [])[:8]
        ]
        risk_assessment = getattr(deep_analysis, "risk_assessment", None)
        gap_meta = {}
        if gap_analysis is not None:
            gap_meta = {
                "completeness_score": getattr(gap_analysis, "overall_completeness_score", None),
                "critical_count": getattr(gap_analysis, "critical_count", 0),
                "high_count": getattr(gap_analysis, "high_count", 0),
            }
        return {
            "parties": parties,
            "timeline": timeline,
            "financial_data": financial,
            "issue_analyses": issues,
            "risk_assessment": {
                "major_risks": getattr(risk_assessment, "major_risks", []),
                "evidence_gaps": getattr(risk_assessment, "evidence_gaps", []),
            },
            "gap_analysis": gap_meta,
        }

    def _build_claim_plans(self, *, fact_matrix, deep_analysis) -> List[ClaimPlanV1]:
        """Build claim plans ranked by confidence."""
        confidence_rank = {"strong": 0, "moderate": 1, "weak": 2}
        issue_analyses = list(getattr(deep_analysis, "issue_analyses", []))
        issue_analyses.sort(
            key=lambda issue: confidence_rank.get(str(getattr(issue, "confidence_level", "moderate")).lower(), 3)
        )

        timeline = list(getattr(fact_matrix, "timeline", []))
        financial_data = list(getattr(fact_matrix, "financial_data", []))
        claim_plans: List[ClaimPlanV1] = []

        for idx, issue in enumerate(issue_analyses[: self._MAX_THEORIES], start=1):
            anchors = self._anchors_for_issue(
                issue_name=getattr(issue, "issue_name", ""),
                supporting_evidence=list(getattr(issue, "supporting_evidence", [])),
                timeline=timeline,
                financial_data=financial_data,
            )
            rationale = f"Prioritize {getattr(issue, 'issue_name', 'this theory')} based on available documentation."
            claim_plans.append(
                ClaimPlanV1(
                    theory=getattr(issue, "issue_name", f"Theory {idx}"),
                    priority=idx,
                    rationale=rationale,
                    supporting_anchors=anchors,
                )
            )

        if not claim_plans:
            claim_plans.append(
                ClaimPlanV1(
                    theory="Contract-based recovery",
                    priority=1,
                    rationale="Signed deal documents provide the cleanest enforcement path.",
                    supporting_anchors=self._fallback_anchors(timeline=timeline, financial_data=financial_data),
                )
            )

        return claim_plans

    def _anchors_for_issue(
        self,
        *,
        issue_name: str,
        supporting_evidence: List[str],
        timeline: List[Any],
        financial_data: List[Any],
    ) -> List[EvidenceAnchorV1]:
        """Build evidence anchors for a specific issue."""
        anchors: List[EvidenceAnchorV1] = []
        issue_name_lower = issue_name.lower()

        for entry in supporting_evidence[: self._MAX_ANCHORS_PER_THEORY]:
            source = self._extract_document_name(entry)
            amount = self._extract_amount(entry)
            anchors.append(
                EvidenceAnchorV1(
                    anchor_type="communication" if "email" in entry.lower() else "document",
                    summary=entry[:220],
                    source_document=source,
                    amount=amount,
                )
            )

        if len(anchors) < self._MAX_ANCHORS_PER_THEORY:
            for item in financial_data:
                desc = str(getattr(item, "description", ""))
                if issue_name_lower and issue_name_lower.split()[0] not in desc.lower() and anchors:
                    continue
                anchors.append(
                    EvidenceAnchorV1(
                        anchor_type="amount",
                        summary=desc or "Recorded payment entry",
                        source_document=getattr(item, "source_document", None),
                        source_date=str(getattr(item, "date", "")) or None,
                        amount=getattr(item, "amount", None),
                    )
                )
                if len(anchors) >= self._MAX_ANCHORS_PER_THEORY:
                    break

        if len(anchors) < self._MAX_ANCHORS_PER_THEORY:
            for event in timeline:
                anchors.append(
                    EvidenceAnchorV1(
                        anchor_type="date",
                        summary=str(getattr(event, "description", ""))[:220],
                        source_document=getattr(event, "source_document", None),
                        source_date=str(getattr(event, "date", "")) or None,
                    )
                )
                if len(anchors) >= self._MAX_ANCHORS_PER_THEORY:
                    break

        return anchors[: self._MAX_ANCHORS_PER_THEORY]

    def _fallback_anchors(self, *, timeline: List[Any], financial_data: List[Any]) -> List[EvidenceAnchorV1]:
        anchors: List[EvidenceAnchorV1] = []
        for item in financial_data[:2]:
            anchors.append(
                EvidenceAnchorV1(
                    anchor_type="amount",
                    summary=str(getattr(item, "description", ""))[:220] or "Recorded financial entry",
                    source_document=getattr(item, "source_document", None),
                    source_date=str(getattr(item, "date", "")) or None,
                    amount=getattr(item, "amount", None),
                )
            )
        for event in timeline[:2]:
            anchors.append(
                EvidenceAnchorV1(
                    anchor_type="date",
                    summary=str(getattr(event, "description", ""))[:220],
                    source_document=getattr(event, "source_document", None),
                    source_date=str(getattr(event, "date", "")) or None,
                )
            )
        return anchors

    def _build_timeline_highlights(self, fact_matrix) -> List[str]:
        """Build sorted timeline highlights."""
        events = list(getattr(fact_matrix, "timeline", []))
        normalized = []
        for event in events:
            date_str = str(getattr(event, "date", "") or "")
            desc = str(getattr(event, "description", "")).strip()
            source = str(getattr(event, "source_document", "")).strip()
            if not desc:
                continue
            normalized.append((date_str, f"{date_str or 'Undated'}: {desc} ({source or 'source not specified'})"))
        normalized.sort(key=lambda row: row[0] or "9999-99-99")
        return [row[1] for row in normalized[: self._MAX_TIMELINE_ITEMS]]

    def _build_risk_flags(self, *, deep_analysis, gap_analysis=None) -> List[str]:
        risks = list(getattr(getattr(deep_analysis, "risk_assessment", None), "major_risks", []) or [])
        if gap_analysis is not None:
            critical = int(getattr(gap_analysis, "critical_count", 0) or 0)
            high = int(getattr(gap_analysis, "high_count", 0) or 0)
            if critical or high:
                risks.append(
                    f"Gap analysis indicates {critical} critical and {high} high-severity documentation risks."
                )
        return risks[:8]

    def _build_uncertainty_items(self, *, deep_analysis, gap_analysis=None) -> List[str]:
        items = list(getattr(getattr(deep_analysis, "risk_assessment", None), "evidence_gaps", []) or [])
        if gap_analysis is not None:
            score = getattr(gap_analysis, "overall_completeness_score", None)
            if score is not None and float(score) < 70:
                items.append(
                    "Current documentation completeness is below optimal threshold; additional records may change prioritization."
                )
        return items[:8]

    def _load_prompt(self, filename: str) -> str:
        path = os.path.join(self.prompts_dir, filename)
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _parse_json_like(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON output that may be wrapped in code fences."""
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
            candidate = re.sub(r"\s*```$", "", candidate)
            candidate = candidate.strip()
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def _extract_document_name(self, text: str) -> Optional[str]:
        match = re.search(
            r"(subscription agreement|operating agreement|financing memo|investor packet|email update|ledger|wire confirmation)",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1) if match else None

    def _extract_amount(self, text: str) -> Optional[float]:
        match = re.search(r"\$([\d,]+(?:\.\d{2})?)", text)
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None

    def _merge_dict(self, primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
        """Merge sparse primary strategy payload onto deterministic fallback."""
        merged = dict(fallback)
        for key, value in primary.items():
            if value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_dict(value, merged[key])
            else:
                merged[key] = value
        return merged
