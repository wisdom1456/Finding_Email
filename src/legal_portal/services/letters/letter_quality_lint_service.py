"""Deterministic client-letter quality lint checks.

This module provides fast, machine-readable checks used by letter generation
routes to enforce readability, structure, and user-facing language constraints.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

from legal_portal.config.default import get_settings
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


def _emit_qa_failure_log(
    *, letter_type: str, qa: Dict[str, Any], word_count: int
) -> None:
    """Log a structured WARN when any QA v2 check fails. Silent on pass."""
    failed: List[str] = []
    if qa.get("term_explainer_passed") is False:
        failed.append("term_explainer")
    if qa.get("demand_specificity_passed") is False:
        failed.append("demand_specificity")
    evidence = qa.get("evidence_linkage_score")
    if isinstance(evidence, (int, float)) and evidence < 0.5:
        failed.append(f"evidence_linkage<0.5({evidence:.2f})")
    flags = qa.get("unsupported_assertion_flags")
    if isinstance(flags, list) and flags:
        failed.append(f"unsupported_assertions×{len(flags)}")
    if not failed:
        return
    logger.warning(
        "letter_qa_failed",
        extra={
            "letter_type": letter_type,
            "failed_checks": failed,
            "word_count": word_count,
            "term_explainer_passed": qa.get("term_explainer_passed"),
            "evidence_linkage_score": qa.get("evidence_linkage_score"),
            "demand_specificity_passed": qa.get("demand_specificity_passed"),
            "section_depth_score": qa.get("section_depth_score"),
        },
    )


@dataclass
class LintViolation:
    """Single lint violation."""

    rule: str
    severity: str
    message: str
    details: Dict[str, Any]


class LetterQualityLintService:
    """Deterministic lint validator for generated client letters."""

    _STRICT_SECTIONS: List[Tuple[str, str, List[re.Pattern[str]]]] = [
        (
            "background_issue",
            "Background & Issue",
            [
                re.compile(r"\bBACKGROUND\s*(?:&|AND)\s*ISSUE\b", re.IGNORECASE),
                re.compile(r"\byou report\b", re.IGNORECASE),
                re.compile(r"\bafter reviewing\b", re.IGNORECASE),
                re.compile(r"\bbased on (?:the )?records\b", re.IGNORECASE),
            ],
        ),
        (
            "key_legal_issues",
            "Key Legal Issues",
            [
                re.compile(r"\bKEY\s*(?:PROVISIONS?|LEGAL\s*ISSUES?)\b", re.IGNORECASE),
                re.compile(r"\bcontract\b", re.IGNORECASE),
                re.compile(r"\bfraud|misrepresentation\b", re.IGNORECASE),
                re.compile(r"\bsecurities\b", re.IGNORECASE),
            ],
        ),
        (
            "analysis",
            "Analysis",
            [
                re.compile(r"\bANALYSIS\b", re.IGNORECASE),
                re.compile(r"\bstatute of limitations\b", re.IGNORECASE),
                re.compile(r"\bdefense\b", re.IGNORECASE),
                re.compile(r"\bevidence\b", re.IGNORECASE),
            ],
        ),
        (
            "next_steps",
            "Recommended Next Steps",
            [
                re.compile(r"\bRECOMMENDED\s*NEXT\s*STEPS?\b", re.IGNORECASE),
                re.compile(r"\bwe recommend\b", re.IGNORECASE),
                re.compile(r"\bscope of\s*(?:our\s*)?(?:engagement|representation)\b", re.IGNORECASE),
                re.compile(r"\bplease (?:help us|send|provide|let us know)\b", re.IGNORECASE),
            ],
        ),
    ]

    _BANNED_LANGUAGE: List[Tuple[str, str, str]] = [
        ("gap_analysis_flagged", r"\bgap analysis flagged\b", "Internal-lawyer language should not appear."),
        ("plain_english_redundancy", r"\bin plain english\b", "Avoid repetitive plain-language scaffolding."),
    ]
    _META_LANGUAGE_PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
        (
            "micro_explainer_label",
            re.compile(r"\bmicro-?explainer\b", re.IGNORECASE),
            "Do not expose internal prompt labels (for example, 'micro-explainer') in client letters.",
        ),
        (
            "snake_case_legal_token",
            re.compile(
                r"\b("
                r"unjust_enrichment|promissory_estoppel|breach_of_contract|"
                r"statute_of_limitations|veil_piercing|fraudulent_inducement|"
                r"securities_law"
                r")\b",
                re.IGNORECASE,
            ),
            "Do not expose internal snake_case legal tokens in client letters.",
        ),
    ]
    _EXPLICIT_SECTION_HEADER_PATTERN = re.compile(
        (
            r"(?im)^\s*("
            r"opening\s+review|"
            r"factual\s+summary|"
            r"core\s+issue|"
            r"legal\s+theories(?:\s*\([^)]+\))?|"
            r"legal\s+claims?\s+analysis|"
            r"timing(?:\s+and)?\s+risk|"
            r"strategy(?:\s*\([^)]+\))?|"
            r"action\s+items(?:\s*\([^)]+\))?|"
            r"case\s+assessment|"
            r"procedural\s+requirements"
            r")\s*$"
        )
    )
    _REQUIRED_SECTION_HEADERS = re.compile(
        r"(?im)^\s*("
        r"BACKGROUND\s*(?:&|AND)\s*ISSUE|"
        r"Background\s*(?:&|and)\s*Issue|"
        r"KEY\s*(?:PROVISIONS?|LEGAL\s*ISSUES?)|"
        r"Key\s*(?:Provisions?|Legal\s*Issues?)|"
        r"ANALYSIS|"
        r"Analysis|"
        r"RECOMMENDED\s*NEXT\s*STEPS?|"
        r"Recommended\s*Next\s*Steps?"
        r")\s*:?\s*$"
    )

    _URGENCY_GUARD = re.compile(r"\b\d+\s+days?\s+from\s+today\b", re.IGNORECASE)
    _ACTION_BULLET_PATTERN = re.compile(r"^\s*(?:[-*•]\s+|\d+\.\s+)", re.MULTILINE)
    _CLAIM_PARAGRAPH_PATTERN = re.compile(
        r"\b(contract|breach|fraud|misrepresentation|securities|promissory estoppel|"
        r"unjust enrichment|liability|veil|rescission)\b",
        re.IGNORECASE,
    )
    _ANCHOR_PATTERN = re.compile(
        r"(\$[\d,]+(?:\.\d{2})?|"
        r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}\b|"
        r"\b(?:subscription agreement|operating agreement|financing memo|investor packet|ledger|email|update|wire|bank)\b|"
        r"\b\d{4}\b)",
        re.IGNORECASE,
    )
    _UNSUPPORTED_ASSERTION_PATTERN = re.compile(
        r"\b(fraudulent|criminal|stole|theft|embezzl|ponzi|scam)\b",
        re.IGNORECASE,
    )
    _HEDGING_PATTERN = re.compile(
        r"\b(alleged|appears|may|might|based on|according to|subject to verification)\b",
        re.IGNORECASE,
    )
    _LEGAL_TERM_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
        ("breach_of_contract", re.compile(r"\bbreach of contract\b", re.IGNORECASE)),
        ("promissory_estoppel", re.compile(r"\bpromissory estoppel\b", re.IGNORECASE)),
        ("unjust_enrichment", re.compile(r"\bunjust enrichment\b", re.IGNORECASE)),
        ("misrepresentation", re.compile(r"\bmisrepresentation\b", re.IGNORECASE)),
        ("securities_law", re.compile(r"\bsecurities(?:\s+law)?\b", re.IGNORECASE)),
        ("statute_of_limitations", re.compile(r"\bstatute of limitations\b", re.IGNORECASE)),
        ("veil_piercing", re.compile(r"\b(?:piercing the corporate veil|veil piercing|alter ego)\b", re.IGNORECASE)),
        ("rescission", re.compile(r"\brescission\b", re.IGNORECASE)),
    ]
    _EXPLAINER_MARKERS = re.compile(
        r"(\bwhich means\b|\bmeaning\b|\bthis means\b|\bin plain terms\b|\bin other words\b|\(.*?\))",
        re.IGNORECASE,
    )
    _GENERIC_SNAKE_CASE_PATTERN = re.compile(r"\b[a-z]{3,}_[a-z0-9_]{3,}\b")
    _RAW_FILENAME_PATTERN = re.compile(
        r"(?<!@)\b[A-Za-z0-9][A-Za-z0-9._/-]{7,}\.(?:pdf|docx?|xlsx?|xls|csv|txt|eml)\b",
        re.IGNORECASE,
    )
    _MACHINE_DOC_TOKEN_PATTERN = re.compile(
        r"\b(?=[A-Za-z0-9_-]{16,}\b)(?=.*(?:agreement|subscription|operating|memo|packet|ledger|"
        r"update|cuchillo|grow|financing))[A-Za-z0-9_-]+\b",
        re.IGNORECASE,
    )
    _PARENTHETICAL_PATTERN = re.compile(r"\(([^)]{3,180})\)")
    _CITATION_LIKE_MARKER = re.compile(
        r"(\b(?:19|20)\d{2}\b|\$[\d,]+|\b(?:email|update|memo|packet|p&l|ledger|source|document|"
        r"subscription|operating agreement|financing|sos|stat\.)\b)",
        re.IGNORECASE,
    )

    def lint_letter(
        self,
        content: str,
        *,
        mode: str = "default",
        letter_type: str = "findings",
    ) -> Dict[str, Any]:
        """Lint a generated letter and return a machine-readable report."""
        text = self._strip_html(content)
        text_lower = text.lower()
        word_count = self._count_words(text)

        violations: List[LintViolation] = []
        section_counts, section_positions = self._scan_sections(text)
        action_bullet_count = self._count_action_bullets(content)
        section_counts["action_item_bullets"] = action_bullet_count

        bounds = self._word_count_bounds(mode=mode, letter_type=letter_type)
        if word_count < bounds[0] or word_count > bounds[1]:
            severity = "error" if mode == "strict_quality" and letter_type == "findings" else "warning"
            violations.append(
                LintViolation(
                    rule="word_count_bounds",
                    severity=severity,
                    message=f"Word count {word_count} is outside target range {bounds[0]}-{bounds[1]}.",
                    details={"min": bounds[0], "max": bounds[1], "actual": word_count},
                )
            )

        for rule, pattern, guidance in self._BANNED_LANGUAGE:
            if re.search(pattern, text, flags=re.IGNORECASE):
                severity = "error" if rule == "gap_analysis_flagged" else "warning"
                violations.append(
                    LintViolation(
                        rule=rule,
                        severity=severity,
                        message=guidance,
                        details={"pattern": pattern},
                    )
                )

        for rule, pattern, guidance in self._META_LANGUAGE_PATTERNS:
            if pattern.search(text):
                violations.append(
                    LintViolation(
                        rule=rule,
                        severity="error" if mode == "strict_quality" else "warning",
                        message=guidance,
                        details={},
                    )
                )

        generic_snake_case = self._find_non_email_snake_case_tokens(text)
        if generic_snake_case:
            violations.append(
                LintViolation(
                    rule="generic_snake_case_token",
                    severity="error" if mode == "strict_quality" else "warning",
                    message="Do not include snake_case tokens in client-facing prose.",
                    details={"tokens": generic_snake_case[:10]},
                )
            )

        raw_filenames = self._RAW_FILENAME_PATTERN.findall(text)
        machine_doc_tokens = self._MACHINE_DOC_TOKEN_PATTERN.findall(text)
        exposed_tokens = []
        seen_exposed = set()
        for token in raw_filenames + machine_doc_tokens:
            lowered = token.lower()
            if lowered in seen_exposed:
                continue
            seen_exposed.add(lowered)
            exposed_tokens.append(token)
        if exposed_tokens:
            violations.append(
                LintViolation(
                    rule="raw_filename_exposure",
                    severity="error" if mode == "strict_quality" else "warning",
                    message=(
                        "Use readable document labels in client-facing text. "
                        "Do not expose raw upload filenames or machine-style file keys."
                    ),
                    details={"tokens": exposed_tokens[:10]},
                )
            )

        header_hits = [match.group(1) for match in self._EXPLICIT_SECTION_HEADER_PATTERN.finditer(text)]
        if header_hits and letter_type == "findings":
            violations.append(
                LintViolation(
                    rule="explicit_section_headers",
                    severity="error" if mode == "strict_quality" else "warning",
                    message=(
                        "Non-standard section headers detected. Use only: "
                        "Background & Issue, Key Legal Issues, Analysis, Recommended Next Steps."
                    ),
                    details={"headers_found": header_hits},
                )
            )

        if letter_type == "findings" and mode == "strict_quality":
            required_headers = [match.group(1) for match in self._REQUIRED_SECTION_HEADERS.finditer(text)]
            required_labels = {"background", "provisions", "analysis", "next steps"}
            found_labels = set()
            for h in required_headers:
                h_lower = h.lower()
                if "background" in h_lower:
                    found_labels.add("background")
                elif "provision" in h_lower or "legal issue" in h_lower:
                    found_labels.add("provisions")
                elif "analysis" in h_lower:
                    found_labels.add("analysis")
                elif "next step" in h_lower:
                    found_labels.add("next steps")
            missing = required_labels - found_labels
            if missing:
                violations.append(
                    LintViolation(
                        rule="missing_required_section_headers",
                        severity="warning",
                        message=(
                            "Letter is missing one or more required section headers: "
                            f"{', '.join(sorted(missing))}."
                        ),
                        details={"missing_sections": sorted(missing), "found_headers": required_headers},
                    )
                )

        plain_english_hits = len(re.findall(r"\bwhat this means for you\b", text_lower))
        if plain_english_hits > 1:
            violations.append(
                LintViolation(
                    rule="plain_english_repetition",
                    severity="warning",
                    message="Reduce repeated 'What this means for you' phrasing.",
                    details={"occurrences": plain_english_hits},
                )
            )

        if self._URGENCY_GUARD.search(text):
            violations.append(
                LintViolation(
                    rule="hardcoded_today_math",
                    severity="error",
                    message="Avoid hard-coded today/date math in urgency language.",
                    details={},
                )
            )

        if mode == "strict_quality" and letter_type == "findings":
            self._apply_strict_section_checks(section_counts, section_positions, violations)
            self._apply_strict_actionability_checks(text_lower, action_bullet_count, violations)

        parenthetical_density = self._citation_parenthetical_density_check(text)
        if parenthetical_density["overloaded_paragraphs"]:
            violations.append(
                LintViolation(
                    rule="citation_parenthetical_overload",
                    severity="error" if mode == "strict_quality" else "warning",
                    message=(
                        "Too many citation-style parentheticals in one or more paragraphs. "
                        "Integrate support into prose and reduce stacking."
                    ),
                    details=parenthetical_density,
                )
            )

        settings = get_settings()
        term_result = self._term_micro_explainer_check(text)
        evidence_result = self._evidence_linkage_check(text)
        section_depth_result = self._section_depth_check(text=text, letter_type=letter_type)
        demand_specificity = self._demand_specificity_check(text) if letter_type == "demand" else None

        if (
            getattr(settings, "letter_term_micro_explainers_enabled", True)
            and letter_type == "findings"
            and not term_result["passed"]
        ):
            violations.append(
                LintViolation(
                    rule="term_micro_explainer_coverage",
                    severity="error" if mode == "strict_quality" else "warning",
                    message=(
                        "First-use legal term micro-explainer coverage is below target "
                        f"({term_result['coverage']:.2f} < 0.90)."
                    ),
                    details=term_result,
                )
            )

        if evidence_result["score"] < 0.85:
            severity = "error" if mode == "strict_quality" and letter_type in {"findings", "demand"} else "warning"
            violations.append(
                LintViolation(
                    rule="evidence_linkage_score",
                    severity=severity,
                    message=f"Evidence linkage score is below target ({evidence_result['score']:.2f} < 0.85).",
                    details=evidence_result,
                )
            )

        unsupported_flags = evidence_result.get("unsupported_assertion_flags", [])
        if unsupported_flags:
            violations.append(
                LintViolation(
                    rule="unsupported_assertions",
                    severity="error",
                    message="Letter contains hard assertions without sufficient evidence anchors.",
                    details={"flags": unsupported_flags},
                )
            )

        if letter_type == "findings" and section_depth_result["score"] < 0.60:
            violations.append(
                LintViolation(
                    rule="section_depth",
                    severity="error" if mode == "strict_quality" else "warning",
                    message="Section depth is thinner than target ranges for balanced client strategy output.",
                    details=section_depth_result,
                )
            )

        if letter_type == "demand" and demand_specificity and not demand_specificity["complete"]:
            violations.append(
                LintViolation(
                    rule="demand_specificity",
                    severity="error" if mode == "strict_quality" else "warning",
                    message="Demand letter is missing one or more required specificity components.",
                    details=demand_specificity,
                )
            )

        score = self._score(violations)
        lint_passed = self._passed(mode=mode, score=score, violations=violations)
        quality_report_v2 = {
            "term_explainer_passed": bool(term_result["passed"]),
            "evidence_linkage_score": float(evidence_result["score"]),
            "section_depth_score": float(section_depth_result["score"]),
            "unsupported_assertion_flags": list(evidence_result.get("unsupported_assertion_flags", [])),
            "demand_specificity_passed": bool(demand_specificity["complete"]) if demand_specificity else None,
            "term_micro_explainer_coverage": float(term_result["coverage"]),
            "citation_parenthetical_density": float(parenthetical_density["density_score"]),
        }

        # Structured WARN log when a QA check fails. Surfaces to Vercel /
        # Railway logs so operators can grep `letter_qa_failed` without
        # building a UI surface. Stays silent on clean letters to avoid
        # log spam.
        _emit_qa_failure_log(
            letter_type=letter_type,
            qa=quality_report_v2,
            word_count=word_count,
        )

        return {
            "mode": mode,
            "letter_type": letter_type,
            "lint_passed": lint_passed,
            "score": score,
            "violations": [asdict(item) for item in violations],
            "word_count": word_count,
            "section_counts": section_counts,
            "quality_report_v2": quality_report_v2,
            "term_explainer_passed": quality_report_v2["term_explainer_passed"],
            "evidence_linkage_score": quality_report_v2["evidence_linkage_score"],
            "section_depth_score": quality_report_v2["section_depth_score"],
            "unsupported_assertion_flags": quality_report_v2["unsupported_assertion_flags"],
        }

    def _apply_strict_section_checks(
        self,
        section_counts: Dict[str, int],
        section_positions: Dict[str, int],
        violations: List[LintViolation],
    ) -> None:
        """Apply strict section checks for structured professional format."""
        del section_positions
        theme_keys = ["background_issue", "key_legal_issues", "analysis", "next_steps"]
        matched = [name for name in theme_keys if section_counts.get(name, 0) > 0]
        if len(matched) < 3:
            violations.append(
                LintViolation(
                    rule="theme_signal_coverage",
                    severity="warning",
                    message=(
                        "Letter may be missing one or more required sections "
                        "(Background & Issue, Key Legal Issues, Analysis, Recommended Next Steps)."
                    ),
                    details={"matched_themes": matched, "required_minimum": 3},
                )
            )

    def _apply_strict_actionability_checks(
        self,
        text_lower: str,
        action_bullet_count: int,
        violations: List[LintViolation],
    ) -> None:
        """Apply strict actionability checks for structured professional correspondence."""
        if not re.search(
            r"\b(next steps?|please (?:help us|send|provide|share|forward|let us know)|we recommend|we suggest)\b",
            text_lower,
            re.IGNORECASE,
        ):
            violations.append(
                LintViolation(
                    rule="strategy_next_step_missing",
                    severity="warning",
                    message="Letter should include an explicit client-ready next-step recommendation.",
                    details={},
                )
            )

        if action_bullet_count > 5:
            violations.append(
                LintViolation(
                    rule="action_item_bullet_count",
                    severity="warning",
                    message="Too many action bullets can reduce readability; keep action lists concise.",
                    details={"actual": action_bullet_count, "target_max": 5},
                )
            )

    def _term_micro_explainer_check(self, text: str) -> Dict[str, Any]:
        """Check whether first-use legal terms include a brief explainer."""
        terms_used = 0
        explained = 0
        missing_terms: List[str] = []

        for term_name, pattern in self._LEGAL_TERM_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            terms_used += 1
            sentence = self._extract_sentence_around(text, match.start())
            if self._EXPLAINER_MARKERS.search(sentence):
                explained += 1
            else:
                missing_terms.append(term_name)

        coverage = 1.0 if terms_used == 0 else explained / terms_used
        return {
            "terms_used": terms_used,
            "terms_explained": explained,
            "coverage": round(coverage, 3),
            "missing_terms": missing_terms,
            "passed": coverage >= 0.90,
        }

    def _evidence_linkage_check(self, text: str) -> Dict[str, Any]:
        """Check that claim paragraphs are anchored to concrete facts."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        claim_paragraphs = [p for p in paragraphs if self._CLAIM_PARAGRAPH_PATTERN.search(p)]
        linked = [p for p in claim_paragraphs if self._ANCHOR_PATTERN.search(p)]
        score = 1.0 if not claim_paragraphs else len(linked) / len(claim_paragraphs)

        unsupported_flags: List[str] = []
        for para in claim_paragraphs:
            if self._UNSUPPORTED_ASSERTION_PATTERN.search(para) and not self._ANCHOR_PATTERN.search(para):
                if not self._HEDGING_PATTERN.search(para):
                    unsupported_flags.append(para[:180])

        return {
            "claim_paragraphs": len(claim_paragraphs),
            "linked_claim_paragraphs": len(linked),
            "score": round(score, 3),
            "unsupported_assertion_flags": unsupported_flags,
        }

    def _section_depth_check(self, *, text: str, letter_type: str) -> Dict[str, Any]:
        """Check section depth against target word ranges."""
        targets: Dict[str, Tuple[int, int]] = {}
        if letter_type == "findings":
            targets = {
                "background_issue": (100, 350),
                "key_legal_issues": (150, 500),
                "analysis": (80, 350),
                "next_steps": (50, 200),
            }
        elif letter_type == "demand":
            targets = {
                "background": (120, 260),
                "legal_analysis": (140, 320),
                "demand": (100, 240),
            }

        if not targets:
            return {"score": 1.0, "sections": {}}

        section_words: Dict[str, int] = {}
        section_scores: List[float] = []

        for section, bounds in targets.items():
            words = self._estimate_section_words(text=text, section=section, letter_type=letter_type)
            section_words[section] = words
            section_scores.append(self._range_score(words, bounds[0], bounds[1]))

        overall = sum(section_scores) / len(section_scores) if section_scores else 1.0
        return {"score": round(overall, 3), "sections": section_words, "targets": targets}

    def _demand_specificity_check(self, text: str) -> Dict[str, Any]:
        """Check required demand-specific specificity package fields."""
        checks = {
            "has_target": bool(re.search(r"\bdear\b", text, re.IGNORECASE)),
            "has_deadline": bool(
                re.search(
                    r"\b(?:\d+\s+(?:business\s+)?days?|by\s+[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})\b",
                    text,
                    re.IGNORECASE,
                )
            ),
            "has_amount_mode": bool(
                re.search(
                    r"\$[\d,]+(?:\.\d{2})?|\bamount to be finalized\b|\bfull compensation\b",
                    text,
                    re.IGNORECASE,
                )
            ),
            "has_cure_ladder": bool(
                re.search(
                    r"\b(if we do not|if you fail|failure to|will proceed|legal action|litigation)\b",
                    text,
                    re.IGNORECASE,
                )
            ),
            "has_accounting_request": bool(
                re.search(
                    r"\b(accounting|ledger|funds received|how (?:the )?funds were used)\b",
                    text,
                    re.IGNORECASE,
                )
            ),
        }
        missing = [name for name, passed in checks.items() if not passed]
        return {"checks": checks, "missing": missing, "complete": not missing}

    def _estimate_section_words(self, *, text: str, section: str, letter_type: str) -> int:
        """Estimate section word count by heading heuristics."""
        if letter_type == "findings":
            heading_map = {
                "background_issue": [
                    r"(?im)^(?:BACKGROUND\s*(?:&|AND)\s*ISSUE|Background\s*(?:&|and)\s*Issue)\s*:?\s*$",
                ],
                "key_legal_issues": [
                    r"(?im)^(?:KEY\s*(?:PROVISIONS?|LEGAL\s*ISSUES?)|Key\s*(?:Provisions?|Legal\s*Issues?))\s*:?\s*$",
                ],
                "analysis": [
                    r"(?im)^(?:ANALYSIS|Analysis)\s*:?\s*$",
                ],
                "next_steps": [
                    r"(?im)^(?:RECOMMENDED\s*NEXT\s*STEPS?|Recommended\s*Next\s*Steps?)\s*:?\s*$",
                ],
            }
            target_patterns = heading_map.get(section, [])
            all_heading_patterns = [pattern for patterns in heading_map.values() for pattern in patterns]

            start = None
            for pattern in target_patterns:
                match = re.search(pattern, text)
                if match:
                    start = match.end()
                    break
            if start is not None:
                next_positions: List[int] = []
                for pattern in all_heading_patterns:
                    for match in re.finditer(pattern, text):
                        if match.start() > start:
                            next_positions.append(match.start())
                            break
                end = min(next_positions) if next_positions else len(text)
                snippet = text[start:end]
                return self._count_words(snippet)

            section_patterns = {
                "background_issue": [
                    r"\byou report\b",
                    r"\bafter reviewing\b",
                    r"\bbased on (?:the )?records\b",
                    r"\byou invested\b",
                ],
                "key_legal_issues": [
                    r"\bkey (?:provisions|legal issues)\b",
                    r"\bcontract claim\b",
                    r"\bunjust enrichment\b",
                    r"\bbreach of contract\b",
                ],
                "analysis": [
                    r"\bapplying (?:these|the) provisions\b",
                    r"\bthe evidence\b",
                    r"\bdefense\b",
                ],
                "next_steps": [
                    r"\bbased on the above\b",
                    r"\bwe recommend\b",
                    r"\bnext steps\b",
                    r"\bscope of (?:our )?(?:engagement|representation)\b",
                ],
            }
        else:
            section_patterns = {
                "background": [r"\bbackground\b", r"\bon or about\b", r"\bfactual summary\b"],
                "legal_analysis": [r"\blegal analysis\b", r"\blikely claims\b", r"\bpursuant to\b"],
                "demand": [r"\bas such, let this correspondence serve as a formal demand\b", r"\brecommended next steps\b", r"\bwe demand\b"],
            }

        paragraph_windows = {
            "background_issue": 4,
            "key_legal_issues": 5,
            "analysis": 4,
            "next_steps": 3,
            "background": 3,
            "legal_analysis": 3,
            "demand": 2,
        }
        window_size = paragraph_windows.get(section, 2)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        patterns = section_patterns.get(section, [])
        for idx, paragraph in enumerate(paragraphs):
            if any(re.search(pattern, paragraph, re.IGNORECASE) for pattern in patterns):
                snippet = " ".join(paragraphs[idx: idx + window_size])
                return self._count_words(snippet)

        patterns = section_patterns.get(section, [])
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            start = match.end()
            next_header = re.search(r"\n\s*(?:\d+\.\s+|[A-Z][A-Za-z ]{2,}:\s*$|##\s+)", text[start:], re.MULTILINE)
            end = start + next_header.start() if next_header else len(text)
            snippet = text[start:end]
            return self._count_words(snippet)
        return 0

    def _range_score(self, actual: int, min_words: int, max_words: int) -> float:
        """Return score 0-1 for how close a section is to target range."""
        if min_words <= actual <= max_words:
            return 1.0
        if actual < min_words:
            gap = min_words - actual
            return max(0.0, 1.0 - (gap / max(min_words, 1)))
        gap = actual - max_words
        return max(0.0, 1.0 - (gap / max(max_words, 1)))

    def _extract_sentence_around(self, text: str, index: int) -> str:
        """Extract sentence near index for explainer detection."""
        left = text.rfind(".", 0, index)
        left = 0 if left < 0 else left + 1
        right = text.find(".", index)
        right = len(text) if right < 0 else right + 1
        sentence = text[left:right].strip()
        return sentence if sentence else text[max(0, index - 120): index + 120]

    def _find_non_email_snake_case_tokens(self, text: str) -> List[str]:
        """Find snake_case tokens, excluding probable email addresses."""
        scrubbed = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", " ", text)
        tokens = self._GENERIC_SNAKE_CASE_PATTERN.findall(scrubbed)
        unique = []
        seen = set()
        for token in tokens:
            lowered = token.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(token)
        return unique

    def _citation_parenthetical_density_check(self, text: str) -> Dict[str, Any]:
        """Detect paragraphs overloaded with citation-style parentheticals."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        overloaded: List[Dict[str, Any]] = []
        total_citation_like = 0
        total_parentheticals = 0

        for idx, paragraph in enumerate(paragraphs, start=1):
            groups = self._PARENTHETICAL_PATTERN.findall(paragraph)
            if not groups:
                continue
            total_parentheticals += len(groups)
            citation_like = [g for g in groups if self._CITATION_LIKE_MARKER.search(g)]
            total_citation_like += len(citation_like)

            if len(citation_like) > 2:
                overloaded.append(
                    {
                        "paragraph_index": idx,
                        "citation_parentheticals": len(citation_like),
                        "paragraph_preview": paragraph[:180],
                    }
                )

        density_score = 1.0
        if total_parentheticals:
            density_score = max(0.0, 1.0 - min(1.0, total_citation_like / max(8, total_parentheticals)))

        return {
            "overloaded_paragraphs": overloaded,
            "total_parentheticals": total_parentheticals,
            "total_citation_like_parentheticals": total_citation_like,
            "density_score": round(density_score, 3),
        }

    def _word_count_bounds(self, *, mode: str, letter_type: str) -> Tuple[int, int]:
        """Return word-count bounds for the current lint profile."""
        if letter_type == "findings" and mode == "strict_quality":
            return (700, 1600)
        if letter_type == "findings":
            return (600, 1800)
        if letter_type == "recommendation":
            return (300, 900)
        return (450, 1300)

    def _scan_sections(self, text: str) -> Tuple[Dict[str, int], Dict[str, int]]:
        """Detect section presence and first-match position."""
        counts: Dict[str, int] = {}
        positions: Dict[str, int] = {}

        for key, _label, patterns in self._STRICT_SECTIONS:
            matches: List[re.Match[str]] = []
            for pattern in patterns:
                found = list(pattern.finditer(text))
                matches.extend(found)
            counts[key] = len(matches)
            positions[key] = min((match.start() for match in matches), default=-1)

        return counts, positions

    def _count_action_bullets(self, content: str) -> int:
        """Count action-item bullets using markdown/HTML-friendly heuristics."""
        li_count = len(re.findall(r"<li\b", content, flags=re.IGNORECASE))
        if li_count > 0:
            return li_count
        return len(self._ACTION_BULLET_PATTERN.findall(content))

    def _count_words(self, text: str) -> int:
        """Count words in normalized text."""
        return len(re.findall(r"\b[\w'-]+\b", text))

    def _strip_html(self, content: str) -> str:
        """Strip HTML tags while preserving rough line structure."""
        if "<" not in content and ">" not in content:
            text = content.replace("\r\n", "\n").replace("\r", "\n")
            text = re.sub(r"[ \t\f\v]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()

        text = re.sub(r"</?(p|div|h\d|li|ul|ol|br)[^>]*>", "\n", content, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"[ \t\f\v]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _score(self, violations: List[LintViolation]) -> int:
        """Compute lint score from violation severity."""
        severity_weight = {"error": 20, "warning": 8, "info": 3}
        penalty = sum(severity_weight.get(item.severity, 5) for item in violations)
        return max(0, 100 - penalty)

    def _passed(self, *, mode: str, score: int, violations: List[LintViolation]) -> bool:
        """Decide pass/fail using mode-aware thresholds."""
        if any(item.severity == "error" for item in violations):
            return False
        threshold = 85 if mode == "strict_quality" else 80
        return score >= threshold
