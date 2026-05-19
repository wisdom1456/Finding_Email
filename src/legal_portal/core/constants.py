"""Shared constants for the Legal Portal application.

This module is the single source of truth for values that are referenced
across multiple modules.  Domain-specific constants that are only used
inside a single service should stay in that service.
"""

from __future__ import annotations

from decimal import Decimal

# ============================================================================
# OpenAI Model Names
# ============================================================================

DEFAULT_MODEL: str = "gpt-5.5"
"""Primary model for analysis and letter generation. May 2026 flagship —
1M context, supports tools/structured outputs, $5/M input, $30/M output."""

FALLBACK_MODEL: str = "gpt-5.4-mini"
"""Workhorse for document analysis, chat, and cost-sensitive tasks.
400K context, $0.75/M input, $4.50/M output."""

VISION_MODEL: str = "gpt-5.5"
"""Model used for PDF OCR and image-based processing. gpt-5.5 has native
image input support per the May 2026 release."""

# ============================================================================
# Model Pricing (per 1 K tokens, USD)
# ============================================================================

MODEL_PRICING: dict[str, dict[str, float]] = {
    # Current flagships (May 2026)
    "gpt-5.5": {"input": 0.005, "output": 0.030},
    "gpt-5.4": {"input": 0.0025, "output": 0.015},
    "gpt-5.4-mini": {"input": 0.00075, "output": 0.0045},
    "gpt-5.4-nano": {"input": 0.00010, "output": 0.0008},
    # Older but still in MODEL_PRICING for cost reporting on legacy calls
    "gpt-5.2": {"input": 0.00175, "output": 0.014},
    "gpt-5.2-pro": {"input": 0.015, "output": 0.045},
    "gpt-5-mini": {"input": 0.00025, "output": 0.002},
    "gpt-5-nano": {"input": 0.00005, "output": 0.0004},
    "gpt-4.1": {"input": 0.002, "output": 0.008},
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
    "gpt-4.1-nano": {"input": 0.0001, "output": 0.0004},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4-32k": {"input": 0.06, "output": 0.12},
}

# ============================================================================
# Model Context Windows (usable tokens — 80 % of full context)
# ============================================================================

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-5.5": 840_000,        # 1 M context × 0.80
    "gpt-5.4": 840_000,        # 1 M context × 0.80
    "gpt-5.4-mini": 320_000,   # 400 K context × 0.80
    "gpt-5.4-nano": 320_000,   # 400 K context × 0.80
    "gpt-5.2": 840_000,        # 1 M context × 0.80
    "gpt-5-mini": 320_000,     # 400 K context × 0.80
    "gpt-4": 25_600,           # 32 K context × 0.80
}

# ============================================================================
# Service Pricing Rates (USD, Decimal)
#
# Canonical pricing table for CostCalculator and CostEstimator.
# ============================================================================

SERVICE_PRICING_RATES: dict[str, dict[str, Decimal]] = {
    # OpenAI Pricing
    "openai_gpt4o": {
        "input_tokens": Decimal("5.00") / Decimal("1000000"),  # $5.00 per 1M tokens
        "output_tokens": Decimal("15.00") / Decimal("1000000"),  # $15.00 per 1M tokens
    },
    "openai_gpt4o_mini": {
        "input_tokens": Decimal("0.15") / Decimal("1000000"),  # $0.15 per 1M tokens
        "output_tokens": Decimal("0.60") / Decimal("1000000"),  # $0.60 per 1M tokens
    },
    "openai_gpt5_2": {
        "input_tokens": Decimal("10.00") / Decimal("1000000"),  # $10.00 per 1M tokens
        "output_tokens": Decimal("30.00") / Decimal("1000000"),  # $30.00 per 1M tokens
    },
    "openai_whisper": {
        "per_minute": Decimal("0.006"),  # $0.006 per minute
    },
    # Google Cloud Pricing
    "vertex_ai_gemini_flash": {
        "input_tokens": Decimal("0.075") / Decimal("1000000"),  # $0.075 per 1M tokens
        "output_tokens": Decimal("0.30") / Decimal("1000000"),  # $0.30 per 1M tokens
    },
    "vertex_ai_video": {
        "per_minute": Decimal("0.10"),  # $0.10 per minute
    },
    "google_speech_to_text": {
        "per_minute": Decimal("0.024"),  # $0.024 per minute
    },
}

# ============================================================================
# Default Jurisdiction
# ============================================================================

DEFAULT_JURISDICTION: str = "Florida"
