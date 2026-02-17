"""Deterministic client-letter quality lint checks.

This module provides fast, machine-readable checks used by letter generation
routes to enforce readability, structure, and user-facing language constraints.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple


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
            "opening_review",
            "Opening - What We Reviewed",
            [
                re.compile(r"\bwhat we reviewed\b", re.IGNORECASE),
                re.compile(r"\bafter reviewing\b", re.IGNORECASE),
                re.compile(r"\bwe reviewed\b", re.IGNORECASE),
            ],
        ),
        (
            "core_issue",
            "Core Issue - The Real Question",
            [
                re.compile(r"\bcore issue\b", re.IGNORECASE),
                re.compile(r"\breal question\b", re.IGNORECASE),
                re.compile(r"\bprimary concern\b", re.IGNORECASE),
            ],
        ),
        (
            "facts",
            "What the Documents Show",
            [
                re.compile(r"\bwhat the documents show\b", re.IGNORECASE),
                re.compile(r"\bbased on (?:the )?records\b", re.IGNORECASE),
                re.compile(r"\b2022\b"),
            ],
        ),
        (
            "legal_theories",
            "Legal Theories",
            [
                re.compile(r"\bcontract\b", re.IGNORECASE),
                re.compile(r"\bfraud|misrepresentation\b", re.IGNORECASE),
                re.compile(r"\bsecurities\b", re.IGNORECASE),
            ],
        ),
        (
            "timing_risk",
            "Timing Risk",
            [
                re.compile(r"\btiming risk\b", re.IGNORECASE),
                re.compile(r"\bstatute of limitations\b", re.IGNORECASE),
                re.compile(r"\bdeadline\b", re.IGNORECASE),
            ],
        ),
        (
            "strategy",
            "Strategy - What We Recommend",
            [
                re.compile(r"\bwhat we recommend\b", re.IGNORECASE),
                re.compile(r"\bwe recommend\b", re.IGNORECASE),
                re.compile(r"\bdemand letter\b", re.IGNORECASE),
            ],
        ),
        (
            "action_items",
            "Immediate Client Action Items",
            [
                re.compile(r"\bimmediate (?:client )?action items\b", re.IGNORECASE),
                re.compile(r"\bplease (?:help us|send|provide)\b", re.IGNORECASE),
                re.compile(r"\bproof of payment\b", re.IGNORECASE),
            ],
        ),
    ]

    _BANNED_LANGUAGE: List[Tuple[str, str, str]] = [
        ("gap_analysis_flagged", r"\bgap analysis flagged\b", "Internal-lawyer language should not appear."),
        ("plain_english_redundancy", r"\bin plain english\b", "Avoid repetitive plain-language scaffolding."),
    ]

    _URGENCY_GUARD = re.compile(r"\b\d+\s+days?\s+from\s+today\b", re.IGNORECASE)
    _ACTION_BULLET_PATTERN = re.compile(r"^\s*(?:[-*•]\s+|\d+\.\s+)", re.MULTILINE)

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

        score = self._score(violations)
        lint_passed = self._passed(mode=mode, score=score, violations=violations)

        return {
            "mode": mode,
            "letter_type": letter_type,
            "lint_passed": lint_passed,
            "score": score,
            "violations": [asdict(item) for item in violations],
            "word_count": word_count,
            "section_counts": section_counts,
        }

    def _apply_strict_section_checks(
        self,
        section_counts: Dict[str, int],
        section_positions: Dict[str, int],
        violations: List[LintViolation],
    ) -> None:
        """Apply strict required-section and ordering checks."""
        missing = [name for name, count in section_counts.items() if name != "action_item_bullets" and count == 0]
        if missing:
            violations.append(
                LintViolation(
                    rule="required_sections_missing",
                    severity="error",
                    message="One or more required strategy-memo sections are missing.",
                    details={"missing_sections": missing},
                )
            )

        ordered_names = [section[0] for section in self._STRICT_SECTIONS]
        observed = [name for name in ordered_names if section_positions.get(name, -1) >= 0]
        position_values = [section_positions[name] for name in observed]
        if len(position_values) > 1 and position_values != sorted(position_values):
            violations.append(
                LintViolation(
                    rule="section_order",
                    severity="error",
                    message="Required sections are out of order.",
                    details={"observed_order": observed},
                )
            )

    def _apply_strict_actionability_checks(
        self,
        text_lower: str,
        action_bullet_count: int,
        violations: List[LintViolation],
    ) -> None:
        """Apply strict actionability checks."""
        if "demand letter" not in text_lower:
            violations.append(
                LintViolation(
                    rule="strategy_demand_letter_missing",
                    severity="warning",
                    message="Strategy section should explicitly recommend a demand letter first move.",
                    details={},
                )
            )

        if action_bullet_count < 4 or action_bullet_count > 5:
            violations.append(
                LintViolation(
                    rule="action_item_bullet_count",
                    severity="warning",
                    message="Immediate action items should include 4-5 concise bullets.",
                    details={"actual": action_bullet_count, "target": "4-5"},
                )
            )

    def _word_count_bounds(self, *, mode: str, letter_type: str) -> Tuple[int, int]:
        """Return word-count bounds for the current lint profile."""
        if letter_type == "findings" and mode == "strict_quality":
            return (650, 900)
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
            return re.sub(r"\s+", " ", content).strip()

        text = re.sub(r"</?(p|div|h\d|li|ul|ol|br)[^>]*>", "\n", content, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text)
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
